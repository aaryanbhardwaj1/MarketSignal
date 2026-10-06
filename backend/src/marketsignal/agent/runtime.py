"""The bounded research agent: the agent <-> executor boundary (plan §19; ADR-0007).

``ResearchAgent.gather`` runs the state machine in ``agent/state.py`` and returns an
:class:`AgentOutcome` with the evidence pool (handles only). It never raises for model or tool
failures; ``CancelledError`` propagates (running tool calls are cancelled with it).

Privacy: model thinking and prose stay inside the in-memory transcript. Progress events,
the outcome, the trace and logs are built only from validated tool arguments, tool status and
counters. ``finish_research`` gaps are bounded plain strings and are the one model-written
field in the outcome (by contract).

Pool order (``AgentOutcome.pool``): best fused rank first, then first step, then first-seen
order (see ``agent/pool.py``).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from marketsignal.agent.execute import CallRecord, Decision, PlannedCall, execute, to_call
from marketsignal.agent.pool import EvidencePool, PoolItem
from marketsignal.agent.progress import (
    STATUS_PLANNING,
    STATUS_SEARCHING,
    tool_completed,
    tool_label,
    tool_started,
    validated_args,
)
from marketsignal.agent.prompts import (
    FINISH_RESEARCH_SPEC,
    FINISH_TOOL,
    RESEARCH_SYSTEM_PROMPT,
    error_observation,
    parse_finish,
    research_user_message,
    wrap_observation,
)
from marketsignal.agent.state import (
    STOP_FLAGS,
    AgentBounds,
    AgentState,
    Progress,
    StateMachine,
    StopReason,
    canonical_call_key,
    check_bounds,
)
from marketsignal.agent.transcript import ToolResultBlock, Transcript
from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.providers.llm.base import AgentLLM, AgentLLMRequest, AgentTurn, ToolUse
from marketsignal.telemetry.logging import get_logger
from marketsignal.tools.contracts import ToolTransport

__all__ = ["AgentContext", "AgentOutcome", "PoolItem", "ResearchAgent"]

log = get_logger(__name__)

CHARS_PER_TOKEN = 4
LLM_GRACE_S = 0.5  # lets the provider raise its own timeout before the backstop fires
EVIDENCE_TOOLS = frozenset({"search_evidence", "search_evidence_keyword", "get_evidence"})
GONE = frozenset({"NOT_FOUND", "SOURCE_DELETED"})
# Exits that mean "the model chose to stop": with zero successful searches they become
# ``no_successful_search`` so the executor runs the deterministic standard gather instead.
_FALLBACK_EXITS = frozenset({"end_turn", "finish_research", "llm_unavailable"})

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class AgentContext:
    run_id: uuid.UUID
    scope: WorkspaceScope
    question: str
    persona: str
    conversation_summary: str
    recent_questions: tuple[str, ...]
    credential: str  # capability token; never logged
    deadline: float  # time.monotonic() deadline for gathering
    emit: Emit  # progress sink -> SSE (status / tool_started / tool_completed only)

    def __repr__(self) -> str:  # keep the credential and question out of reprs/logs
        return f"AgentContext(run_id={self.run_id}, workspace={self.scope.workspace_code!r})"


@dataclass(frozen=True)
class AgentOutcome:
    pool: tuple[PoolItem, ...]
    stop_reason: StopReason
    flags: tuple[str, ...]
    steps: int
    tool_calls: int  # executed calls (denied ones excluded)
    tool_errors: int
    usage: dict[str, int]
    trace: tuple[dict[str, Any], ...]
    sufficient: bool | None
    gaps: tuple[str, ...]
    states: tuple[AgentState, ...] = ()  # the state history, for tests and the trace


class ResearchAgent:
    def __init__(
        self,
        *,
        llm: AgentLLM,
        transport: ToolTransport,
        settings: Settings | None = None,
        bounds: AgentBounds | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if bounds is None:
            if settings is None:
                raise ValueError("ResearchAgent needs settings or bounds")
            bounds = AgentBounds.from_settings(settings)
        self._llm = llm
        self._transport = transport
        self._bounds = bounds
        self._clock = clock

    async def gather(self, ctx: AgentContext) -> AgentOutcome:
        return await _GatherRun(self._llm, self._transport, self._bounds, self._clock, ctx).run()


class _GatherRun:
    """Mutable state of one ``gather`` call (never shared between runs)."""

    def __init__(
        self,
        llm: AgentLLM,
        transport: ToolTransport,
        bounds: AgentBounds,
        clock: Callable[[], float],
        ctx: AgentContext,
    ) -> None:
        self.llm, self.transport, self.bounds, self.clock, self.ctx = (
            llm,
            transport,
            bounds,
            clock,
            ctx,
        )
        self.deadline = min(ctx.deadline, clock() + bounds.gather_budget_s)
        self.sm = StateMachine()
        self.pool = EvidencePool(bounds.pool_max)
        self.transcript = Transcript(
            research_user_message(
                question=ctx.question,
                persona=ctx.persona,
                conversation_summary=ctx.conversation_summary,
                recent_questions=ctx.recent_questions,
            )
        )
        self.steps = 0
        self.tool_calls = 0
        self.tool_errors = 0
        self.consecutive_errors = 0
        self.successful_searches = 0
        self.output_tokens = 0
        self.context_tokens = 0
        self.usage: Counter[str] = Counter()
        self.call_counts: Counter[str] = Counter()
        self.trace: list[dict[str, Any]] = []
        self.sufficient: bool | None = None
        self.gaps: tuple[str, ...] = ()
        self.searching_announced = False

    def remaining(self) -> float:
        return self.deadline - self.clock()

    def progress(self) -> Progress:
        return Progress(
            steps=self.steps,
            tool_calls=self.tool_calls,
            consecutive_tool_errors=self.consecutive_errors,
            output_tokens=self.output_tokens,
            context_tokens=self.context_tokens,
            pool_size=len(self.pool),
            remaining_s=self.remaining(),
        )

    def fallback_or(self, reason: StopReason) -> StopReason:
        if reason in _FALLBACK_EXITS and self.successful_searches == 0:
            return "no_successful_search"
        return reason

    async def run(self) -> AgentOutcome:
        await self.ctx.emit("status", dict(STATUS_PLANNING))
        tools = await self.load_tools()
        if tools is None:
            self.sm.stop("planner_unavailable")
        while self.sm.state is not AgentState.DONE:
            await self.iterate(tools or ())
        return self.outcome()

    async def load_tools(self) -> tuple[dict[str, Any], ...] | None:
        try:
            specs = await self.transport.list_tools()
        except Exception as exc:
            log.warning(
                "agent_tools_unavailable", run_id=str(self.ctx.run_id), error=type(exc).__name__
            )
            return None
        model_tools = sorted((s for s in specs if s.name != FINISH_TOOL), key=lambda s: s.name)
        return (*(s.to_anthropic() for s in model_tools), FINISH_RESEARCH_SPEC.to_anthropic())

    async def iterate(self, tools: tuple[dict[str, Any], ...]) -> None:
        """One pass around the loop: bound checks, one model call, tools, observation."""
        bound = check_bounds(self.progress(), self.bounds)
        if bound is not None:
            self.sm.stop(bound)
            return
        self.sm.advance(AgentState.AGENT_STEP)
        turn = await self.model_step(tools)
        if turn is None:
            if self.steps == 1:
                self.sm.stop("planner_unavailable")
            else:
                self.sm.stop(
                    "time_limit" if self.remaining() <= 0 else self.fallback_or("llm_unavailable")
                )
            return
        self.transcript.append_assistant(turn.content)
        self.account(turn)
        if turn.stop_reason == "max_tokens":
            self.sm.stop("token_limit")  # a truncated turn's tool_use input is unreliable
            return
        if not turn.tool_uses:
            self.sm.stop(self.fallback_or("end_turn"))  # any prose is discarded
            return
        finish = [u for u in turn.tool_uses if u.name == FINISH_TOOL]
        if finish:
            self.sufficient, self.gaps = parse_finish(finish[0].input)
        uses = [u for u in turn.tool_uses if u.name != FINISH_TOOL]
        if not uses:
            self.sm.stop(self.fallback_or("finish_research"))
            return
        planned = self.plan(uses)
        if planned is None:
            self.sm.stop("repeat_call")
            return
        self.sm.advance(AgentState.EXECUTE)
        records = await self.run_calls(planned)
        self.sm.advance(AgentState.OBSERVE)
        blocks = self.observe(records)
        if finish:
            self.sm.stop(self.fallback_or("finish_research"))
            return
        self.transcript.append_tool_results(blocks)
        self.context_tokens += sum(len(b.content) for b in blocks) // CHARS_PER_TOKEN

    async def model_step(self, tools: tuple[dict[str, Any], ...]) -> AgentTurn | None:
        self.steps += 1
        remaining = self.remaining()
        request = AgentLLMRequest(
            system=RESEARCH_SYSTEM_PROMPT,
            messages=self.transcript.messages,
            tools=tools,
            max_tokens=self.bounds.max_tokens,
            effort=self.bounds.effort,
            timeout_s=max(remaining, 0.001),
        )
        try:  # the provider bounds itself by timeout_s; this is the backstop
            return await asyncio.wait_for(self.llm.step(request), remaining + LLM_GRACE_S)
        except Exception as exc:  # LLMUnavailableError, timeouts, anything: never raise
            log.warning(
                "agent_llm_failed",
                run_id=str(self.ctx.run_id),
                step=self.steps,
                error=type(exc).__name__,
            )
            return None

    def account(self, turn: AgentTurn) -> None:
        u = turn.usage
        self.usage.update(u.as_dict())
        self.output_tokens += u.output_tokens
        self.context_tokens = (
            u.input_tokens
            + u.cache_read_input_tokens
            + u.cache_creation_input_tokens
            + u.output_tokens
        )

    def plan(self, uses: list[ToolUse]) -> list[PlannedCall] | None:
        """Budget and repeat policy, decided before anything runs. ``None`` = stop
        (some call is the 2nd repeat of an identical (tool, canonical args))."""
        budget = self.bounds.max_tool_calls - self.tool_calls
        planned: list[PlannedCall] = []
        for index, use in enumerate(uses):
            key = canonical_call_key(use.name, use.input)
            self.call_counts[key] += 1
            count = self.call_counts[key]
            decision: Decision
            if count >= self.bounds.repeat_stop_at:
                return None
            if count > 1:
                decision = "deny_repeat"
            elif budget > 0:
                decision, budget = "run", budget - 1
            else:
                decision = "deny_budget"
            planned.append(PlannedCall(call=to_call(use, self.steps, index), decision=decision))
        return planned

    async def run_calls(self, planned: list[PlannedCall]) -> list[CallRecord]:
        if not self.searching_announced:
            self.searching_announced = True
            await self.ctx.emit("status", dict(STATUS_SEARCHING))
        for p in planned:
            c = p.call
            await self.ctx.emit(
                "tool_started", tool_started(c.step, c.call_index, c.name, c.arguments)
            )
        records = await execute(
            self.transport,
            planned,
            credential=self.ctx.credential,
            timeout_s=lambda: min(self.bounds.tool_timeout_s, self.remaining()),
        )
        for r in records:
            c = r.call
            await self.ctx.emit(
                "tool_completed",
                tool_completed(
                    c.step,
                    c.call_index,
                    c.name,
                    r.status,
                    _result_count(r),
                    round(r.result.duration_ms),
                    r.result.error.code if r.result.error else None,
                ),
            )
        return records

    def observe(self, records: list[CallRecord]) -> list[ToolResultBlock]:
        """Fold results into counters and the pool (block order) and build tool_results."""
        blocks: list[ToolResultBlock] = []
        obs_max_chars = self.bounds.obs_max_tokens * CHARS_PER_TOKEN
        for r in records:
            result = r.result
            if r.executed:
                self.tool_calls += 1
                if result.ok:
                    self.consecutive_errors = 0
                    self.merge(r)
                else:
                    self.tool_errors += 1
                    self.consecutive_errors += 1
            self.trace.append(_trace_entry(r))
            if result.ok:
                content = wrap_observation(
                    tool_label(result.name), result.observation[:obs_max_chars]
                )
            else:
                code = result.error.code if result.error else "INTERNAL"
                message = result.error.message if result.error else "Tool call failed."
                content = error_observation(code, message[:obs_max_chars])
            blocks.append(ToolResultBlock(r.call.call_id, content, is_error=not result.ok))
        return blocks

    def merge(self, record: CallRecord) -> None:
        output = record.result.output or {}
        name, step = record.call.name, record.call.step
        if name in EVIDENCE_TOOLS:
            self.successful_searches += 1
        for hit in output.get("hits") or []:
            self.pool.add_hit(hit, step=step, via_tool=name)
        for position, item in enumerate(output.get("items") or [], start=1):
            if item.get("found"):
                self.pool.add_lookup(item, rank=position, step=step)
            elif item.get("miss_reason") in GONE:
                self.pool.discard(str(item.get("handle")))

    def outcome(self) -> AgentOutcome:
        reason = self.sm.stop_reason
        assert reason is not None  # the loop only exits through DONE
        flag = STOP_FLAGS.get(reason)
        log.info(
            "agent_gather_done",
            run_id=str(self.ctx.run_id),
            stop_reason=reason,
            steps=self.steps,
            tool_calls=self.tool_calls,
            tool_errors=self.tool_errors,
            pool=len(self.pool),
        )
        return AgentOutcome(
            pool=self.pool.items(),
            stop_reason=reason,
            flags=(flag,) if flag else (),
            steps=self.steps,
            tool_calls=self.tool_calls,
            tool_errors=self.tool_errors,
            usage={
                k: self.usage.get(k, 0)
                for k in (
                    "input_tokens",
                    "output_tokens",
                    "cache_read_input_tokens",
                    "cache_creation_input_tokens",
                )
            }
            | {"llm_attempts": self.steps},
            trace=tuple(self.trace),
            sufficient=self.sufficient,
            gaps=self.gaps,
            states=self.sm.history,
        )


def _result_count(record: CallRecord) -> int:
    result = record.result
    if not result.ok or not result.output:
        return 0
    if "sources" in result.output:
        return len(result.output.get("sources") or [])
    return len(result.handles())


def _trace_entry(record: CallRecord) -> dict[str, Any]:
    call, result = record.call, record.result
    return {
        "step": call.step,
        "call_index": call.call_index,
        "tool": tool_label(call.name),
        "args": validated_args(call.name, call.arguments) or {},
        "status": record.status,
        "error_code": result.error.code if result.error else None,
        "handles": list(result.handles()),
        "duration_ms": round(result.duration_ms),
    }
