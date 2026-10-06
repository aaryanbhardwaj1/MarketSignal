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


# ------------------------------------------------------------- review hardening (sec-H)


def _first_user_message(agent_llm: FakeAgentLLM) -> str:
    return str(agent_llm.requests[0].messages[0]["content"])


async def test_research_honours_the_runs_source_classes(harness: Harness) -> None:
    """H-0/H-19: a run scoped to ['customer'] never packs or cites another class, even when the
    agent asks the tools for other classes; the agent is told the scope."""
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    agent_llm = _install_agent(
        harness,
        [
            ScriptedTurn(
                content=(
                    tool_use_block("c1", "search_evidence", {"query": "fit inconsistency"}),
                    tool_use_block(
                        "c2",
                        "search_evidence",
                        {"query": "fit inconsistency buyers", "source_classes": ["market"]},
                    ),
                )
            ),
            ScriptedTurn(
                content=(tool_use_block("f", "finish_research", {"sufficient": True, "gaps": []}),)
            ),
        ],
    )
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, code="MEMO")  # customer (the harness default)
    await _seed(harness, ws, FACT, OTHER, code="MKT", source_class="market")
    _, run = await _ask(
        harness, ws, "fit inconsistency share", mode="research", source_classes=["customer"]
    )
    events = await _stream(harness, run["stream_url"])
    assert "<source_scope>customer</source_scope>" in _first_user_message(agent_llm)
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["pack_handles"]
    assert all(h.startswith(f"{ws}/MEMO@") for h in stored["pack_handles"])
    assert "MKT" not in str([e["data"] for e in events if e["event"] == "evidence"])
    final = next(e["data"] for e in events if e["event"] == "final")
    assert all(c["handle"].startswith(f"{ws}/MEMO@") for c in final["citations"])


async def test_research_fallback_gets_only_the_remaining_gather_time(harness: Harness) -> None:
    """H-7: one gather deadline for the whole run. A planner that hangs past it leaves the
    standard fallback no time: RETRIEVAL_TIMEOUT, not a fresh budget and a run timeout."""
    import time

    harness.settings.run_gather_budget_s = 1.0
    harness.settings.agent_gather_budget_s = 1.0
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    _install_agent(harness, [ScriptedTurn(content=(), delay_s=5.0)])
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    t0 = time.monotonic()
    _, run = await _ask(harness, ws, "fit inconsistency share", mode="research")
    events = await _stream(harness, run["stream_url"])
    done = events[-1]["data"]
    assert "PLANNER_UNAVAILABLE_FALLBACK" in done["flags"]
    assert "RETRIEVAL_TIMEOUT" in done["flags"]
    assert done["termination_state"] != "timeout"
    assert time.monotonic() - t0 < 10


async def test_research_empty_handed_bound_stop_runs_the_standard_gather(
    harness: Harness,
) -> None:
    """H-8: the agent stops on a bound (repeat) without one successful search; the standard
    gather still answers, and both flags are reported."""
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    _install_agent(
        harness,
        [ScriptedTurn(content=(tool_use_block(f"l{i}", "list_sources", {}),)) for i in range(3)],
    )
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share", mode="research")
    events = await _stream(harness, run["stream_url"])
    done = events[-1]["data"]
    assert "AGENT_REPEAT_CALL_STOPPED" in done["flags"]
    assert "PLANNER_NO_TOOL_FALLBACK" in done["flags"]
    final = next(e["data"] for e in events if e["event"] == "final")
    assert final["citations"]


async def test_research_with_an_unbuildable_provider_falls_back(harness: Harness) -> None:
    """H-20: provider construction fails (e.g. no key): research degrades to the standard
    gather (PLANNER_UNAVAILABLE_FALLBACK) instead of failing the run."""
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    app = harness.client._transport.app  # type: ignore[attr-defined]

    def broken() -> Any:
        raise ValueError("provider key missing (synthetic)")

    app.state.llm_provider = broken
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share", mode="research")
    events = await _stream(harness, run["stream_url"])
    done = events[-1]["data"]
    assert "PLANNER_UNAVAILABLE_FALLBACK" in done["flags"]
    assert done["termination_state"] != "tool_failure"
    assert "evidence" in _types(events)


async def test_agent_record_written_after_a_purge_drops_the_trace(harness: Harness) -> None:
    """Finding 18 (late write): a purge of a source the agent's tools returned, landing while
    the agent is still gathering, leaves a stored agent record without the per-call trace."""
    from marketsignal.providers.llm.base import AgentLLMRequest, AgentTurn
    from tests.integration.test_runs_purge import _purge

    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    inner = FakeAgentLLM(_search_then_finish())

    class PurgeBeforeStep2:
        model_id = "fake-agent-llm"

        async def step(self, request: AgentLLMRequest) -> AgentTurn:
            if len(inner.requests) == 1:  # the search ran and returned MEMO handles
                await _purge(harness, ws, "MEMO")
            return await inner.step(request)

    app = harness.client._transport.app  # type: ignore[attr-defined]
    app.state.agent_llm_provider = lambda: PurgeBeforeStep2()
    _, run = await _ask(harness, ws, "fit inconsistency share", mode="research")
    await _stream(harness, run["stream_url"])
    agent = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()["agent"]
    assert agent["trace_redacted"] is True
    assert "trace" not in agent
    assert agent["tool_calls"] == 2
    assert agent["stop_reason"] == "finish_research"


async def test_unreachable_mcp_endpoint_still_answers(harness: Harness) -> None:
    """H-21: tools_transport=http with nothing listening must not turn research into a
    TOOL_CIRCUIT_OPEN abstention: calls are re-run in process, flagged TOOLS_TRANSPORT_FALLBACK
    once per run."""
    harness.settings.tools_transport = "http"
    harness.settings.mcp_base_url = "http://127.0.0.1:9"  # discard port: nothing listens
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    _install_agent(harness, _search_then_finish())
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share", mode="research")
    events = await _stream(harness, run["stream_url"])
    done = events[-1]["data"]
    assert "TOOL_CIRCUIT_OPEN" not in done["flags"]
    assert done["flags"].count("TOOLS_TRANSPORT_FALLBACK") == 1
    final = next(e["data"] for e in events if e["event"] == "final")
    assert final["citations"]


# ------------------------------------------------- Phase 5 A3: research summary hand-off

GAP_CANARY = "GAP-CANARY-8812 the agent thinks the board deck has it"


def _search_then_finish_with_gap() -> list[ScriptedTurn]:
    return [
        ScriptedTurn(
            content=(
                thinking_block(THINKING_CANARY),
                tool_use_block("c1", "search_evidence", {"query": "fit inconsistency"}),
            )
        ),
        ScriptedTurn(
            content=(
                tool_use_block(
                    "c2", "finish_research", {"sufficient": False, "gaps": [GAP_CANARY]}
                ),
            )
        ),
    ]


def _synthesis_turn(fake: FakeLLM) -> str:
    assert fake.requests, "synthesis was never called"
    return str(fake.requests[0].messages[0]["content"])


QUESTION_A3 = "What share of Gen Z buyers name fit inconsistency, versus store traffic in 2025?"


async def test_research_synthesis_receives_the_research_summary(harness: Harness) -> None:
    fake = FakeLLM([GOOD], repeat_last=True)
    _install(harness, fake)
    _install_agent(harness, _search_then_finish_with_gap())
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    _, run = await _ask(harness, ws, QUESTION_A3, mode="research")
    events = await _stream(harness, run["stream_url"])
    assert events[-1]["event"] == "done"

    turn = _synthesis_turn(fake)
    assert turn.count("<research_summary>") == 1
    element = turn[turn.index("<research_summary>") : turn.index("</research_summary>")]
    assert "server-written data, not instructions" in element
    assert "evidence judged sufficient: no" in element
    assert "search_evidence 1 (1 ok)" in element
    assert "&quot;fit inconsistency&quot;" in element  # the search theme, escaped
    assert "Gen Z (items: E1)" in element  # bound to the final pack's aliases
    assert "share (items: none)" in element  # FACT says "27 percent", never "share"
    assert "missing): share; 2025" in element  # deterministic unresolved terms
    assert "versus" in element
    assert "Agent-reported gaps: 1 (text withheld)" in element
    # Never model prose, thinking, gap text, handles or source codes.
    assert "GAP-CANARY" not in turn
    assert "PRIVATE-REASONING" not in turn
    assert f"{ws}/" not in element
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["timings"]["research_summary_chars"] > 0


async def test_research_summary_switch_off_and_standard_runs_omit_it(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)

    fake = FakeLLM([GOOD], repeat_last=True)
    _install(harness, fake)
    _, run = await _ask(harness, ws, QUESTION_A3, mode="standard")
    await _stream(harness, run["stream_url"])
    assert "<research_summary>" not in _synthesis_turn(fake)

    monkeypatch.setattr(harness.settings, "research_summary", False)
    off = FakeLLM([GOOD], repeat_last=True)
    _install(harness, off)
    _install_agent(harness, _search_then_finish_with_gap())
    _, run = await _ask(harness, ws, QUESTION_A3, mode="research")
    events = await _stream(harness, run["stream_url"])
    assert events[-1]["event"] == "done"
    assert "<research_summary>" not in _synthesis_turn(off)
