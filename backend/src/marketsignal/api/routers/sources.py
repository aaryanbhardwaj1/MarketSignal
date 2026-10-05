"""Sources: upload (202, transactional job hand-off), list/status, detail, purge, retry."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from sqlalchemy import text

from marketsignal.api.deps import Factory, Principal, Scope, SettingsDep
from marketsignal.api.errors import AppError
from marketsignal.db.session import scoped_session
from marketsignal.domain.enums import Confidentiality, IngestErrorCode, SourceClass, VersionStatus
from marketsignal.ingestion import repository as repo
from marketsignal.ingestion.models import IngestionError
from marketsignal.ingestion.purge import purge_source
from marketsignal.ingestion.uploads import register_upload
from marketsignal.ingestion.validation import validate_upload

router = APIRouter(prefix="/api/workspaces/{ws}/sources", tags=["sources"])
_READ_CHUNK = 1024 * 1024

_VERSION_COLUMNS = (
    "v.id, v.version, v.status, v.source_class, v.confidentiality, v.original_filename, "
    "v.byte_size, v.error_code, v.error_detail, v.warnings, v.parent_count, v.child_count, "
    "v.embedding_model, v.timings, v.health, v.created_at, v.ready_at, v.attempts"
)


_LIST_SQL = (
    "SELECT s.id AS source_id, s.source_code, s.title, s.source_type, s.deleted_at, "  # noqa: S608 - constants
    "s.current_version_id, " + _VERSION_COLUMNS + " FROM sources s JOIN LATERAL ("
    " SELECT * FROM source_versions WHERE source_id = s.id ORDER BY version DESC LIMIT 1"
    ") v ON true ORDER BY s.source_code"
)


def _version_dict(row: Any) -> dict[str, Any]:
    return {
        "version_id": str(row.id),
        "version": row.version,
        "status": row.status,
        "source_class": row.source_class,
        "confidentiality": row.confidentiality,
        "original_filename": row.original_filename,
        "byte_size": row.byte_size,
        "error_code": row.error_code,
        "error_detail": row.error_detail,
        "warnings": list(row.warnings or []),
        "parent_count": row.parent_count,
        "child_count": row.child_count,
        "embedding_model": row.embedding_model,
        "timings": row.timings,
        "health": row.health,
        "attempts": row.attempts,
        "created_at": row.created_at.isoformat(),
        "ready_at": row.ready_at.isoformat() if row.ready_at else None,
    }


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    """Read at most limit+1 bytes: never trust Content-Length, never buffer unbounded input."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_READ_CHUNK):
        total += len(chunk)
        if total > limit:
            raise IngestionError(
                IngestErrorCode.FILE_TOO_LARGE.value, "file exceeds the upload size limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", status_code=202)
async def upload_source(
    request: Request,
    response: Response,
    scope: Scope,
    factory: Factory,
    settings: SettingsDep,
    principal: Principal,
    file: Annotated[UploadFile, File()],
    source_class: Annotated[SourceClass, Form()],
    confidentiality: Annotated[Confidentiality, Form()] = Confidentiality.INTERNAL,
    title: Annotated[str | None, Form(max_length=300)] = None,
    source_code: Annotated[str | None, Form(max_length=80)] = None,
) -> dict[str, Any]:
    data = await _read_limited(file, settings.upload_max_bytes)
    upload = validate_upload(file.filename, data, settings)  # raises -> 4xx with error code
    async with scoped_session(factory, scope) as session:
        result = await register_upload(
            session,
            scope=scope,
            actor=principal,
            upload=upload,
            source_class=source_class,
            confidentiality=confidentiality,
            title=title,
            source_code=source_code,
            settings=settings,
            defer_job=request.app.state.defer_job,
        )
    if not result.created:
        response.status_code = 200
    return {
        "source_id": str(result.source_id),
        "source_code": result.source_code,
        "version_id": str(result.version_id),
        "version": result.version,
        "status": result.status,
        "created": result.created,
        "duplicate_of": result.duplicate_of,
        "status_url": f"/api/workspaces/{scope.workspace_code}/sources/{result.source_id}",
    }


@router.get("")
async def list_sources(scope: Scope, factory: Factory) -> list[dict[str, Any]]:
    """Each source with its current (active) version and its latest attempt."""
    async with scoped_session(factory, scope) as session:
        rows = await session.execute(text(_LIST_SQL))
        out = []
        for row in rows:
            latest = _version_dict(row)
            out.append(
                {
                    "source_id": str(row.source_id),
                    "source_code": row.source_code,
                    "title": row.title,
                    "source_type": row.source_type,
                    "deleted": row.deleted_at is not None,
                    "current_version_id": str(row.current_version_id)
                    if row.current_version_id
                    else None,
                    "latest": latest,
                }
            )
        return out


@router.get("/{source_id}")
async def get_source(scope: Scope, factory: Factory, source_id: uuid.UUID) -> dict[str, Any]:
    async with scoped_session(factory, scope) as session:
        source = (
            await session.execute(
                text(
                    "SELECT id, source_code, title, source_type, current_version_id, deleted_at, "
                    "created_at FROM sources WHERE id = :id"
                ),
                {"id": source_id},
            )
        ).one_or_none()
        if source is None:
            raise AppError(404, "SOURCE_NOT_FOUND", "source not found")
        versions = await session.execute(
            text(
                f"SELECT {_VERSION_COLUMNS} FROM source_versions v WHERE v.source_id = :id "  # noqa: S608 - constant columns
                f"ORDER BY v.version DESC"
            ),
            {"id": source_id},
        )
        return {
            "source_id": str(source.id),
            "source_code": source.source_code,
            "title": source.title,
            "source_type": source.source_type,
            "deleted": source.deleted_at is not None,
            "current_version_id": str(source.current_version_id)
            if source.current_version_id
            else None,
            "versions": [_version_dict(v) for v in versions],
        }


@router.delete("/{source_id}")
async def delete_source(
    scope: Scope, factory: Factory, principal: Principal, source_id: uuid.UUID
) -> dict[str, Any]:
    async with scoped_session(factory, scope) as session:
        result = await purge_source(session, scope, source_id, principal)
    if result is None:
        raise AppError(404, "SOURCE_NOT_FOUND", "source not found")
    return {
        "source_code": result.source_code,
        "versions_purged": result.versions_purged,
        "corpus_version": result.corpus_version,
        "status": VersionStatus.PURGED.value,
    }


@router.post("/{source_id}/retry", status_code=202)
async def retry_source(
    request: Request, scope: Scope, factory: Factory, principal: Principal, source_id: uuid.UUID
) -> dict[str, Any]:
    """Re-queue the latest version if it failed (e.g. after fixing an embedder outage)."""
    async with scoped_session(factory, scope) as session:
        latest = (
            await session.execute(
                text(
                    "SELECT v.id, v.version, v.status FROM source_versions v JOIN sources s "
                    "ON s.id = v.source_id WHERE s.id = :id AND s.deleted_at IS NULL "
                    "ORDER BY v.version DESC LIMIT 1 FOR UPDATE OF v"
                ),
                {"id": source_id},
            )
        ).one_or_none()
        if latest is None:
            raise AppError(404, "SOURCE_NOT_FOUND", "source not found")
        if latest.status != VersionStatus.FAILED.value:
            raise AppError(409, "NOT_RETRYABLE", f"latest version is {latest.status}")
        await repo.set_status(
            session, latest.id, VersionStatus.QUEUED, error_code=None, error_detail=None
        )
        await repo.audit(
            session, scope.workspace_id, principal, "source_version.retried", str(latest.id)
        )
        connection = await session.connection()
        raw = await connection.get_raw_connection()
        await request.app.state.defer_job(raw.driver_connection, scope.workspace_id, latest.id)
        await session.commit()
    return {"version_id": str(latest.id), "version": latest.version, "status": "queued"}
