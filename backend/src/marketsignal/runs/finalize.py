"""Finalization of a standard run: persist the answer, emit ``final``, advance the conversation.

While a pack source has been purged (purge wins, ADR-0016) the answer falls back to an
evidence-only one from the surviving sources, or abstains when none survive.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.generation import fallback
from marketsignal.generation.types import EvidencePack, VerificationReport
from marketsignal.runs import store
from marketsignal.runs.conversation import next_state
from marketsignal.runs.events import EventWriter
from marketsignal.runs.flags import CONVERSATION_STATE_NOT_UPDATED, SOURCE_DELETED_DURING_RUN
from marketsignal.runs.state import RunRequest, _RunState
from marketsignal.telemetry.logging import get_logger

log = get_logger(__name__)


def without_sources(pack: EvidencePack, codes: frozenset[str] | set[str]) -> EvidencePack:
    """The pack minus every item (every parent) of the given purged sources."""
    return EvidencePack(
        items=tuple(i for i in pack.items if i.source_code not in codes),
        tokens=pack.tokens,
        truncated=pack.truncated,
        dropped=pack.dropped,
    )


async def finish(
    factory: SessionFactory,
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
            factory,
            req.scope,
            conversation_id=req.conversation_id,
            run_id=req.run_id,
            content=content,
            citations=citations,
            sections=sections,
            status="complete",
            model=state.model,
            usage=state.usage,
        )
        if outcome.message_id is not None:
            break
        if not outcome.purged_codes:  # cannot happen; never loop without progress
            raise RuntimeError("answer not stored and no purged source reported")
        pack = without_sources(pack, outcome.purged_codes)
        alt = await source_deleted_fallback(factory, req, writer, state, pack)
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
    await store.update_run(factory, req.scope, req.run_id, cited_handles=cited)
    await advance_conversation(factory, req, state, sections, cited, outcome.message_id)


async def source_deleted_fallback(
    factory: SessionFactory,
    req: RunRequest,
    writer: EventWriter,
    state: _RunState,
    survivors: EvidencePack,
) -> fallback.DeterministicAnswer:
    state.flag(SOURCE_DELETED_DURING_RUN)
    state.states.add("generation_unavailable")
    if not writer.withheld:  # the store already logged the one withheld-content notice
        await writer.emit(
            "warning",
            {"code": SOURCE_DELETED_DURING_RUN, "message": "A source was deleted."},
        )
    writer.discard_pending()
    if writer.draft_open:
        await writer.emit("draft_reset", {"attempt": 0, "reason": "evidence_only"})
    if survivors.empty:
        return fallback.abstention(await present_classes(factory, req.scope))
    return fallback.evidence_only(survivors, SOURCE_DELETED_DURING_RUN)


async def advance_conversation(
    factory: SessionFactory,
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
            factory,
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


async def present_classes(factory: SessionFactory, scope: WorkspaceScope) -> list[str]:
    async with scoped_session(factory, scope) as session:
        rows = await session.execute(
            text(
                "SELECT DISTINCT v.source_class FROM sources s "
                "JOIN source_versions v ON v.id = s.current_version_id "
                "WHERE s.workspace_id = :ws AND s.deleted_at IS NULL"
            ),
            {"ws": scope.workspace_id},
        )
        return sorted(r[0] for r in rows.all())
