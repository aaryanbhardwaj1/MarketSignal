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

Fallback: whenever gathering ends with zero successful evidence calls (and so an empty pool),
for any reason but cancellation, ``planner_unavailable`` and a ``time_limit`` that leaves no
time before ``ctx.deadline`` (the whole gather's deadline), the outcome reports
``no_successful_search`` (flag ``PLANNER_NO_TOOL_FALLBACK``, after the original bound's flag)
so the executor runs the standard gather with whatever gather time is left.

Per-turn work is bounded: at most the remaining tool budget of a turn's tool_use blocks is
handled per call (progress events, trace entry); the rest are denied in one aggregated trace
entry without per-call events. Every progress emit is bounded by the gather deadline.
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
    printable,
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
from marketsignal.tools.contracts import TOOLS_TRANSPORT_FALLBACK, ToolTransport

__all__ = ["AgentContext", "AgentOutcome", "PoolItem", "ResearchAgent"]

log = get_logger(__name__)

CHARS_PER_TOKEN = 4  # observation clipping (characters), as the tool layer clips
# Context estimate for tool_result text added since the last request: UTF-8 bytes // 3. That is
# >= 1 token per CJK character (3 bytes) and over-counts ASCII (~4 chars/token) by about a
# third, so the next request never exceeds ``max_context_tokens`` by more than the estimate's
# own error on the conservative side (chars // 4 under-counted non-Latin text up to 4x).
BYTES_PER_TOKEN = 3
LLM_GRACE_S = 0.5  # lets the provider raise its own timeout before the backstop fires
EVIDENCE_TOOLS = frozenset({"search_evidence", "search_evidence_keyword", "get_evidence"})
GONE = frozenset({"NOT_FOUND", "SOURCE_DELETED"})
# Tool-result warnings that are reported once as run flags (e.g. the HTTP transport was
# unreachable and the call was re-run in process, plan §27).
RUN_FLAG_WARNINGS = (TOOLS_TRANSPORT_FALLBACK,)
# Stops that never become ``no_successful_search`` (the executor already falls back for them).
_NO_FALLBACK_REWRITE = frozenset({"planner_unavailable", "no_successful_search"})

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
    source_classes: tuple[str, ...] = ()  # the run's class filter, stated to the model

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
                source_classes=ctx.source_classes,
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
        self.warning_flags: set[str] = set()

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

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """A progress emit bounded by the gather deadline (a slow event write must not stretch
        gathering); skipped once the deadline has passed. Other failures are the sink's to
        handle (research_gather's emitter is best-effort); cancellation propagates."""
        remaining = self.remaining()
        if remaining <= 0:
            return
        try:
            async with asyncio.timeout(remaining):
                await self.ctx.emit(event_type, payload)
        except TimeoutError:
            log.warning("agent_emit_timeout", run_id=str(self.ctx.run_id), event_type=event_type)

    async def run(self) -> AgentOutcome:
        await self.emit("status", dict(STATUS_PLANNING))
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
                self.sm.stop("time_limit" if self.remaining() <= 0 else "llm_unavailable")
            return
        self.transcript.append_assistant(turn.content)
        self.account(turn)
        if turn.stop_reason == "max_tokens":
            self.sm.stop("token_limit")  # a truncated turn's tool_use input is unreliable
            return
        if not turn.tool_uses:
            self.sm.stop("end_turn")  # any prose is discarded
            return
        finish = [u for u in turn.tool_uses if u.name == FINISH_TOOL]
        if finish:
            self.sufficient, self.gaps = parse_finish(finish[0].input)
        uses = [u for u in turn.tool_uses if u.name != FINISH_TOOL]
        if not uses:
            self.sm.stop("finish_research")
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
            self.sm.stop("finish_research")
            return
        self.transcript.append_tool_results(blocks)
        self.context_tokens += (
            sum(len(b.content.encode("utf-8")) for b in blocks) // BYTES_PER_TOKEN
        )

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
        (some call is the 2nd repeat of an identical (tool, canonical args)).

        Only the first ``remaining budget`` blocks are considered (run or repeat-denied); any
        further blocks are ``deny_budget`` without a repeat check, and get no per-call events."""
        budget = max(self.bounds.max_tool_calls - self.tool_calls, 0)
        overflow = [
            PlannedCall(call=to_call(use, self.steps, index), decision="deny_budget")
            for index, use in enumerate(uses[budget:], start=budget)
        ]
        planned: list[PlannedCall] = []
        for index, use in enumerate(uses[:budget]):
            key = canonical_call_key(use.name, use.input)
            self.call_counts[key] += 1
            count = self.call_counts[key]
            if count >= self.bounds.repeat_stop_at:
                return None
            decision: Decision = "deny_repeat" if count > 1 else "run"
            planned.append(PlannedCall(call=to_call(use, self.steps, index), decision=decision))
        return planned + overflow

    async def run_calls(self, planned: list[PlannedCall]) -> list[CallRecord]:
        if not self.searching_announced:
            self.searching_announced = True
            await self.emit("status", dict(STATUS_SEARCHING))
        for p in planned:
            if p.decision == "deny_budget":
                continue  # aggregated: no per-call events
            c = p.call
            await self.emit("tool_started", tool_started(c.step, c.call_index, c.name, c.arguments))
        records = await execute(
            self.transport,
            planned,
            credential=self.ctx.credential,
            timeout_s=lambda: min(self.bounds.tool_timeout_s, self.remaining()),
        )
        for r in records:
            if r.decision == "deny_budget":
                continue
            c = r.call
            await self.emit(
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
            self.warning_flags.update(w for w in result.warnings if w in RUN_FLAG_WARNINGS)
            if r.executed:
                self.tool_calls += 1
                if result.ok:
                    self.consecutive_errors = 0
                    self.merge(r)
                else:
                    self.tool_errors += 1
                    self.consecutive_errors += 1
            if r.decision != "deny_budget":
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
        overflow = [r for r in records if r.decision == "deny_budget"]
        if overflow:
            self.trace.append(_overflow_entry(overflow))
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
        flags = [STOP_FLAGS[reason]] if reason in STOP_FLAGS else []
        if (
            reason not in _NO_FALLBACK_REWRITE
            and self.successful_searches == 0
            and len(self.pool) == 0
            and not (reason == "time_limit" and self.ctx.deadline - self.clock() <= 0)
        ):  # empty-handed for any reason: let the executor run the standard gather
            reason = "no_successful_search"
            flags.append(STOP_FLAGS[reason])
        flags.extend(w for w in RUN_FLAG_WARNINGS if w in self.warning_flags)
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
            flags=tuple(flags),
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
        "handles": [printable(h) for h in result.handles()],
        "duration_ms": round(result.duration_ms),
    }


def _overflow_entry(records: list[CallRecord]) -> dict[str, Any]:
    """One trace entry for a turn's tool_use blocks beyond the remaining tool budget."""
    first = records[0].call
    return {
        "step": first.step,
        "call_index": first.call_index,
        "tool": "unknown",
        "args": {},
        "status": "denied",
        "error_code": "POLICY_DENIED",
        "handles": [],
        "duration_ms": 0,
        "denied_calls": len(records),
    }
