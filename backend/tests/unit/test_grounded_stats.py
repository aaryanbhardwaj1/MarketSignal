from typing import Any

import pytest

from marketsignal.evaluation.grounded import ItemOutcome
from marketsignal.evaluation.grounded_stats import Prices, pipeline_stats


def _outcome(
    *,
    timings: dict[str, Any],
    usage: dict[str, int] | None = None,
    verification: dict[str, Any] | None = None,
    flags: list[str] | None = None,
    events: list[dict[str, Any]] | None = None,
    llm: bool = True,
) -> ItemOutcome:
    final = {"content": "x", "verification": verification} if verification is not None else None
    out = ItemOutcome(
        item={"id": "i", "category": "answerable_fact", "expect": "answer"},
        events=events or [],
        final=final,
        done={"termination_state": "completed", "flags": flags or []},
        run={"timings": timings, "usage": usage or {}},
    )
    out.checks = {"llm_called": llm, "evidence_only": "evidence_only" in (flags or [])}
    return out


PRICES = Prices(input=2.0, output=10.0, cache_write=2.5, cache_read=0.2)


def test_stage_latencies_sum_attempts_and_report_percentiles() -> None:
    outs = [
        _outcome(
            timings={
                "retrieval_ms": 30,
                "pack_ms": 2,
                "synthesis_ms_1": 1000,
                "verify_ms_1": 3,
                "total_ms": 1100,
            }
        ),
        _outcome(
            timings={
                "retrieval_ms": 50,
                "pack_ms": 4,
                "synthesis_ms_1": 1000,
                "synthesis_ms_2": 900,
                "verify_ms_1": 3,
                "verify_ms_2": 2,
                "total_ms": 2000,
            }
        ),
    ]
    stages = pipeline_stats(outs, PRICES)["stage_latency_ms"]
    assert stages["retrieval"]["p50"] == pytest.approx(40)
    assert stages["model"]["max"] == pytest.approx(1900)  # both attempts count
    assert stages["verification"]["max"] == pytest.approx(5)
    assert stages["model"]["n"] == 2


def test_verifier_outcomes_and_fallback_frequency() -> None:
    outs = [
        _outcome(
            timings={},
            verification={
                "passed": True,
                "repairs": ["a", "b"],
                "unknown_aliases": ["E99"],
                "numeric_violations": [],
                "leaks_removed": ["url"],
                "structural_failures": [],
            },
        ),
        _outcome(
            timings={},
            verification={
                "passed": True,
                "repairs": [],
                "unknown_aliases": [],
                "numeric_violations": ["Answer #1: 41%"],
                "leaks_removed": [],
                "structural_failures": [],
            },
            events=[
                {"event": "draft_reset", "data": {"attempt": 2, "reason": "verification_failed"}}
            ],
        ),
        _outcome(
            timings={},
            flags=["CITATION_VERIFICATION_FAILED"],
            events=[
                {"event": "draft_reset", "data": {"attempt": 2, "reason": "verification_failed"}}
            ],
        ),
    ]
    v = pipeline_stats(outs, PRICES)["verification"]
    assert v["runs_with_repairs"] == 1
    assert v["repairs_total"] == 2
    assert v["unknown_aliases_removed"] == 1
    assert v["numeric_units_dropped"] == 1
    assert v["leaks_removed"] == 1
    assert v["first_attempt_failed"] == 2
    assert v["regenerated"] == 2
    assert v["fallback_after_verification"] == 1


def test_cost_uses_cache_prices_and_counts_only_reported_usage() -> None:
    outs = [
        _outcome(
            timings={},
            usage={
                "input_tokens": 1_000_000,
                "output_tokens": 100_000,
                "cache_read_input_tokens": 1_000_000,
                "cache_creation_input_tokens": 0,
            },
        ),
        _outcome(
            timings={},
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 1_000_000,
            },
        ),
    ]
    cost = pipeline_stats(outs, PRICES)["cost_usd"]
    assert cost["input"] == pytest.approx(2.0)
    assert cost["output"] == pytest.approx(1.0)
    assert cost["cache_read"] == pytest.approx(0.2)
    assert cost["cache_write"] == pytest.approx(2.5)
    assert cost["total"] == pytest.approx(5.7)
    assert cost["per_model_run"] == pytest.approx(2.85)
