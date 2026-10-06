"""Grounded synthesis and verification loop of the standard run (plan §19; ADR-0004).

Each LLM call is clamped to the time left before the run deadline (minus a finalize reserve),
so a slow or broken provider degrades to an evidence-only answer instead of a run timeout.

Every verified attempt is persisted to ``verification_attempts`` (Phase 4, A6) via
:mod:`marketsignal.runs.verification_log`; the citation cap comes from
``settings.verifier_max_citations`` and is stated in the system prompt and the feedback.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

from marketsignal.config import Settings
from marketsignal.db.session import SessionFactory
from marketsignal.generation.aliases import AliasGate, GateCitation, GateText, GateWarning
from marketsignal.generation.prompts import build_system_prompt, render_user_turn
from marketsignal.generation.types import EvidencePack, VerificationReport
from marketsignal.generation.verifier import (
    VERIFIER_ERROR,
    VerifiedAnswer,
    detect_conflicts,
    regeneration_feedback,
    verify_answer,
)
from marketsignal.providers.llm.base import (
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMText,
    LLMUnavailableError,
)
from marketsignal.runs.events import EventWriter
from marketsignal.runs.flags import (
    CITATION_VERIFICATION_FAILED,
    GENERATION_TRUNCATED,
    LLM_SYNTHESIS_UNAVAILABLE,
    MODEL_REFUSAL,
    SOURCE_DELETED_DURING_RUN,
    STATUS,
)
from marketsignal.runs.state import RunRequest, _Attempt, _RunState, _SourceWithheldError
from marketsignal.runs.verification_log import disposition, record_attempt
from marketsignal.telemetry.logging import get_logger

log = get_logger(__name__)


async def generate_and_verify(
    settings: Settings,
    llm: Callable[[], LLMProvider],
    req: RunRequest,
    writer: EventWriter,
    state: _RunState,
    pack: EvidencePack,
    summary: str,
    recent_q: tuple[str, ...],
    started: float,
    *,
    factory: SessionFactory | None = None,
) -> tuple[VerifiedAnswer | None, VerificationReport | None, str]:
    """Generate, verify, and regenerate at most once. ``factory`` (optional, keyword-only)
    persists one ``verification_attempts`` row per verified attempt (the executor always passes
    it; without it nothing is recorded)."""
    audit = factory
    feedback: str | None = None
    report: VerificationReport | None = None
    for attempt in (1, 2):
        if attempt == 2:
            await writer.emit("draft_reset", {"attempt": attempt, "reason": "verification_failed"})
        await writer.emit("status", {"phase": "synthesizing", "message": STATUS["synthesizing"]})
        try:
            generated = await generate(
                settings,
                llm,
                req,
                writer,
                state,
                pack,
                summary,
                recent_q,
                attempt,
                feedback,
                started,
            )
        except _SourceWithheldError:
            state.flag(SOURCE_DELETED_DURING_RUN)
            return None, report, SOURCE_DELETED_DURING_RUN
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
            await writer.emit("warning", {"code": MODEL_REFUSAL, "message": "The model declined."})
            return None, report, MODEL_REFUSAL
        if stop == "max_tokens":
            state.flag(GENERATION_TRUNCATED)
            await writer.emit(
                "warning", {"code": GENERATION_TRUNCATED, "message": "The answer was cut off."}
            )
            return None, report, GENERATION_TRUNCATED
        await writer.emit("status", {"phase": "verifying", "message": STATUS["verifying"]})
        t0 = time.monotonic()
        verified = _verify_safely(req, settings, generated.raw, pack)
        state.timings[f"verify_ms_{attempt}"] = round((time.monotonic() - t0) * 1000, 2)
        report = verified.report
        remaining = settings.run_deadline_s - (time.monotonic() - started)
        regenerate = (
            not verified.ok and attempt == 1 and remaining >= settings.regeneration_min_remaining_s
        )
        report.attempt = attempt
        report.regeneration_requested = regenerate
        report.disposition = disposition(
            report, ok=verified.ok, regenerate=regenerate, final=attempt == 2
        )
        if audit is not None:
            await record_attempt(audit, req.scope, req.run_id, report)
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
        if not regenerate:
            break
    return None, report, CITATION_VERIFICATION_FAILED


def _verify_safely(
    req: RunRequest, settings: Settings, raw: str, pack: EvidencePack
) -> VerifiedAnswer:
    """``verify_answer``, with any unexpected verifier error counted as a failed verification
    (regenerate or evidence-only), never a crashed run. Only the exception type is logged."""
    try:
        return verify_answer(
            raw,
            pack,
            pack_truncated=pack.truncated,
            question=req.question,
            max_citations=settings.verifier_max_citations,
        )
    except Exception as exc:
        log.warning("verifier_error", run_id=str(req.run_id), error=type(exc).__name__)
        report = VerificationReport(
            passed=False,
            structural_failures=[VERIFIER_ERROR],
            failure_categories=[VERIFIER_ERROR],
            max_citations=settings.verifier_max_citations,
        )
        return VerifiedAnswer(content="", sections={}, citations=[], report=report, ok=False)


async def generate(
    settings: Settings,
    llm: Callable[[], LLMProvider],
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
    remaining = settings.run_deadline_s - (time.monotonic() - started)
    budget = min(settings.llm_timeout_s, remaining - settings.run_finalize_reserve_s)
    if budget <= 0:
        raise LLMUnavailableError("no time left before the run deadline")
    request = LLMRequest(
        system=build_system_prompt(settings.verifier_max_citations),
        messages=(
            {
                "role": "user",
                "content": render_user_turn(
                    req.question,
                    pack,
                    summary=summary,
                    recent_questions=recent_q,
                    feedback=feedback,
                    notes=detect_conflicts(pack),
                ),
            },
        ),
        max_tokens=settings.llm_max_tokens,
        effort=settings.llm_effort,
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
            contextlib.aclosing(provider_stream(llm, request)) as chunks,
        ):
            async for chunk in chunks:
                if isinstance(chunk, LLMText):
                    out.raw += chunk.text
                    if out.first_token_ms is None:
                        out.first_token_ms = round((time.monotonic() - t0) * 1000, 1)
                        state.timings.setdefault("first_token_ms", out.first_token_ms)
                    await emit_gate(writer, attempt, gate.push(chunk.text), by_alias)
                    if writer.withheld:  # a pack source was purged: stop quoting it
                        raise _SourceWithheldError
                else:
                    out.stop = chunk
                    state.model = chunk.model
                    state.add_usage(chunk.usage)
    except TimeoutError as exc:  # this call's budget (the run deadline arrives as a cancel)
        raise LLMUnavailableError(f"synthesis exceeded its {budget:.1f}s budget") from exc
    await emit_gate(writer, attempt, gate.flush(), by_alias)
    out.duration_ms = round((time.monotonic() - t0) * 1000, 1)
    state.timings[f"synthesis_ms_{attempt}"] = out.duration_ms
    return out


async def provider_stream(
    llm: Callable[[], LLMProvider], request: LLMRequest
) -> AsyncGenerator[LLMChunk]:
    """The provider's chunks, with every provider-side failure (construction, a missing
    key, an exhausted fake script, an SDK error) surfaced as ``LLMUnavailableError`` so the
    run degrades to evidence-only. Only provider calls are wrapped: failures in our own
    event writing propagate unchanged."""
    try:
        iterator = aiter(llm().stream(request))
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


async def emit_gate(
    writer: EventWriter, attempt: int, events: list[Any], by_alias: dict[str, Any]
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
