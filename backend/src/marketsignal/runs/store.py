"""Persistence for conversations, runs, run events and answers (migration 0004).

Every function opens its own short scoped transaction (RLS + explicit workspace predicate).
``persist_answer`` share-locks every cited source row (``FOR SHARE``), the same rule ingestion
uses against purge (ADR-0016): either the answer commits first and a later purge redacts it,
or the purge committed first and the caller is told which cited handles are gone so it can
fall back instead of storing a citation to deleted evidence.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

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


@dataclass
class PersistOutcome:
    message_id: uuid.UUID | None
    purged_handles: list[str] = field(default_factory=list)


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
    async with scoped_session(factory, scope) as session:
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
    assignments: list[str] = []
    params: dict[str, Any] = {"ws": scope.workspace_id, "id": run_id}
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
    if not assignments:
        return
    sql = f"UPDATE query_runs SET {', '.join(assignments)} WHERE workspace_id = :ws AND id = :id"  # noqa: S608 - allowlisted columns
    async with scoped_session(factory, scope) as session:
        await session.execute(text(sql), params)
        await session.commit()


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
) -> PersistOutcome:
    """Store a *verified* answer. Cited sources are share-locked; if any was purged, nothing is
    stored and the purged handles are returned so the caller can fall back."""
    codes = sorted({c["source_code"] for c in citations})
    async with scoped_session(factory, scope) as session:
        if codes:
            rows = (
                await session.execute(
                    text(
                        "SELECT source_code, deleted_at FROM sources WHERE workspace_id = :ws "
                        "AND source_code = ANY(CAST(:codes AS text[])) ORDER BY id FOR SHARE"
                    ),
                    {"ws": scope.workspace_id, "codes": codes},
                )
            ).all()
            alive = {r[0] for r in rows if r[1] is None}
            gone = [c["handle"] for c in citations if c["source_code"] not in alive]
            if gone:
                await session.rollback()
                return PersistOutcome(None, gone)
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


async def update_conversation_state(
    factory: SessionFactory,
    scope: WorkspaceScope,
    conversation_id: uuid.UUID,
    *,
    summary: str,
    recent_questions: list[str],
    recent_handles: list[str],
    through_message_id: uuid.UUID | None,
) -> None:
    async with scoped_session(factory, scope) as session:
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
                "q": recent_questions,
                "h": recent_handles,
                "m": through_message_id,
            },
        )
        await session.commit()
