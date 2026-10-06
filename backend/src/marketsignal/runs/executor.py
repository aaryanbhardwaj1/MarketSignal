"""Standard-mode run executor (plan §3, §19; ADR-0004, ADR-0008, ADR-0015).

    question -> hybrid retrieval -> evidence pack -> grounded synthesis (streamed through the
    alias gate) -> deterministic verification (repair; at most one regeneration) -> persisted,
    canonical answer -> ``final`` -> ``done``

Invariants:
* An empty pack never reaches the model: the run abstains deterministically.
* Only verified content becomes ``final`` or is stored; otherwise the run falls back to an
  evidence-only answer (cards, no prose).
* Stored answers contain canonical handles only; aliases live in this run's events.
* Status text is generated from system state, never from model reasoning (thinking is never
  requested for display and never streamed).
* ``done`` is always emitted last and exactly once, whatever happens (cancel, timeout, errors).
  The pipeline runs under the run deadline and *returns* the answer to publish; finalization
  (persist -> ``final``) and termination (``done`` + the row update) then run once, outside the
  deadline scope and shielded from further cancels, so a late deadline or a second cancel can
  neither interrupt ``done`` nor re-terminate a published answer.
* An unverified draft is withdrawn (``draft_reset``) whenever no ``final`` follows it.
* Each LLM call is clamped to the time left before the deadline (minus a finalize reserve), so a
  slow or broken provider degrades to an evidence-only answer instead of a run timeout.
Termination follows the plan §28 precedence.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy import text

from marketsignal.agent.runtime import ResearchAgent
from marketsignal.agent.summary import ResearchSummary
from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.domain.enums import Confidentiality
from marketsignal.generation import fallback
from marketsignal.generation.pack import PackLimits, build_pack
from marketsignal.generation.types import EvidencePack, VerificationReport
from marketsignal.generation.verifier import VerifiedAnswer
from marketsignal.providers.llm.base import LLMProvider
from marketsignal.retrieval.pipeline import RetrievalService
from marketsignal.retrieval.traces import persist_trace
from marketsignal.retrieval.types import ParentCandidate, RetrievalFilters
from marketsignal.runs import store
from marketsignal.runs.broker import RunBroker
from marketsignal.runs.events import EventWriter
from marketsignal.runs.finalize import finish, present_classes, without_sources
from marketsignal.runs.flags import (
    CITATION_VERIFICATION_FAILED,
    EVIDENCE_EMPTY,
    PACK_BUDGET_TRUNCATED,
    RESEARCH_UNAVAILABLE,
    RETRIEVAL_FLAGS,
    RETRIEVAL_TIMEOUT,
    RUN_TIMEOUT,
    SOURCE_DELETED_DURING_RUN,
    STATUS,
    termination_state,
)
from marketsignal.runs.reaper import status_for_termination
from marketsignal.runs.research import research_gather
from marketsignal.runs.state import RunRequest, _Answer, _Outcome, _RunState, _ToolFailureError
from marketsignal.runs.synthesis import generate_and_verify
from marketsignal.telemetry.logging import get_logger

__all__ = ["RunRequest", "StandardRunExecutor", "termination_state"]

log = get_logger(__name__)

_RUN_FAILED = (
    "error",
    {"code": "RUN_FAILED", "message": "The run failed unexpectedly.", "retryable": True},
)


async def _uninterruptible(coro: Coroutine[Any, Any, None]) -> None:
    """Run ``coro`` to completion even if the caller is cancelled (any number of times) while
    it runs; the cancellation is re-raised afterwards so the task still ends cancelled."""
    task = asyncio.ensure_future(coro)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    task.result()  # surfaces the inner task's own failure (or its own cancellation)
    if cancelled:
        raise asyncio.CancelledError


class StandardRunExecutor:
    def __init__(
        self,
        factory: SessionFactory,
        settings: Settings,
        retrieval: RetrievalService,
        llm: Callable[[], LLMProvider],
        broker: RunBroker,
        agent_factory: Callable[[], ResearchAgent] | None = None,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._retrieval = retrieval
        self._llm = llm
        self._broker = broker
        self._agent_factory = agent_factory  # None: research requests run the standard gather

    # ------------------------------------------------------------------ entry point
    async def execute(self, req: RunRequest) -> None:
        writer = EventWriter(
            self._factory,
            req.scope,
            req.run_id,
            self._broker,
            coalesce_ms=self._settings.sse_token_coalesce_ms,
        )
        state = _RunState()
        started = time.monotonic()
        answer: _Answer | None = None
        outcome = _Outcome()
        try:
            async with asyncio.timeout(self._settings.run_deadline_s):
                answer = await self._run(req, writer, state, started)
        except asyncio.CancelledError:
            state.states.add("cancelled")
            outcome = _Outcome(status="cancelled", cancelled=True)
        except TimeoutError:
            state.states.add("timeout")
            state.flag(RUN_TIMEOUT)
            notice = {"code": RUN_TIMEOUT, "message": "The run exceeded its time limit."}
            outcome = _Outcome(status="failed", notice=("warning", notice))
        except _ToolFailureError as exc:
            state.states.add("tool_failure")
            state.flag(exc.code)
            notice = {"code": exc.code, "message": exc.message}
            outcome = _Outcome(status="failed", error=exc.code, notice=("warning", notice))
        except Exception as exc:  # never leave a run without ``done``
            log.exception("run_failed", run_id=str(req.run_id))
            state.states.add("tool_failure")
            outcome = _Outcome(status="failed", error=type(exc).__name__, notice=_RUN_FAILED)
        # Exactly one conclusion, outside the deadline and immune to further cancels.
        await _uninterruptible(self._conclude(req, writer, state, started, answer, outcome))
        if outcome.cancelled:
            raise asyncio.CancelledError

    async def _conclude(
        self,
        req: RunRequest,
        writer: EventWriter,
        state: _RunState,
        started: float,
        answer: _Answer | None,
        outcome: _Outcome,
    ) -> None:
        """Publish + terminate, bounded by ``run_finalize_timeout_s`` (a DB-starved finalize must
        not outlive the reap threshold). On expiry: a best-effort ``done`` + row update, bounded
        by half the rest of the reap margin."""
        settings = self._settings
        try:
            async with asyncio.timeout(settings.run_finalize_timeout_s):
                await self._publish_and_terminate(req, writer, state, started, answer, outcome)
            return
        except TimeoutError:
            log.error("run_finalize_timeout", run_id=str(req.run_id))
        status, error = outcome.status, outcome.error
        notice: tuple[str, dict[str, Any]] | None = None
        if writer.done:  # only the row update was starved: make it match the done written
            status = status_for_termination(termination_state(state.states))
        elif not writer.final_emitted and status == "completed":  # the answer never went out
            state.states.add("timeout")
            state.flag(RUN_TIMEOUT)
            status, error = "failed", "FinalizeTimeout"
            notice = ("warning", {"code": RUN_TIMEOUT, "message": "The run could not finish."})
        grace = (settings.run_reap_margin_s - settings.run_finalize_timeout_s) / 2
        try:
            async with asyncio.timeout(grace):
                # done is skipped if already written (writer.done); the row update is retried.
                await self._terminate(
                    req, writer, state, started, status=status, error=error, notice=notice
                )
        except TimeoutError:
            log.error("run_terminate_timeout", run_id=str(req.run_id))

    async def _publish_and_terminate(
        self,
        req: RunRequest,
        writer: EventWriter,
        state: _RunState,
        started: float,
        answer: _Answer | None,
        outcome: _Outcome,
    ) -> None:
        if answer is not None:
            try:
                await self._finish(
                    req,
                    writer,
                    state,
                    answer.content,
                    answer.sections,
                    answer.citations,
                    answer.report,
                    answer.pack,
                )
            except Exception as exc:
                if writer.final_emitted:  # the answer is published: bookkeeping failed only
                    log.exception("run_post_final_failed", run_id=str(req.run_id))
                else:
                    log.exception("run_failed", run_id=str(req.run_id))
                    state.states.add("tool_failure")
                    outcome = _Outcome(
                        status="failed", error=type(exc).__name__, notice=_RUN_FAILED
                    )
        await self._terminate(
            req,
            writer,
            state,
            started,
            status=outcome.status,
            error=outcome.error,
            notice=outcome.notice,
        )

    async def _safe_emit(
        self,
        writer: EventWriter,
        event_type: str,
        payload: dict[str, Any],
        *,
        run_fields: dict[str, Any] | None = None,
    ) -> None:
        if writer.done:
            return
        try:
            await writer.emit(event_type, payload, run_fields=run_fields)
        except Exception:
            log.exception("event_write_failed", run_id=str(writer.run_id), event_type=event_type)

    async def _terminate(
        self,
        req: RunRequest,
        writer: EventWriter,
        state: _RunState,
        started: float,
        *,
        status: str,
        error: str | None = None,
        notice: tuple[str, dict[str, Any]] | None = None,
    ) -> None:
        state.timings["total_ms"] = round((time.monotonic() - started) * 1000, 1)
        termination = termination_state(state.states)
        if not writer.final_emitted:
            writer.discard_pending()  # unsent draft text is never streamed only to be withdrawn
        if notice is not None:
            await self._safe_emit(writer, *notice)
        if not writer.final_emitted and writer.draft_open:  # no final will follow this draft
            await self._safe_emit(writer, "draft_reset", {"attempt": 0, "reason": termination})
        done = {
            "termination_state": termination,
            "flags": state.flags,
            "cache_status": "disabled",
            "timings": state.timings,
        }
        run_fields: dict[str, Any] = {
            "status": status,
            "termination_state": termination,
            "degradation_flags": state.flags,
            "usage": state.usage,
            "timings": state.timings,
            "models": {"synthesis": state.model} if state.model else {},
            "error_class": error,
            "finished_at": True,
        }
        for _ in range(2):  # one retry: a failed write re-syncs seq before trying again
            # done and the finished run row commit together: whoever sees done sees the row.
            await self._safe_emit(writer, "done", done, run_fields=run_fields)
            if writer.done:
                break
        if writer.run_finished:
            return
        try:  # done was not ours to write (or failed): still finish the row
            await store.update_run(self._factory, req.scope, req.run_id, **run_fields)
        except Exception:
            log.exception("run_finalize_failed", run_id=str(req.run_id))

    # ------------------------------------------------------------------ the pipeline
    async def _run(
        self, req: RunRequest, writer: EventWriter, state: _RunState, started: float
    ) -> _Answer:
        """The deadline-bound pipeline; returns the answer to publish (never publishes)."""
        settings = self._settings
        await writer.emit(
            "run_started",
            {
                "conversation_id": str(req.conversation_id),
                "persona": req.persona,
                "mode": req.mode,
                "route": req.route,
            },
        )
        convo = await store.conversation_state(self._factory, req.scope, req.conversation_id)
        summary = convo.summary if convo else ""
        recent_q = convo.recent_questions if convo else ()

        max_conf = await self._llm_max_confidentiality(req.scope)
        research_summary: ResearchSummary | None = None
        if req.mode == "research" and self._agent_factory is not None:
            # 1. Research gather: the bounded agent over the governed tools (ADR-0007/0015).
            # The agent itself reports the planning/searching phases.
            research = await research_gather(
                factory=self._factory,
                settings=settings,
                req=req,
                writer=writer,
                state=state,
                agent_factory=self._agent_factory,
                max_conf=max_conf,
                summary=summary,
                recent_questions=recent_q,
            )
            ranked = research.ranked
            research_summary = research.summary
            if research.fallback:  # plan §19: no plan or no successful search → standard gather
                ranked = await self._standard_gather(
                    req,
                    writer,
                    state,
                    max_conf,
                    step=research.outcome.steps + 1,
                    deadline=research.gather_deadline,  # the time left, not a fresh budget
                )
        else:
            if req.mode == "research":
                state.flag(RESEARCH_UNAVAILABLE)
            ranked = await self._standard_gather(req, writer, state, max_conf, step=1)

        # 2. Evidence pack.
        await writer.emit("status", {"phase": "analyzing", "message": STATUS["analyzing"]})
        t0 = time.monotonic()
        pack = await build_pack(
            self._factory,
            req.scope,
            ranked,
            PackLimits(
                max_items=settings.pack_max_items,
                max_tokens=settings.pack_max_tokens,
                item_max_tokens=settings.pack_item_max_tokens,
                candidates=settings.pack_candidates,
            ),
        )
        state.timings["pack_ms"] = round((time.monotonic() - t0) * 1000, 1)
        # Freeze the pack before anything (event or model call) can quote it: pack_handles are
        # written under a share lock on the pack's sources, so a purge either commits first
        # (and its source is dropped here) or sees this run's pack_handles and cleans up after
        # it (store module docstring; ADR-0016).
        gone = await store.freeze_pack(
            self._factory,
            req.scope,
            req.run_id,
            items=[(i.handle, i.source_code) for i in pack.items],
            normalized_query=" ".join(req.question.split()),
            standalone_query=req.question,
            retrieved_handles=[p.handle for p in ranked[: settings.pack_candidates]],
            pack_tokens=pack.tokens,
            context_tokens=pack.tokens + len(summary) // 4,
        )
        if gone:
            pack = without_sources(pack, gone)
            state.flag(SOURCE_DELETED_DURING_RUN)
            await writer.emit(
                "warning",
                {"code": SOURCE_DELETED_DURING_RUN, "message": "A source was deleted."},
            )
        await writer.emit("evidence", {k: v for k, v in pack.summary().items() if k != "tokens"})
        if pack.truncated:
            state.flag(PACK_BUDGET_TRUNCATED)
            state.states.add("completed_with_limited_evidence")
            await writer.emit(
                "warning",
                {"code": PACK_BUDGET_TRUNCATED, "message": "Some evidence did not fit the budget."},
            )

        # 3. Empty pack: deterministic abstention, no LLM call.
        if pack.empty:
            state.flag(EVIDENCE_EMPTY)
            state.states.add("no_relevant_evidence")
            present = await present_classes(self._factory, req.scope)
            abstained = fallback.abstention(present, req.source_classes)
            return _Answer(abstained.content, abstained.sections, [], None, pack)

        # 4. Synthesis -> 5. verification (at most one regeneration) -> fallback.
        verified, report, reason = await self._generate_and_verify(
            req, writer, state, pack, summary, recent_q, started, research_summary=research_summary
        )
        if verified is None:
            state.states.add("generation_unavailable")
            if reason == CITATION_VERIFICATION_FAILED:
                state.flag(CITATION_VERIFICATION_FAILED)
            writer.discard_pending()
            if writer.draft_open:
                await writer.emit("draft_reset", {"attempt": 0, "reason": "evidence_only"})
            answer = fallback.evidence_only(pack, reason)
            return _Answer(answer.content, answer.sections, answer.citations, report, pack)
        return _Answer(
            verified.content, verified.sections, verified.citations, verified.report, pack
        )

    async def _generate_and_verify(
        self,
        req: RunRequest,
        writer: EventWriter,
        state: _RunState,
        pack: EvidencePack,
        summary: str,
        recent_q: tuple[str, ...],
        started: float,
        *,
        research_summary: ResearchSummary | None = None,
    ) -> tuple[VerifiedAnswer | None, VerificationReport | None, str]:
        return await generate_and_verify(
            self._settings,
            self._llm,
            req,
            writer,
            state,
            pack,
            summary,
            recent_q,
            started,
            factory=self._factory,
            research_summary=research_summary,
        )

    async def _finish(
        self,
        req: RunRequest,
        writer: EventWriter,
        state: _RunState,
        content: str,
        sections: dict[str, Any],
        citations: list[dict[str, Any]],
        report: VerificationReport | None,
        pack: EvidencePack,
    ) -> None:
        await finish(self._factory, req, writer, state, content, sections, citations, report, pack)

    async def _standard_gather(
        self,
        req: RunRequest,
        writer: EventWriter,
        state: _RunState,
        max_conf: Confidentiality,
        *,
        step: int,
        deadline: float | None = None,
    ) -> list[ParentCandidate]:
        """The Phase 3 standard gather (production hybrid RRF), unchanged; also the research
        fallback. ``deadline`` (a ``time.monotonic()`` instant) is the research run's single
        gather deadline: the fallback gets only the time left before it, and when none is left
        it reports RETRIEVAL_TIMEOUT (tool_failure) without starting a search that cannot
        finish. ``None``: a fresh ``run_gather_budget_s`` (standard mode)."""
        settings = self._settings
        # 1. Retrieval (the production default: hybrid RRF).
        await writer.emit("status", {"phase": "searching", "message": STATUS["searching"]})
        await writer.emit(
            "tool_started",
            {"step": step, "tool": "search_evidence", "kind": "search", "summary": "hybrid search"},
        )
        t0 = time.monotonic()
        filters = RetrievalFilters.of(req.source_classes, (), max_conf)
        budget_s = settings.run_gather_budget_s if deadline is None else deadline - time.monotonic()
        try:
            if budget_s <= 0:
                raise TimeoutError
            async with asyncio.timeout(budget_s):
                result = await self._retrieval.search(
                    self._factory, req.scope, req.question, filters, top_k=settings.pack_candidates
                )
        except TimeoutError as exc:  # the gather budget, not the run deadline (that is a cancel)
            await writer.emit(
                "tool_completed",
                {
                    "step": step,
                    "tool": "search_evidence",
                    "status": "error",
                    "result_count": 0,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                },
            )
            raise _ToolFailureError(
                RETRIEVAL_TIMEOUT, "Evidence search exceeded its time budget."
            ) from exc
        trace_id = await persist_trace(
            self._factory, req.scope, result, origin="api", query_run_id=req.run_id
        )
        state.timings["retrieval_ms"] = round((time.monotonic() - t0) * 1000, 1)
        for flag in result.flags:
            state.flag(flag)
            if flag in RETRIEVAL_FLAGS:
                state.states.add("retrieval_degraded")
            await writer.emit("warning", {"code": flag, "message": f"Retrieval degraded: {flag}"})
        await writer.emit(
            "tool_completed",
            {
                "step": step,
                "tool": "search_evidence",
                "status": "ok",
                "result_count": len(result.parents),
                "classes_found": sorted(
                    {p.source_class for p in result.parents[: settings.pack_candidates]}
                ),
                "duration_ms": state.timings["retrieval_ms"],
                "trace_id": str(trace_id) if trace_id else None,
            },
        )
        return list(result.parents)

    async def _llm_max_confidentiality(self, scope: WorkspaceScope) -> Confidentiality:
        async with scoped_session(self._factory, scope) as session:
            value = (
                await session.execute(
                    text("SELECT llm_max_confidentiality FROM workspaces WHERE id = :ws"),
                    {"ws": scope.workspace_id},
                )
            ).scalar_one_or_none()
        return Confidentiality(value or Confidentiality.CONFIDENTIAL.value)
