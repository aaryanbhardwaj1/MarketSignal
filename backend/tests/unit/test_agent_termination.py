"""Every research-agent bound terminates gathering (plan §19 bounds table; ADR-0007)."""

from __future__ import annotations

import asyncio
import random

import pytest

from marketsignal.agent.state import AgentState
from marketsignal.providers.llm.base import AgentLLMRequest, LLMUnavailableError
from marketsignal.providers.llm.fake import FakeAgentLLM, ScriptedTurn, text_block, tool_use_block
from marketsignal.tools.contracts import ToolCall, ToolResult
from tests.unit.test_agent_support import (
    CREDENTIAL,
    FakeTransport,
    ManualClock,
    Sink,
    err,
    finish,
    hit,
    make_agent,
    make_ctx,
    ok,
    search,
    turn,
    usage,
)

S = AgentState


async def test_finish_research_ends_gathering_with_pool_and_gaps() -> None:
    llm = FakeAgentLLM(
        [turn(search("a", "fit complaints")), turn(finish(gaps=["no pricing data"]))]
    )
    agent, transport = make_agent(llm)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "finish_research"
    assert out.flags == ()
    assert (out.sufficient, out.gaps) == (True, ("no pricing data",))
    assert out.steps == 2
    assert out.tool_calls == 1
    assert llm.calls == 2
    assert len(out.pool) == 2
    assert out.states == (S.INIT, S.AGENT_STEP, S.EXECUTE, S.OBSERVE, S.AGENT_STEP, S.DONE)
    assert transport.calls[0][1] == CREDENTIAL


async def test_finish_alongside_calls_executes_them_then_stops() -> None:
    llm = FakeAgentLLM([turn(search("a", "fit"), finish(sufficient=False))])
    agent, transport = make_agent(llm)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "finish_research"
    assert out.sufficient is False
    assert len(transport.calls) == 1
    assert len(out.pool) == 2
    assert all(c.name != "finish_research" for c, _ in transport.calls)  # harness-local


async def test_end_turn_after_search_discards_prose() -> None:
    llm = FakeAgentLLM([turn(search("a", "fit")), turn(text_block("Here is my answer"))])
    agent, _ = make_agent(llm)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "end_turn"
    assert "Here is my answer" not in repr(out)


@pytest.mark.parametrize("script", [[turn(text_block("prose"))], [turn(finish())]])
async def test_no_successful_search_falls_back(script: list[ScriptedTurn]) -> None:
    agent, _ = make_agent(FakeAgentLLM(script))
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "no_successful_search"
    assert out.flags == ("PLANNER_NO_TOOL_FALLBACK",)


async def test_step_limit() -> None:
    llm = FakeAgentLLM(lambda req, i: turn(search(f"c{i}", f"query number {i}")))
    agent, _ = make_agent(llm, step_limit=3)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "step_limit"
    assert llm.calls == 3
    assert out.steps == 3
    assert out.flags == ("AGENT_STEP_BUDGET_EXHAUSTED",)


async def test_tool_call_limit_denies_excess_parallel_calls_without_running_them() -> None:
    blocks = [search(f"c{i}", f"query {i}") for i in range(5)]
    llm = FakeAgentLLM([turn(*blocks), turn(finish())])
    sink = Sink()
    agent, transport = make_agent(llm, max_tool_calls=3)
    out = await agent.gather(make_ctx(sink))
    assert out.stop_reason == "tool_limit"
    assert out.flags == ("AGENT_STEP_BUDGET_EXHAUSTED",)
    assert len(transport.calls) == 3
    assert out.tool_calls == 3
    assert llm.calls == 1
    assert [t["status"] for t in out.trace] == ["ok", "ok", "ok", "denied", "denied"]
    assert [t["error_code"] for t in out.trace][3:] == ["POLICY_DENIED", "POLICY_DENIED"]
    assert [e["status"] for e in sink.named("tool_completed")][3:] == ["denied", "denied"]


async def test_tool_limit_denials_are_sent_to_the_model_when_budget_runs_out_mid_run() -> None:
    llm = FakeAgentLLM(
        [
            turn(search("a", "one"), search("b", "two")),
            turn(search("c", "three"), search("d", "four")),
            turn(finish()),
        ]
    )
    agent, transport = make_agent(llm, max_tool_calls=3)
    out = await agent.gather(make_ctx())
    assert len(transport.calls) == 3
    assert out.stop_reason == "tool_limit"


async def test_token_budget() -> None:
    llm = FakeAgentLLM(lambda req, i: turn(search(f"c{i}", f"q {i}"), usage=usage(out=600)))
    agent, _ = make_agent(llm, max_output_tokens_total=1000)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "token_limit"
    assert llm.calls == 2
    assert out.flags == ("AGENT_TOKEN_BUDGET_EXHAUSTED",)
    assert out.usage["output_tokens"] == 1200


async def test_max_tokens_stop_reason_stops_without_running_truncated_calls() -> None:
    llm = FakeAgentLLM([turn(search("a", "q"), stop_reason="max_tokens")])
    agent, transport = make_agent(llm)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "token_limit"
    assert transport.calls == []


async def test_context_limit_stops_without_editing_history() -> None:
    llm = FakeAgentLLM(
        lambda req, i: turn(search(f"c{i}", f"q {i}"), usage=usage(inp=3000 * (i + 1)))
    )
    agent, _ = make_agent(llm, max_context_tokens=5000)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "context_limit"
    assert llm.calls == 2
    assert out.flags == ("AGENT_CONTEXT_LIMIT",)


async def test_elapsed_time_limit_uses_the_injected_clock() -> None:
    clock = ManualClock()

    def tick(call: ToolCall) -> ToolResult:
        clock.now += 20
        return ok(call, {"hits": [hit(len(call.call_id))], "classes_found": {}})

    llm = FakeAgentLLM(lambda req, i: turn(search(f"c{i}", f"q {i}")))
    agent, _ = make_agent(llm, FakeTransport(handler=tick), clock=clock, gather_budget_s=35)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "time_limit"
    assert out.flags == ("GATHER_TIMEOUT",)
    assert llm.calls == 2
    assert len(out.pool) >= 1


async def test_ctx_deadline_already_passed_makes_no_model_call() -> None:
    clock = ManualClock(start=500.0)
    llm = FakeAgentLLM([])
    agent, _ = make_agent(llm, clock=clock)
    out = await agent.gather(make_ctx(deadline=499.0))
    assert out.stop_reason == "time_limit"
    assert llm.calls == 0


async def test_slow_tool_times_out_and_counts_as_error() -> None:
    llm = FakeAgentLLM([turn(search("a", "q")), turn(finish())])
    agent, transport = make_agent(llm, FakeTransport(delay_s=5), tool_timeout_s=0.05)
    out = await agent.gather(make_ctx())
    assert out.trace[0]["status"] == "timeout"
    assert out.trace[0]["error_code"] == "TIMEOUT"
    assert out.tool_errors == 1
    assert transport.cancelled == 1


async def test_repeat_call_second_repeat_stops() -> None:
    llm = FakeAgentLLM(lambda req, i: turn(search(f"c{i}", "fit", top_k=5)))
    agent, transport = make_agent(llm)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "repeat_call"
    assert out.flags == ("AGENT_REPEAT_CALL_STOPPED",)
    assert llm.calls == 3
    assert len(transport.calls) == 1
    assert [t["status"] for t in out.trace] == ["ok", "denied"]


async def test_repeat_detection_uses_canonical_argument_order() -> None:
    a = tool_use_block("a", "search_evidence", {"query": "fit", "top_k": 3})
    b = tool_use_block("b", "search_evidence", {"top_k": 3, "query": "fit"})
    c = tool_use_block("c", "search_evidence", {"top_k": 3, "query": "fit"})
    agent, transport = make_agent(FakeAgentLLM([turn(a, b, c)]))
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "repeat_call"
    assert transport.calls == []


async def test_consecutive_tool_errors_open_the_circuit() -> None:
    llm = FakeAgentLLM(lambda req, i: turn(search(f"c{i}", f"q {i}")))
    agent, _ = make_agent(
        llm, FakeTransport(handler=lambda c: err(c)), max_consecutive_tool_errors=3
    )
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "tool_errors"
    assert out.flags == ("TOOL_CIRCUIT_OPEN",)
    assert llm.calls == 3
    assert out.tool_errors == 3
    assert out.pool == ()


async def test_success_resets_the_error_streak() -> None:
    results = iter([False, False, True, False, False])
    llm = FakeAgentLLM(lambda req, i: turn(search(f"c{i}", f"q {i}")) if i < 5 else turn(finish()))
    handler = lambda c: search_or_err(c, next(results))  # noqa: E731
    agent, _ = make_agent(
        llm, FakeTransport(handler=handler), step_limit=10, max_consecutive_tool_errors=3
    )
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "finish_research"
    assert out.tool_errors == 4


def search_or_err(call: ToolCall, good: bool) -> ToolResult:
    return ok(call, {"hits": [hit(9)], "classes_found": {}}) if good else err(call)


async def test_pool_full_stops_gathering() -> None:
    def many(call: ToolCall) -> ToolResult:
        n = int(call.call_id[1:]) * 10
        return ok(call, {"hits": [hit(n + k, rank=k + 1) for k in range(4)], "classes_found": {}})

    llm = FakeAgentLLM(lambda req, i: turn(search(f"c{i}", f"q {i}")))
    agent, _ = make_agent(llm, FakeTransport(handler=many), pool_max=6)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "pool_full"
    assert len(out.pool) == 6
    assert llm.calls == 2


async def test_purged_evidence_is_removed_from_the_pool() -> None:
    gone = hit(1)["handle"]

    def handler(call: ToolCall) -> ToolResult:
        if call.name == "get_evidence":
            items = [
                {"handle": gone, "found": False, "miss_reason": "SOURCE_DELETED"},
                {"handle": hit(2)["handle"], "found": True, "source_class": "customer"},
            ]
            return ok(call, {"items": items})
        return ok(call, {"hits": [hit(1), hit(2, rank=2)], "classes_found": {}})

    get = tool_use_block("g", "get_evidence", {"handles": [gone, hit(2)["handle"]]})
    llm = FakeAgentLLM([turn(search("a", "fit")), turn(get), turn(finish())])
    agent, _ = make_agent(llm, FakeTransport(handler=handler))
    out = await agent.gather(make_ctx())
    assert [p.handle for p in out.pool] == [hit(2)["handle"]]


async def test_not_found_tool_errors_count_toward_the_circuit() -> None:
    llm = FakeAgentLLM(
        lambda req, i: turn(
            tool_use_block(f"g{i}", "get_evidence", {"handles": [f"acme/X@v1:S{i}"]})
        )
    )
    agent, _ = make_agent(
        llm, FakeTransport(handler=lambda c: err(c, "NOT_FOUND")), max_consecutive_tool_errors=2
    )
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "tool_errors"


async def test_first_llm_failure_is_planner_unavailable() -> None:
    llm = FakeAgentLLM([ScriptedTurn(error=LLMUnavailableError("down"))])
    agent, transport = make_agent(llm)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "planner_unavailable"
    assert out.flags == ("PLANNER_UNAVAILABLE_FALLBACK",)
    assert transport.calls == []
    assert out.pool == ()


async def test_tool_listing_failure_is_planner_unavailable() -> None:
    class Broken(FakeTransport):
        async def list_tools(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    llm = FakeAgentLLM([])
    agent, _ = make_agent(llm, Broken())
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "planner_unavailable"
    assert llm.calls == 0


async def test_later_llm_failure_keeps_the_pool() -> None:
    llm = FakeAgentLLM([turn(search("a", "fit")), ScriptedTurn(error=LLMUnavailableError("down"))])
    agent, _ = make_agent(llm)
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "llm_unavailable"
    assert out.flags == ("AGENT_LLM_UNAVAILABLE",)
    assert len(out.pool) == 2


async def test_later_llm_failure_without_evidence_falls_back() -> None:
    llm = FakeAgentLLM([turn(search("a", "fit")), ScriptedTurn(error=TimeoutError())])
    agent, _ = make_agent(llm, FakeTransport(handler=lambda c: err(c)))
    out = await agent.gather(make_ctx())
    assert out.stop_reason == "no_successful_search"


async def test_cancellation_propagates_and_cancels_running_tools() -> None:
    llm = FakeAgentLLM([turn(search("a", "one"), search("b", "two"))])
    agent, transport = make_agent(llm, FakeTransport(delay_s=10))
    task = asyncio.create_task(agent.gather(make_ctx()))
    while transport.running < 2:  # noqa: ASYNC110 - polling a fake's counter
        await asyncio.sleep(0.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.running == 0
    assert transport.cancelled == 2


async def test_cancellation_during_model_call_propagates() -> None:
    llm = FakeAgentLLM([ScriptedTurn(delay_s=10)])
    agent, _ = make_agent(llm)
    task = asyncio.create_task(agent.gather(make_ctx()))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize("seed", range(150))
async def test_random_scripts_always_terminate_within_the_step_limit(seed: int) -> None:
    rng = random.Random(seed)  # noqa: S311 - deterministic test data
    names = [
        "search_evidence",
        "search_evidence_keyword",
        "get_evidence",
        "list_sources",
        "finish_research",
        "bogus",
    ]

    def respond(req: AgentLLMRequest, i: int) -> ScriptedTurn:
        if rng.random() < 0.05:
            return ScriptedTurn(error=LLMUnavailableError("x"))
        blocks = [
            tool_use_block(
                f"t{i}_{k}", rng.choice(names), {"query": rng.choice(["a b", "c d", "e f"])}
            )
            for k in range(rng.randint(0, 6))
        ]
        if rng.random() < 0.2:
            blocks.append(text_block("prose"))
        return ScriptedTurn(
            content=tuple(blocks), usage=usage(inp=rng.randint(1, 20_000), out=rng.randint(1, 5000))
        )

    def handler(call: ToolCall) -> ToolResult:
        return (
            ok(call, {"hits": [hit(rng.randint(1, 80))], "classes_found": {}})
            if rng.random() < 0.6
            else err(call)
        )

    step_limit = rng.randint(1, 6)
    llm = FakeAgentLLM(respond)
    agent, _ = make_agent(
        llm,
        FakeTransport(handler=handler),
        step_limit=step_limit,
        max_tool_calls=rng.randint(1, 12),
    )
    out = await asyncio.wait_for(agent.gather(make_ctx()), 5)
    assert llm.calls <= step_limit
    assert out.steps == llm.calls
    assert out.states[-1] is S.DONE


async def test_hung_model_call_is_bounded_by_the_deadline() -> None:
    clock = ManualClock(start=1000.0)
    llm = FakeAgentLLM([ScriptedTurn(delay_s=30)])
    agent, _ = make_agent(llm, clock=clock)
    out = await asyncio.wait_for(agent.gather(make_ctx(deadline=1000.1)), 5)
    assert out.stop_reason == "planner_unavailable"
    assert out.usage["llm_attempts"] == 1
