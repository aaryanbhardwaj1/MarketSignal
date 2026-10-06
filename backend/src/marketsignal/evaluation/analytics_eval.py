"""Structured-analytics evaluation (Phase 5; analytics-v0; deterministic metrics, no LLM judge).

Drives the real in-process API exactly like the grounded harness (conversation -> run -> SSE ->
``GET /runs/{id}``), then reads the run's persisted ``analytics_results`` (scoped session, by
``query_run_id``), resolves every ``[[result:<id>]]`` through ``GET /results/{id}`` and every
``[[HANDLE]]`` through ``GET /evidence/{handle}``. Scoring (:func:`score`) is pure over that
record so it is unit-testable; metric definitions live in :mod:`analytics_metrics`.

Per item (``checks``):
* routing - ``route_task_type`` vs ``task_type``; analytics/search call counts;
* analytics correctness (gold analytics, ``expect`` answer/no_result) - per gold value match
  (exact-result accuracy), denominator/unit/rounding of the matched cell, spec components of
  the best result per gold entry;
* answer - gold values stated / approximately stated / provenance (LLM answers; evidence-only
  fallbacks under ``fallback_*``), result-unit re-check (faithfulness, unsupported claims);
* mixed - quantitative correct, gold evidence in pack / cited, both components in the answer;
* security - foreign evidence/result citations or persisted results, Southpeak markers, canary
  (ledger surface forms), safe rejection of invalid/insufficient items, tool error codes;
* gates - every cited evidence handle and result resolves; evidence in pack; results belong to
  the run; every run ``done``; every item has a ``final``.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from marketsignal.evaluation import analytics_metrics as am
from marketsignal.evaluation.corpus import REPO_ROOT
from marketsignal.evaluation.grounded import SOUTHPEAK_MARKERS, ItemOutcome, run_item
from marketsignal.evaluation.grounded_stats import Prices, run_metrics
from marketsignal.generation import contract
from marketsignal.generation.types import CANONICAL_RE

LEDGER = REPO_ROOT / "seed_data" / "fact_ledger.json"


@dataclass
class AnalyticsOutcome(ItemOutcome):
    """A grounded :class:`ItemOutcome` plus the analytics side of the run."""

    results: list[dict[str, Any]] = field(default_factory=list)  # persisted, by query_run_id
    lookups: dict[str, dict[str, Any]] = field(default_factory=dict)  # cited result id -> GET
    texts: dict[str, str] = field(default_factory=dict)  # resolvable cited handle -> text
    evidence_status: dict[str, int] = field(default_factory=dict)  # cited handle -> status

    def as_dict(self) -> dict[str, Any]:
        return {
            **super().as_dict(),
            "task_type": self.item.get("task_type"),
            "results": [_brief(r) for r in self.results],
        }


def _brief(result: Mapping[str, Any]) -> dict[str, Any]:
    keep = ("result_id", "dataset", "operation", "spec", "rows_matched", "warnings", "workspace")
    return {k: result.get(k) for k in keep}


# ------------------------------------------------------------------------------------------
# Collection (DB + HTTP)
# ------------------------------------------------------------------------------------------


async def run_results(app: Any, ws: str, run_id: str) -> list[dict[str, Any]]:
    """The run's persisted results (creation order), read in the workspace scope (RLS)."""
    from sqlalchemy import text

    from marketsignal.db.scope import WorkspaceScope
    from marketsignal.db.session import scoped_session, unscoped_session

    factory = app.state.session_factory
    async with unscoped_session(factory) as session:
        row = (
            await session.execute(
                text("SELECT id, code FROM workspaces WHERE code = :c"), {"c": ws}
            )
        ).one_or_none()
    if row is None:
        return []
    async with scoped_session(factory, WorkspaceScope(row[0], row[1])) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT result FROM analytics_results WHERE workspace_id = :ws "
                    "AND query_run_id = :run ORDER BY created_at, id"
                ),
                {"ws": row[0], "run": uuid.UUID(run_id)},
            )
        ).all()
    return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows]


async def collect(app: Any, client: AsyncClient, out: ItemOutcome) -> AnalyticsOutcome:
    ws = out.item["workspace"]
    record = AnalyticsOutcome(out.item, out.events, out.final, out.done, out.run, mode=out.mode)
    run_id = str(out.run.get("run_id") or "")
    record.results = await run_results(app, ws, run_id) if run_id else []
    content = (out.final or {}).get("content") or ""
    for rid in dict.fromkeys(r.lower() for r in am.RESULT_RE.findall(content)):
        response = await client.get(f"/api/workspaces/{ws}/results/{rid}")
        body = response.json() if response.status_code == 200 else {}
        record.lookups[rid] = {
            "status": response.status_code,
            "query_run_id": body.get("query_run_id"),
            "result": body.get("result"),
        }
    for handle in dict.fromkeys(CANONICAL_RE.findall(content)):
        response = await client.get(f"/api/workspaces/{ws}/evidence/{handle}")
        record.evidence_status[handle] = response.status_code
        if response.status_code == 200:
            record.texts[handle] = str(response.json().get("text", ""))
    return record


# ------------------------------------------------------------------------------------------
# Scoring (pure)
# ------------------------------------------------------------------------------------------


def _answer_text(content: str) -> str:
    return contract.parse_sections(content).get(contract.ANSWER, "")


def _results_by_id(o: AnalyticsOutcome) -> dict[str, dict[str, Any]]:
    out = {str(r.get("result_id")).lower(): r for r in o.results}
    for rid, look in o.lookups.items():
        if look.get("result") and rid not in out:
            out[rid] = look["result"]
    return out


def _routing(o: AnalyticsOutcome) -> dict[str, Any]:
    route = o.run.get("route") or {}
    return {
        "route_task_type": route.get("task_type"),
        "task_type_correct": route.get("task_type") == o.item.get("task_type"),
        "analytics_calls": len(am.calls(o.run, am.ANALYTICS_TOOLS)),
        "compute_calls": len(am.calls(o.run, am.COMPUTE_TOOLS)),
        "search_calls": am.retrieval_calls(o.run),
        "analytics_durations_ms": [
            float(t["duration_ms"])
            for t in am.calls(o.run, am.ANALYTICS_TOOLS)
            if t.get("duration_ms") is not None and t.get("status") != "denied"
        ],
        "tool_error_codes": sorted(
            str(t.get("error_code"))
            for t in am.calls(o.run, am.ANALYTICS_TOOLS)
            if t.get("error_code")
        ),
    }


def _correctness(o: AnalyticsOutcome) -> dict[str, Any]:
    entries = o.item["gold"].get("analytics") or []
    all_cells = [c for r in o.results for c in am.cells(r)]
    matches = [am.match_gold(g, all_cells) for e in entries for g in am.gold_values(e)]
    specs = [am.best_spec_match(e, o.results) for e in entries]

    def frac(flags: Sequence[bool | None]) -> float | None:
        known = [f for f in flags if f is not None]
        return sum(known) / len(known) if known else None

    return {
        "gold_values": len(matches),
        "values_matched": sum(m.matched for m in matches),
        "exact_result_accuracy": frac([m.matched for m in matches]),
        "all_values_matched": bool(matches) and all(m.matched for m in matches),
        "denominator_correct": frac([m.component("denominator") for m in matches]),
        "unit_correct": frac([m.component("unit") for m in matches]),
        "result_rounding_correct": frac([m.component("rounding") for m in matches]),
        "aggregation_correct": frac([s["aggregation"] for s in specs]),
        "grouping_correct": frac([s["grouping"] for s in specs]),
        "filter_correct": frac([s["filter"] for s in specs]),
        "dataset_used": frac([s["dataset"] for s in specs]),
        "unmatched": [
            {"group": m.gold.get("group"), "metric": m.gold.get("metric"), "gold": m.gold["value"]}
            for m in matches
            if not m.matched
        ][:10],
    }


def _stated_values(o: AnalyticsOutcome, content: str) -> dict[str, Any]:
    entries = o.item["gold"].get("analytics") or []
    golds = [g for e in entries for g in am.gold_values(e) if g.get("value") is not None]
    units = am.answer_units(content)
    by_id = _results_by_id(o)
    found = am.mentions(content)
    stated = approximate = provenanced = 0
    for g in golds:
        kind = am.best_statement(g, found)
        approximate += kind is not None
        if kind != "stated":
            continue
        stated += 1
        provenanced += any(
            am.best_statement(g, am.mentions(u)) == "stated"
            and any(
                am.match_gold(g, am.cells(by_id[r.lower()])).matched
                for r in am.RESULT_RE.findall(u)
                if r.lower() in by_id
            )
            for u in units
        )
    return {
        "values_stated_rate": stated / len(golds) if golds else None,
        "allowed_rounding_rate": stated / approximate if approximate else None,
        "provenance_coverage": provenanced / stated if stated else None,
        "stated_counts": {"gold": len(golds), "stated": stated, "approx": approximate},
    }


def _mixed(o: AnalyticsOutcome, content: str, quant_ok: bool) -> dict[str, Any]:
    evidence = o.item["gold"].get("evidence") or []
    pack = set(o.run.get("pack_handles") or [])
    cited = set(CANONICAL_RE.findall(content))
    any_value_stated = bool((o.checks.get("stated_counts") or {}).get("stated"))
    return {
        "mixed_quant_correct": quant_ok,
        "mixed_evidence_retrieved": all(set(e["handles"]) & pack for e in evidence),
        "mixed_evidence_cited": all(set(e["handles"]) & cited for e in evidence),
        "mixed_both_in_answer": any_value_stated
        and any(set(e["handles"]) & cited for e in evidence),
    }


def _canary_leak(item: Mapping[str, Any], content: str, ledger: Mapping[str, Any]) -> bool:
    fact = ledger.get(item.get("canary_must_not_appear") or "")
    if not fact:
        return False
    forms = [str(f) for f in fact.get("surface_forms") or [] if am.dec(f) is None]
    if any(f.casefold() in content.casefold() for f in forms):
        return True
    value = am.dec(fact.get("value"))
    found = am.mentions(_answer_text(content))
    return value is not None and any(am.same_number(m.mantissa_text, value) for m in found)


def _security(o: AnalyticsOutcome, content: str, ledger: Mapping[str, Any]) -> dict[str, Any]:
    ws = o.item["workspace"]
    cited = list(dict.fromkeys(CANONICAL_RE.findall(content)))
    trace_handles = [h for t in am.trace_of(o.run) for h in t.get("handles") or []]
    foreign_results = [
        str(r.get("result_id"))
        for r in [*o.results, *(x["result"] for x in o.lookups.values() if x.get("result"))]
        if r.get("workspace") not in (None, ws)
    ]
    answer = _answer_text(content)
    fabricated = bool(am.RESULT_RE.search(answer)) or (
        bool(am.mentions(answer)) and not contract.states_insufficient(answer)
    )
    return {
        "foreign_citations": [h for h in cited if not h.startswith(f"{ws}/")],
        "foreign_trace_handles": [h for h in trace_handles if not h.startswith(f"{ws}/")],
        "foreign_results": sorted(set(foreign_results)),
        # A marker the question itself names is an echo, not a leak (the canary check below
        # catches leaked Southpeak values).
        "southpeak_marker_leak": ws != "SOUTHPEAK"
        and any(m in content and m not in o.item["question"] for m in SOUTHPEAK_MARKERS),
        "canary_leak": _canary_leak(o.item, content, ledger),
        "safe_rejection": o.final is not None and not fabricated,
    }


def _gates(o: AnalyticsOutcome) -> dict[str, Any]:
    run_id = str(o.run.get("run_id") or "")
    own = {str(r.get("result_id")).lower() for r in o.results}
    pack = set(o.run.get("pack_handles") or [])
    return {
        "evidence_citations": len(o.evidence_status),
        "evidence_resolvable": sum(1 for s in o.evidence_status.values() if s == 200),
        "evidence_in_pack": sum(1 for h in o.evidence_status if h in pack),
        "result_citations": len(o.lookups),
        "results_resolvable": sum(1 for x in o.lookups.values() if x["status"] == 200),
        "results_in_run": sum(
            1
            for rid, x in o.lookups.items()
            if x["status"] == 200 and (x.get("query_run_id") == run_id or rid in own)
        ),
        "has_final": o.final is not None,
        "has_done": bool(o.done),
    }


def score(o: AnalyticsOutcome, ledger: Mapping[str, Any] | None = None) -> None:
    """Fill ``o.checks`` (pure: reads only the collected record)."""
    item, checks = o.item, o.checks
    content = (o.final or {}).get("content") or ""
    sections = (o.final or {}).get("sections") or {}
    evidence_only = bool(sections.get("evidence_only"))
    abstained = bool(sections.get("abstained"))
    cited_any = bool(CANONICAL_RE.search(content) or am.RESULT_RE.search(content))
    checks["evidence_only"] = evidence_only
    checks["answered"] = cited_any and not evidence_only and not abstained
    checks.update(_routing(o))
    checks.update(_gates(o))
    if item["gold"].get("analytics") and item["expect"] in ("answer", "no_result"):
        checks.update(_correctness(o))
        stated = _stated_values(o, content)
        checks["stated_counts"] = stated.pop("stated_counts")
        prefix = "" if checks["answered"] else "fallback_"
        checks.update({f"{prefix}{k}": v for k, v in stated.items()})
    recheck = am.recheck_result_units(content, _results_by_id(o), o.texts)
    checks["result_units"] = recheck.result_units
    checks["unsupported_result_units"] = recheck.unsupported_units
    checks["result_numbers"] = recheck.numbers
    checks["supported_result_numbers"] = recheck.supported_numbers
    checks["unsupported_examples"] = recheck.unsupported[:3]
    if item["task_type"] == "mixed":
        checks.update(_mixed(o, content, bool(checks.get("all_values_matched"))))
    checks.update(_security(o, content, ledger or {}))
    if item["expect"] in ("insufficient", "invalid"):
        checks["pass_behaviour"] = checks["safe_rejection"]
    elif item["expect"] == "no_result":
        empty = any("EMPTY_SELECTION" in (r.get("warnings") or []) for r in o.results)
        checks["pass_behaviour"] = o.final is not None and (
            empty or contract.states_insufficient(_answer_text(content))
        )
    else:
        checks["pass_behaviour"] = checks["answered"]
    timings = o.run.get("timings") or {}
    checks["total_ms"] = timings.get("total_ms")
    checks["first_token_ms"] = timings.get("first_token_ms")


def load_ledger(path: Path = LEDGER) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    facts = data.get("facts", data) if isinstance(data, dict) else data
    return {f["fact_id"]: f for f in facts if isinstance(f, dict) and "fact_id" in f}


# ------------------------------------------------------------------------------------------
# Driver
# ------------------------------------------------------------------------------------------


async def evaluate(
    app: Any,
    items: list[dict[str, Any]],
    *,
    mode: str = "auto",
    concurrency: int = 1,
    prices: Prices | None = None,
) -> dict[str, Any]:
    """Run every item once in ``mode`` and summarize (see :mod:`analytics_summary`)."""
    from httpx import ASGITransport

    from marketsignal.evaluation.analytics_summary import summarize

    prices = prices or Prices(0.0, 0.0, 0.0, 0.0)
    ledger = load_ledger()
    started = time.monotonic()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app), base_url="http://eval", timeout=240
        ) as client,
    ):
        semaphore = asyncio.Semaphore(concurrency)

        async def one(item: dict[str, Any]) -> AnalyticsOutcome:
            async with semaphore:
                record = await collect(app, client, await run_item(client, item, mode))
                score(record, ledger)
                record.metrics = run_metrics(record, prices)
                return record

        outcomes = list(await asyncio.gather(*(one(i) for i in items)))
    return {
        "elapsed_s": round(time.monotonic() - started, 1),
        "summary": summarize(outcomes),
        "items": [o.as_dict() for o in outcomes],
    }
