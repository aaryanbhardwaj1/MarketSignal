"""Persistence for conversations, runs, run events and answers (migration 0004).

Every function opens its own short scoped transaction (RLS + explicit workspace predicate).

Purge always wins (ADR-0016). Nothing a run stores may outlive the purge of a source version
in its frozen evidence pack (``query_runs.pack_handles``). Purge state is read from
``source_versions.status = 'purged'`` for the pack's *versions*, never from
``sources.deleted_at``: re-uploading a purged source restores the source row but leaves the
purged version purged, so a pack frozen on ``X@v1`` stays guarded after ``X@v2`` arrives.

``ingestion.purge.purge_source`` runs in one transaction: ``FOR UPDATE`` on the source row,
versions marked purged, then (``_purge_run_artifacts``) ``FOR UPDATE`` on every
``query_runs`` row whose pack includes the source, and only then the conversation reset, the
answer redaction and the run-event delete. The run side locks per run, never shared rows:

* **Freezing the pack** (``freeze_pack``, once per run) share-locks the pack's ``sources``
  rows, then reads the versions' purge state, then writes ``pack_handles``. If the purge holds
  the source lock, the freeze waits until it commits and then sees the purged version (each
  READ COMMITTED statement takes a new snapshot), so it drops it. If the freeze holds the lock,
  the purge waits at its first statement and its later ``query_runs`` lock sees the committed
  ``pack_handles``. So either the purge locks this run, or the freeze has dropped the source.
  Nothing can quote the pack before this commits.
* **Every later write that can carry evidence text** (``append_event`` for token / citation /
  final, ``persist_answer``, ``advance_conversation_state``) first takes ``FOR KEY SHARE`` on
  the run's own ``query_runs`` row (it conflicts with the purge's ``FOR UPDATE``), *then* reads
  the pack versions' purge state, then writes, all in one transaction. If the write gets the
  lock first, the purge waits for it to commit, and the purge's redaction, reset and delete
  statements (run later, with later snapshots) remove what it wrote. If the purge gets the lock
  first, the write waits until the purge commits and then sees the purged version, so it
  withholds the text.

The source rows are therefore never locked per token. The only contention is a run with
itself, or with a purge that actually concerns it.
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
        "route",
        "agent",
        "tool_calls",
    }
)
_JSON_FIELDS = frozenset({"models", "usage", "timings", "route", "agent"})
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


# Version number of a canonical handle "WS/CODE@vN:LOCATOR".
_HANDLE_VERSION_SQL = "CAST(split_part(split_part(h, '@v', 2), ':', 1) AS integer)"


async def _purged_pack_codes(
    session: AsyncSession, scope: WorkspaceScope, handles: Sequence[str]
) -> set[str]:
    """Source codes whose version behind any of ``handles`` is purged (callers hold a lock that
    orders this read after any purge of those versions; see the module docstring)."""
    if not handles:
        return set()
    rows = await session.execute(
        text(
            f"SELECT DISTINCT s.source_code FROM unnest(CAST(:handles AS text[])) h "  # noqa: S608 - constant SQL
            f"JOIN sources s ON s.workspace_id = :ws AND s.source_code = {_HANDLE_CODE_SQL} "
            "JOIN source_versions v ON v.source_id = s.id "
            f"AND v.version = {_HANDLE_VERSION_SQL} WHERE v.status = 'purged'"
        ),
        {"ws": scope.workspace_id, "handles": sorted(set(handles))},
    )
    return {str(r[0]) for r in rows.all()}


async def _lock_run_pack(
    session: AsyncSession, scope: WorkspaceScope, run_id: uuid.UUID
) -> list[str]:
    """``FOR KEY SHARE`` on the run's own row (conflicts only with a purge's ``FOR UPDATE`` of
    it); returns its frozen pack handles."""
    handles = (
        await session.execute(
            text(
                "SELECT pack_handles FROM query_runs WHERE workspace_id = :ws AND id = :r "
                "FOR KEY SHARE"
            ),
            {"ws": scope.workspace_id, "r": run_id},
        )
    ).scalar_one_or_none()
    return list(handles or [])


async def _run_pack_purged(session: AsyncSession, scope: WorkspaceScope, run_id: uuid.UUID) -> bool:
    """Lock the run's row, then: was any version in its frozen pack purged?"""
    handles = await _lock_run_pack(session, scope, run_id)
    return bool(await _purged_pack_codes(session, scope, handles))


async def run_pack_purged(session: AsyncSession, scope: WorkspaceScope, run_id: uuid.UUID) -> bool:
    """Public form of the run-side purge guard for other text-bearing writers (verification
    reports): ``FOR KEY SHARE`` on the run row, then the pack's version purge state, in the
    caller's transaction (module docstring: either purge sees the write or the write sees the
    purge)."""
    return await _run_pack_purged(session, scope, run_id)


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
    route: dict[str, Any] | None = None,
) -> uuid.UUID:
    """Insert the run (status ``running``, with its route decision) and the user's message in
    one transaction."""
    async with scoped_session(factory, scope) as session:
        run_id = (
            await session.execute(
                text(
                    "INSERT INTO query_runs (workspace_id, conversation_id, mode, persona, "
                    "original_query, config_hash, prompt_version, route, corpus_version_start) "
                    "VALUES (:ws, :c, :m, :p, :q, :ch, :pv, CAST(:route AS jsonb), "
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
                    "route": json.dumps(route or {}),
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
    *,
    run_fields: dict[str, Any] | None = None,
) -> str | None:
    """Append one event; returns the type actually stored, or ``None`` when nothing was stored
    because the run's log already ends with ``done`` (nothing, not even a second ``done``, may
    follow it).

    ``run_fields`` (``done`` only) finishes the ``query_runs`` row in the same transaction as
    the ``done`` row, so a reader who sees ``done`` also sees the final status and usage.

    A text-bearing event of a run whose pack lost a version to a purge is stored as a
    ``SOURCE_DELETED_DURING_RUN`` ``warning`` instead (same ``seq``): the purge already deleted
    this run's earlier events and must not be outlived by later ones."""
    async with scoped_session(factory, scope) as session:
        if event_type in TEXT_EVENT_TYPES and await _run_pack_purged(session, scope, run_id):
            keep: dict[str, Any] = {k: payload[k] for k in ("run_id", "seq", "ts") if k in payload}
            event_type, payload = "warning", {**keep, **_WITHHELD}
        stored = (
            await session.execute(
                text(
                    "INSERT INTO run_events (workspace_id, run_id, seq, type, payload) "
                    "SELECT :ws, :r, :s, :t, CAST(:p AS jsonb) WHERE NOT EXISTS ("
                    "  SELECT 1 FROM run_events WHERE workspace_id = :ws AND run_id = :r "
                    "  AND type = 'done') RETURNING type"
                ),
                {
                    "ws": scope.workspace_id,
                    "r": run_id,
                    "s": seq,
                    "t": event_type,
                    "p": json.dumps(payload, default=str),
                },
            )
        ).scalar_one_or_none()
        if stored == "done" and run_fields:
            assignments, params = _run_assignments(run_fields)
            params.update({"ws": scope.workspace_id, "id": run_id})
            await session.execute(
                text(
                    f"UPDATE query_runs SET {', '.join(assignments)} "  # noqa: S608 - allowlisted
                    "WHERE workspace_id = :ws AND id = :id"
                ),
                params,
            )
        await session.commit()
    return None if stored is None else str(stored)


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
                    "created_at, finished_at, route, agent, tool_calls FROM query_runs "
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
        "route",
        "agent",
        "tool_calls",
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
    other run ``fields``, under a share lock on its sources. Returns the source codes whose
    pack version was purged since the pack was read; their handles are left out and the caller
    must drop those items before any event or model call quotes the pack."""
    if "pack_handles" in fields:
        raise ValueError("freeze_pack derives pack_handles from items")
    async with scoped_session(factory, scope) as session:
        codes = sorted({code for _, code in items})
        if codes:  # serialises with purge_source's FOR UPDATE on the source row
            await session.execute(
                text(
                    "SELECT id FROM sources WHERE workspace_id = :ws "
                    "AND source_code = ANY(CAST(:codes AS text[])) ORDER BY id FOR SHARE"
                ),
                {"ws": scope.workspace_id, "codes": codes},
            )
        gone = await _purged_pack_codes(session, scope, [h for h, _ in items])
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
) -> PersistOutcome:
    """Store a *verified* answer, unless a version of any pack **or** cited source was purged
    (the answer can use pack text it does not cite; the run row is locked first, see the module
    docstring). Then nothing is stored; in the same
    transaction the purged sources are dropped from the run's ``pack_handles`` (so the caller's
    fallback built from the survivors can be emitted) and any text-bearing event of this run is
    deleted (defence in depth: the purge already removed them). The caller falls back."""
    async with scoped_session(factory, scope) as session:
        pack = await _lock_run_pack(session, scope, run_id)
        gone = await _purged_pack_codes(session, scope, [*pack, *(c["handle"] for c in citations)])
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

    The run's row is locked first: if a version in its pack was purged the summary is left alone
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
