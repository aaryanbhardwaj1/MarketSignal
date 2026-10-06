"""Pipeline statistics for the grounded-answer evaluation: per-stage latency, verifier
outcomes, regeneration/fallback frequency and approximate model cost.

Every number is computed from what the production path recorded (``query_runs.timings``,
``usage``, ``route`` and ``agent``, the ``final`` event's verification report, the event log);
nothing is re-derived from model text. Cost is approximate: returned usage (research agent
steps + synthesis attempts) times the configured list prices.

Per-run metrics (``run_metrics``; exact definitions):
* ``model_calls`` = ``agent.usage.llm_attempts`` + ``usage.llm_attempts`` (synthesis attempts,
  recorded even when the call fails);
* ``tool_calls`` = ``agent.tool_calls`` (governed tool calls, incl. denied/failed);
  ``tool_failures`` = ``agent.tool_errors``; ``steps`` = ``agent.steps`` (0 for standard);
* ``retrieval_calls``: a run without an agent record = 1 if the standard gather ran
  (``timings.retrieval_ms``); a research run = trace calls to ``search_evidence`` or
  ``search_evidence_keyword`` (any status) + 1 if the fallback standard gather ran;
* ``research_fallback``: the agent stopped with ``planner_unavailable``/``no_successful_search``
  or flagged ``PLANNER_UNAVAILABLE_FALLBACK``/``PLANNER_NO_TOOL_FALLBACK``;
* ``tokens``: input/output/cache_read/cache_write summed over agent and synthesis usage;
* ``regenerated``: a ``draft_reset`` with attempt 2 or reason ``verification_failed``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from marketsignal.evaluation.stats import percentile, wilson

if TYPE_CHECKING:
    from marketsignal.evaluation.grounded import ItemOutcome

_PER_MTOK = 1_000_000
_VERIFICATION_FALLBACK_FLAG = "CITATION_VERIFICATION_FAILED"
_FALLBACK_STOPS = frozenset({"planner_unavailable", "no_successful_search"})
_FALLBACK_FLAGS = frozenset({"PLANNER_UNAVAILABLE_FALLBACK", "PLANNER_NO_TOOL_FALLBACK"})
_SEARCH_TOOLS = frozenset({"search_evidence", "search_evidence_keyword"})
_TOKEN_KEYS = (
    ("input", "input_tokens"),
    ("output", "output_tokens"),
    ("cache_read", "cache_read_input_tokens"),
    ("cache_write", "cache_creation_input_tokens"),
)


@dataclass(frozen=True)
class Prices:
    """USD per million tokens."""

    input: float
    output: float
    cache_write: float
    cache_read: float


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    return {
        "n": len(values),
        "p50": round(percentile(values, 0.5), 1),
        "p95": round(percentile(values, 0.95), 1),
        "max": round(max(values), 1),
    }


def _summed(timings: dict[str, Any], prefix: str) -> float | None:
    parts = [float(v) for k, v in timings.items() if k.startswith(prefix)]
    return sum(parts) if parts else None


def _stage_latency(outcomes: Sequence[ItemOutcome]) -> dict[str, dict[str, Any]]:
    stages: dict[str, list[float]] = {
        "agent": [],
        "retrieval": [],
        "pack": [],
        "model": [],
        "verification": [],
        "end_to_end": [],
    }
    for o in outcomes:
        t = o.run.get("timings") or {}
        for stage, key in (
            ("agent", "agent_ms"),
            ("retrieval", "retrieval_ms"),
            ("pack", "pack_ms"),
        ):
            if key in t:
                stages[stage].append(float(t[key]))
        for stage, prefix in (("model", "synthesis_ms_"), ("verification", "verify_ms_")):
            total = _summed(t, prefix)
            if total is not None:
                stages[stage].append(total)
        if "total_ms" in t:
            stages["end_to_end"].append(float(t["total_ms"]))
    return {stage: _distribution(values) for stage, values in stages.items()}


def _verification(outcomes: Sequence[ItemOutcome]) -> dict[str, int]:
    reports = [o.final["verification"] for o in outcomes if o.final and o.final.get("verification")]
    regenerated = [
        o
        for o in outcomes
        if any(
            e["event"] == "draft_reset" and e["data"].get("reason") == "verification_failed"
            for e in o.events
        )
    ]
    fallback = [o for o in outcomes if _VERIFICATION_FALLBACK_FLAG in (o.done.get("flags") or [])]
    return {
        "verified_answers": len(reports),
        "runs_with_repairs": sum(1 for r in reports if r.get("repairs")),
        "repairs_total": sum(len(r.get("repairs") or []) for r in reports),
        "unknown_aliases_removed": sum(len(r.get("unknown_aliases") or []) for r in reports),
        "numeric_units_dropped": sum(len(r.get("numeric_violations") or []) for r in reports),
        "leaks_removed": sum(len(r.get("leaks_removed") or []) for r in reports),
        # A regeneration happens only after attempt 1 failed verification.
        "first_attempt_failed": len(regenerated),
        "regenerated": len(regenerated),
        "fallback_after_verification": len(fallback),
        "evidence_only_total": sum(1 for o in outcomes if o.checks.get("evidence_only")),
    }


def _tokens(usage: dict[str, Any] | None) -> dict[str, int]:
    usage = usage or {}
    return {short: int(usage.get(key) or 0) for short, key in _TOKEN_KEYS}


def run_tokens(o: ItemOutcome) -> dict[str, int]:
    """Agent + synthesis tokens of one run."""
    agent = _tokens((o.run.get("agent") or {}).get("usage"))
    synthesis = _tokens(o.run.get("usage"))
    return {k: agent[k] + synthesis[k] for k in agent}


def _token_cost(tokens: dict[str, int], prices: Prices) -> dict[str, float]:
    return {
        "input": tokens["input"] * prices.input / _PER_MTOK,
        "output": tokens["output"] * prices.output / _PER_MTOK,
        "cache_write": tokens["cache_write"] * prices.cache_write / _PER_MTOK,
        "cache_read": tokens["cache_read"] * prices.cache_read / _PER_MTOK,
    }


def _cost(outcomes: Sequence[ItemOutcome], prices: Prices) -> dict[str, float]:
    totals = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    for o in outcomes:
        for key, value in run_tokens(o).items():
            totals[key] += value
    cost = _token_cost(totals, prices)
    total = sum(cost.values())
    model_runs = sum(1 for o in outcomes if o.checks.get("llm_called"))
    return {
        **{k: round(v, 4) for k, v in cost.items()},
        "total": round(total, 4),
        "per_model_run": round(total / model_runs, 5) if model_runs else 0.0,
    }


def pipeline_stats(outcomes: Sequence[ItemOutcome], prices: Prices) -> dict[str, Any]:
    return {
        "stage_latency_ms": _stage_latency(outcomes),
        "verification": _verification(outcomes),
        "cost_usd": _cost(outcomes, prices),
        "prices_usd_per_mtok": vars(prices),
    }


def _retrieval_calls(agent: dict[str, Any] | None, timings: dict[str, Any], fallback: bool) -> int:
    if not agent:
        return 1 if "retrieval_ms" in timings else 0
    searches = sum(1 for t in agent.get("trace") or [] if t.get("tool") in _SEARCH_TOOLS)
    return searches + (1 if fallback else 0)


def _regenerated(o: ItemOutcome) -> bool:
    return any(
        e["event"] == "draft_reset"
        and (e["data"].get("attempt") == 2 or e["data"].get("reason") == "verification_failed")
        for e in o.events
    )


def run_metrics(o: ItemOutcome, prices: Prices) -> dict[str, Any]:
    """Cost/effort metrics of one run (definitions in the module docstring)."""
    agent: dict[str, Any] = o.run.get("agent") or {}
    route: dict[str, Any] = o.run.get("route") or {}
    timings: dict[str, Any] = o.run.get("timings") or {}
    trace = agent.get("trace") or []
    fallback = bool(agent) and (
        agent.get("stop_reason") in _FALLBACK_STOPS
        or bool(_FALLBACK_FLAGS & set(agent.get("flags") or []))
    )
    agent_calls = int((agent.get("usage") or {}).get("llm_attempts") or 0)
    synthesis_calls = int((o.run.get("usage") or {}).get("llm_attempts") or 0)
    tokens = run_tokens(o)
    expected = o.item.get("router_expectation")
    decided = route.get("decided")
    return {
        "mode": o.run.get("mode") or decided or o.mode,
        "requested_mode": o.mode,
        "route_decided": decided,
        "route_reason": route.get("reason"),
        "route_cues": route.get("cues"),
        "router_expectation": expected,
        "router_agree": (decided == expected) if o.mode == "auto" and expected else None,
        "model_calls": agent_calls + synthesis_calls,
        "agent_model_calls": agent_calls,
        "synthesis_model_calls": synthesis_calls,
        "tool_calls": int(agent.get("tool_calls", len(trace)) or 0),
        "tool_failures": int(
            agent.get("tool_errors", sum(1 for t in trace if t.get("status") != "ok")) or 0
        ),
        "retrieval_calls": _retrieval_calls(agent, timings, fallback),
        "steps": int(agent.get("steps") or 0),
        "stop_reason": agent.get("stop_reason"),
        "agent_flags": list(agent.get("flags") or []),
        "research_fallback": fallback,
        "termination_state": o.done.get("termination_state"),
        "tokens": tokens,
        "cost_usd": round(sum(_token_cost(tokens, prices).values()), 6),
        "first_token_ms": timings.get("first_token_ms"),
        "total_ms": timings.get("total_ms"),
        "agent_ms": timings.get("agent_ms"),
        "regenerated": _regenerated(o),
        "evidence_only": bool(o.checks.get("evidence_only")),
    }


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _vals(outcomes: Sequence[ItemOutcome], key: str, *, metrics: bool = False) -> list[float]:
    source = (o.metrics if metrics else o.checks for o in outcomes)
    return [float(d[key]) for d in source if d.get(key) is not None]


def _rate(outcomes: Sequence[ItemOutcome], key: str) -> dict[str, Any] | None:
    flags = [bool(o.checks[key]) for o in outcomes if o.checks.get(key) is not None]
    if not flags:
        return None
    k = sum(flags)
    return {"k": k, "n": len(flags), "ci": wilson(k, len(flags)).as_dict()}


def _counted(outcomes: Sequence[ItemOutcome], key: str) -> dict[str, Any]:
    values = _vals(outcomes, key, metrics=True)
    return {"total": int(sum(values)), "mean": _mean(values)}


def _quality(outcomes: Sequence[ItemOutcome]) -> dict[str, Any]:
    answered = [o for o in outcomes if o.checks.get("answered")]
    cited_units = sum(int(o.checks.get("cited_units") or 0) for o in answered)
    unsupported = sum(int(o.checks.get("unsupported_units") or 0) for o in answered)
    return {
        "behaviour_pass": _rate(outcomes, "pass_behaviour"),
        "gold_coverage_mean": _mean(_vals(outcomes, "gold_coverage")),
        "answer_completeness_mean": _mean(_vals(outcomes, "answer_completeness")),
        "gold_handle_recall_mean": _mean(_vals(outcomes, "gold_handle_recall")),
        "conflict_coverage": _rate(outcomes, "conflict_covered"),
        "abstention_correct": _rate(outcomes, "abstention_correct"),
        "unsupported_claim_rate": {
            "unsupported_units": unsupported,
            "cited_units": cited_units,
            "rate": round(unsupported / cited_units, 4) if cited_units else None,
        },
    }


def _distribution_of(outcomes: Sequence[ItemOutcome], key: str) -> dict[str, int]:
    counts = Counter(str(o.metrics.get(key)) for o in outcomes)
    return dict(sorted(counts.items()))


def _router_agreement(outcomes: Sequence[ItemOutcome]) -> dict[str, Any] | None:
    judged = [o for o in outcomes if o.metrics.get("router_agree") is not None]
    if not judged:
        return None
    k = sum(1 for o in judged if o.metrics["router_agree"])
    confusion = Counter(
        f"{o.metrics['router_expectation']}->{o.metrics['route_decided']}" for o in judged
    )
    return {
        "k": k,
        "n": len(judged),
        "ci": wilson(k, len(judged)).as_dict(),
        "confusion": dict(sorted(confusion.items())),
    }


def mode_summary(outcomes: Sequence[ItemOutcome], *, mode: str | None) -> dict[str, Any]:
    """Per-mode totals, distributions and quality means (overall and per category)."""
    first = _vals(outcomes, "first_token_ms", metrics=True)
    total = _vals(outcomes, "total_ms", metrics=True)
    tokens = {k: 0 for k, _ in _TOKEN_KEYS}
    for o in outcomes:
        for key, value in (o.metrics.get("tokens") or {}).items():
            tokens[key] += int(value)
    cost = sum(float(o.metrics.get("cost_usd") or 0.0) for o in outcomes)
    agent_runs = [o for o in outcomes if o.run.get("agent")]
    categories: dict[str, list[ItemOutcome]] = {}
    for o in outcomes:
        categories.setdefault(o.item["category"], []).append(o)
    return {
        "mode": mode,
        "n": len(outcomes),
        "model_calls": _counted(outcomes, "model_calls"),
        "tool_calls": _counted(outcomes, "tool_calls"),
        "tool_failures": _counted(outcomes, "tool_failures"),
        "retrieval_calls": _counted(outcomes, "retrieval_calls"),
        "steps": _counted(outcomes, "steps"),
        "tokens_total": tokens,
        "cost_usd": {
            "total": round(cost, 6),
            "per_run": round(cost / len(outcomes), 6) if outcomes else None,
        },
        "latency_ms": {
            "first_token_p50": percentile(first, 0.5) if first else None,
            "first_token_p95": percentile(first, 0.95) if first else None,
            "total_p50": percentile(total, 0.5) if total else None,
            "total_p95": percentile(total, 0.95) if total else None,
        },
        "routes_decided": _distribution_of(outcomes, "route_decided"),
        "stop_reasons": _distribution_of(agent_runs, "stop_reason"),
        "termination_states": _distribution_of(outcomes, "termination_state"),
        "research_fallbacks": sum(1 for o in outcomes if o.metrics.get("research_fallback")),
        "regenerations": sum(1 for o in outcomes if o.metrics.get("regenerated")),
        "evidence_only": sum(1 for o in outcomes if o.metrics.get("evidence_only")),
        **_quality(outcomes),
        "router_agreement": _router_agreement(outcomes) if mode == "auto" else None,
        "categories": {
            name: {
                "n": len(members),
                **_quality(members),
                "total_ms_p50": percentile(t, 0.5)
                if (t := _vals(members, "total_ms", metrics=True))
                else None,
                "model_calls_mean": _mean(_vals(members, "model_calls", metrics=True)),
                "tool_calls_mean": _mean(_vals(members, "tool_calls", metrics=True)),
                "cost_usd": round(sum(float(o.metrics.get("cost_usd") or 0) for o in members), 6),
            }
            for name, members in sorted(categories.items())
        },
    }
