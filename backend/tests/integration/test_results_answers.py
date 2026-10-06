# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""Computed results in grounded answers, end to end (Phase 5 B, W4a).

A research run whose scripted agent calls the real governed ``aggregate`` tool on a
harness-uploaded CSV, then ``finish_research``; synthesis (FakeLLM) cites the result as [R1].
The stored answer carries ``[[result:<id>]]`` for the persisted ``analytics_results`` row and a
result citation card; wrong numbers are dropped; an analytics-only answer works; purging the
CSV source redacts the answer and the result."""

from __future__ import annotations

import re
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.providers.llm.fake import (
    FakeAgentLLM,
    FakeLLM,
    ScriptedTurn,
    tool_use_block,
)
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_runs_api import FACT, OTHER, _ask, _install, _scoped, _seed, _stream
from tests.integration.test_runs_purge import _purge

pytestmark = pytest.mark.integration

CODE = "NPSDATA"
CSV = b"segment,nps\nGen Z,9\nGen Z,7\nMillennial,6\nMillennial,8\n"  # means: 8 and 7
RESULT_MARKER = re.compile(r"\[\[result:([0-9a-f-]{36})\]\]")
ANSWER = (
    "### Answer\nGen Z buyers average an NPS of 8 [R1]. Fit inconsistency is the top "
    "frustration for 27 percent of Gen Z buyers [E1].\n\n"
    "### Key findings\n- Millennial buyers average an NPS of 7 [R1].\n"
    "- Millennial buyers are promoters at 9 [R1].\n"  # wrong number: dropped
    "- 27 percent of Gen Z buyers name fit inconsistency as their top frustration [E1].\n"
)
ANALYTICS_ONLY = (
    "### Answer\nGen Z buyers average an NPS of 8 [R1]. Millennial buyers average 7 [R1].\n"
)


def _install_agent(h: Harness, turns: list[ScriptedTurn]) -> None:
    agent_llm = FakeAgentLLM(turns)
    app = h.client._transport.app  # type: ignore[attr-defined]
    app.state.agent_llm_provider = lambda: agent_llm


def _aggregate_turns(*, search: bool) -> list[ScriptedTurn]:
    calls: list[Any] = [
        tool_use_block(
            "call-1",
            "aggregate",
            {
                "dataset": f"{CODE}:1",
                "metrics": [{"fn": "mean", "column": "nps"}],
                "group_by": ["segment"],
            },
        )
    ]
    if search:
        calls.append(tool_use_block("call-2", "search_evidence", {"query": "fit inconsistency"}))
    return [
        ScriptedTurn(content=tuple(calls)),
        ScriptedTurn(
            content=(tool_use_block("call-3", "finish_research", {"sufficient": True, "gaps": []}),)
        ),
    ]


async def _upload_csv(h: Harness, ws: str) -> None:
    response = await h.upload(ws, "nps.csv", CSV, source_code=CODE)
    assert response.status_code in (200, 202), response.text
    await h.drain()


async def _stored_results(engine: AsyncEngine, ws: str, run_id: str) -> list[str]:
    async with engine.begin() as conn:
        await _scoped(conn, ws)
        rows = await conn.execute(
            text("SELECT id FROM analytics_results WHERE query_run_id = CAST(:r AS uuid)"),
            {"r": run_id},
        )
        return [str(r[0]) for r in rows.all()]


def _final(events: list[dict[str, Any]]) -> dict[str, Any]:
    final: dict[str, Any] = next(e["data"] for e in events if e["event"] == "final")
    return final


async def test_answer_cites_persisted_result_and_purge_redacts_it(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    fake = FakeLLM([ANSWER], repeat_last=True)
    _install(harness, fake)
    _install_agent(harness, _aggregate_turns(search=True))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    await _upload_csv(harness, ws)
    conversation, run = await _ask(
        harness, ws, "What is the average NPS by segment?", mode="research"
    )
    events = await _stream(harness, run["stream_url"])

    completed = [e["data"] for e in events if e["event"] == "tool_completed"]
    assert completed[0]["tool"] == "aggregate"
    assert completed[0]["status"] == "ok", completed[0]
    final = _final(events)
    content = final["content"]
    stored = await _stored_results(app_engine, ws, run["run_id"])
    assert RESULT_MARKER.findall(content) == [stored[0]] * 2  # Answer + one kept finding
    assert "[R1]" not in content
    assert "average an NPS of 8" in content
    assert "promoters at 9" not in content  # wrong number dropped
    assert "27 percent" in content  # the evidence citation survives alongside
    kinds = [c["kind"] for c in final["citations"]]
    assert kinds == ["result", "evidence"]
    card = final["citations"][0]
    assert card["result_id"] == stored[0]
    assert card["source_code"] == CODE
    assert card["op"] == "aggregate"
    assert final["verification"]["results_checked"] == ["R1"]
    assert any(e["data"].get("alias") == "R1" for e in events if e["event"] == "citation")
    # The model saw the computed block, never the result id.
    turn = fake.requests[0].messages[0]["content"]
    assert '<result alias="R1"' in turn
    assert stored[0] not in turn

    ok = await harness.client.get(f"/api/workspaces/{ws}/results/{stored[0]}")
    assert ok.status_code == 200

    await _purge(harness, ws, CODE)
    messages = (
        await harness.client.get(f"/api/workspaces/{ws}/conversations/{conversation}/messages")
    ).json()
    assistant = [m for m in messages if m["role"] == "assistant"][-1]
    assert "NPS of 8" not in assistant["content"]
    assert all(c["source_code"] != CODE or c.get("purged") for c in assistant["citations"])
    gone = await harness.client.get(f"/api/workspaces/{ws}/results/{stored[0]}")
    assert gone.status_code == 404


async def test_analytics_only_answer_with_empty_evidence_pack(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    _install(harness, FakeLLM([ANALYTICS_ONLY], repeat_last=True))
    _install_agent(harness, _aggregate_turns(search=False))
    ws = await harness.create_workspace()
    await _upload_csv(harness, ws)
    _, run = await _ask(harness, ws, "What is the average NPS by segment?", mode="research")
    events = await _stream(harness, run["stream_url"])

    evidence = next(e["data"] for e in events if e["event"] == "evidence")
    assert evidence["item_count"] == 0, evidence  # analytics-only: empty evidence pack
    final = _final(events)
    stored = await _stored_results(app_engine, ws, run["run_id"])
    assert stored
    assert RESULT_MARKER.findall(final["content"])[0] == stored[0]
    assert final["verification"]["passed"]
    assert final["citations"][0]["kind"] == "result"
    assert "Millennial buyers average 7" in final["content"]
    # The result's source version is frozen with the pack, so every purge guard covers it.
    run_row = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    source_handle = final["citations"][0]["handle"]
    assert source_handle in run_row["pack_handles"]


async def test_results_of_a_source_purged_before_the_freeze_never_reach_synthesis(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 5 review finding 0/19: when the freeze reports the data source as purged, its
    computed results are dropped for good: synthesis must not re-attach them from the raw list."""
    from marketsignal.runs import store as run_store

    original = run_store.freeze_pack

    async def freeze_reports_purge(*args: Any, **kwargs: Any) -> set[str]:
        gone = await original(*args, **kwargs)
        return {*gone, CODE}  # as if CODE were purged between the gather and the freeze

    monkeypatch.setattr(run_store, "freeze_pack", freeze_reports_purge)
    synth = FakeLLM([ANALYTICS_ONLY], repeat_last=True)
    _install(harness, synth)
    _install_agent(harness, _aggregate_turns(search=True))
    ws = await harness.create_workspace()
    await _upload_csv(harness, ws)
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "What is the average NPS by segment?", mode="research")
    events = await _stream(harness, run["stream_url"])
    assert events[-1]["event"] == "done"
    assert "<computed_results>" not in synth.sent_text()
    assert "SOURCE_DELETED_DURING_RUN" in events[-1]["data"]["flags"]
