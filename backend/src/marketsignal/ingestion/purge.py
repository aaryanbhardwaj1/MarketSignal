"""Source deletion = content purge (ADR-0016: privacy wins over immutability).

In one transaction: every version's derived content (parents -> children -> embeddings,
dataset tables -> rows) and raw blob is deleted; versions become ``purged`` with filename and
content hash nulled; the source keeps code/title/version numbers so its handles resolve to a
410 tombstone; the corpus version is bumped (cache invalidation); an audit event is written.
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
    # Answers and token events can quote the purged text (migration 0004): redact assistant
    # answers that cited this source (their handles stay and resolve to the 410 tombstone) and
    # delete the event logs of runs whose evidence pack included it.
    handle_prefix = f"{scope.workspace_code}/{source.source_code}@v%"
    await session.execute(
        text(
            "UPDATE messages SET content = :redacted, sections = '{}'::jsonb, status = 'redacted' "
            "WHERE workspace_id = :ws AND role = 'assistant' AND EXISTS ("
            "  SELECT 1 FROM jsonb_array_elements(citations) c "
            "  WHERE c->>'source_code' = :code)"
        ),
        {"ws": scope.workspace_id, "code": source.source_code, "redacted": REDACTED_ANSWER},
    )
    await session.execute(
        text(
            "DELETE FROM run_events WHERE workspace_id = :ws AND run_id IN ("
            "  SELECT id FROM query_runs WHERE workspace_id = :ws AND EXISTS ("
            "    SELECT 1 FROM unnest(pack_handles) h WHERE h LIKE :prefix))"
        ),
        {"ws": scope.workspace_id, "prefix": handle_prefix},
    )
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
