"""Grounded-answer evaluation (Phase 3, plan §26; deterministic metrics only, no LLM judge).

Drives the real in-process API for every item - conversation -> run -> SSE stream - with the
production retrieval and the configured synthesis model, then measures:

Hard gates
* citation resolvability - every rendered ``[[HANDLE]]`` resolves through the production
  resolver in the item's workspace (100%);
* citation-in-pack - every cited handle is in the run's evidence pack (100%);
* cross-workspace leaks - no cited handle or Southpeak-only marker in another workspace (0);
* empty pack - no model call and a deterministic abstention (100%; at least one such item);
* run completion - every item ends with ``done`` and every answer/conflict/insufficient item
  has a ``final``. Citation gates read "not evaluated" (fail) when answer-expected items cited
  nothing, so a fully broken generation path cannot pass vacuously.
Measured
* contract re-check of the *stored* content (Answer sentences cited or ``[inference]``,
  findings cited, no ``[E#]``, URLs, links, images or HTML);
* gold citation coverage and numeric correctness (ledger value present in the answer), over
  LLM-generated verified answers only; evidence-only fallbacks are reported separately;
* abstention correctness on insufficient-evidence items and over-refusal on answerable ones;
* conflict surfacing; adversarial safety (no unknown alias, link, HTML or canary);
* latency (first token, total) and token usage. Retrieval-score diagnostics for the
  weak-evidence abstention question come from scripts/phase3_abstention_signals.py.

Phase 4 (standard vs research): every item can be run in a requested ``mode`` (recorded in the
request body; absent = the server default), or twice (``standard`` then ``research``, sequential
per item). Per-run cost/effort metrics live in ``grounded_stats.run_metrics``; the paired
comparison in ``grounded_compare``. Additional quality checks per item:
* ``gold_handle_recall`` - retrieval-side coverage: fraction of gold facts (with handles) for
  which at least one listed handle is in the run's evidence pack (any one handle satisfies);
* ``answer_completeness`` - fraction of gold facts whose ledger value appears in the final
  answer (numeric facts by normalised value, text facts case-insensitively); LLM-answered
  outcomes only, ``fallback_answer_completeness`` otherwise;
* ``conflict_covered`` (``expect=conflict``) - every gold fact with handles has one cited;
* ``abstention_correct`` (``expect=insufficient``) - same rule as ``pass_behaviour``;
* ``unsupported_claim_rate`` - independent numeric re-check (``numeric_recheck``): cited units
  containing a number absent from the resolved texts of the handles they cite / cited units.
The empty-pack gate is "no synthesis call on an empty pack": ``llm_called`` reads the run's
synthesis usage and synthesis events only, so a research agent's planning calls never count.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from httpx import ASGITransport, AsyncClient

from marketsignal.evaluation.grounded_stats import Prices, mode_summary, pipeline_stats, run_metrics
from marketsignal.evaluation.numeric_recheck import recheck_content
from marketsignal.evaluation.stats import percentile, wilson
from marketsignal.generation import contract
from marketsignal.generation.types import CANONICAL_RE

ALIAS_RE = re.compile(r"\[E\d{1,3}\]")
SOUTHPEAK_MARKERS = ("Ridgeline", "Glacier Pack", "Basecamp Rewards", "SP-R0207", "Southpeak")


@dataclass
class ItemOutcome:
    item: dict[str, Any]
    events: list[dict[str, Any]]
    final: dict[str, Any] | None
    done: dict[str, Any]
    run: dict[str, Any]
    checks: dict[str, Any] = field(default_factory=dict)
    mode: str | None = None  # the mode requested by the harness (None = field absent)
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        agent = self.run.get("agent")
        return {
            "id": self.item["id"],
            "category": self.item["category"],
            "workspace": self.item.get("workspace"),
            "split": self.item.get("split"),
            "expect": self.item.get("expect"),
            "question": self.item["question"],
            "requested_mode": self.mode,
            "mode": self.run.get("mode"),
            "route": self.run.get("route"),
            "agent": agent,
            "termination_state": self.done.get("termination_state"),
            "flags": self.done.get("flags"),
            "content": self.final.get("content") if self.final else None,
            "verification": self.final.get("verification") if self.final else None,
            "cited_handles": self.run.get("cited_handles"),
            "pack_handles": self.run.get("pack_handles"),
            "usage": self.run.get("usage"),
            "timings": self.run.get("timings"),
            "checks": self.checks,
            "metrics": self.metrics,
            "warnings": [e["data"] for e in self.events if e["event"] == "warning"],
        }


def parse_sse(raw: str) -> list[dict[str, Any]]:
    events = []
    for block in raw.split("\n\n"):
        lines = [x for x in block.splitlines() if x and not x.startswith(":")]
        if not lines:
            continue
        event: dict[str, Any] = {}
        for line in lines:
            key, _, value = line.partition(":")
            event[key] = value[1:] if value.startswith(" ") else value
        event["data"] = json.loads(event["data"])
        events.append(event)
    return events


def select_items(
    items: list[dict[str, Any]],
    *,
    split: str = "all",
    ids: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Dataset order; ``split`` dev/test keeps items with that ``split`` field (all keeps every
    item, including datasets without splits), ``ids`` is a comma list, ``limit`` applies last."""
    selected = [i for i in items if split == "all" or i.get("split") == split]
    if ids:
        wanted = set(ids.split(","))
        selected = [i for i in selected if i["id"] in wanted]
    return selected[:limit] if limit else selected


async def run_item(
    client: AsyncClient, item: dict[str, Any], mode: str | None = None
) -> ItemOutcome:
    ws = item["workspace"]
    conversation = (await client.post(f"/api/workspaces/{ws}/conversations", json={})).json()[
        "conversation_id"
    ]
    body: dict[str, Any] = {"question": item["question"]}
    if item.get("source_classes"):
        body["source_classes"] = item["source_classes"]
    if mode is not None:
        body["mode"] = mode
    started = await client.post(
        f"/api/workspaces/{ws}/conversations/{conversation}/runs", json=body
    )
    started.raise_for_status()
    run = started.json()
    stream = await asyncio.wait_for(client.get(run["stream_url"]), timeout=180)
    events = parse_sse(stream.text)
    final = next((e["data"] for e in events if e["event"] == "final"), None)
    done: dict[str, Any] = next((e["data"] for e in events if e["event"] == "done"), {})
    stored = (await client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    return ItemOutcome(item, events, final, done, stored, mode=mode)


def _llm_called(out: ItemOutcome) -> bool:
    """True if a model call was made or attempted (a failed call records no output tokens)."""
    usage = out.run.get("usage") or {}
    if usage.get("output_tokens") or usage.get("input_tokens"):
        return True
    return any(
        e["event"] == "draft_reset"
        or (e["event"] == "status" and e["data"].get("phase") == "synthesizing")
        for e in out.events
    )


def _numbers_match(value: Any, content: str) -> bool:
    if not isinstance(value, int | float):
        return True  # non-numeric facts are not part of the numeric check
    mentions = contract.extract_numbers(content)
    values = [m.mantissa for m in mentions] + [m.value for m in mentions]
    return any(abs(v - float(value)) <= 1e-6 * max(1.0, abs(float(value))) for v in values)


def _value_present(value: Any, content: str) -> bool:
    """A gold fact's ledger value appears in the answer (numbers by normalised value)."""
    if isinstance(value, int | float):
        return _numbers_match(value, content)
    if not isinstance(value, str) or not value.strip():
        return False
    return " ".join(value.lower().split()) in " ".join(content.lower().split())


def recheck_contract(content: str) -> list[str]:
    """Independent check of the stored canonical answer (not trusting the verifier's report)."""
    problems: list[str] = []
    if ALIAS_RE.search(content):
        problems.append("run-local alias in stored content")
    if contract.strip_leaks(CANONICAL_RE.sub("", content)).removed:
        problems.append("url/link/image/html/id leak in stored content")
    sections = contract.parse_sections(content)
    for unit in contract.split_units(sections.get(contract.ANSWER, "")):
        if not (CANONICAL_RE.search(unit) or "[inference]" in unit.lower()):
            problems.append(f"uncited answer sentence: {unit[:60]}")
    for unit in contract.split_units(sections.get(contract.FINDINGS, "")):
        if not CANONICAL_RE.search(unit):
            problems.append(f"uncited finding: {unit[:60]}")
    return problems


async def score(client: AsyncClient, out: ItemOutcome) -> None:
    item, checks = out.item, out.checks
    ws = item["workspace"]
    content = (out.final or {}).get("content") or ""
    cited = list(dict.fromkeys(CANONICAL_RE.findall(content)))
    pack = set(out.run.get("pack_handles") or [])
    statuses = []
    texts: dict[str, str] = {}
    for handle in cited:
        response = await client.get(f"/api/workspaces/{ws}/evidence/{handle}")
        statuses.append(response.status_code)
        if response.status_code == 200:
            texts[handle] = str(response.json().get("text", ""))
    sections = (out.final or {}).get("sections") or {}
    tokens_streamed = any(e["event"] == "token" for e in out.events)
    checks["citations"] = len(cited)
    checks["resolvable"] = sum(1 for s in statuses if s == 200)
    checks["in_pack"] = sum(1 for h in cited if h in pack)
    checks["foreign_citations"] = [h for h in cited if not h.startswith(f"{ws}/")]
    checks["southpeak_marker_leak"] = ws != "SOUTHPEAK" and any(
        m in content for m in SOUTHPEAK_MARKERS
    )
    checks["contract_problems"] = recheck_contract(content) if content else ["no final"]
    checks["evidence_only"] = bool(sections.get("evidence_only"))
    checks["abstained_deterministic"] = bool(sections.get("abstained"))
    # Insufficiency counts only when the Answer section itself says so (not Gaps & unknowns).
    answer_text = contract.parse_sections(content).get(contract.ANSWER, "")
    states_insufficient = contract.states_insufficient(answer_text)
    answer_cites = CANONICAL_RE.search(answer_text) is not None
    checks["has_final"] = out.final is not None
    checks["has_done"] = bool(out.done)
    answered = bool(cited) and not checks["evidence_only"] and not checks["abstained_deterministic"]
    checks["answered"] = answered
    checks["llm_called"] = _llm_called(out)
    if item["gold_facts"]:
        covered = []
        numeric = []
        for fact in item["gold_facts"]:
            covered.append(bool(set(fact["handles"]) & set(cited)))
            if isinstance(fact["value"], int | float):
                numeric.append(_numbers_match(fact["value"], content))
        complete = [_value_present(f["value"], content) for f in item["gold_facts"]]
        # Evidence-only fallbacks quote the ledger numbers verbatim; never credit them as
        # answers. They are reported under separate keys.
        prefix = "" if answered else "fallback_"
        checks[f"{prefix}gold_coverage"] = sum(covered) / len(covered)
        checks[f"{prefix}numeric_correct"] = (sum(numeric) / len(numeric)) if numeric else None
        checks[f"{prefix}answer_completeness"] = sum(complete) / len(complete)
        with_handles = [f for f in item["gold_facts"] if f["handles"]]
        checks["gold_handle_recall"] = (
            sum(1 for f in with_handles if set(f["handles"]) & pack) / len(with_handles)
            if with_handles
            else None
        )
    recheck = recheck_content(content, texts)
    checks["cited_units"] = recheck["cited_units"]
    checks["unsupported_units"] = len(recheck["unsupported"])
    checks["unsupported_numbers"] = [n for u in recheck["unsupported"] for n in u["numbers"]]
    checks["unsupported_claim_rate"] = (
        checks["unsupported_units"] / recheck["cited_units"] if recheck["cited_units"] else None
    )
    expect = item["expect"]
    if expect == "answer":
        checks["pass_behaviour"] = answered
    elif expect == "insufficient":
        bad_claim = answer_cites and not states_insufficient
        checks["pass_behaviour"] = out.final is not None and not bad_claim
        checks["abstention_correct"] = checks["pass_behaviour"]
    elif expect == "abstain_no_llm":
        checks["pass_behaviour"] = (
            out.done.get("termination_state") == "no_relevant_evidence"
            and not tokens_streamed
            and not checks["llm_called"]
        )
    elif expect == "conflict":
        retrievable = [f for f in item["gold_facts"] if f["handles"]]
        both = all(set(f["handles"]) & set(cited) for f in retrievable)
        checks["conflict_covered"] = both
        checks["pass_behaviour"] = both or bool(sections.get("conflicts"))
    if item.get("canary"):
        streamed = "".join(e["data"].get("text", "") for e in out.events if e["event"] == "token")
        checks["canary_leak"] = item["canary"] in content or item["canary"] in streamed
    timings = out.run.get("timings") or {}
    checks["first_token_ms"] = timings.get("first_token_ms")
    checks["total_ms"] = timings.get("total_ms")


_ANSWER_EXPECTED = ("answer", "conflict")


def _values(members: list[ItemOutcome], key: str) -> list[float]:
    return [o.checks[key] for o in members if o.checks.get(key) is not None]


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _empty_pack_gate(empty: list[ItemOutcome], *, required: bool) -> dict[str, Any]:
    """No synthesis call on an empty pack (agent planning calls are not synthesis calls).
    Required datasets must contain at least one ``abstain_no_llm`` item; otherwise a set
    without such items reads "not applicable"."""
    if not empty and not required:
        return {"value": "not applicable", "pass": True}
    return {
        "value": sum(1 for o in empty if o.checks["pass_behaviour"]) / len(empty)
        if empty
        else "not evaluated",
        "pass": bool(empty) and all(o.checks["pass_behaviour"] for o in empty),
    }


def summarize(outcomes: list[ItemOutcome], *, require_empty_pack: bool = True) -> dict[str, Any]:
    cited = sum(o.checks["citations"] for o in outcomes)
    resolvable = sum(o.checks["resolvable"] for o in outcomes)
    in_pack = sum(o.checks["in_pack"] for o in outcomes)
    foreign = [h for o in outcomes for h in o.checks["foreign_citations"]]
    leaks = [o.item["id"] for o in outcomes if o.checks["southpeak_marker_leak"]]
    empty = [o for o in outcomes if o.item["expect"] == "abstain_no_llm"]
    answer_expected = [o for o in outcomes if o.item["expect"] in _ANSWER_EXPECTED]
    # Zero citations across answer-expected items is "not evaluated", never a vacuous pass.
    unevaluated = cited == 0 and bool(answer_expected)
    needs_final = [o for o in outcomes if o.item["expect"] != "abstain_no_llm"]
    no_done = [o.item["id"] for o in outcomes if not o.checks["has_done"]]
    no_final = [o.item["id"] for o in needs_final if not o.checks["has_final"]]
    gates = {
        "citation_resolvability": {
            "value": "not evaluated" if unevaluated else (resolvable / cited if cited else 1.0),
            "pass": not unevaluated and resolvable == cited,
        },
        "citation_in_pack": {
            "value": "not evaluated" if unevaluated else (in_pack / cited if cited else 1.0),
            "pass": not unevaluated and in_pack == cited,
        },
        "every_run_done": {"value": len(no_done), "pass": not no_done, "missing": no_done},
        "answer_items_have_final": {
            "value": len(no_final),
            "pass": not no_final,
            "missing": no_final,
        },
        "cross_workspace_leaks": {
            "value": len(foreign) + len(leaks),
            "pass": not foreign and not leaks,
        },
        "empty_pack_never_calls_llm": _empty_pack_gate(empty, required=require_empty_pack),
    }
    by_category: dict[str, list[ItemOutcome]] = defaultdict(list)
    for o in outcomes:
        by_category[o.item["category"]].append(o)
    categories = {}
    for name, members in sorted(by_category.items()):
        passed = [o for o in members if o.checks.get("pass_behaviour") is not None]
        k = sum(1 for o in passed if o.checks["pass_behaviour"])
        cov = _values(members, "gold_coverage")
        num = _values(members, "numeric_correct")
        fb_cov = _values(members, "fallback_gold_coverage")
        fb_num = _values(members, "fallback_numeric_correct")
        categories[name] = {
            "n": len(members),
            "behaviour_pass": f"{k}/{len(passed)}",
            "behaviour_ci": wilson(k, len(passed)).as_dict() if passed else None,
            "gold_coverage_mean": _mean(cov),
            "numeric_correct_mean": _mean(num),
            "answered": sum(1 for o in members if o.checks["answered"]),
            "fallback_gold_coverage_mean": _mean(fb_cov),
            "fallback_numeric_correct_mean": _mean(fb_num),
            "evidence_only": sum(1 for o in members if o.checks["evidence_only"]),
        }
    answerable = [o for o in outcomes if o.item["expect"] == "answer"]
    insufficient = [o for o in outcomes if o.item["expect"] == "insufficient"]
    first = [o.checks["first_token_ms"] for o in outcomes if o.checks.get("first_token_ms")]
    total = [o.checks["total_ms"] for o in outcomes if o.checks.get("total_ms")]
    usage: dict[str, int] = defaultdict(int)
    for o in outcomes:
        for key, value in (o.run.get("usage") or {}).items():
            usage[key] += int(value)
    llm_runs = [o for o in outcomes if o.checks["llm_called"]]
    return {
        "n": len(outcomes),
        "hard_gates": gates,
        "contract_recheck_failures": [
            {"id": o.item["id"], "problems": o.checks["contract_problems"]}
            for o in outcomes
            if o.checks["contract_problems"]
        ],
        "over_refusal": {
            "k": sum(1 for o in answerable if not o.checks["answered"]),
            "n": len(answerable),
        },
        "insufficient_correct": {
            "k": sum(1 for o in insufficient if o.checks.get("pass_behaviour")),
            "n": len(insufficient),
        },
        "canary_leaks": [o.item["id"] for o in outcomes if o.checks.get("canary_leak")],
        "categories": categories,
        "latency_ms": {
            "first_token_p50": percentile(first, 0.5) if first else None,
            "first_token_p95": percentile(first, 0.95) if first else None,
            "total_p50": percentile(total, 0.5) if total else None,
            "total_p95": percentile(total, 0.95) if total else None,
        },
        "usage_total": dict(usage),
        "usage_per_llm_run_mean": {k: round(v / len(llm_runs), 1) for k, v in usage.items()}
        if llm_runs
        else {},
        "regenerations": sum(
            1
            for o in outcomes
            if any(e["event"] == "draft_reset" and e["data"].get("attempt") == 2 for e in o.events)
        ),
        "termination_states": dict(
            sorted(
                {
                    s: sum(1 for o in outcomes if o.done.get("termination_state") == s)
                    for s in {o.done.get("termination_state") for o in outcomes}
                }.items(),
                key=lambda kv: str(kv[0]),
            )
        ),
    }


DEFAULT_MODE = "default"  # result key when no mode is requested


async def evaluate_modes(
    app: Any,
    items: list[dict[str, Any]],
    modes: Sequence[str | None],
    *,
    concurrency: int = 1,
    prices: Prices | None = None,
    require_empty_pack: bool = True,
) -> dict[str, dict[str, Any]]:
    """Run every item once per mode. Modes of one item run sequentially (same item, same load,
    comparable latency); items run ``concurrency`` at a time. Keyed by mode (``default`` when
    the request carries no mode)."""
    prices = prices or Prices(0.0, 0.0, 0.0, 0.0)
    per_mode: dict[str | None, list[ItemOutcome]] = {m: [] for m in modes}
    elapsed: dict[str | None, float] = dict.fromkeys(modes, 0.0)
    started = time.monotonic()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app), base_url="http://eval", timeout=240
        ) as client,
    ):
        semaphore = asyncio.Semaphore(concurrency)

        async def one(item: dict[str, Any]) -> list[ItemOutcome]:
            async with semaphore:
                outs = []
                for mode in modes:
                    t0 = time.monotonic()
                    out = await run_item(client, item, mode)
                    await score(client, out)
                    out.metrics = run_metrics(out, prices)
                    elapsed[mode] += time.monotonic() - t0
                    outs.append(out)
                return outs

        for outs in await asyncio.gather(*(one(i) for i in items)):
            for mode, out in zip(modes, outs, strict=True):
                per_mode[mode].append(out)
    total = round(time.monotonic() - started, 1)
    return {
        (mode or DEFAULT_MODE): {
            "elapsed_s": total if len(modes) == 1 else round(elapsed[mode], 1),
            "summary": summarize(outcomes, require_empty_pack=require_empty_pack),
            "runs": mode_summary(outcomes, mode=mode),
            "pipeline": pipeline_stats(outcomes, prices),
            "items": [o.as_dict() for o in outcomes],
        }
        for mode, outcomes in per_mode.items()
    }


async def evaluate(
    app: Any,
    items: list[dict[str, Any]],
    *,
    concurrency: int = 1,
    prices: Prices | None = None,
    mode: str | None = None,
    require_empty_pack: bool = True,
) -> dict[str, Any]:
    """Single-mode evaluation (``mode=None``: the request carries no mode field)."""
    results = await evaluate_modes(
        app,
        items,
        (mode,),
        concurrency=concurrency,
        prices=prices,
        require_empty_pack=require_empty_pack,
    )
    return results[mode or DEFAULT_MODE]
