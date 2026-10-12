# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""Run telemetry API (E10) end to end, as ``ms_app`` under RLS, over FakeLLM runs.

FakeLLM runs record ``models.synthesis = 'fake-llm'``, so they are test-harness runs: hidden by
default and visible with ``include_test_runs=true``. The run detail must never carry answer or
token text, rejected spans or model reasoning, and must surface purge redaction.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from marketsignal.providers.llm.fake import FakeLLM
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_research_runs import (
    PROSE_CANARY,
    THINKING_CANARY,
    _install_agent,
    _search_then_finish,
)
from tests.integration.test_runs_api import FACT, GOOD, OTHER, _ask, _install, _seed, _stream
from tests.integration.test_runs_purge import _purge

pytestmark = pytest.mark.integration

ANSWER_SENTENCE = "Fit inconsistency is the top frustration for 27 percent of Gen Z buyers"
QUESTION = "What share of Gen Z buyers name fit as their top frustration?"


async def _standard_run(h: Harness, ws: str) -> str:
    _, run = await _ask(h, ws, QUESTION, mode="standard")
    await _stream(h, run["stream_url"])
    return str(run["run_id"])


async def _research_run(h: Harness, ws: str) -> str:
    _install_agent(h, _search_then_finish())
    _, run = await _ask(h, ws, "What share of buyers name fit inconsistency?", mode="research")
    await _stream(h, run["stream_url"])
    return str(run["run_id"])


async def _get(h: Harness, path: str, **params: Any) -> Any:
    response = await h.client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


async def test_summary_counts_test_runs_only_when_included(harness: Harness) -> None:
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    await _standard_run(harness, ws)
    await _standard_run(harness, ws)
    base = f"/api/workspaces/{ws}/telemetry/summary"

    hidden = await _get(harness, base)
    assert hidden["runs"]["total"] == 0
    assert hidden["test_runs_excluded"] == 2
    assert hidden["cost"]["total_usd"] is None
    assert hidden["cost"]["n_runs_with_usage"] == 0
    assert set(hidden["latency_ms"]["stages"]) == {
        "retrieval",
        "agent",
        "pack",
        "synthesis",
        "verification",
        "first_token",
    }
    assert hidden["latency_ms"]["stages"]["retrieval"] == {"p50": None, "p95": None, "n": 0}

    shown = await _get(harness, base, include_test_runs="true")
    assert shown["test_runs_excluded"] == 0
    assert shown["runs"]["total"] == 2
    assert shown["runs"]["by_mode"] == {"standard": 2}
    assert shown["latency_ms"]["total_by_mode"]["standard"]["n"] == 2
    assert shown["latency_ms"]["stages"]["retrieval"]["n"] == 2
    assert shown["latency_ms"]["stages"]["agent"]["n"] == 0  # not recorded: never zero-filled
    assert shown["retrieval"]["n"] == 2
    assert shown["retrieval"]["candidates"]["final"]["n"] == 2
    assert shown["coverage"]["runs_with_route"] == 2
    assert shown["cost"]["basis"] == "list_prices_from_persisted_usage"
    assert shown["cost"]["prices_per_mtok"] == {
        "input": 2.0,
        "output": 10.0,
        "cache_write": 2.5,
        "cache_read": 0.2,
    }
    assert 0.0 <= shown["rates"]["degraded"] <= 1.0
    assert sum(d["n"] for d in shown["verification"]["dispositions"]) >= 2

    window = await _get(harness, base, include_test_runs="true", since="2999-01-01T00:00:00Z")
    assert window["runs"]["total"] == 0
    assert window["window"]["since"].startswith("2999-01-01")


async def test_runs_list_filters_and_keyset_pages(harness: Harness) -> None:
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    ids = {await _standard_run(harness, ws) for _ in range(3)}
    base = f"/api/workspaces/{ws}/telemetry/runs"

    assert (await _get(harness, base)) == {"items": [], "next_cursor": None}

    first = await _get(harness, base, include_test_runs="true", limit=2)
    assert len(first["items"]) == 2
    assert first["next_cursor"]
    second = await _get(
        harness, base, include_test_runs="true", limit=2, cursor=first["next_cursor"]
    )
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None
    seen = [r["id"] for r in first["items"] + second["items"]]
    assert set(seen) == ids
    assert len(seen) == 3
    stamps = [r["created_at"] for r in first["items"] + second["items"]]
    assert stamps == sorted(stamps, reverse=True)

    row = first["items"][0]
    assert row["model"] == "fake-llm"
    assert row["mode"] == "standard"
    assert row["question"] == QUESTION
    assert row["evidence_count"] >= 1
    assert isinstance(row["regenerated"], bool)

    research = await _get(harness, base, include_test_runs="true", mode="research")
    assert research["items"] == []
    by_model = await _get(harness, base, include_test_runs="true", model="fake-llm")
    assert len(by_model["items"]) == 3

    bad = await harness.client.get(base, params={"cursor": "not-a-cursor"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    too_many = await harness.client.get(base, params={"limit": 101})
    assert too_many.status_code == 422


async def test_run_detail_has_no_answer_or_token_text(harness: Harness) -> None:
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    run_id = await _standard_run(harness, ws)

    detail = await _get(harness, f"/api/workspaces/{ws}/telemetry/runs/{run_id}")
    raw = json.dumps(detail)
    assert ANSWER_SENTENCE not in raw
    assert "### Answer" not in raw
    assert detail["run"]["id"] == run_id
    assert detail["agent"] is None  # standard run: no agent record
    kinds = [e["kind"] for e in detail["timeline"]]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "done"
    assert "token" not in kinds
    assert "citation" not in kinds
    streams = [e for e in detail["timeline"] if e["kind"] == "tokens"]
    assert len(streams) == 1
    assert streams[0]["detail"]["count"] > 0
    assert streams[0]["label"] == f"Streamed {streams[0]['detail']['count']} chunks"
    assert not {"text", "content", "sections", "span"} & _keys(detail["timeline"])
    assert "span" not in _keys(detail["verification"])
    assert detail["verification"][0]["attempt"] == 1
    offsets = [e["t_ms"] for e in detail["timeline"]]
    assert offsets == sorted(offsets)
    retrieval = detail["retrieval"]
    assert retrieval is not None
    assert retrieval["lanes"]["final"] >= len(retrieval["top_final"]) > 0
    assert set(retrieval["top_final"][0]) == {"rank", "handle", "source", "lanes", "rrf"}


async def test_research_detail_never_carries_reasoning(harness: Harness) -> None:
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    run_id = await _research_run(harness, ws)

    detail = await _get(harness, f"/api/workspaces/{ws}/telemetry/runs/{run_id}")
    raw = json.dumps(detail)
    assert THINKING_CANARY not in raw
    assert PROSE_CANARY not in raw
    assert not {"thinking", "reasoning", "trace"} & _keys(detail)
    agent = detail["agent"]
    assert agent is not None
    assert agent["stop_reason"] == "finish_research"
    assert agent["states"][0] == "INIT"
    assert [(t["step"], t["tool"]) for t in detail["tools"]][:2] == [
        (1, "search_evidence"),
        (1, "search_evidence_keyword"),
    ]
    assert all(t["redacted"] is False for t in detail["tools"])

    summary = await _get(
        harness, f"/api/workspaces/{ws}/telemetry/summary", include_test_runs="true"
    )
    assert summary["coverage"]["runs_with_agent"] == 1
    tools = {t["tool"]: t for t in summary["tool_calls"]["by_tool"]}
    assert tools["search_evidence"]["n"] == 1
    assert summary["governance"]["tool_status"]["ok"] >= 2


async def test_foreign_or_unknown_run_is_not_found(harness: Harness) -> None:
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws_a = await harness.create_workspace()
    ws_b = await harness.create_workspace()
    await _seed(harness, ws_a, FACT, OTHER)
    run_id = await _standard_run(harness, ws_a)

    for ws, rid in ((ws_b, run_id), (ws_a, str(uuid.uuid4()))):
        response = await harness.client.get(f"/api/workspaces/{ws}/telemetry/runs/{rid}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RUN_NOT_FOUND"
    other = await _get(harness, f"/api/workspaces/{ws_b}/telemetry/runs", include_test_runs="true")
    assert other["items"] == []


async def test_purge_redaction_surfaces_as_redacted(harness: Harness) -> None:
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    run_id = await _research_run(harness, ws)
    await _purge(harness, ws, "MEMO")

    detail = await _get(harness, f"/api/workspaces/{ws}/telemetry/runs/{run_id}")
    assert detail["tools"], "audit rows are kept after a purge"
    assert all(t["redacted"] is True for t in detail["tools"])
    assert all(t["args"] == {"redacted": True} for t in detail["tools"])
    assert detail["verification"] == []  # reports are deleted by the purge
    assert "trace_redacted" not in (detail["agent"] or {})
    summary = await _get(
        harness, f"/api/workspaces/{ws}/telemetry/summary", include_test_runs="true"
    )
    assert summary["governance"]["redacted_tool_args"] == len(detail["tools"])
    assert summary["governance"]["redacted_messages"] >= 1
