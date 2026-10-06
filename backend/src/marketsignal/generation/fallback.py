"""Deterministic answers that never call (or never trust) the model (plan §3, §19, §28).

* **Abstention** - the evidence pack is empty. No LLM call is made; the response says the
  workspace evidence is insufficient and, where possible, which source classes are missing.
* **Evidence-only** - generation failed, was refused, was truncated, timed out, or could not
  be verified after one regeneration. The response lists the top pack items as citation cards
  with extractive snippets: evidence, no prose. A fluent but unverified answer is never shown.
Both are rendered in the canonical format (``[[HANDLE]]`` markers) and pass the same rules as
generated answers (no URLs, HTML or ids).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from marketsignal.domain.enums import SourceClass
from marketsignal.generation.types import EvidencePack, PackItem

SNIPPET_CHARS = 280
EVIDENCE_ONLY_ITEMS = 8


@dataclass(frozen=True, slots=True)
class DeterministicAnswer:
    content: str
    sections: dict[str, Any]
    citations: list[dict[str, Any]] = field(default_factory=list)


def snippet(item: PackItem, limit: int = SNIPPET_CHARS) -> str:
    """Extractive snippet centred on the anchor span (offsets are into the parent; the shown
    text may be a window starting at ``item.window[0]``)."""
    offset = item.window[0] if item.window else 0
    start = max(0, item.anchor_char_start - offset)
    end = min(len(item.text), max(start, item.anchor_char_end - offset))
    centre = (start + end) // 2
    lo = max(0, centre - limit // 2)
    hi = min(len(item.text), lo + limit)
    lo = max(0, hi - limit)
    while 0 < lo < hi and not item.text[lo - 1].isspace():
        lo += 1  # start at a word boundary (bounded by the window end)
    text = " ".join(item.text[lo:hi].split())
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(item.text) else ""
    return f"{prefix}{text}{suffix}"


def _clean(value: str) -> str:
    # Snippets are document text: neutralise anything a renderer could treat as markup/links.
    return value.replace("[", "(").replace("]", ")").replace("<", "\u2039").replace(">", "\u203a")


def evidence_only(
    pack: EvidencePack, reason: str, limit: int = EVIDENCE_ONLY_ITEMS
) -> DeterministicAnswer:
    items = pack.items[:limit]
    lines = [
        "### Evidence (no generated answer)",
        "",
        "A verified answer could not be produced, so the most relevant workspace evidence is "
        "listed instead.",
        "",
    ]
    units = []
    for item in items:
        unit = (
            f"**{_clean(item.source_title)}**, {_clean(item.locator_label)}: "
            f"“{_clean(snippet(item))}” [[{item.handle}]]"
        )
        units.append(unit)
        lines.append(f"- {unit}")
    return DeterministicAnswer(
        content="\n".join(lines).rstrip() + "\n",
        sections={"evidence_only": units, "reason": reason},
        citations=[i.card() for i in items],
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
