"""Run telemetry pure helpers: cost estimate, cursor, allowlists, timeline and SQL filters."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from marketsignal.devtools.run_telemetry import RunFilters, run_where
from marketsignal.devtools.run_telemetry_view import (
    EventRow,
    agent_view,
    build_timeline,
    cost_estimate,
    decode_cursor,
    encode_cursor,
    estimate_cost_usd,
    event_offset_ms,
    is_redacted_args,
    numeric_only,
    pct,
    route_view,
    verification_summary,
)

WS = uuid.UUID("00000000-0000-0000-0000-000000000001")


# --- cost ------------------------------------------------------------------------------------


def test_cost_uses_the_list_prices_per_million_tokens() -> None:
    tokens = {"input": 1_000_000, "output": 1_000_000, "cache_write": 1_000_000, "cache_read": 0}
    assert estimate_cost_usd(tokens) == pytest.approx(2.0 + 10.0 + 2.5)
    assert estimate_cost_usd({"cache_read": 1_000_000}) == pytest.approx(0.2)
    assert estimate_cost_usd({}) == 0.0


def test_cost_estimate_is_null_without_usage_and_labelled() -> None:
    empty = cost_estimate({"input": 0}, 0)
    assert empty["total_usd"] is None
    assert empty["per_run_usd"] is None
    assert empty["basis"] == "list_prices_from_persisted_usage"
    assert empty["prices_per_mtok"] == {
        "input": 2.0,
        "output": 10.0,
        "cache_write": 2.5,
        "cache_read": 0.2,
    }
    some = cost_estimate({"input": 500_000, "output": 100_000}, 4)
    assert some["total_usd"] == pytest.approx(2.0)
    assert some["per_run_usd"] == pytest.approx(0.5)
    assert some["n_runs_with_usage"] == 4


def test_pct_keeps_null_percentiles_and_counts_n() -> None:
    assert pct(None, None, 0) == {"p50": None, "p95": None, "n": 0}
    assert pct(12.345, 99.99, 3) == {"p50": 12.3, "p95": 100.0, "n": 3}


# --- cursor ----------------------------------------------------------------------------------


def test_cursor_round_trips() -> None:
    stamp = datetime(2026, 10, 6, 23, 6, 18, 178123, tzinfo=UTC)
    run_id = uuid.uuid4()
    assert decode_cursor(encode_cursor(stamp, run_id)) == (stamp, run_id)


@pytest.mark.parametrize("bad", ["", "not-a-cursor", "@@@", "MjAyNi0xMC0wNnxub3QtdXVpZA"])
def test_malformed_cursors_raise_value_error(bad: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - every malformed shape is a ValueError
        decode_cursor(bad)


def test_naive_cursor_timestamp_is_rejected() -> None:
    naive = encode_cursor(datetime(2026, 1, 1), uuid.uuid4())
    with pytest.raises(ValueError, match="timezone"):
        decode_cursor(naive)


# --- allowlisted views -----------------------------------------------------------------------


def test_agent_view_drops_trace_and_unknown_keys() -> None:
    stored = {
        "stop_reason": "finish_research",
        "steps": 3,
        "trace": [{"tool": "search_evidence", "args": {"query": "q"}}],
        "trace_redacted": True,
        "thinking": "never stored, never served",
        "states": ["INIT", "DONE"],
        "usage": {"input_tokens": 10},
    }
    view = agent_view(stored)
    assert view == {
        "stop_reason": "finish_research",
        "steps": 3,
        "usage": {"input_tokens": 10},
        "states": ["INIT", "DONE"],
    }
    assert agent_view({}) is None
    assert agent_view(None) is None
    assert agent_view({"steps": 1})["states"] == []  # type: ignore[index]


def test_route_and_numeric_views_are_allowlists() -> None:
    assert route_view({"reason": "auto_cues", "cues": ["share"], "other": 1}) == {
        "reason": "auto_cues",
        "cues": ["share"],
    }
    assert route_view({}) == {}
    assert numeric_only({"total_ms": 5.0, "attempts": 1, "flag": True, "note": "x"}) == {
        "total_ms": 5.0,
        "attempts": 1,
    }


def test_redacted_args_detection() -> None:
    assert is_redacted_args({"redacted": True})
    assert not is_redacted_args({"query": "fit", "redacted": True})
    assert not is_redacted_args({})


def test_verification_summary_keeps_reasons_not_spans() -> None:
    rejected = [{"reason": "uncited_claim", "section": "answer", "aliases": ["E1"], "span": "S"}]
    row = (2, "fallback", False, 4, ["uncited_claim"], 3, rejected, ["r-1"])
    summary = verification_summary(row)
    assert summary == {
        "attempt": 2,
        "disposition": "fallback",
        "passed": False,
        "citations": 4,
        "failure_categories": ["uncited_claim"],
        "repairs_n": 3,
        "rejected": [{"reason": "uncited_claim", "section": "answer", "aliases": ["E1"]}],
        "result_ids": ["r-1"],
    }
    sparse = verification_summary((1, "accepted", True, None, None, None, None, None))
    assert sparse["citations"] == 0
    assert sparse["rejected"] == []


# --- timeline --------------------------------------------------------------------------------


def _ev(seq: int, etype: str, t: float, /, **payload: object) -> EventRow:
    return EventRow(seq, etype, t, payload)


def test_timeline_folds_tokens_per_attempt_and_drops_text() -> None:
    events = [
        _ev(1, "run_started", 1, mode="standard", persona="generalist", route={"r": 1}),
        _ev(2, "status", 2, phase="searching", message="Searching workspace evidence"),
        _ev(3, "token", 10, attempt=1, text="secret answer text"),
        _ev(4, "citation", 11, attempt=1, handle="H", source_title="T"),
        _ev(5, "token", 12, attempt=1, text="more"),
        _ev(6, "draft_reset", 13, attempt=1, reason="verification_failed"),
        _ev(7, "token", 20, attempt=2, text="again"),
        _ev(8, "final", 30, citations=2, passed=True, content="never"),
        _ev(9, "done", 31, termination_state="completed", flags=[], timings={"x": 1}),
        _ev(10, "mystery", 32, text="unknown types are skipped"),
    ]
    timeline = build_timeline(events)
    kinds = [e["kind"] for e in timeline]
    assert kinds == [
        "run_started",
        "status",
        "tokens",
        "draft_reset",
        "tokens",
        "final",
        "done",
    ]
    first, second = (e for e in timeline if e["kind"] == "tokens")
    assert first["detail"] == {"count": 2, "citations": 1, "attempt": 1, "last_t_ms": 12}
    assert first["label"] == "Streamed 2 chunks"
    assert first["t_ms"] == 10
    assert second["detail"]["count"] == 1
    assert timeline[0]["detail"] == {"mode": "standard", "persona": "generalist"}
    assert timeline[-1]["detail"] == {"termination_state": "completed", "flags": []}
    assert timeline[-2]["detail"] == {"citations": 2, "passed": True}
    flat = repr(timeline)
    for leaked in ("secret answer text", "never", "unknown types", "source_title"):
        assert leaked not in flat


def test_timeline_tool_events_keep_audit_fields_only() -> None:
    timeline = build_timeline(
        [
            _ev(2, "tool_completed", 5, tool="search_evidence", status="ok", step=1,
                call_index=0, duration_ms=80, result_count=6, trace_id="t"),
            _ev(1, "tool_started", 1, tool="search_evidence", step=1, call_index=0,
                kind="search", summary='Searching all evidence for "fit"'),
        ]
    )  # fmt: skip
    started, completed = timeline
    assert started["label"] == 'Searching all evidence for "fit"'
    assert started["detail"] == {
        "step": 1,
        "call_index": 0,
        "tool": "search_evidence",
        "kind": "search",
    }
    assert completed["label"] == "search_evidence ok"
    assert "trace_id" not in completed["detail"]


def test_event_offset_prefers_payload_ts_and_falls_back() -> None:
    start = datetime(2026, 10, 6, 23, 0, 0, tzinfo=UTC)
    row_time = start + timedelta(seconds=5)
    assert event_offset_ms({"ts": "2026-10-06T23:00:01.250+00:00"}, row_time, start) == 1250
    assert event_offset_ms({"ts": "garbage"}, row_time, start) == 5000
    assert event_offset_ms({}, row_time, start) == 5000


# --- SQL filters -----------------------------------------------------------------------------


def test_run_where_binds_values_and_excludes_test_runs_by_default() -> None:
    where, params = run_where(RunFilters(mode="research", model="x'; DROP TABLE runs; --"), WS)
    assert "fake-llm" in where
    assert "<>" in where
    assert "DROP" not in where
    assert params == {"ws": WS, "mode": "research", "model": "x'; DROP TABLE runs; --"}


def test_run_where_optional_filters() -> None:
    since = datetime(2026, 1, 1, tzinfo=UTC)
    where, params = run_where(
        RunFilters(since=since, include_test_runs=True, degraded=False, disposition="fallback"),
        WS,
    )
    assert "fake-llm" not in where
    assert "cardinality(r.degradation_flags) = 0" in where
    assert ":disposition" in where
    assert params["since"] == since
    degraded, _ = run_where(RunFilters(degraded=True), WS)
    assert "cardinality(r.degradation_flags) > 0" in degraded
