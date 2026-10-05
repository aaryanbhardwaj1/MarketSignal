"""SQL for the evidence model. Every function takes a *scoped* session (RLS applies).

Writes that must be atomic are grouped by the caller into one transaction; this module never
commits on its own.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.domain.enums import VersionStatus
from marketsignal.ingestion.models import ChildDraft, DatasetTable, ParentDraft
from marketsignal.providers.embeddings import Vector


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class VersionRow:
    id: uuid.UUID
    workspace_id: uuid.UUID
    source_id: uuid.UUID
    source_code: str
    title: str
    source_type: str
    version: int
    source_class: str
    confidentiality: str
    status: str
    attempts: int
    content_hash: str | None
    parser_version: str
    structure_version: str
    source_deleted_at: datetime | None


_VERSION_SELECT = """
    SELECT v.id, v.workspace_id, v.source_id, s.source_code, s.title, s.source_type, v.version,
           v.source_class, v.confidentiality, v.status, v.attempts, v.content_hash,
           v.parser_version, v.structure_version, s.deleted_at
    FROM source_versions v JOIN sources s ON s.id = v.source_id
"""


async def get_version(
    session: AsyncSession, version_id: uuid.UUID, *, for_update: bool = False
) -> VersionRow | None:
    sql = _VERSION_SELECT + " WHERE v.id = :id" + (" FOR UPDATE OF v" if for_update else "")
    row = (await session.execute(text(sql), {"id": version_id})).one_or_none()
    return VersionRow(*row) if row else None


async def set_status(
    session: AsyncSession, version_id: uuid.UUID, status: VersionStatus, **fields: Any
) -> None:
    assignments = ["status = :status", "updated_at = now()"]
    params: dict[str, Any] = {"id": version_id, "status": status.value}
    for key, value in fields.items():
        if key not in _UPDATABLE:
            raise ValueError(f"not an updatable version field: {key}")
        # CAST(:x AS jsonb), not :x::jsonb - text() does not bind a name followed by "::".
        is_json = key in ("timings", "health")
        assignments.append(f"{key} = CAST(:{key} AS jsonb)" if is_json else f"{key} = :{key}")
        params[key] = json.dumps(value) if is_json else value
    sql = f"UPDATE source_versions SET {', '.join(assignments)} WHERE id = :id"  # noqa: S608 - allowlisted columns
    await session.execute(text(sql), params)


_UPDATABLE = frozenset(
    {
        "error_code",
        "error_detail",
        "warnings",
        "attempts",
        "started_at",
        "ready_at",
        "chunking_policy_version",
        "embedding_model",
        "parent_count",
        "child_count",
        "health",
        "timings",
    }
)


async def load_blob(session: AsyncSession, version_id: uuid.UUID) -> bytes:
    row = await session.execute(
        text("SELECT bytes FROM source_blobs WHERE source_version_id = :id"), {"id": version_id}
    )
    data: bytes = row.scalar_one()
    return bytes(data)


async def insert_parents(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    version_id: uuid.UUID,
    parents: Sequence[ParentDraft],
    handles: Sequence[str],
    labels: Sequence[str],
    token_counts: Sequence[int],
) -> list[uuid.UUID]:
    rows = [
        {
            "ws": workspace_id,
            "v": version_id,
            "handle": handle,
            "ordinal": ordinal,
            "locator": json.dumps(
                {
                    "units": [[kind.value, index] for kind, index in parent.locator],
                    **parent.locator_meta,
                }
            ),
            "label": label,
            "heading": list(parent.heading_path),
            "text": parent.text,
            "tokens": tokens,
            "hash": sha256_text(parent.text),
            "list_group": parent.list_group_id,
            "metadata": json.dumps({"kind": parent.kind.value, **parent.metadata}),
        }
        for ordinal, (parent, handle, label, tokens) in enumerate(
            zip(parents, handles, labels, token_counts, strict=True)
        )
    ]
    if rows:
        await session.execute(
            text(
                "INSERT INTO parent_chunks (workspace_id, source_version_id, handle, ordinal, "
                "locator, locator_label, heading_path, text, token_count, content_hash, "
                "list_group_id, metadata) VALUES (:ws, :v, :handle, :ordinal, "
                "CAST(:locator AS jsonb), :label, :heading, :text, :tokens, :hash, :list_group, "
                "CAST(:metadata AS jsonb))"
            ),
            rows,
        )
    result = await session.execute(
        text("SELECT id FROM parent_chunks WHERE source_version_id = :v ORDER BY ordinal"),
        {"v": version_id},
    )
    return [r[0] for r in result]


async def insert_children(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    version: VersionRow,
    parent_ids: Sequence[uuid.UUID],
    children: Sequence[ChildDraft],
    chunking_policy_version: str,
) -> list[uuid.UUID]:
    rows = [
        {
            "ws": workspace_id,
            "p": parent_ids[child.parent_ordinal],
            "v": version.id,
            "cls": version.source_class,
            "conf": version.confidentiality,
            "ordinal": child.ordinal,
            "kind": child.kind.value,
            "text": child.text,
            "heading": child.heading_text,
            "cs": child.char_start,
            "ce": child.char_end,
            "tokens": child.token_count,
            "hash": sha256_text(child.text),
            "policy": chunking_policy_version,
        }
        for child in children
    ]
    if rows:
        await session.execute(
            text(
                "INSERT INTO child_chunks (workspace_id, parent_id, source_version_id, "
                "source_class, confidentiality, ordinal, kind, text, heading_text, char_start, "
                "char_end, token_count, text_sha256, chunking_policy_version) VALUES (:ws, :p, "
                ":v, :cls, :conf, :ordinal, :kind, :text, :heading, :cs, :ce, :tokens, :hash, "
                ":policy)"
            ),
            rows,
        )
    result = await session.execute(
        text(
            "SELECT c.id FROM child_chunks c JOIN parent_chunks p ON p.id = c.parent_id "
            "WHERE c.source_version_id = :v ORDER BY p.ordinal, c.ordinal"
        ),
        {"v": version.id},
    )
    return [r[0] for r in result]


def vector_literal(vector: Vector) -> str:
    return "[" + ",".join(f"{float(x):.7g}" for x in vector) + "]"


async def insert_embeddings(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    child_ids: Sequence[uuid.UUID],
    vectors: Sequence[Vector],
    input_hashes: Sequence[str],
    model_id: str,
) -> None:
    rows = [
        {"c": cid, "ws": workspace_id, "m": model_id, "e": vector_literal(vec), "h": h}
        for cid, vec, h in zip(child_ids, vectors, input_hashes, strict=True)
    ]
    if rows:
        await session.execute(
            text(
                "INSERT INTO chunk_embeddings (child_id, workspace_id, model_id, embedding, "
                "embed_input_sha256) VALUES (:c, :ws, :m, CAST(:e AS vector), :h)"
            ),
            rows,
        )


async def insert_datasets(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    version_id: uuid.UUID,
    tables: Sequence[DatasetTable],
    row_handle: Any,
) -> None:
    for table in tables:
        columns = [
            {
                "name": c.name,
                "type": c.type,
                "role": c.role,
                "non_empty": c.non_empty,
                "distinct": c.distinct,
                "levels": list(c.levels),
            }
            for c in table.columns
        ]
        table_id = (
            await session.execute(
                text(
                    "INSERT INTO dataset_tables (workspace_id, source_version_id, sheet_ordinal, "
                    "name, header_row, columns, row_count) VALUES (:ws, :v, :ord, :name, :hdr, "
                    "CAST(:cols AS jsonb), :n) RETURNING id"
                ),
                {
                    "ws": workspace_id,
                    "v": version_id,
                    "ord": table.sheet_ordinal,
                    "name": table.name,
                    "hdr": table.header_row,
                    "cols": json.dumps(columns),
                    "n": len(table.rows),
                },
            )
        ).scalar_one()
        rows = [
            {
                "ws": workspace_id,
                "t": table_id,
                "n": number,
                "h": row_handle(table.sheet_ordinal, number),
                "vals": json.dumps(values, default=str),
            }
            for number, values in table.rows
        ]
        if rows:
            await session.execute(
                text(
                    "INSERT INTO dataset_rows (workspace_id, table_id, row_number, parent_handle, "
                    "values) VALUES (:ws, :t, :n, :h, CAST(:vals AS jsonb))"
                ),
                rows,
            )


async def audit(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    actor: str,
    action: str,
    target: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            "INSERT INTO audit_events (workspace_id, actor, action, target, metadata) "
            "VALUES (:ws, :actor, :action, :target, CAST(:meta AS jsonb))"
        ),
        {
            "ws": workspace_id,
            "actor": actor,
            "action": action,
            "target": target,
            "meta": json.dumps(metadata or {}, default=str),
        },
    )


async def bump_corpus_version(session: AsyncSession, workspace_id: uuid.UUID) -> int:
    result = await session.execute(
        text(
            "INSERT INTO workspace_corpus_state (workspace_id, version) VALUES (:ws, 1) "
            "ON CONFLICT (workspace_id) DO UPDATE SET version = workspace_corpus_state.version + 1 "
            "RETURNING version"
        ),
        {"ws": workspace_id},
    )
    version: int = result.scalar_one()
    return version


async def delete_version_content(session: AsyncSession, version_id: uuid.UUID) -> None:
    """Remove derived content of one version (children/embeddings cascade from parents)."""
    await session.execute(
        text("DELETE FROM parent_chunks WHERE source_version_id = :v"), {"v": version_id}
    )
    await session.execute(
        text("DELETE FROM dataset_tables WHERE source_version_id = :v"), {"v": version_id}
    )
