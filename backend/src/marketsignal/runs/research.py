"""Research-mode gather: the bounded agent in place of the standard single search (ADR-0015).

The modes differ only here. Research mints a run-scoped capability token, lets the bounded
agent (ADR-0007) call the governed tools, and turns its evidence pool into ranked parents;
everything after that (freeze, pack, synthesis, verification, persistence, ``done``) is the
shared Phase 3 tail. When the agent cannot plan (first model call fails) or ends without one
successful search, the caller runs the standard gather instead (plan §19 fallbacks).

What is recorded (``query_runs.agent``, ``query_runs.tool_calls``) is observable action only:
stop reason, bound flags, step and call counts, the state path, per-call tool, sanitized
arguments, status, handles and timing, and token usage. Model prose, thinking and
``finish_research`` gap text are never stored. The record is written purge-safely
(:func:`write_agent_record`): if a version behind any traced handle was purged meanwhile, the
per-call trace is dropped (``trace_redacted``) and only counts, states and usage are kept.

Scope: ``req.source_classes`` is minted into the capability token (the tools enforce it),
stated to the agent, and enforced again when the pool is resolved (``pool_to_candidates``).

Time: the whole gather (agent plus any standard fallback) shares one deadline,
``research start + run_gather_budget_s`` (:attr:`ResearchResult.gather_deadline`); the agent
stops at the earlier of that and its own ``agent_gather_budget_s``, and the fallback gets only
what is left (none left: the fallback reports RETRIEVAL_TIMEOUT, see the executor).

Progress events are best-effort (:func:`progress_emitter`): a failed event write is logged
(type only) and skipped, so the agent outcome is always persisted.

Synthesis hand-off (Phase 5, A3): :attr:`ResearchResult.summary` is the deterministic, bounded
:class:`~marketsignal.agent.summary.ResearchSummary` of the gather (observable state and the
question only; ``finish_research`` gap text is never included). The executor passes it to
synthesis, which binds it to the final pack and renders it as ``<research_summary>``. It is on
by default; the ``research_summary`` setting (env ``MS_RESEARCH_SUMMARY``) turns it off, for the
before/after evaluation only.

Computed results (Phase 5, B): :attr:`ResearchResult.results` carries the agent's computed
analytics results (``AgentOutcome.results``; each is also persisted in ``analytics_results`` under
this run) for synthesis to cite as ``[R#]``. A filter_rows listing's row handles are already in
the pool, so they are resolved like any other pooled handle.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from marketsignal.agent.pool import pool_to_candidates
from marketsignal.agent.runtime import AgentContext, AgentOutcome, ResearchAgent
from marketsignal.agent.summary import ResearchSummary, build_research_summary
from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.domain.enums import Confidentiality
from marketsignal.retrieval.types import ParentCandidate
from marketsignal.runs import store
from marketsignal.runs.events import EventWriter
from marketsignal.runs.state import RunRequest, _RunState
from marketsignal.telemetry.logging import get_logger
from marketsignal.tools import capability
from marketsignal.tools.contracts import TOOL_NAMES

log = get_logger(__name__)
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]

FALLBACK_STOPS = frozenset({"planner_unavailable", "no_successful_search"})
_PROGRESS_EVENTS = frozenset({"status", "tool_started", "tool_completed"})
_TOKEN_SLACK_S = 60  # the capability token outlives the gather budget by this much


@dataclass(frozen=True, slots=True)
class ResearchResult:
    ranked: list[ParentCandidate]
    fallback: bool  # True: the caller runs the standard gather
    outcome: AgentOutcome
    gather_deadline: float  # time.monotonic() deadline shared by the agent and the fallback
    summary: ResearchSummary | None = None  # the synthesis hand-off (None: switched off)
    # The agent's computed results (full AnalyticsResult dicts, call order, unique, at most
    # MAX_RESULTS_FOR_SYNTHESIS): passed to synthesis as [R#] results, also on fallback.
    results: tuple[dict[str, Any], ...] = ()


def agent_record(outcome: AgentOutcome, *, duration_ms: float) -> dict[str, Any]:
    """The persisted agent trace: observable actions and counts, never model text."""
    return {
        "stop_reason": outcome.stop_reason,
        "flags": list(outcome.flags),
        "steps": outcome.steps,
        "tool_calls": outcome.tool_calls,
        "tool_errors": outcome.tool_errors,
        "states": [str(s) for s in outcome.states],
        "pool_size": len(outcome.pool),
        "sufficient": outcome.sufficient,
        "gap_count": len(outcome.gaps),
        "usage": dict(outcome.usage),
        "trace": list(outcome.trace),
        "duration_ms": round(duration_ms, 1),
    }


def progress_emitter(writer: EventWriter) -> Emit:
    """The agent's progress sink: progress event types only, best-effort. A failed write is
    logged by exception type (never the payload, which may quote model text) and skipped;
    ``CancelledError`` propagates."""

    async def emit(event_type: str, payload: dict[str, Any]) -> None:
        if event_type not in _PROGRESS_EVENTS or writer.done:
            return
        try:
            await writer.emit(event_type, payload)
        except Exception as exc:
            log.warning(
                "event_write_failed",
                run_id=str(writer.run_id),
                event_type=event_type,
                error=type(exc).__name__,
            )

    return emit


async def write_agent_record(
    factory: SessionFactory,
    scope: WorkspaceScope,
    run_id: Any,
    record: dict[str, Any],
    *,
    tool_calls: int,
) -> bool:
    """Persist ``query_runs.agent``/``tool_calls`` in one transaction under the run row's
    ``FOR KEY SHARE`` lock (the purge guard, see ``runs/store.py``): if any traced handle's
    version is purged, the trace is replaced by ``trace_redacted: true``. Either the purge sees
    this write (and strips the trace itself) or this write sees the purge. Returns whether the
    trace was redacted."""
    handles = sorted({h for entry in record.get("trace", []) for h in entry.get("handles", [])})
    async with scoped_session(factory, scope) as session:
        await store._lock_run_pack(session, scope, run_id)
        redacted = bool(await store._purged_pack_codes(session, scope, handles))
        if redacted:
            record = {k: v for k, v in record.items() if k != "trace"} | {"trace_redacted": True}
        assignments, params = store._run_assignments({"agent": record, "tool_calls": tool_calls})
        params.update({"ws": scope.workspace_id, "id": run_id})
        await session.execute(
            text(
                f"UPDATE query_runs SET {', '.join(assignments)} "  # noqa: S608 - allowlisted columns
                "WHERE workspace_id = :ws AND id = :id"
            ),
            params,
        )
        await session.commit()
    return redacted


async def research_gather(
    *,
    factory: SessionFactory,
    settings: Settings,
    req: RunRequest,
    writer: EventWriter,
    state: _RunState,
    agent_factory: Callable[[], ResearchAgent],
    max_conf: Confidentiality,
    summary: str,
    recent_questions: tuple[str, ...],
) -> ResearchResult:
    started = time.monotonic()
    gather_deadline = started + settings.run_gather_budget_s
    credential = capability.issue(
        settings.mcp_token_key,
        run_id=req.run_id,
        workspace_id=req.scope.workspace_id,
        workspace_code=req.scope.workspace_code,
        principal="api",
        persona=req.persona,
        tools=TOOL_NAMES,
        max_conf=max_conf.value,
        ttl_s=min(3600.0, settings.agent_gather_budget_s + _TOKEN_SLACK_S),
        source_classes=req.source_classes,
    )
    outcome = await agent_factory().gather(
        AgentContext(
            run_id=req.run_id,
            scope=req.scope,
            question=req.question,
            persona=req.persona,
            conversation_summary=summary,
            recent_questions=recent_questions,
            credential=credential,
            deadline=gather_deadline,  # the agent also applies agent_gather_budget_s
            emit=progress_emitter(writer),
            source_classes=tuple(req.source_classes),
        )
    )
    duration_ms = (time.monotonic() - started) * 1000
    state.timings["agent_ms"] = round(duration_ms, 1)
    for flag in outcome.flags:
        state.flag(flag)
    await write_agent_record(
        factory,
        req.scope,
        req.run_id,
        agent_record(outcome, duration_ms=duration_ms),
        tool_calls=outcome.tool_calls,
    )
    handoff = build_research_summary(req.question, outcome) if settings.research_summary else None
    if outcome.stop_reason in FALLBACK_STOPS:
        return ResearchResult([], True, outcome, gather_deadline, handoff, outcome.results)
    ranked = await pool_to_candidates(
        factory, req.scope, outcome.pool, source_classes=req.source_classes
    )
    if outcome.stop_reason == "tool_errors" and not ranked:
        state.states.add("tool_failure")  # plan §28: circuit open and nothing gathered
    return ResearchResult(ranked, False, outcome, gather_deadline, handoff, outcome.results)
