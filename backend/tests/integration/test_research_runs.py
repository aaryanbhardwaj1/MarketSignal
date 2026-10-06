# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""Research mode end to end (ADR-0015, ADR-0007, ADR-0006): router → bounded agent over the
governed in-process tools → evidence pool → the shared Phase 3 tail → done.

The agent model is scripted (FakeAgentLLM) and so is synthesis (FakeLLM); the tools, the
capability token, the governance pipeline, the tool audit, the pool resolution, the pack,
the verifier and persistence are all real, as ``ms_app`` under RLS.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

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

THINKING_CANARY = "PRIVATE-REASONING-7731 the user probably wants"
PROSE_CANARY = "AGENT-PROSE-4410 here is my plan"


def _install_agent(h: Harness, turns: list[ScriptedTurn]) -> FakeAgentLLM:
    agent_llm = FakeAgentLLM(turns)
    app = h.client._transport.app  # type: ignore[attr-defined]
    app.state.agent_llm_provider = lambda: agent_llm
    return agent_llm


def _search_then_finish() -> list[ScriptedTurn]:
    return [
        ScriptedTurn(
            content=(
                thinking_block(THINKING_CANARY),
                text_block(PROSE_CANARY),
                tool_use_block("call-1", "search_evidence", {"query": "fit inconsistency"}),
                tool_use_block(
                    "call-2", "search_evidence_keyword", {"terms": ["27 percent"], "match": "all"}
                ),
            )
        ),
        ScriptedTurn(
            content=(tool_use_block("call-3", "finish_research", {"sufficient": True, "gaps": []}),)
        ),
    ]


def _types(events: list[dict[str, Any]]) -> list[str]:
    return [e["event"] for e in events]


async def test_research_run_end_to_end_with_governed_tools(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    agent_llm = _install_agent(harness, _search_then_finish())
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    _, run = await _ask(
        harness, ws, "What share of buyers name fit inconsistency?", mode="research"
    )
    events = await _stream(harness, run["stream_url"])

    # Route and progress: deterministic events only, never thinking or agent prose.
    assert events[0]["data"]["route"]["decided"] == "research"
    raw = " ".join(str(e["data"]) for e in events)
    assert "PRIVATE-REASONING" not in raw
    assert "AGENT-PROSE" not in raw
    phases = [e["data"]["phase"] for e in events if e["event"] == "status"]
    assert phases[0] == "planning"
    started = [e["data"] for e in events if e["event"] == "tool_started"]
    assert [(s["step"], s["call_index"], s["tool"]) for s in started] == [
        (1, 0, "search_evidence"),
        (1, 1, "search_evidence_keyword"),
    ]
    assert started[0]["summary"] == 'Searching all evidence for "fit inconsistency"'
    completed = [e["data"] for e in events if e["event"] == "tool_completed"]
    assert all(c["status"] == "ok" for c in completed)

    # The shared tail ran: a verified final citing only pack handles of this workspace.
    final = next(e["data"] for e in events if e["event"] == "final")
    assert final["citations"]
    assert all(c["handle"].startswith(f"{ws}/") for c in final["citations"])
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["termination_state"] == "completed"

    # The trace: route, agent record (no model text), tool audit rows under RLS.
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    agent = stored["agent"]
    assert agent["stop_reason"] == "finish_research"
    assert agent["tool_calls"] == 2
    assert stored["tool_calls"] == 2
    assert agent["states"][0] == "INIT"
    assert agent["states"][-1] == "DONE"
    assert "PRIVATE-REASONING" not in str(agent)
    assert "AGENT-PROSE" not in str(agent)
    assert set(stored["pack_handles"]) <= {h for c in agent["trace"] for h in c.get("handles", [])}
    async with app_engine.begin() as conn:
        await _scoped(conn, ws)
        rows = (
            await conn.execute(
                text(
                    "SELECT tool, status, transport, result_count, args FROM tool_runs "
                    "WHERE query_run_id = CAST(:r AS uuid) ORDER BY step, call_index"
                ),
                {"r": run["run_id"]},
            )
        ).all()
    assert [(r[0], r[1], r[2]) for r in rows] == [
        ("search_evidence", "ok", "inprocess"),
        ("search_evidence_keyword", "ok", "inprocess"),
    ]
    assert "credential" not in str([r[4] for r in rows]).lower()

    # The second agent request resent the first assistant turn unchanged (append-only).
    assert len(agent_llm.requests) == 2
    assert (
        agent_llm.requests[1].messages[1]["content"] == list(_search_then_finish()[0].content)
        or agent_llm.requests[1].messages[1]["content"] == _search_then_finish()[0].content
    )


async def test_research_token_is_revoked_once_the_run_ends(harness: Harness) -> None:
    """The capability token minted for a run stops working when the run is no longer
    running (revocation by run status, ADR-0006)."""
    from marketsignal.tools import capability
    from marketsignal.tools.contracts import ToolCall

    _install(harness, FakeLLM([GOOD], repeat_last=True))
    _install_agent(harness, _search_then_finish())
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share", mode="research")
    await _stream(harness, run["stream_url"])
    app = harness.client._transport.app  # type: ignore[attr-defined]
    ws_row = (await harness.client.get(f"/api/workspaces/{ws}")).json()
    token = capability.issue(
        harness.settings.mcp_token_key,
        run_id=run["run_id"],
        workspace_id=ws_row["id"] if "id" in ws_row else ws_row["workspace_id"],
        workspace_code=ws,
        principal="api",
        persona="generalist",
        tools=("search_evidence",),
        max_conf="restricted",
        ttl_s=60,
    )
    from marketsignal.tools.inprocess import InProcessToolTransport

    result = await InProcessToolTransport(app.state.tool_governor).call(
        ToolCall("c1", "search_evidence", {"query": "fit inconsistency"}), credential=token
    )
    assert not result.ok
    assert result.error is not None
    assert result.error.code == "UNAUTHENTICATED"


async def test_research_agent_failure_mid_run_still_answers_from_the_pool(
    harness: Harness,
) -> None:
    """A model failure after a successful search stops gathering and keeps the evidence."""
    from marketsignal.providers.llm.base import LLMUnavailableError

    _install(harness, FakeLLM([GOOD], repeat_last=True))
    _install_agent(
        harness,
        [
            ScriptedTurn(
                content=(tool_use_block("c1", "search_evidence", {"query": "fit inconsistency"}),)
            ),
            ScriptedTurn(error=LLMUnavailableError("down")),
        ],
    )
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share", mode="research")
    events = await _stream(harness, run["stream_url"])
    done = events[-1]["data"]
    assert "AGENT_LLM_UNAVAILABLE" in done["flags"]
    assert "PLANNER_UNAVAILABLE_FALLBACK" not in done["flags"]
    assert "final" in _types(events)
