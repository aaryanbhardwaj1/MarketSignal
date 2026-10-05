"""Upload registration: version resolution, idempotency, and transactional job hand-off.

Semantics (ADR-0016):
* ``source_code`` given and the source exists -> the upload is a new version of that source
  (type must match); given but unknown -> a new source with that code; absent -> a new source
  whose code is derived from the filename (suffixed on collision), unless the bytes duplicate a
  live version of another source, in which case that version is returned (``duplicate_of``).
* Bytes identical to the target source's live (current or in-flight) version -> idempotent
  no-op, the existing version is returned. Identical to a superseded/failed/purged version ->
  a new version (revert, retry-after-fix, re-add after delete).
* The version number is allocated under ``SELECT ... FOR UPDATE`` on the source row.
* Source row, version row, blob, audit event and the ingestion job are written in ONE
  transaction: the job is deferred on the same database connection, so a rollback leaves
  neither an orphan version nor an orphan job (no dual-write).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.domain.enums import (
    LIVE_STATUSES,
    Confidentiality,
    IngestErrorCode,
    SourceClass,
)
from marketsignal.evidence.handles import is_valid_source_code
from marketsignal.ingestion import repository as repo
from marketsignal.ingestion.models import IngestionError
from marketsignal.ingestion.validation import ValidatedUpload

# (raw psycopg connection, workspace_id, version_id) -> job id
DeferJob = Callable[[Any, uuid.UUID, uuid.UUID], Awaitable[int]]
_SEGMENT = 12
_MAX_SEGMENTS = 6


@dataclass(frozen=True, slots=True)
class UploadResult:
    source_id: uuid.UUID
    source_code: str
    version_id: uuid.UUID
    version: int
    status: str
    created: bool  # False: idempotent no-op (existing version returned)
    duplicate_of: str | None = None


def derive_source_code(filename: str) -> str:
    """``Northstar_Customer_Survey_2026.csv`` -> ``NORTHSTAR-CUSTOMER-SURVEY-2026``."""
    stem = PurePosixPath(filename).stem.upper()
    segments = [s[:_SEGMENT] for s in re.split(r"[^A-Z0-9]+", stem) if s][:_MAX_SEGMENTS]
    return "-".join(segments) or "SOURCE"


def _with_suffix(code: str, n: int) -> str:
    segments = code.split("-")[: _MAX_SEGMENTS - 1]
    return "-".join([*segments, str(n)])


async def _unique_code(session: AsyncSession, base: str) -> str:
    taken = set(
        (
            await session.execute(
                text(
                    "SELECT source_code FROM sources WHERE source_code = :b OR source_code LIKE :p"
                ),
                {"b": base, "p": base.rsplit("-", 1)[0] + "-%"},
            )
        ).scalars()
    )
    if base not in taken:
        return base
    n = 2
    while _with_suffix(base, n) in taken:
        n += 1
    return _with_suffix(base, n)


async def register_upload(
    session: AsyncSession,
    *,
    scope: WorkspaceScope,
    actor: str,
    upload: ValidatedUpload,
    source_class: SourceClass,
    confidentiality: Confidentiality,
    title: str | None,
    source_code: str | None,
    settings: Settings,
    defer_job: DeferJob,
) -> UploadResult:
    """Must be called inside a scoped session; commits on success."""
    content_hash = hashlib.sha256(upload.data).hexdigest()
    if source_code is not None and not is_valid_source_code(source_code):
        raise IngestionError(IngestErrorCode.UNSUPPORTED_TYPE.value, "invalid source_code")

    source = None
    if source_code is not None:
        source = (
            await session.execute(
                text(
                    "SELECT id, source_code, source_type, deleted_at FROM sources "
                    "WHERE source_code = :c FOR UPDATE"
                ),
                {"c": source_code},
            )
        ).one_or_none()
    else:
        duplicate = (
            await session.execute(
                text(
                    "SELECT s.id, s.source_code, v.id, v.version, v.status FROM source_versions v "
                    "JOIN sources s ON s.id = v.source_id WHERE v.content_hash = :h "
                    "AND v.parser_version = :p AND v.structure_version = :sv "
                    "AND v.status = ANY(:live) AND s.deleted_at IS NULL LIMIT 1"
                ),
                {
                    "h": content_hash,
                    "p": settings.parser_version,
                    "sv": settings.structure_version,
                    "live": [s.value for s in LIVE_STATUSES],
                },
            )
        ).one_or_none()
        if duplicate is not None:
            sid, code, vid, ver, status = duplicate
            return UploadResult(sid, code, vid, ver, status, created=False, duplicate_of=code)

    if source is not None and source.source_type != upload.source_type.value:
        raise IngestionError(
            IngestErrorCode.SOURCE_TYPE_MISMATCH.value,
            f"source {source.source_code} is {source.source_type}, upload is "
            f"{upload.source_type.value}",
        )
    if source is None:
        code = source_code or await _unique_code(session, derive_source_code(upload.filename))
        source_id = (
            await session.execute(
                text(
                    "INSERT INTO sources (workspace_id, source_code, title, source_type) "
                    "VALUES (:ws, :c, :t, :st) RETURNING id"
                ),
                {
                    "ws": scope.workspace_id,
                    "c": code,
                    "t": (title or PurePosixPath(upload.filename).stem)[:300],
                    "st": upload.source_type.value,
                },
            )
        ).scalar_one()
        await session.execute(
            text("SELECT id FROM sources WHERE id = :id FOR UPDATE"), {"id": source_id}
        )
    else:
        source_id, code = source.id, source.source_code
        if source.deleted_at is not None:  # re-adding a deleted source restores it
            await session.execute(
                text("UPDATE sources SET deleted_at = NULL, updated_at = now() WHERE id = :id"),
                {"id": source_id},
            )
        if title:
            await session.execute(
                text("UPDATE sources SET title = :t, updated_at = now() WHERE id = :id"),
                {"t": title[:300], "id": source_id},
            )
        live = (
            await session.execute(
                text(
                    "SELECT id, version, status FROM source_versions WHERE source_id = :s "
                    "AND content_hash = :h AND parser_version = :p AND structure_version = :sv "
                    "AND status = ANY(:live)"
                ),
                {
                    "s": source_id,
                    "h": content_hash,
                    "p": settings.parser_version,
                    "sv": settings.structure_version,
                    "live": [s.value for s in LIVE_STATUSES],
                },
            )
        ).one_or_none()
        if live is not None:
            return UploadResult(source_id, code, live.id, live.version, live.status, created=False)

    next_version = (
        await session.execute(
            text("SELECT coalesce(max(version), 0) + 1 FROM source_versions WHERE source_id = :s"),
            {"s": source_id},
        )
    ).scalar_one()
    version_id = (
        await session.execute(
            text(
                "INSERT INTO source_versions (workspace_id, source_id, version, source_class, "
                "confidentiality, content_hash, original_filename, mime_type, byte_size, "
                "parser_version, structure_version) VALUES (:ws, :s, :ver, :cls, :conf, :h, :fn, "
                ":mime, :size, :p, :sv) RETURNING id"
            ),
            {
                "ws": scope.workspace_id,
                "s": source_id,
                "ver": next_version,
                "cls": source_class.value,
                "conf": confidentiality.value,
                "h": content_hash,
                "fn": upload.filename,
                "mime": upload.mime_type,
                "size": len(upload.data),
                "p": settings.parser_version,
                "sv": settings.structure_version,
            },
        )
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO source_blobs (workspace_id, source_version_id, bytes) VALUES (:ws, :v, :b)"
        ),
        {"ws": scope.workspace_id, "v": version_id, "b": upload.data},
    )
    await repo.audit(
        session,
        scope.workspace_id,
        actor,
        "source_version.uploaded",
        f"{code}@v{next_version}",
        {"bytes": len(upload.data), "sha256": content_hash, "filename": upload.filename},
    )
    connection = await session.connection()
    raw = await connection.get_raw_connection()
    await defer_job(raw.driver_connection, scope.workspace_id, version_id)
    await session.commit()
    return UploadResult(source_id, code, version_id, next_version, "queued", created=True)
