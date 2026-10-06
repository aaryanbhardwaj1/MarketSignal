# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""A mixed research run end to end (Phase 5 B): the scripted agent describes an uploaded CSV,
computes over it with the governed analytics tools, then searches evidence and finishes.

Real: the run API, the capability token, the governed tools, analytics persistence, the agent
runtime and the progress events. Scripted: the agent model (FakeAgentLLM) and synthesis
(FakeLLM)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.agent.runtime import AgentContext, AgentOutcome, ResearchAgent
from marketsignal.providers.llm.fake import (
    FakeAgentLLM,
    FakeLLM,
    ScriptedTurn,
    text_block,
    thinking_block,
    tool_use_block,
)
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_runs_api import (
    FACT,
    GOOD,
    OTHER,
    _ask,
    _install,
    _scoped,
    _seed,
    _stream,
)

pytestmark = pytest.mark.integration

THINKING_CANARY = "PRIVATE-REASONING-5521 compute first"
PROSE_CANARY = "AGENT-PROSE-8812 the north region wins"
SURVEY = (
    "respondent,segment,region,nps\n"
    "R1,Gen Z,North,9\n"
    "R2,Gen Z,South,6\n"
    "R3,Millennial,North,10\n"
    "R4,Millennial,South,\n"
    "R5,Gen X,North,7\n"
)
AGGREGATE = {
    "dataset": "SURV:1",
    "metrics": [{"fn": "mean", "column": "nps"}, {"fn": "count"}],
    "group_by": ["region"],
}


def _script() -> list[ScriptedTurn]:
    return [
        ScriptedTurn(
            content=(
                thinking_block(THINKING_CANARY),
                text_block(PROSE_CANARY),
                tool_use_block("c1", "describe_dataset", {}),
            )
        ),
        ScriptedTurn(content=(tool_use_block("c2", "aggregate", AGGREGATE),)),
        ScriptedTurn(
            content=(tool_use_block("c3", "search_evidence", {"query": "fit inconsistency"}),)
        ),
        ScriptedTurn(
            content=(tool_use_block("c4", "finish_research", {"sufficient": True, "gaps": []}),)
        ),
    ]


async def test_agent_computes_then_searches_and_hands_results_over(
    harness: Harness, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    agent_llm = FakeAgentLLM(_script())
    app = harness.client._transport.app  # type: ignore[attr-defined]
    app.state.agent_llm_provider = lambda: agent_llm
    outcomes: list[AgentOutcome] = []
    gather = ResearchAgent.gather

    async def capture(self: ResearchAgent, ctx: AgentContext) -> AgentOutcome:
        outcome = await gather(self, ctx)
        outcomes.append(outcome)
        return outcome

    monkeypatch.setattr(ResearchAgent, "gather", capture)
    ws = await harness.create_workspace()
    uploaded = await harness.upload(ws, "survey.csv", SURVEY.encode(), source_code="SURV")
    assert uploaded.status_code in (200, 202), uploaded.text
    await _seed(harness, ws, FACT, OTHER)
    _, run = await _ask(harness, ws, "What is the average NPS by region, and why?", mode="research")
    events = await _stream(harness, run["stream_url"])

    # Progress: deterministic analytics templates; never thinking or agent prose.
    raw = json.dumps([e["data"] for e in events])
    assert "PRIVATE-REASONING" not in raw
    assert "AGENT-PROSE" not in raw
    started = [e["data"] for e in events if e["event"] == "tool_started"]
    assert [(s["tool"], s["kind"], s["summary"]) for s in started] == [
        ("describe_dataset", "analytics", "Describing datasets"),
        ("aggregate", "analytics", "Computing mean(nps), count by region on SURV:1"),
        ("search_evidence", "search", 'Searching all evidence for "fit inconsistency"'),
    ]
    completed = [e["data"] for e in events if e["event"] == "tool_completed"]
    assert [c["status"] for c in completed] == ["ok", "ok", "ok"]
    assert completed[1]["result_count"] == 2  # North, South
    assert events[-1]["event"] == "done"

    # The hand-off: exactly the persisted analytics_results row, under this run.
    [outcome] = outcomes
    assert outcome.stop_reason == "finish_research"
    assert len(outcome.results) == 1
    result = outcome.results[0]
    assert result["operation"] == "aggregate"
    north = result["rows"][0]
    assert north["group"] == {"region": "North"}
    assert [m["value"] for m in north["metrics"]] == [8.67, 3]
    async with app_engine.begin() as conn:
        await _scoped(conn, ws)
        stored = (
            await conn.execute(
                text(
                    "SELECT id::text, tool, result FROM analytics_results "
                    "WHERE query_run_id = CAST(:r AS uuid)"
                ),
                {"r": run["run_id"]},
            )
        ).all()
    assert len(stored) == 1
    row_id, tool, persisted = stored[0]
    persisted_dict: dict[str, Any] = (
        json.loads(persisted) if isinstance(persisted, str) else persisted
    )
    assert (row_id, tool) == (result["result_id"], "aggregate")
    assert persisted_dict == result

    # The stored agent record carries no model text either.
    run_row = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    agent = run_row["agent"]
    assert [t["tool"] for t in agent["trace"]] == [
        "describe_dataset",
        "aggregate",
        "search_evidence",
    ]
    assert "PRIVATE-REASONING" not in str(agent)
    assert "AGENT-PROSE" not in str(agent)
