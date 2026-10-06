"""Persistence for conversations, runs, run events and answers (migration 0004).

Every function opens its own short scoped transaction (RLS + explicit workspace predicate).

Purge always wins (ADR-0016). ``ingestion.purge.purge_source`` takes ``FOR UPDATE`` on the
source row first and, in the same transaction, redacts answers, deletes run events and resets
conversation summaries for every run whose ``query_runs.pack_handles`` include the source. Every
write here that can carry evidence text share-locks (``FOR SHARE``) the sources behind it and
re-checks ``deleted_at`` in the *same* transaction as the write, so for each such write either:

* it commits first, and the purge (blocked on the row lock until then; its statements read
  after our commit) sees the write and removes it; or
* the purge commits first, and the write (blocked on the row lock until then; a locking read in
  READ COMMITTED returns the latest committed row) sees ``deleted_at`` and does not store it.

The writes covered: ``freeze_pack`` (records ``pack_handles`` before any event or model call can
quote the pack, dropping sources purged since the pack was read), ``append_event`` for
text-bearing events, ``persist_answer`` (every pack source, cited or not) and
``advance_conversation_state`` (the rolling summary later prompts are built from).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session

_RUN_FIELDS = frozenset(
    {
        "normalized_query",
        "standalone_query",
        "retrieved_handles",
        "pack_handles",
        "cited_handles",
        "context_tokens",
        "pack_tokens",
        "models",
        "usage",
        "cache_status",
        "timings",
        "status",
        "termination_state",
        "degradation_flags",
        "error_class",
        "finished_at",
        "corpus_version_start",
    }
)
_JSON_FIELDS = frozenset({"models", "usage", "timings"})
# Events whose payload can quote or point at pack evidence (alias-gated draft text, citation
# cards, the final answer). They are only stored while every pack source is still alive.
TEXT_EVENT_TYPES = frozenset({"token", "citation", "final"})
SOURCE_DELETED_DURING_RUN = "SOURCE_DELETED_DURING_RUN"
_WITHHELD = {
    "code": SOURCE_DELETED_DURING_RUN,
    "message": "Content was withheld because a source in this run's evidence was deleted.",
}
# Source code of a canonical handle "WS/CODE@vN:LOCATOR" (codes never contain '/' or '@').
_HANDLE_CODE_SQL = "split_part(split_part(h, '/', 2), '@v', 1)"


@dataclass(frozen=True, slots=True)
class ConversationState:
    conversation_id: uuid.UUID
    persona: str
    summary: str
    recent_questions: tuple[str, ...]
    recent_handles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoredEvent:
    seq: int
    type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class PersistOutcome:
    message_id: uuid.UUID | None
    purged_handles: list[str] = field(default_factory=list)  # cited handles of purged sources
    purged_codes: frozenset[str] = frozenset()  # every purged pack/cited source code


async def _purged_codes(
    session: AsyncSession, scope: WorkspaceScope, codes: Sequence[str]
) -> set[str]:
    """Share-lock the given sources (purge takes ``FOR UPDATE``) and return the purged ones."""
    wanted = sorted(set(codes))
    if not wanted:
        return set()
    rows = (
        await session.execute(
            text(
                "SELECT source_code, deleted_at FROM sources WHERE workspace_id = :ws "
                "AND source_code = ANY(CAST(:codes AS text[])) ORDER BY id FOR SHARE"
            ),
            {"ws": scope.workspace_id, "codes": wanted},
        )
    ).all()
    alive = {r[0] for r in rows if r[1] is None}
    return {c for c in wanted if c not in alive}


async def _run_pack_purged(session: AsyncSession, scope: WorkspaceScope, run_id: uuid.UUID) -> bool:
    """Share-lock the sources of the run's frozen pack; True if any of them was purged."""
    rows = (
        await session.execute(
            text(
                "SELECT s.deleted_at FROM sources s WHERE s.workspace_id = :ws AND s.source_code "  # noqa: S608 - constant SQL
                f"IN (SELECT {_HANDLE_CODE_SQL} FROM query_runs r, unnest(r.pack_handles) h "
                "WHERE r.workspace_id = :ws AND r.id = :r) ORDER BY s.id FOR SHARE OF s"
            ),
            {"ws": scope.workspace_id, "r": run_id},
        )
    ).all()
    return any(r[0] is not None for r in rows)


def _run_assignments(fields: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    assignments: list[str] = []
    params: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in _RUN_FIELDS:
            raise ValueError(f"not an updatable run field: {key}")
        if key in _JSON_FIELDS:
            assignments.append(f"{key} = CAST(:{key} AS jsonb)")
            params[key] = json.dumps(value, default=str)
        elif key == "finished_at":
            assignments.append("finished_at = now()")
        else:
            assignments.append(f"{key} = :{key}")
            params[key] = value
    return assignments, params


async def create_conversation(
    factory: SessionFactory, scope: WorkspaceScope, *, persona: str, title: str
) -> uuid.UUID:
    async with scoped_session(factory, scope) as session:
        conversation_id = (
            await session.execute(
                text(
                    "INSERT INTO conversations (workspace_id, persona, title) "
                    "VALUES (:ws, :p, :t) RETURNING id"
                ),
                {"ws": scope.workspace_id, "p": persona, "t": title[:200]},
            )
        ).scalar_one()
        await session.commit()
    return uuid.UUID(str(conversation_id))


async def conversation_state(
    factory: SessionFactory, scope: WorkspaceScope, conversation_id: uuid.UUID
) -> ConversationState | None:
    async with scoped_session(factory, scope) as session:
        row = (
            await session.execute(
                text(
                    "SELECT persona, rolling_summary, recent_questions, recent_handles "
                    "FROM conversations WHERE workspace_id = :ws AND id = :id"
                ),
                {"ws": scope.workspace_id, "id": conversation_id},
            )
        ).one_or_none()
    if row is None:
        return None
    return ConversationState(conversation_id, row[0], row[1], tuple(row[2]), tuple(row[3]))


async def create_run(
    factory: SessionFactory,
    scope: WorkspaceScope,
    *,
    conversation_id: uuid.UUID,
    question: str,
    mode: str,
    persona: str,
    config_hash: str,
    prompt_version: str,
) -> uuid.UUID:
    """Insert the run (status ``running``) and the user's message in one transaction."""
    async with scoped_session(factory, scope) as session:
        run_id = (
            await session.execute(
                text(
                    "INSERT INTO query_runs (workspace_id, conversation_id, mode, persona, "
                    "original_query, config_hash, prompt_version, corpus_version_start) "
                    "VALUES (:ws, :c, :m, :p, :q, :ch, :pv, "
                    "(SELECT version FROM workspace_corpus_state WHERE workspace_id = :ws)) "
                    "RETURNING id"
                ),
                {
                    "ws": scope.workspace_id,
                    "c": conversation_id,
                    "m": mode,
                    "p": persona,
                    "q": question,
                    "ch": config_hash,
                    "pv": prompt_version,
                },
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO messages (workspace_id, conversation_id, role, content, "
                "query_run_id) VALUES (:ws, :c, 'user', :q, :r)"
            ),
            {"ws": scope.workspace_id, "c": conversation_id, "q": question, "r": run_id},
        )
        await session.execute(
            text("UPDATE conversations SET updated_at = now() WHERE id = :c"),
            {"c": conversation_id},
        )
        await session.commit()
    return uuid.UUID(str(run_id))


async def append_event(
    factory: SessionFactory,
    scope: WorkspaceScope,
    run_id: uuid.UUID,
    seq: int,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Append one event. A text-bearing event of a run whose pack lost a source to a purge is
    stored as a ``warning`` instead (same ``seq``, so replay stays gap-free): the purge already
    deleted this run's earlier events and must not be outlived by later ones."""
    async with scoped_session(factory, scope) as session:
        if event_type in TEXT_EVENT_TYPES and await _run_pack_purged(session, scope, run_id):
            keep: dict[str, Any] = {k: payload[k] for k in ("run_id", "seq", "ts") if k in payload}
            event_type, payload = "warning", {**keep, **_WITHHELD}
        await session.execute(
            text(
                "INSERT INTO run_events (workspace_id, run_id, seq, type, payload) "
                "VALUES (:ws, :r, :s, :t, CAST(:p AS jsonb))"
            ),
            {
                "ws": scope.workspace_id,
                "r": run_id,
                "s": seq,
                "t": event_type,
                "p": json.dumps(payload, default=str),
            },
        )
        await session.commit()


async def load_events(
    factory: SessionFactory, scope: WorkspaceScope, run_id: uuid.UUID, after_seq: int
) -> list[StoredEvent]:
    async with scoped_session(factory, scope) as session:
        rows = await session.execute(
            text(
                "SELECT seq, type, payload FROM run_events "
                "WHERE workspace_id = :ws AND run_id = :r AND seq > :s ORDER BY seq"
            ),
            {"ws": scope.workspace_id, "r": run_id, "s": after_seq},
        )
        return [StoredEvent(int(r[0]), str(r[1]), dict(r[2])) for r in rows.all()]


async def get_run(
    factory: SessionFactory, scope: WorkspaceScope, run_id: uuid.UUID
) -> dict[str, Any] | None:
    async with scoped_session(factory, scope) as session:
        row = (
            await session.execute(
                text(
                    "SELECT id, conversation_id, mode, status, termination_state, "
                    "degradation_flags, original_query, pack_handles, cited_handles, usage, "
                    "timings, models, context_tokens, pack_tokens, config_hash, prompt_version, "
                    "created_at, finished_at FROM query_runs "
                    "WHERE workspace_id = :ws AND id = :id"
                ),
                {"ws": scope.workspace_id, "id": run_id},
            )
        ).one_or_none()
    if row is None:
        return None
    keys = (
        "run_id",
        "conversation_id",
        "mode",
        "status",
        "termination_state",
        "degradation_flags",
        "original_query",
        "pack_handles",
        "cited_handles",
        "usage",
        "timings",
        "models",
        "context_tokens",
        "pack_tokens",
        "config_hash",
        "prompt_version",
        "created_at",
        "finished_at",
    )
    return dict(zip(keys, row, strict=True))


async def update_run(
    factory: SessionFactory, scope: WorkspaceScope, run_id: uuid.UUID, **fields: Any
) -> None:
    assignments, params = _run_assignments(fields)
    if not assignments:
        return
    params.update({"ws": scope.workspace_id, "id": run_id})
    sql = f"UPDATE query_runs SET {', '.join(assignments)} WHERE workspace_id = :ws AND id = :id"  # noqa: S608 - allowlisted columns
    async with scoped_session(factory, scope) as session:
        await session.execute(text(sql), params)
        await session.commit()


async def freeze_pack(
    factory: SessionFactory,
    scope: WorkspaceScope,
    run_id: uuid.UUID,
    *,
    items: Sequence[tuple[str, str]],
    **fields: Any,
) -> set[str]:
    """Record the run's pack (``(handle, source_code)`` pairs) as ``pack_handles``, plus any
    other run ``fields``, under a share lock on its sources. Returns the source codes purged
    since the pack was read; their handles are left out and the caller must drop those items
    before any event or model call quotes the pack."""
    if "pack_handles" in fields:
        raise ValueError("freeze_pack derives pack_handles from items")
    async with scoped_session(factory, scope) as session:
        gone = await _purged_codes(session, scope, [code for _, code in items])
        assignments, params = _run_assignments(
            {**fields, "pack_handles": [h for h, code in items if code not in gone]}
        )
        params.update({"ws": scope.workspace_id, "id": run_id})
        await session.execute(
            text(
                f"UPDATE query_runs SET {', '.join(assignments)} "  # noqa: S608 - allowlisted
                "WHERE workspace_id = :ws AND id = :id"
            ),
            params,
        )
        await session.commit()
    return gone


async def persist_answer(
    factory: SessionFactory,
    scope: WorkspaceScope,
    *,
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
    content: str,
    citations: list[dict[str, Any]],
    sections: dict[str, Any],
    status: str,
    model: str | None,
    usage: dict[str, Any],
    pack_codes: Sequence[str] = (),
) -> PersistOutcome:
    """Store a *verified* answer. Every cited **and** pack source is share-locked (the answer
    can use pack text it does not cite). If any was purged, nothing is stored; in the same
    transaction the purged sources are dropped from the run's ``pack_handles`` (so the caller's
    fallback built from the survivors can be emitted) and any text-bearing event of this run is
    deleted (defence in depth: the purge already removed them). The caller falls back."""
    codes = {c["source_code"] for c in citations} | set(pack_codes)
    async with scoped_session(factory, scope) as session:
        gone = await _purged_codes(session, scope, sorted(codes))
        if gone:
            await session.execute(
                text(
                    "UPDATE query_runs SET pack_handles = ARRAY("  # noqa: S608 - constant SQL
                    f"  SELECT h FROM unnest(pack_handles) h WHERE {_HANDLE_CODE_SQL} "
                    "  <> ALL(CAST(:gone AS text[]))) WHERE workspace_id = :ws AND id = :r"
                ),
                {"ws": scope.workspace_id, "r": run_id, "gone": sorted(gone)},
            )
            await session.execute(
                text(
                    "DELETE FROM run_events WHERE workspace_id = :ws AND run_id = :r "
                    "AND type = ANY(CAST(:types AS text[]))"
                ),
                {"ws": scope.workspace_id, "r": run_id, "types": sorted(TEXT_EVENT_TYPES)},
            )
            await session.commit()
            purged = [c["handle"] for c in citations if c["source_code"] in gone]
            return PersistOutcome(None, purged, frozenset(gone))
        message_id = (
            await session.execute(
                text(
                    "INSERT INTO messages (workspace_id, conversation_id, role, content, "
                    "citations, sections, status, query_run_id, model, usage) VALUES "
                    "(:ws, :c, 'assistant', :content, CAST(:cit AS jsonb), CAST(:sec AS jsonb), "
                    ":status, :r, :m, CAST(:u AS jsonb)) RETURNING id"
                ),
                {
                    "ws": scope.workspace_id,
                    "c": conversation_id,
                    "content": content,
                    "cit": json.dumps(citations),
                    "sec": json.dumps(sections),
                    "status": status,
                    "r": run_id,
                    "m": model,
                    "u": json.dumps(usage),
                },
            )
        ).scalar_one()
        await session.commit()
    return PersistOutcome(uuid.UUID(str(message_id)))


ConversationAdvance = Callable[[ConversationState], tuple[str, list[str], list[str]]]


async def advance_conversation_state(
    factory: SessionFactory,
    scope: WorkspaceScope,
    conversation_id: uuid.UUID,
    *,
    run_id: uuid.UUID,
    advance: ConversationAdvance,
    through_message_id: uuid.UUID | None,
) -> bool:
    """Fold a finished run into the conversation's rolling state in one transaction.

    The run's pack sources are share-locked first: if any was purged the summary is left alone
    (the purge resets it) and ``False`` is returned. The conversation row is then read
    ``FOR UPDATE`` so concurrent runs in one conversation cannot lose each other's turn."""
    async with scoped_session(factory, scope) as session:
        if await _run_pack_purged(session, scope, run_id):
            await session.rollback()
            return False
        row = (
            await session.execute(
                text(
                    "SELECT persona, rolling_summary, recent_questions, recent_handles "
                    "FROM conversations WHERE workspace_id = :ws AND id = :id FOR UPDATE"
                ),
                {"ws": scope.workspace_id, "id": conversation_id},
            )
        ).one_or_none()
        if row is None:
            await session.rollback()
            return True
        summary, questions, handles = advance(
            ConversationState(conversation_id, row[0], row[1], tuple(row[2]), tuple(row[3]))
        )
        await session.execute(
            text(
                "UPDATE conversations SET rolling_summary = :s, recent_questions = :q, "
                "recent_handles = :h, summary_through_message_id = :m, updated_at = now() "
                "WHERE workspace_id = :ws AND id = :c"
            ),
            {
                "ws": scope.workspace_id,
                "c": conversation_id,
                "s": summary,
                "q": questions,
                "h": handles,
                "m": through_message_id,
            },
        )
        await session.commit()
    return True
