"""Evidence resolution endpoint: ``GET /api/workspaces/{ws}/evidence/{handle}``.

The handle contains ``/``, so the route uses a ``path`` converter; clients may send it raw or
percent-encoded. Error contract: 400 MALFORMED_HANDLE, 404 EVIDENCE_NOT_FOUND (also for another
workspace's handle), 410 SOURCE_DELETED (tombstone).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from marketsignal.api.deps import Factory, Scope
from marketsignal.api.errors import AppError
from marketsignal.db.session import scoped_session
from marketsignal.evidence.handles import MalformedHandleError
from marketsignal.evidence.resolver import (
    EvidenceDeletedError,
    EvidenceNotFoundError,
    resolve_evidence,
)

router = APIRouter(prefix="/api/workspaces/{ws}/evidence", tags=["evidence"])


@router.get("/{handle:path}")
async def get_evidence(
    scope: Scope, factory: Factory, handle: str, child_id: uuid.UUID | None = None
) -> dict[str, Any]:
    try:
        async with scoped_session(factory, scope) as session:
            resolved = await resolve_evidence(session, scope, handle, child_id=child_id)
    except MalformedHandleError as exc:
        raise AppError(400, "MALFORMED_HANDLE", "not a canonical evidence handle") from exc
    except EvidenceNotFoundError as exc:
        raise AppError(404, "EVIDENCE_NOT_FOUND", "evidence not found") from exc
    except EvidenceDeletedError as exc:
        tomb = exc.tombstone
        raise AppError(
            410,
            "SOURCE_DELETED",
            "the source of this evidence was deleted",
            tombstone={
                "handle": tomb.handle,
                "source_code": tomb.source_code,
                "title": tomb.title,
                "version": tomb.version,
                "deleted_at": tomb.deleted_at.isoformat() if tomb.deleted_at else None,
            },
        ) from exc
    return resolved.as_dict()
