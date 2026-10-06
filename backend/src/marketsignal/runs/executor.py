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
import contextlib
import time
import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.domain.enums import Confidentiality
from marketsignal.generation import fallback
from marketsignal.generation.aliases import AliasGate, GateCitation, GateText, GateWarning
from marketsignal.generation.pack import PackLimits, build_pack
from marketsignal.generation.prompts import SYSTEM_PROMPT, render_user_turn
from marketsignal.generation.types import EvidencePack, VerificationReport
from marketsignal.generation.verifier import VerifiedAnswer, regeneration_feedback, verify_answer
from marketsignal.providers.llm.base import (
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMStop,
    LLMText,
    LLMUnavailableError,
    LLMUsage,
)
from marketsignal.retrieval.pipeline import RetrievalService
from marketsignal.retrieval.traces import persist_trace
from marketsignal.retrieval.types import RetrievalFilters
from marketsignal.runs import store
from marketsignal.runs.broker import RunBroker
from marketsignal.runs.conversation import next_state
from marketsignal.runs.events import EventWriter
from marketsignal.telemetry.logging import get_logger

log = get_logger(__name__)

# Degradation flags (plan §28).
EVIDENCE_EMPTY = "EVIDENCE_EMPTY"
LLM_SYNTHESIS_UNAVAILABLE = "LLM_SYNTHESIS_UNAVAILABLE"
MODEL_REFUSAL = "MODEL_REFUSAL"
GENERATION_TRUNCATED = "GENERATION_TRUNCATED"
CITATION_VERIFICATION_FAILED = "CITATION_VERIFICATION_FAILED"
PACK_BUDGET_TRUNCATED = "PACK_BUDGET_TRUNCATED"
SOURCE_DELETED_DURING_RUN = "SOURCE_DELETED_DURING_RUN"
RUN_TIMEOUT = "RUN_TIMEOUT"
RETRIEVAL_TIMEOUT = "RETRIEVAL_TIMEOUT"
RETRIEVAL_FLAGS = frozenset(
    {"RETRIEVAL_LEXICAL_FALLBACK", "RETRIEVAL_DENSE_UNAVAILABLE", "RERANKER_UNAVAILABLE"}
)
PRECEDENCE = (
    "cancelled",
    "timeout",
    "tool_failure",
    "no_relevant_evidence",
    "generation_unavailable",
    "retrieval_degraded",
    "completed_with_limited_evidence",
    "completed",
)
_RUN_FAILED = (
    "error",
    {"code": "RUN_FAILED", "message": "The run failed unexpectedly.", "retryable": True},
)
STATUS = {
    "searching": "Searching workspace evidence",
    "analyzing": "Assembling the evidence pack",
    "synthesizing": "Writing a grounded answer",
    "verifying": "Verifying citations and numbers",
}


def termination_state(states: set[str]) -> str:
    """Highest-precedence state among those reached (plan §28)."""
    return next((s for s in PRECEDENCE if s in states), "completed")


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


class _ToolFailureError(Exception):
    """A pipeline tool failed in a way the run reports (warning ``code``) rather than crashes."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


# A finished run's conversation summary could not be updated (best effort after ``final``).
CONVERSATION_STATE_NOT_UPDATED = "CONVERSATION_STATE_NOT_UPDATED"


def _without_sources(pack: EvidencePack, codes: frozenset[str] | set[str]) -> EvidencePack:
    """The pack minus every item (every parent) of the given purged sources."""
    return EvidencePack(
        items=tuple(i for i in pack.items if i.source_code not in codes),
        tokens=pack.tokens,
        truncated=pack.truncated,
        dropped=pack.dropped,
    )


@dataclass(frozen=True, slots=True)
class RunRequest:
    run_id: uuid.UUID
    scope: WorkspaceScope
    conversation_id: uuid.UUID
    question: str
    persona: str
    mode: str = "standard"
    source_classes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Answer:
    """What the pipeline decided to publish; finalized outside the deadline scope."""

    content: str
    sections: dict[str, Any]
    citations: list[dict[str, Any]]
    report: VerificationReport | None
    pack: EvidencePack


@dataclass(frozen=True, slots=True)
class _Outcome:
    status: str = "completed"
    error: str | None = None
    notice: tuple[str, dict[str, Any]] | None = None  # warning/error emitted before done
    cancelled: bool = False


@dataclass
class _Attempt:
    raw: str = ""
    stop: LLMStop | None = None
    first_token_ms: float | None = None
    duration_ms: float = 0.0


@dataclass
class _RunState:
    flags: list[str] = field(default_factory=list)
    states: set[str] = field(default_factory=set)
    usage: dict[str, int] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    model: str | None = None

    def flag(self, code: str) -> None:
        if code not in self.flags:
            self.flags.append(code)

    def count(self, key: str) -> None:
        self.usage[key] = self.usage.get(key, 0) + 1

    def add_usage(self, usage: LLMUsage) -> None:
        for key, value in usage.as_dict().items():
            self.usage[key] = self.usage.get(key, 0) + value


class StandardRunExecutor:
    def __init__(
        self,
        factory: SessionFactory,
        settings: Settings,
        retrieval: RetrievalService,
        llm: Callable[[], LLMProvider],
        broker: RunBroker,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._retrieval = retrieval
        self._llm = llm
        self._broker = broker

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
        self, writer: EventWriter, event_type: str, payload: dict[str, Any]
    ) -> None:
        if writer.done:
            return
        try:
            await writer.emit(event_type, payload)
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
        for _ in range(2):  # one retry: a failed write re-syncs seq before trying again
            await self._safe_emit(writer, "done", done)
            if writer.done:
                break
        try:
            await store.update_run(
                self._factory,
                req.scope,
                req.run_id,
                status=status,
                termination_state=termination,
                degradation_flags=state.flags,
                usage=state.usage,
                timings=state.timings,
                models={"synthesis": state.model} if state.model else {},
                error_class=error,
                finished_at=True,
            )
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
            {"conversation_id": str(req.conversation_id), "persona": req.persona, "mode": req.mode},
        )
        convo = await store.conversation_state(self._factory, req.scope, req.conversation_id)
        summary = convo.summary if convo else ""
        recent_q = convo.recent_questions if convo else ()

        # 1. Retrieval (the production default: hybrid RRF).
        await writer.emit("status", {"phase": "searching", "message": STATUS["searching"]})
        await writer.emit(
            "tool_started",
            {"step": 1, "tool": "search_evidence", "kind": "search", "summary": "hybrid search"},
        )
        t0 = time.monotonic()
        max_conf = await self._llm_max_confidentiality(req.scope)
        filters = RetrievalFilters.of(req.source_classes, (), max_conf)
        try:
            async with asyncio.timeout(settings.run_gather_budget_s):
                result = await self._retrieval.search(
                    self._factory, req.scope, req.question, filters, top_k=settings.pack_candidates
                )
        except TimeoutError as exc:  # the gather budget, not the run deadline (that is a cancel)
            await writer.emit(
                "tool_completed",
                {
                    "step": 1,
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
                "step": 1,
                "tool": "search_evidence",
                "status": "ok",
                "result_count": len(result.parents),
                "classes_found": sorted({p.source_class for p in result.parents[:24]}),
                "duration_ms": state.timings["retrieval_ms"],
                "trace_id": str(trace_id) if trace_id else None,
            },
        )

        # 2. Evidence pack.
        await writer.emit("status", {"phase": "analyzing", "message": STATUS["analyzing"]})
        t0 = time.monotonic()
        pack = await build_pack(
            self._factory,
            req.scope,
            result.parents,
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
            retrieved_handles=[p.handle for p in result.parents[: settings.pack_candidates]],
            pack_tokens=pack.tokens,
            context_tokens=pack.tokens + len(summary) // 4,
        )
        if gone:
            pack = _without_sources(pack, gone)
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
            present = await self._present_classes(req.scope)
            abstained = fallback.abstention(present, req.source_classes)
            return _Answer(abstained.content, abstained.sections, [], None, pack)

        # 4. Synthesis -> 5. verification (at most one regeneration) -> fallback.
        verified, report, reason = await self._generate_and_verify(
            req, writer, state, pack, summary, recent_q, started
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
    ) -> tuple[VerifiedAnswer | None, VerificationReport | None, str]:
        feedback: str | None = None
        report: VerificationReport | None = None
        for attempt in (1, 2):
            if attempt == 2:
                remaining = self._settings.run_deadline_s - (time.monotonic() - started)
                if remaining < self._settings.regeneration_min_remaining_s:
                    return None, report, CITATION_VERIFICATION_FAILED
                await writer.emit(
                    "draft_reset", {"attempt": attempt, "reason": "verification_failed"}
                )
            await writer.emit(
                "status", {"phase": "synthesizing", "message": STATUS["synthesizing"]}
            )
            try:
                generated = await self._generate(
                    req, writer, state, pack, summary, recent_q, attempt, feedback, started
                )
            except LLMUnavailableError as exc:
                log.warning("llm_unavailable", run_id=str(req.run_id), reason=str(exc)[:200])
                state.count("llm_failures")
                state.flag(LLM_SYNTHESIS_UNAVAILABLE)
                await writer.emit(
                    "warning",
                    {
                        "code": LLM_SYNTHESIS_UNAVAILABLE,
                        "message": "The language model is unavailable.",
                    },
                )
                return None, report, LLM_SYNTHESIS_UNAVAILABLE
            stop = generated.stop.stop_reason if generated.stop else "unknown"
            if stop == "refusal":
                state.flag(MODEL_REFUSAL)
                await writer.emit(
                    "warning", {"code": MODEL_REFUSAL, "message": "The model declined."}
                )
                return None, report, MODEL_REFUSAL
            if stop == "max_tokens":
                state.flag(GENERATION_TRUNCATED)
                await writer.emit(
                    "warning", {"code": GENERATION_TRUNCATED, "message": "The answer was cut off."}
                )
                return None, report, GENERATION_TRUNCATED
            await writer.emit("status", {"phase": "verifying", "message": STATUS["verifying"]})
            t0 = time.monotonic()
            verified = verify_answer(generated.raw, pack, pack_truncated=pack.truncated)
            state.timings[f"verify_ms_{attempt}"] = round((time.monotonic() - t0) * 1000, 2)
            report = verified.report
            if verified.ok:
                state.timings["attempts"] = attempt
                return verified, report, ""
            feedback = regeneration_feedback(verified.report)
            log.info(
                "verification_failed",
                run_id=str(req.run_id),
                attempt=attempt,
                failures=verified.report.structural_failures,
            )
        return None, report, CITATION_VERIFICATION_FAILED

    async def _generate(
        self,
        req: RunRequest,
        writer: EventWriter,
        state: _RunState,
        pack: EvidencePack,
        summary: str,
        recent_q: tuple[str, ...],
        attempt: int,
        feedback: str | None,
        started: float,
    ) -> _Attempt:
        state.count("llm_attempts")  # recorded even when the call fails (evaluation needs it)
        settings = self._settings
        remaining = settings.run_deadline_s - (time.monotonic() - started)
        budget = min(settings.llm_timeout_s, remaining - settings.run_finalize_reserve_s)
        if budget <= 0:
            raise LLMUnavailableError("no time left before the run deadline")
        request = LLMRequest(
            system=SYSTEM_PROMPT,
            messages=(
                {
                    "role": "user",
                    "content": render_user_turn(
                        req.question,
                        pack,
                        summary=summary,
                        recent_questions=recent_q,
                        feedback=feedback,
                    ),
                },
            ),
            max_tokens=self._settings.llm_max_tokens,
            effort=self._settings.llm_effort,
            timeout_s=budget,
            metadata={"run_id": str(req.run_id), "attempt": attempt},
        )
        gate = AliasGate.from_pack(pack)
        by_alias = pack.by_alias()
        out = _Attempt()
        t0 = time.monotonic()
        try:
            async with (
                asyncio.timeout(budget),
                contextlib.aclosing(self._provider_stream(request)) as chunks,
            ):
                async for chunk in chunks:
                    if isinstance(chunk, LLMText):
                        out.raw += chunk.text
                        if out.first_token_ms is None:
                            out.first_token_ms = round((time.monotonic() - t0) * 1000, 1)
                            state.timings.setdefault("first_token_ms", out.first_token_ms)
                        await self._emit_gate(writer, attempt, gate.push(chunk.text), by_alias)
                    else:
                        out.stop = chunk
                        state.model = chunk.model
                        state.add_usage(chunk.usage)
        except TimeoutError as exc:  # this call's budget (the run deadline arrives as a cancel)
            raise LLMUnavailableError(f"synthesis exceeded its {budget:.1f}s budget") from exc
        await self._emit_gate(writer, attempt, gate.flush(), by_alias)
        out.duration_ms = round((time.monotonic() - t0) * 1000, 1)
        state.timings[f"synthesis_ms_{attempt}"] = out.duration_ms
        return out

    async def _provider_stream(self, request: LLMRequest) -> AsyncGenerator[LLMChunk]:
        """The provider's chunks, with every provider-side failure (construction, a missing
        key, an exhausted fake script, an SDK error) surfaced as ``LLMUnavailableError`` so the
        run degrades to evidence-only. Only provider calls are wrapped: failures in our own
        event writing propagate unchanged."""
        try:
            iterator = aiter(self._llm().stream(request))
        except LLMUnavailableError:
            raise
        except Exception as exc:
            raise LLMUnavailableError(f"provider unavailable: {type(exc).__name__}") from exc
        try:
            while True:
                try:
                    chunk = await anext(iterator)
                except StopAsyncIteration:
                    return
                except LLMUnavailableError:
                    raise
                except Exception as exc:
                    raise LLMUnavailableError(f"provider failed: {type(exc).__name__}") from exc
                yield chunk
        finally:
            closer = getattr(iterator, "aclose", None)
            if closer is not None:
                with contextlib.suppress(Exception):
                    await closer()

    async def _emit_gate(
        self, writer: EventWriter, attempt: int, events: list[Any], by_alias: dict[str, Any]
    ) -> None:
        for event in events:
            if isinstance(event, GateText):
                await writer.token(attempt, event.text)
            elif isinstance(event, GateCitation):
                item = by_alias[event.alias]
                await writer.emit(
                    "citation",
                    {
                        "attempt": attempt,
                        "alias": event.alias,
                        "handle": item.handle,
                        "source_title": item.source_title,
                        "source_class": item.source_class,
                        "locator_label": item.locator_label,
                    },
                )
            elif isinstance(event, GateWarning):
                await writer.emit("warning", {"code": event.code, "message": event.message})

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
        # Every pack source is share-locked and re-checked, cited or not (an answer can use
        # uncited pack text). While any has been purged (purge wins, ADR-0016): fall back to
        # an evidence-only answer from the surviving sources, or abstain when none survive.
        # Each failed attempt drops at least one source, so this ends (abstention cites none).
        while True:
            outcome = await store.persist_answer(
                self._factory,
                req.scope,
                conversation_id=req.conversation_id,
                run_id=req.run_id,
                content=content,
                citations=citations,
                sections=sections,
                status="complete",
                model=state.model,
                usage=state.usage,
                pack_codes=sorted({i.source_code for i in pack.items}),
            )
            if outcome.message_id is not None:
                break
            if not outcome.purged_codes:  # cannot happen; never loop without progress
                raise RuntimeError("answer not stored and no purged source reported")
            pack = _without_sources(pack, outcome.purged_codes)
            alt = await self._source_deleted_fallback(req, writer, state, pack)
            content, sections, citations, report = alt.content, alt.sections, alt.citations, None
        cited = [c["handle"] for c in citations]
        await writer.emit(
            "final",
            {
                "message_id": str(outcome.message_id),
                "content": content,
                "citations": citations,
                "sections": sections,
                "verification": report.as_dict() if report else None,
            },
        )
        await store.update_run(self._factory, req.scope, req.run_id, cited_handles=cited)
        await self._advance_conversation(req, state, sections, cited, outcome.message_id)

    async def _source_deleted_fallback(
        self, req: RunRequest, writer: EventWriter, state: _RunState, survivors: EvidencePack
    ) -> fallback.DeterministicAnswer:
        state.flag(SOURCE_DELETED_DURING_RUN)
        state.states.add("generation_unavailable")
        await writer.emit(
            "warning",
            {"code": SOURCE_DELETED_DURING_RUN, "message": "A source was deleted."},
        )
        if writer.tokens_emitted:
            await writer.emit("draft_reset", {"attempt": 0, "reason": "evidence_only"})
        if survivors.empty:
            return fallback.abstention(await self._present_classes(req.scope))
        return fallback.evidence_only(survivors, SOURCE_DELETED_DURING_RUN)

    async def _advance_conversation(
        self,
        req: RunRequest,
        state: _RunState,
        sections: dict[str, Any],
        cited: list[str],
        message_id: uuid.UUID | None,
    ) -> None:
        """Best effort after ``final``: the answer is stored and delivered, so a failure here is
        logged and flagged, never turned into a failed run."""

        def advance(convo: store.ConversationState) -> tuple[str, list[str], list[str]]:
            return next_state(
                summary=convo.summary,
                recent_questions=convo.recent_questions,
                recent_handles=convo.recent_handles,
                question=req.question,
                sections=sections,
                cited_handles=cited,
            )

        try:
            updated = await store.advance_conversation_state(
                self._factory,
                req.scope,
                req.conversation_id,
                run_id=req.run_id,
                advance=advance,
                through_message_id=message_id,
            )
        except Exception:
            log.exception("conversation_state_update_failed", run_id=str(req.run_id))
            state.flag(CONVERSATION_STATE_NOT_UPDATED)
            return
        if not updated:  # a pack source was purged after the answer was stored
            state.flag(SOURCE_DELETED_DURING_RUN)

    async def _llm_max_confidentiality(self, scope: WorkspaceScope) -> Confidentiality:
        async with scoped_session(self._factory, scope) as session:
            value = (
                await session.execute(
                    text("SELECT llm_max_confidentiality FROM workspaces WHERE id = :ws"),
                    {"ws": scope.workspace_id},
                )
            ).scalar_one_or_none()
        return Confidentiality(value or Confidentiality.CONFIDENTIAL.value)

    async def _present_classes(self, scope: WorkspaceScope) -> list[str]:
        async with scoped_session(self._factory, scope) as session:
            rows = await session.execute(
                text(
                    "SELECT DISTINCT v.source_class FROM sources s "
                    "JOIN source_versions v ON v.id = s.current_version_id "
                    "WHERE s.workspace_id = :ws AND s.deleted_at IS NULL"
                ),
                {"ws": scope.workspace_id},
            )
            return sorted(r[0] for r in rows.all())
