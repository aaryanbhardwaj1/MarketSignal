"""Pipeline statistics for the grounded-answer evaluation: per-stage latency, verifier
outcomes, regeneration/fallback frequency and approximate model cost.

Every number is computed from what the production path recorded (``query_runs.timings`` and
``usage``, the ``final`` event's verification report, the event log); nothing is re-derived
from model text. Cost is approximate: returned usage times the configured list prices.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from marketsignal.evaluation.stats import percentile

if TYPE_CHECKING:
    from marketsignal.evaluation.grounded import ItemOutcome

_PER_MTOK = 1_000_000
_VERIFICATION_FALLBACK_FLAG = "CITATION_VERIFICATION_FAILED"


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
        "retrieval": [],
        "pack": [],
        "model": [],
        "verification": [],
        "end_to_end": [],
    }
    for o in outcomes:
        t = o.run.get("timings") or {}
        for stage, key in (("retrieval", "retrieval_ms"), ("pack", "pack_ms")):
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


def _cost(outcomes: Sequence[ItemOutcome], prices: Prices) -> dict[str, float]:
    totals = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    for o in outcomes:
        usage = o.run.get("usage") or {}
        totals["input"] += int(usage.get("input_tokens") or 0)
        totals["output"] += int(usage.get("output_tokens") or 0)
        totals["cache_write"] += int(usage.get("cache_creation_input_tokens") or 0)
        totals["cache_read"] += int(usage.get("cache_read_input_tokens") or 0)
    cost = {
        "input": totals["input"] * prices.input / _PER_MTOK,
        "output": totals["output"] * prices.output / _PER_MTOK,
        "cache_write": totals["cache_write"] * prices.cache_write / _PER_MTOK,
        "cache_read": totals["cache_read"] * prices.cache_read / _PER_MTOK,
    }
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
