"""Domain enumerations shared by ingestion, evidence resolution and the API.

Values mirror the CHECK constraints in migration 0002; changing one requires a migration.
"""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    CSV = "csv"
    MARKDOWN = "markdown"
    TEXT = "text"


class SourceClass(StrEnum):
    INTERNAL = "internal"
    CUSTOMER = "customer"
    COMPETITOR = "competitor"
    MARKET = "market"
    FINANCIAL = "financial"


class Confidentiality(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class VersionStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    READY = "ready"
    READY_DEGRADED = "ready_degraded"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    PURGED = "purged"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_STATUSES

    @property
    def is_searchable(self) -> bool:
        return self in (VersionStatus.READY, VersionStatus.READY_DEGRADED)


TERMINAL_STATUSES = frozenset(
    {
        VersionStatus.READY,
        VersionStatus.READY_DEGRADED,
        VersionStatus.FAILED,
        VersionStatus.SUPERSEDED,
        VersionStatus.PURGED,
    }
)
# Versions that block an identical re-upload (idempotency); mirrors the partial unique index.
LIVE_STATUSES = frozenset(
    set(VersionStatus) - {VersionStatus.FAILED, VersionStatus.SUPERSEDED, VersionStatus.PURGED}
)


class IngestErrorCode(StrEnum):
    """Structured ingestion error categories, visible on the Sources page (spec §12.6)."""

    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    CONTENT_TOO_LARGE = "CONTENT_TOO_LARGE"
    PARSE_FAILED = "PARSE_FAILED"
    PARSE_TIMEOUT = "PARSE_TIMEOUT"
    ENCRYPTED_DOCUMENT = "ENCRYPTED_DOCUMENT"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
    MALFORMED_SPREADSHEET = "MALFORMED_SPREADSHEET"
    EMBEDDER_UNAVAILABLE = "EMBEDDER_UNAVAILABLE"
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    HEALTH_CHECK_FAILED = "HEALTH_CHECK_FAILED"
    SOURCE_TYPE_MISMATCH = "SOURCE_TYPE_MISMATCH"
    SOURCE_DELETED = "SOURCE_DELETED"
    INGEST_EXTRACT_FAILED = "INGEST_EXTRACT_FAILED"


class ChildKind(StrEnum):
    WINDOW = "window"  # token window over narrative parent text
    ROW = "row"  # free-text row of a structured dataset
    SUMMARY = "summary"  # table-summary unit
