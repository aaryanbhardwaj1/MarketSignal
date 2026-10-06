"""Deterministic answers that never call (or never trust) the model (plan §3, §19, §28).

* **Abstention** - the evidence pack is empty. No LLM call is made; the response says the
  workspace evidence is insufficient and, where possible, which source classes are missing.
* **Evidence-only** - generation failed, was refused, was truncated, timed out, or could not
  be verified after one regeneration. The response lists the top pack items as citation cards
  with extractive snippets: evidence, no prose. A fluent but unverified answer is never shown.
  Instruction-like sentences (planted prompt injections, :mod:`.safe_text`) are replaced by a
  neutral marker in the snippet and such items are listed after normal evidence (Phase 5, A2);
  the citation is kept, so the source viewer still shows the original text. Computed
  analytics results (Phase 5) are listed first, as deterministic value lines (value, unit,
  denominator, provenance) with their ``[[result:<id>]]`` marker and result citation card.
Both are rendered in the canonical format (``[[HANDLE]]`` markers) and pass the same rules as
generated answers (no URLs, HTML or ids).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from marketsignal.domain.enums import SourceClass
from marketsignal.generation.contract import strip_leaks
from marketsignal.generation.safe_text import (
    WITHHELD_MARKER,
    instruction_spans,
    is_instruction_like,
)
from marketsignal.generation.types import EvidencePack, PackItem, ResultItem, result_marker

SNIPPET_CHARS = 280
EVIDENCE_ONLY_ITEMS = 8
_HOLE = "\ufffc"  # placeholder for a withheld span while the window is chosen


@dataclass(frozen=True, slots=True)
class DeterministicAnswer:
    content: str
    sections: dict[str, Any]
    citations: list[dict[str, Any]] = field(default_factory=list)


def _anchor(item: PackItem) -> tuple[int, int]:
    """Anchor span relative to ``item.text`` (offsets are into the parent; the shown text may
    be a window starting at ``item.window[0]``)."""
    offset = item.window[0] if item.window else 0
    start = max(0, min(len(item.text), item.anchor_char_start - offset))
    end = min(len(item.text), max(start, item.anchor_char_end - offset))
    return start, end


def _bounds(text: str, start: int, end: int, limit: int) -> tuple[int, int]:
    centre = (start + end) // 2
    lo = max(0, centre - limit // 2)
    hi = min(len(text), lo + limit)
    lo = max(0, hi - limit)
    while 0 < lo < hi and not text[lo - 1].isspace():
        lo += 1  # start at a word boundary (bounded by the window end)
    return lo, hi


def snippet(item: PackItem, limit: int = SNIPPET_CHARS) -> str:
    """Extractive snippet centred on the anchor span (raw text, not yet cleaned)."""
    lo, hi = _bounds(item.text, *_anchor(item), limit)
    text = " ".join(item.text[lo:hi].split())
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(item.text) else ""
    return f"{prefix}{text}{suffix}"


def _masked(text: str, spans: Sequence[tuple[int, int]]) -> tuple[str, Callable[[int], int]]:
    """``text`` with each span replaced by one :data:`_HOLE` character, and an offset map."""
    pieces: list[str] = []
    cursor = 0
    for lo, hi in spans:
        pieces.extend((text[cursor:lo], _HOLE))
        cursor = hi
    pieces.append(text[cursor:])

    def shift(position: int) -> int:
        removed = 0
        for lo, hi in spans:
            if position >= hi:
                removed += hi - lo - 1
            elif position > lo:
                return lo - removed  # inside a span: its hole
        return position - removed

    return "".join(pieces), shift


def safe_snippet(item: PackItem, limit: int = SNIPPET_CHARS) -> tuple[str, bool]:
    """Cleaned snippet for display, with instruction-like sentences replaced by
    :data:`WITHHELD_MARKER` (A2). Returns ``(text, withheld)``. The stored source text and the
    citation anchor are unchanged; the source viewer still shows the original."""
    spans = instruction_spans(item.text)
    if not spans:
        return _clean(snippet(item)), False
    masked, shift = _masked(item.text, spans)
    start, end = _anchor(item)
    lo, hi = _bounds(masked, shift(start), max(shift(start), shift(end)), limit)
    parts = [_clean(part) for part in masked[lo:hi].split(_HOLE)]
    body = f" {WITHHELD_MARKER} ".join(parts)
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(masked) else ""
    return f"{prefix}{' '.join(body.split())}{suffix}", _HOLE in masked[lo:hi]


def _clean(value: str, default: str = "") -> str:
    """Document text: drop leaks (URLs, ids, handles, HTML) as the verifier does for generated
    answers, then neutralise anything a renderer could still treat as markup or links."""
    text = " ".join(strip_leaks(value).text.split()) or default
    return text.replace("[", "(").replace("]", ")").replace("<", "\u2039").replace(">", "\u203a")


def _safe_label(value: str, default: str) -> str:
    return default if is_instruction_like(value) else _clean(value, default)


def result_unit(item: ResultItem) -> str:
    """One deterministic line per computed result: values, units, denominators, provenance.
    Labels come from documents, so they are cleaned like snippets."""
    values = "; ".join(_clean(line) for line in item.fallback_lines) or "no values"
    provenance = (
        f"{_safe_label(item.source_code, 'source')} v{item.source_version}, "
        f"{_safe_label(item.table, 'table')}, {item.operation}"
    )
    return f"**Computed result** ({provenance}): {values} {result_marker(item.result_id)}"


def evidence_only(
    pack: EvidencePack, reason: str, limit: int = EVIDENCE_ONLY_ITEMS
) -> DeterministicAnswer:
    """Items carrying instruction-like text are listed after every normal item (stable, so
    retrieval order is otherwise kept); this ordering applies to the fallback list only."""
    ordered = sorted(pack.items, key=lambda item: bool(instruction_spans(item.text)))
    items = ordered[:limit]
    lines = [
        "### Evidence (no generated answer)",
        "",
        "A verified answer could not be produced, so the most relevant workspace evidence is "
        "listed instead.",
        "",
    ]
    units = []
    withheld = []
    for result in pack.results:
        unit = result_unit(result)
        units.append(unit)
        lines.append(f"- {unit}")
    for item in items:
        text, hidden = safe_snippet(item)
        if hidden:
            withheld.append(item.handle)
        unit = (
            f"**{_safe_label(item.source_title, 'Untitled source')}**, "
            f"{_safe_label(item.locator_label, 'excerpt')}: "
            f"“{text}” [[{item.handle}]]"
        )
        units.append(unit)
        lines.append(f"- {unit}")
    sections: dict[str, Any] = {"evidence_only": units, "reason": reason}
    if withheld:
        sections["instruction_like_withheld"] = withheld
    return DeterministicAnswer(
        content="\n".join(lines).rstrip() + "\n",
        sections=sections,
        citations=[*(r.card() for r in pack.results), *(i.card() for i in items)],
    )


def abstention(
    present_classes: Sequence[str], requested_classes: Sequence[str] = ()
) -> DeterministicAnswer:
    missing = [c.value for c in SourceClass if c.value not in set(present_classes)]
    scope = (
        f" among the selected source classes ({', '.join(requested_classes)})"
        if requested_classes
        else ""
    )
    gap = f"No relevant evidence was found in this workspace{scope}."
    if missing:
        gap += (
            f" The workspace has no {', '.join(missing)} sources; adding them could close the gap."
        )
    else:
        gap += " Uploading documents that cover this topic would close the gap."
    answer = (
        "The workspace evidence does not contain information that answers this question, "
        "so no answer was generated."
    )
    content = f"### Answer\n\n{answer}\n\n### Gaps & unknowns\n\n{gap}\n"
    return DeterministicAnswer(
        content=content,
        sections={"answer": [answer], "gaps": [gap], "abstained": True},
    )
