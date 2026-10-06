"""Shared types for grounded answering (Phase 3, plan §3, ADR-0004).

An :class:`EvidencePack` is the frozen, deterministic set of parent evidence a generation may
cite. Each item has a run-local alias (``E1``…``En``) that exists only inside one run; the
canonical handle is the stored identity. Citation cards carry the D1 anchor (child id and
``char_start/char_end``) and the parent content hash all the way to the stored answer.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

ALIAS_RE = re.compile(r"\[E(\d{1,2})\]")
# Phase 5: computed analytics results are cited with run-local ``[R#]`` aliases.
RESULT_ALIAS_RE = re.compile(r"\[R(\d{1,2})\]")
ANY_ALIAS_RE = re.compile(r"\[([ER])(\d{1,2})\]")  # groups: letter, digits
# Canonical citation marker used in stored/final answer text: [[WS/SOURCE@vN:LOCATOR]].
CANONICAL_RE = re.compile(r"\[\[([A-Z0-9][A-Z0-9/@:.v-]{2,95})\]\]")
INFERENCE_TAG = "[inference]"
# Canonical stored marker for a cited computed result. The lowercase ``result:`` prefix never
# matches CANONICAL_RE, so result markers are never mistaken for evidence handles.
RESULT_MARKER_PREFIX = "result:"


def result_marker(result_id: str) -> str:
    return f"[[{RESULT_MARKER_PREFIX}{result_id}]]"


@dataclass(frozen=True, slots=True)
class PackItem:
    alias: str  # "E1".."En", run-local
    rank: int  # 1-based pack position (retrieval order)
    handle: str
    parent_id: uuid.UUID
    source_code: str
    source_title: str
    source_class: str
    source_type: str
    locator_label: str
    heading_path: tuple[str, ...]
    text: str  # the text shown to the model (whole parent, or an anchor-centred window)
    window: tuple[int, int] | None  # (start, end) char offsets into the parent when windowed
    tokens: int
    content_hash: str
    anchor_child_id: uuid.UUID
    anchor_char_start: int
    anchor_char_end: int
    fused_rank: int
    lane_ranks: dict[str, int] = field(default_factory=dict)

    def card(self) -> dict[str, Any]:
        """Citation card stored with a final answer (canonical handle, never the alias)."""
        return {
            "kind": "evidence",
            "handle": self.handle,
            "source_code": self.source_code,
            "source_title": self.source_title,
            "source_class": self.source_class,
            "source_type": self.source_type,
            "locator_label": self.locator_label,
            "anchor_child_id": str(self.anchor_child_id),
            "char_start": self.anchor_char_start,
            "char_end": self.anchor_char_end,
            "parent_content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class ResultFigure:
    """One number the model was shown for a result (``generation/results.py`` builds them).

    ``kind`` is ``metric`` (a metric value: ``value`` rounded, ``exact`` unrounded, in
    ``unit``/``scale``), ``difference`` (group_compare A - B, same fields), ``count`` (a
    numerator, denominator or matched-row count) or ``label`` (a numeric group label, cell or
    filter value)."""

    kind: str
    value: Decimal | None
    exact: Decimal | None = None
    unit: str = "number"
    scale: str = ""


@dataclass(frozen=True, slots=True)
class ResultItem:
    """A computed analytics result in the pack (Phase 5): run-local alias ``R1``..``Rn``.

    ``rendered`` is exactly what the model sees inside ``<computed_results>`` (escaped);
    ``figures`` are the numbers in it, the only numbers an ``[R#]`` citation can support."""

    alias: str  # "R1".."Rn", run-local
    result_id: str
    source_code: str
    dataset: str
    source_version: int
    table: str
    operation: str
    summary: str  # short, server-written description (filters/grouping/metrics)
    rendered: str
    figures: tuple[ResultFigure, ...]
    years: frozenset[int]
    workspace: str = ""
    fallback_lines: tuple[str, ...] = ()  # deterministic value lines for the evidence-only answer

    @property
    def source_handle(self) -> str:
        """The source-version handle (``WS/SOURCE@vN``) behind this result: lets the store's
        purge checks (which parse handles) see a cited result's source."""
        return f"{self.workspace}/{self.source_code}@v{self.source_version}"

    def card(self) -> dict[str, Any]:
        """Result citation card. ``source_code`` is required: a purge of the source redacts any
        answer citing it. ``handle`` is the source-version handle (see :attr:`source_handle`)."""
        return {
            "kind": "result",
            "result_id": self.result_id,
            "source_code": self.source_code,
            "dataset": self.dataset,
            "source_version": self.source_version,
            "table": self.table,
            "op": self.operation,
            "summary": self.summary,
            "handle": self.source_handle,
        }


@dataclass(frozen=True, slots=True)
class EvidencePack:
    items: tuple[PackItem, ...]
    tokens: int
    truncated: bool  # budget or item limit dropped candidates (PACK_BUDGET_TRUNCATED)
    dropped: tuple[str, ...] = ()  # handles left out by the budget
    results: tuple[ResultItem, ...] = ()  # Phase 5: computed results ([R#]), research runs

    def by_alias(self) -> dict[str, PackItem]:
        return {i.alias: i for i in self.items}

    def by_result_alias(self) -> dict[str, ResultItem]:
        return {r.alias: r for r in self.results}

    def aliases(self) -> list[str]:
        """Every citable alias: evidence ``E#`` then result ``R#``."""
        return [i.alias for i in self.items] + [r.alias for r in self.results]

    @property
    def has_sources(self) -> bool:
        """Evidence items or computed results: something the answer can cite."""
        return bool(self.items or self.results)

    def handles(self) -> list[str]:
        return [i.handle for i in self.items]

    def classes(self) -> list[str]:
        return sorted({i.source_class for i in self.items})

    @property
    def empty(self) -> bool:
        return not self.items

    def summary(self) -> dict[str, Any]:
        return {
            "item_count": len(self.items),
            **({"result_count": len(self.results)} if self.results else {}),
            "classes": self.classes(),
            "truncated": self.truncated,
            "tokens": self.tokens,
        }


@dataclass
class VerificationReport:
    """Deterministic verification outcome (``final.verification``)."""

    passed: bool = True
    structural_failures: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)
    unknown_aliases: list[str] = field(default_factory=list)
    numeric_violations: list[str] = field(default_factory=list)
    leaks_removed: list[str] = field(default_factory=list)
    citations: int = 0
    cited_aliases: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    # Phase 4 attempt report (additive). ``rejected`` quotes dropped model spans, so it is kept
    # out of :meth:`as_dict` (the UI payload) and stored only in ``verification_attempts``.
    attempt: int = 1
    disposition: str = ""  # accepted|repaired|regenerate|rejected|fallback (set by the run)
    regeneration_requested: bool = False
    failure_categories: list[str] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    evidence_checked: list[str] = field(default_factory=list)  # aliases whose evidence was used
    evidence_handles: list[str] = field(default_factory=list)  # their canonical handles
    gap_statements: list[str] = field(default_factory=list)  # "Answer #2": evidence-gap units
    conflict_signals: list[str] = field(default_factory=list)
    max_citations: int = 20
    # Phase 5 (A1): set only when the raw answer exceeded the cap: markers before/after the
    # deterministic citation budget and the aliases cited by more than one unit.
    citation_budget: dict[str, Any] = field(default_factory=dict)
    # Phase 5: computed-result aliases a cited unit's numbers were checked against, and ids.
    results_checked: list[str] = field(default_factory=list)
    result_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("rejected")
        return payload

    def attempt_record(self) -> dict[str, Any]:
        """Everything, including rejected spans: the ``verification_attempts.report`` row."""
        return asdict(self)
