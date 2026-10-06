"""Source deletion = content purge (ADR-0016: privacy wins over immutability).

In one transaction: every version's derived content (parents -> children -> embeddings,
dataset tables -> rows) and raw blob is deleted; versions become ``purged`` with filename and
content hash nulled; the source keeps code/title/version numbers so its handles resolve to a
410 tombstone; the corpus version is bumped (cache invalidation); an audit event is written.
Everything runs and answers stored that can quote the purged text goes in the same transaction
(``_purge_run_artifacts``); ``runs.store`` explains why a run in flight cannot outlive it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.db.scope import WorkspaceScope
from marketsignal.ingestion import repository as repo

REDACTED_ANSWER = (
    "This answer was removed because a source it cited was deleted from the workspace."
)


@dataclass(frozen=True, slots=True)
class PurgeResult:
    source_code: str
    versions_purged: int
    corpus_version: int


async def purge_source(
    session: AsyncSession, scope: WorkspaceScope, source_id: uuid.UUID, actor: str
) -> PurgeResult | None:
    source = (
        await session.execute(
            text("SELECT source_code FROM sources WHERE id = :id FOR UPDATE"), {"id": source_id}
        )
    ).one_or_none()
    if source is None:
        return None
    version_ids = list(
        (
            await session.execute(
                text("SELECT id FROM source_versions WHERE source_id = :s"), {"s": source_id}
            )
        ).scalars()
    )
    for version_id in version_ids:
        await repo.delete_version_content(session, version_id)
    await session.execute(
        text("DELETE FROM source_blobs WHERE source_version_id = ANY(:ids)"), {"ids": version_ids}
    )
    await session.execute(
        text(
            "UPDATE source_versions SET status = 'purged', content_hash = NULL, "
            "original_filename = NULL, error_detail = NULL, updated_at = now() "
            "WHERE source_id = :s"
        ),
        {"s": source_id},
    )
    await session.execute(
        text("UPDATE sources SET deleted_at = now(), updated_at = now() WHERE id = :s"),
        {"s": source_id},
    )
    await _purge_run_artifacts(session, scope, source.source_code)
    corpus_version = await repo.bump_corpus_version(session, scope.workspace_id)
    await repo.audit(
        session,
        scope.workspace_id,
        actor,
        "source.purged",
        source.source_code,
        {"versions": len(version_ids), "corpus_version": corpus_version},
    )
    await session.commit()
    return PurgeResult(source.source_code, len(version_ids), corpus_version)


# Runs whose frozen evidence pack (query_runs.pack_handles) included the purged source.
_PACK_RUNS = (
    "SELECT id FROM query_runs WHERE workspace_id = :ws AND EXISTS ("
    "  SELECT 1 FROM unnest(pack_handles) h WHERE h LIKE :prefix)"
)
_DELETE_ATTEMPTS = (
    f"DELETE FROM verification_attempts WHERE workspace_id = :ws AND query_run_id IN ({_PACK_RUNS})"  # noqa: S608 - constant SQL
)


async def _purge_run_artifacts(
    session: AsyncSession, scope: WorkspaceScope, source_code: str
) -> None:
    """Remove every stored quote of, or citation to, the purged source's evidence.

    * Conversations: the rolling summary (fed to later prompts) and recent questions/handles
      are reset wherever the source could have reached them: a run whose pack included it, an
      answer citing it, or a recent handle of it.
    * Assistant answers whose run's pack included the source (an answer can use pack text it
      does not cite) or that cite it are redacted; citation cards of the source become
      tombstones ``{handle, source_code, purged}`` (the handle resolves to the 410 tombstone).
    * The event logs of runs whose pack included it are deleted (tokens, citations, final).
    """
    params = {
        "ws": scope.workspace_id,
        "code": source_code,
        "prefix": f"{scope.workspace_code}/{source_code}@v%",
    }
    # Lock the affected runs before touching anything they write: a run's text-bearing write
    # holds FOR KEY SHARE on its own row while it re-checks the pack's purge state, so it either
    # commits before this lock (and the statements below remove what it wrote) or waits for this
    # transaction and then sees the purged version (runs.store module docstring).
    await session.execute(text(f"{_PACK_RUNS} ORDER BY id FOR UPDATE"), params)
    await session.execute(
        text(
            "UPDATE conversations c SET rolling_summary = '', recent_questions = '{}', "  # noqa: S608 - constant SQL
            "recent_handles = '{}', summary_through_message_id = NULL, updated_at = now() "
            "WHERE c.workspace_id = :ws AND ("
            f"  c.id IN (SELECT conversation_id FROM query_runs WHERE id IN ({_PACK_RUNS}))"
            "  OR EXISTS (SELECT 1 FROM unnest(c.recent_handles) h WHERE h LIKE :prefix)"
            "  OR EXISTS (SELECT 1 FROM messages m, jsonb_array_elements(m.citations) e"
            "    WHERE m.workspace_id = :ws AND m.conversation_id = c.id"
            "    AND e->>'source_code' = :code))"
        ),
        params,
    )
    await session.execute(
        text(
            "UPDATE messages m SET content = :redacted, sections = '{}'::jsonb, "  # noqa: S608 - constant SQL
            "status = 'redacted', citations = COALESCE(("
            "  SELECT jsonb_agg(CASE WHEN e.card->>'source_code' = :code THEN "
            "    jsonb_build_object('handle', e.card->'handle', "
            "      'source_code', e.card->'source_code', 'purged', true) "
            "    ELSE e.card END ORDER BY e.pos) "
            "  FROM jsonb_array_elements(m.citations) WITH ORDINALITY AS e(card, pos)"
            "), '[]'::jsonb) "
            "WHERE m.workspace_id = :ws AND m.role = 'assistant' AND ("
            f"  m.query_run_id IN ({_PACK_RUNS})"
            "  OR EXISTS (SELECT 1 FROM jsonb_array_elements(m.citations) c"
            "    WHERE c->>'source_code' = :code))"
        ),
        {**params, "redacted": REDACTED_ANSWER},
    )
    await session.execute(
        text(f"DELETE FROM run_events WHERE workspace_id = :ws AND run_id IN ({_PACK_RUNS})"),  # noqa: S608 - constant SQL
        params,
    )
    # Verification reports quote rejected model spans, which can quote the purged evidence.
    await session.execute(
        text(_DELETE_ATTEMPTS),
        params,
    )
