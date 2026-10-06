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
from typing import Any

ALIAS_RE = re.compile(r"\[E(\d{1,2})\]")
# Canonical citation marker used in stored/final answer text: [[WS/SOURCE@vN:LOCATOR]].
CANONICAL_RE = re.compile(r"\[\[([A-Z0-9][A-Z0-9/@:.v-]{2,95})\]\]")
INFERENCE_TAG = "[inference]"


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
class EvidencePack:
    items: tuple[PackItem, ...]
    tokens: int
    truncated: bool  # budget or item limit dropped candidates (PACK_BUDGET_TRUNCATED)
    dropped: tuple[str, ...] = ()  # handles left out by the budget

    def by_alias(self) -> dict[str, PackItem]:
        return {i.alias: i for i in self.items}

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

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("rejected")
        return payload

    def attempt_record(self) -> dict[str, Any]:
        """Everything, including rejected spans: the ``verification_attempts.report`` row."""
        return asdict(self)
