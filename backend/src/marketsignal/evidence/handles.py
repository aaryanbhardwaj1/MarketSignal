"""Canonical evidence-handle grammar (ADR-0004).

An evidence handle is a deterministic, immutable pointer to one *parent* evidence unit
(the citation unit, ADR-0003) inside one version of one source in one workspace::

    WORKSPACE/SOURCE@vVERSION:LOCATOR

    NORTHSTAR/SURVEY-2026@v1:R185          CSV row 185 (header = row 1)
    NORTHSTAR/BRAND-STRATEGY@v1:P4.B2      PDF page 4, block 2
    NORTHSTAR/INTERVIEWS@v1:S3.Q7          DOCX section 3, Q&A pair 7
    NORTHSTAR/Q3-REVIEW@v1:SL6.N1          PPTX slide 6, speaker notes
    NORTHSTAR/PRODUCT-PERF@v1:SH2.R12      XLSX sheet 2, row 12
    NORTHSTAR/PRODUCT-PERF@v1:AQ3F9A0C21B7D4   computed analytics result (Phase 5)

Grammar (EBNF; total length <= 96)::

    handle = ws "/" src "@v" ver ":" loc
    ws     = [A-Z][A-Z0-9]{1,15}
    src    = [A-Z0-9]{1,12} ( "-" [A-Z0-9]{1,12} ){0,5}
    ver    = [1-9][0-9]{0,3}
    loc    = unit ( "." unit ){0,3} | "AQ" HEX{12}
    unit   = kind [1-9][0-9]{0,6}
    kind   = "SL" | "SH" | "P" | "B" | "S" | "N" | "R" | "Q" | "T"

Properties this module guarantees: parsing is total (any string either parses or raises
``MalformedHandleError``; nothing else), ``str(parse(h)) == h`` for every valid handle, the
alphabet is ``[A-Z0-9v/@:.-]`` (``v`` only in the ``@v`` version marker) so a handle is
safe to render inside markdown/HTML, and there is no fuzzy matching: a near-miss is
rejected, never "repaired".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

MAX_HANDLE_LENGTH: Final = 96
MAX_LOCATOR_UNITS: Final = 4
MAX_UNIT_INDEX: Final = 9_999_999
MAX_VERSION: Final = 9_999
ANALYTIC_ID_HEX_LENGTH: Final = 12

WORKSPACE_CODE_RE: Final = re.compile(r"[A-Z][A-Z0-9]{1,15}")
SOURCE_CODE_RE: Final = re.compile(r"[A-Z0-9]{1,12}(?:-[A-Z0-9]{1,12}){0,5}")

_UNIT = r"(?:SL|SH|P|B|S|N|R|Q|T)[1-9][0-9]{0,6}"
_HANDLE_RE: Final = re.compile(
    r"(?P<ws>[A-Z][A-Z0-9]{1,15})"
    r"/(?P<src>[A-Z0-9]{1,12}(?:-[A-Z0-9]{1,12}){0,5})"
    r"@v(?P<ver>[1-9][0-9]{0,3})"
    rf":(?P<loc>{_UNIT}(?:\.{_UNIT}){{0,3}}|AQ[0-9A-F]{{12}})"
)
_UNIT_RE: Final = re.compile(r"(?P<kind>SL|SH|P|B|S|N|R|Q|T)(?P<index>[1-9][0-9]{0,6})")


class MalformedHandleError(ValueError):
    """The string is not a canonical evidence handle. Never guessed or repaired."""


class LocatorKind(StrEnum):
    SLIDE = "SL"
    SHEET = "SH"
    PAGE = "P"
    BLOCK = "B"
    SECTION = "S"
    NOTES = "N"
    ROW = "R"
    QA = "Q"
    TABLE = "T"


_KIND_LABEL: Final = {
    LocatorKind.SLIDE: "Slide",
    LocatorKind.SHEET: "Sheet",
    LocatorKind.PAGE: "Page",
    LocatorKind.BLOCK: "Block",
    LocatorKind.SECTION: "Section",
    LocatorKind.NOTES: "Notes",
    LocatorKind.ROW: "Row",
    LocatorKind.QA: "Q&A",
    LocatorKind.TABLE: "Table",
}


@dataclass(frozen=True, slots=True)
class LocatorUnit:
    kind: LocatorKind
    index: int

    def __post_init__(self) -> None:
        if not 1 <= self.index <= MAX_UNIT_INDEX:
            raise MalformedHandleError(f"locator index out of range: {self.index}")

    def __str__(self) -> str:
        return f"{self.kind.value}{self.index}"


@dataclass(frozen=True, slots=True)
class EvidenceHandle:
    """A parsed canonical handle. Construct via :func:`parse_handle` or the builders."""

    workspace_code: str
    source_code: str
    version: int
    locator: tuple[LocatorUnit, ...] = ()
    analytic_id: str | None = None  # 12 uppercase hex chars for computed (AQ) handles

    def __post_init__(self) -> None:
        if not WORKSPACE_CODE_RE.fullmatch(self.workspace_code):
            raise MalformedHandleError(f"invalid workspace code: {self.workspace_code!r}")
        if not SOURCE_CODE_RE.fullmatch(self.source_code):
            raise MalformedHandleError(f"invalid source code: {self.source_code!r}")
        if not 1 <= self.version <= MAX_VERSION:
            raise MalformedHandleError(f"invalid version: {self.version}")
        if (self.analytic_id is None) == (not self.locator):
            # exactly one of: structural locator, analytic id
            raise MalformedHandleError("a handle has either a structural locator or an AQ id")
        if self.analytic_id is not None and not re.fullmatch(r"[0-9A-F]{12}", self.analytic_id):
            raise MalformedHandleError(f"invalid analytic id: {self.analytic_id!r}")
        if len(self.locator) > MAX_LOCATOR_UNITS:
            raise MalformedHandleError("too many locator units")
        if len(str(self)) > MAX_HANDLE_LENGTH:
            raise MalformedHandleError("handle exceeds maximum length")

    @property
    def is_analytic(self) -> bool:
        return self.analytic_id is not None

    @property
    def locator_string(self) -> str:
        if self.analytic_id is not None:
            return f"AQ{self.analytic_id}"
        return ".".join(str(unit) for unit in self.locator)

    @property
    def source_ref(self) -> str:
        """``WORKSPACE/SOURCE@vN`` — identifies one immutable source version."""
        return f"{self.workspace_code}/{self.source_code}@v{self.version}"

    def locator_label(self, sheet_names: dict[int, str] | None = None) -> str:
        """Human-readable locator, e.g. ``"Page 4, Block 2"`` or ``"Sheet 'Returns', Row 12"``."""
        if self.analytic_id is not None:
            return f"Computed result {self.analytic_id}"
        parts = []
        for unit in self.locator:
            if unit.kind is LocatorKind.SHEET and sheet_names and unit.index in sheet_names:
                parts.append(f"Sheet '{sheet_names[unit.index]}'")
            else:
                parts.append(f"{_KIND_LABEL[unit.kind]} {unit.index}")
        return ", ".join(parts)

    def with_version(self, version: int) -> EvidenceHandle:
        return EvidenceHandle(
            self.workspace_code, self.source_code, version, self.locator, self.analytic_id
        )

    def __str__(self) -> str:
        return f"{self.source_ref}:{self.locator_string}"

    def rendered(self) -> str:
        """Form used inside answer text: ``[WS/SRC@vN:LOC]``."""
        return f"[{self}]"


def parse_handle(value: str) -> EvidenceHandle:
    """Parse a canonical handle string. Raises :class:`MalformedHandleError` on anything else.

    Deliberately strict: no trimming, no case folding, no bracket stripping (use
    :func:`parse_rendered_handle` for the ``[...]`` form). Non-``str`` input is rejected.
    """
    if not isinstance(value, str):
        raise MalformedHandleError("handle must be a string")
    if len(value) > MAX_HANDLE_LENGTH:
        raise MalformedHandleError("handle exceeds maximum length")
    match = _HANDLE_RE.fullmatch(value)
    if match is None:
        raise MalformedHandleError(f"not a canonical evidence handle: {value[:120]!r}")
    loc = match["loc"]
    if loc.startswith("AQ"):
        return EvidenceHandle(match["ws"], match["src"], int(match["ver"]), (), loc[2:])
    units = tuple(
        LocatorUnit(LocatorKind(m["kind"]), int(m["index"]))
        for m in (_UNIT_RE.fullmatch(part) for part in loc.split("."))
        if m is not None
    )
    return EvidenceHandle(match["ws"], match["src"], int(match["ver"]), units)


def parse_rendered_handle(value: str) -> EvidenceHandle:
    """Parse the bracketed form ``[WS/SRC@vN:LOC]`` used inside answer text."""
    if not (isinstance(value, str) and value.startswith("[") and value.endswith("]")):
        raise MalformedHandleError("rendered handle must be wrapped in [ ]")
    return parse_handle(value[1:-1])


def try_parse_handle(value: str) -> EvidenceHandle | None:
    try:
        return parse_handle(value)
    except MalformedHandleError:
        return None


def is_valid_workspace_code(value: str) -> bool:
    return isinstance(value, str) and WORKSPACE_CODE_RE.fullmatch(value) is not None


def is_valid_source_code(value: str) -> bool:
    return isinstance(value, str) and SOURCE_CODE_RE.fullmatch(value) is not None


def build_handle(
    workspace_code: str, source_code: str, version: int, *units: tuple[LocatorKind, int]
) -> EvidenceHandle:
    """Builder used by ingestion: ``build_handle("NORTHSTAR", "SURVEY-2026", 1, (ROW, 185))``."""
    return EvidenceHandle(
        workspace_code,
        source_code,
        version,
        tuple(LocatorUnit(kind, index) for kind, index in units),
    )


def require_workspace(handle: EvidenceHandle, workspace_code: str) -> None:
    """Cheap syntactic workspace check; the authoritative check is the DB lookup under RLS.

    Raises :class:`ForeignWorkspaceHandleError`, which callers must surface exactly like
    "not found" so a handle's existence in another workspace is never revealed.
    """
    if handle.workspace_code != workspace_code:
        raise ForeignWorkspaceHandleError(handle.workspace_code)


class ForeignWorkspaceHandleError(LookupError):
    """Handle names another workspace. Surface as NOT_FOUND (no existence oracle)."""
