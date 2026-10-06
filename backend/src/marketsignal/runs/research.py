"""Research-mode gather: the bounded agent in place of the standard single search (ADR-0015).

The modes differ only here. Research mints a run-scoped capability token, lets the bounded
agent (ADR-0007) call the governed tools, and turns its evidence pool into ranked parents;
everything after that (freeze, pack, synthesis, verification, persistence, ``done``) is the
shared Phase 3 tail. When the agent cannot plan (first model call fails) or ends without one
successful search, the caller runs the standard gather instead (plan §19 fallbacks).

What is recorded (``query_runs.agent``, ``query_runs.tool_calls``) is observable action only:
stop reason, bound flags, step and call counts, the state path, per-call tool, sanitized
arguments, status, handles and timing, and token usage. Model prose, thinking and
``finish_research`` gap text are never stored.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from marketsignal.agent.pool import pool_to_candidates
from marketsignal.agent.runtime import AgentContext, AgentOutcome, ResearchAgent
from marketsignal.config import Settings
from marketsignal.db.session import SessionFactory
from marketsignal.domain.enums import Confidentiality
from marketsignal.retrieval.types import ParentCandidate
from marketsignal.runs import store
from marketsignal.runs.events import EventWriter
from marketsignal.runs.state import RunRequest, _RunState
from marketsignal.tools import capability
from marketsignal.tools.contracts import TOOL_NAMES

FALLBACK_STOPS = frozenset({"planner_unavailable", "no_successful_search"})
_PROGRESS_EVENTS = frozenset({"status", "tool_started", "tool_completed"})
_TOKEN_SLACK_S = 60  # the capability token outlives the gather budget by this much


@dataclass(frozen=True, slots=True)
class ResearchResult:
    ranked: list[ParentCandidate]
    fallback: bool  # True: the caller runs the standard gather
    outcome: AgentOutcome


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
    )

    async def emit(event_type: str, payload: dict[str, Any]) -> None:
        if event_type in _PROGRESS_EVENTS:  # the agent can only report progress
            await writer.emit(event_type, payload)

    started = time.monotonic()
    outcome = await agent_factory().gather(
        AgentContext(
            run_id=req.run_id,
            scope=req.scope,
            question=req.question,
            persona=req.persona,
            conversation_summary=summary,
            recent_questions=recent_questions,
            credential=credential,
            deadline=started + settings.agent_gather_budget_s,
            emit=emit,
        )
    )
    duration_ms = (time.monotonic() - started) * 1000
    state.timings["agent_ms"] = round(duration_ms, 1)
    for flag in outcome.flags:
        state.flag(flag)
    await store.update_run(
        factory,
        req.scope,
        req.run_id,
        agent=agent_record(outcome, duration_ms=duration_ms),
        tool_calls=outcome.tool_calls,
    )
    if outcome.stop_reason in FALLBACK_STOPS:
        return ResearchResult([], True, outcome)
    ranked = await pool_to_candidates(factory, req.scope, outcome.pool)
    if outcome.stop_reason == "tool_errors" and not ranked:
        state.states.add("tool_failure")  # plan §28: circuit open and nothing gathered
    return ResearchResult(ranked, False, outcome)
