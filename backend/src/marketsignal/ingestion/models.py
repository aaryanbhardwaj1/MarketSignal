"""Intermediate ingestion representations (pure data; no I/O).

Parsers turn a file into :class:`ParentDraft` units (the structure-derived citation units of
ADR-0003) plus, for structured files, :class:`DatasetTable` data. The chunker then derives
:class:`ChildDraft` retrieval units, each carrying the exact character span it covers inside
its parent's text (D1: child-granular retrieval, parent-level citation, highlightable spans).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from marketsignal.domain.enums import ChildKind
from marketsignal.evidence.handles import LocatorKind


class ParentKind(StrEnum):
    NARRATIVE = "narrative"  # paragraph group (PDF page block, DOCX/MD section block)
    QA = "qa"  # interview question + answer
    SLIDE = "slide"
    NOTES = "notes"
    ROW = "row"  # one structured-data row
    TABLE_SUMMARY = "table_summary"


@dataclass(frozen=True, slots=True)
class RowChildSpec:
    """Retrieval text for a row parent plus the span of its free-text cell inside the parent."""

    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class ParentDraft:
    locator: tuple[tuple[LocatorKind, int], ...]
    kind: ParentKind
    text: str
    heading_path: tuple[str, ...] = ()
    locator_meta: dict[str, Any] = field(default_factory=dict)  # page, slide, sheet_name, row...
    list_group_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Row parents: None means "not a retrieval unit" (numeric-only row, plan §9).
    row_child: RowChildSpec | None = None
    index_children: bool = True


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    name: str
    type: str  # numeric | date | categorical | text
    role: str  # identifier | free_text | context | numeric | date
    non_empty: int
    distinct: int
    levels: tuple[str, ...] = ()  # categorical levels (bounded)


@dataclass(frozen=True, slots=True)
class DatasetTable:
    sheet_ordinal: int
    name: str
    header_row: int
    columns: tuple[ColumnProfile, ...]
    rows: tuple[tuple[int, dict[str, Any]], ...]  # (row_number, values)


@dataclass(frozen=True, slots=True)
class ParsedSource:
    parents: tuple[ParentDraft, ...]
    tables: tuple[DatasetTable, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChildDraft:
    parent_ordinal: int
    ordinal: int
    kind: ChildKind
    text: str
    char_start: int
    char_end: int
    token_count: int
    heading_text: str = ""


class IngestionError(Exception):
    """A structured, user-visible ingestion failure (maps to an IngestErrorCode)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
