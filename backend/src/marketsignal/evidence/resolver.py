"""The canonical evidence resolver: handle -> exact authoritative evidence (ADR-0004, §16).

One resolver, backed by Postgres, serves the evidence API, tools, citation verification and
the UI, so a citation can never resolve differently in two places.

Contract:
* malformed handle -> :class:`MalformedHandleError` (HTTP 400). Never fuzzy-matched;
* handle naming another workspace, or not present under RLS -> :class:`EvidenceNotFoundError`
  (HTTP 404, identical for both so no cross-tenant existence oracle);
* handle into a purged source version -> :class:`EvidenceDeletedError` (HTTP 410, tombstone);
* superseded version -> resolves (immutable evidence for old answers), flagged with the latest
  version's number;
* valid -> exact parent text, locator, source/version metadata, provenance, every child span
  in the parent, and the requested child's highlight span.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.db.scope import WorkspaceScope
from marketsignal.domain.enums import VersionStatus
from marketsignal.evidence.handles import (
    EvidenceHandle,
    ForeignWorkspaceHandleError,
    parse_handle,
    require_workspace,
)

CONTEXT_EXCERPT_CHARS = 280


class EvidenceNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class Tombstone:
    handle: str
    source_code: str
    title: str
    version: int
    deleted_at: datetime | None


class EvidenceDeletedError(LookupError):
    def __init__(self, tombstone: Tombstone) -> None:
        super().__init__("source deleted")
        self.tombstone = tombstone


@dataclass(frozen=True)
class ChildSpan:
    child_id: uuid.UUID
    ordinal: int
    kind: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class ResolvedEvidence:
    handle: str
    text: str
    content_hash: str
    locator: dict[str, Any]
    locator_label: str
    heading_path: list[str]
    source: dict[str, Any]
    provenance: dict[str, Any]
    context: dict[str, str | None]
    children: list[ChildSpan]
    highlight: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "text": self.text,
            "content_hash": self.content_hash,
            "locator": self.locator,
            "locator_label": self.locator_label,
            "heading_path": self.heading_path,
            "source": self.source,
            "provenance": self.provenance,
            "context": self.context,
            "children": [
                {
                    "child_id": str(c.child_id),
                    "ordinal": c.ordinal,
                    "kind": c.kind,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                }
                for c in self.children
            ],
            "highlight": self.highlight,
        }


async def resolve_evidence(
    session: AsyncSession,
    scope: WorkspaceScope,
    handle_text: str,
    *,
    child_id: uuid.UUID | None = None,
) -> ResolvedEvidence:
    """Resolve inside a scoped session. Raises MalformedHandleError / EvidenceNotFoundError /
    EvidenceDeletedError per the module contract."""
    handle = parse_handle(handle_text)  # MalformedHandleError propagates (400)
    try:
        require_workspace(handle, scope.workspace_code)
    except ForeignWorkspaceHandleError as exc:
        raise EvidenceNotFoundError(handle_text) from exc
    if handle.is_analytic:
        raise EvidenceNotFoundError(handle_text)  # computed handles arrive in Phase 5

    version = (
        await session.execute(
            text(
                "SELECT v.id, v.version, v.status, v.source_class, v.confidentiality, "
                "v.content_hash, v.original_filename, v.mime_type, v.parser_version, "
                "v.structure_version, v.chunking_policy_version, v.embedding_model, v.ready_at, "
                "s.id, s.source_code, s.title, s.source_type, s.deleted_at, "
                "(SELECT max(version) FROM source_versions WHERE source_id = s.id "
                " AND status IN ('ready', 'ready_degraded')) AS latest "
                "FROM source_versions v JOIN sources s ON s.id = v.source_id "
                "WHERE s.source_code = :code AND v.version = :ver"
            ),
            {"code": handle.source_code, "ver": handle.version},
        )
    ).one_or_none()
    if version is None:
        raise EvidenceNotFoundError(handle_text)
    (
        version_id,
        version_no,
        status,
        source_class,
        confidentiality,
        version_hash,
        filename,
        mime,
        parser_v,
        structure_v,
        chunking_v,
        embed_model,
        ready_at,
        source_id,
        source_code,
        title,
        source_type,
        deleted_at,
        latest,
    ) = version
    if status == VersionStatus.PURGED.value:
        raise EvidenceDeletedError(
            Tombstone(str(handle), source_code, title, version_no, deleted_at)
        )
    parent = (
        await session.execute(
            text(
                "SELECT id, ordinal, locator, locator_label, heading_path, text, content_hash "
                "FROM parent_chunks WHERE handle = :h"
            ),
            {"h": str(handle)},
        )
    ).one_or_none()
    if parent is None:
        raise EvidenceNotFoundError(handle_text)
    parent_id, ordinal, locator, label, heading_path, parent_text, parent_hash = parent

    neighbours = (
        await session.execute(
            text(
                "SELECT ordinal, text FROM parent_chunks WHERE source_version_id = :v "
                "AND ordinal IN (:prev, :next)"
            ),
            {"v": version_id, "prev": ordinal - 1, "next": ordinal + 1},
        )
    ).all()
    by_ordinal = {o: t for o, t in neighbours}
    prev_text, next_text = by_ordinal.get(ordinal - 1), by_ordinal.get(ordinal + 1)

    children = [
        ChildSpan(*row)
        for row in (
            await session.execute(
                text(
                    "SELECT id, ordinal, kind, char_start, char_end FROM child_chunks "
                    "WHERE parent_id = :p ORDER BY ordinal"
                ),
                {"p": parent_id},
            )
        ).all()
    ]
    highlight = None
    if child_id is not None:
        match = next((c for c in children if c.child_id == child_id), None)
        if match is not None:
            highlight = {
                "child_id": str(match.child_id),
                "char_start": match.char_start,
                "char_end": match.char_end,
                "text": parent_text[match.char_start : match.char_end],
            }

    return ResolvedEvidence(
        handle=str(handle),
        text=parent_text,
        content_hash=parent_hash,
        locator=dict(locator),
        locator_label=label,
        heading_path=list(heading_path),
        source={
            "source_id": str(source_id),
            "source_code": source_code,
            "title": title,
            "source_type": source_type,
            "source_class": source_class,
            "confidentiality": confidentiality,
            "version": version_no,
            "version_status": status,
            "latest_version": latest,
            "is_latest": latest == version_no,
            "original_filename": filename,
            "mime_type": mime,
            "ingested_at": ready_at.isoformat() if ready_at else None,
        },
        provenance={
            "source_content_sha256": version_hash,
            "parent_content_sha256": parent_hash,
            "parser_version": parser_v,
            "structure_version": structure_v,
            "chunking_policy_version": chunking_v,
            "embedding_model": embed_model,
        },
        context={
            "previous_excerpt": prev_text[-CONTEXT_EXCERPT_CHARS:] if prev_text else None,
            "next_excerpt": next_text[:CONTEXT_EXCERPT_CHARS] if next_text else None,
        },
        children=children,
        highlight=highlight,
    )


def parse_or_none(handle_text: str) -> EvidenceHandle | None:
    try:
        return parse_handle(handle_text)
    except ValueError:
        return None
