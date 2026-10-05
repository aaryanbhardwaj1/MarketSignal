"""Structure helpers shared by the narrative parsers (PDF, DOCX, Markdown/text).

Parents are *structure-derived*: they never cross a page, slide, row or Q&A boundary. Within
such a container, consecutive paragraph units are grouped into blocks of at most
``parent_max_tokens``. A unit that alone exceeds the cap is split at sentence boundaries, and
a sentence that still exceeds it is split on token boundaries. Runs of list items are kept
together when they fit; when a list must span several parents they share a ``list_group_id``
so structural enumeration (Phase 7) can reassemble the list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from marketsignal.ingestion.tokenizer import Tokenizer

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_WS = re.compile(r"\s+")


def clean(text: str) -> str:
    """Collapse whitespace runs (incl. newlines inside a paragraph) to single spaces."""
    return _WS.sub(" ", text).strip()


@dataclass(frozen=True, slots=True)
class Unit:
    """One paragraph-level unit of text. ``list_run`` groups consecutive list items."""

    text: str
    list_run: int | None = None


@dataclass(frozen=True, slots=True)
class Block:
    text: str
    list_group_id: str | None = None


def _split_oversize(text: str, tokenizer: Tokenizer, max_tokens: int) -> list[str]:
    if tokenizer.count(text) <= max_tokens:
        return [text]
    pieces: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        if tokenizer.count(sentence) <= max_tokens:
            pieces.append(sentence)
            continue
        spans = tokenizer.spans(sentence)
        for start in range(0, len(spans), max_tokens):
            end = min(start + max_tokens, len(spans)) - 1
            pieces.append(sentence[spans.starts[start] : spans.ends[end]])
    # Re-pack sentences greedily so blocks are as full as allowed.
    packed: list[str] = []
    current: list[str] = []
    tokens = 0
    for piece in pieces:
        n = tokenizer.count(piece)
        if current and tokens + n > max_tokens:
            packed.append(" ".join(current))
            current, tokens = [], 0
        current.append(piece)
        tokens += n
    if current:
        packed.append(" ".join(current))
    return packed


def group_units(
    units: list[Unit], tokenizer: Tokenizer, max_tokens: int, list_prefix: str
) -> list[Block]:
    """Greedily pack units into blocks of at most ``max_tokens`` tokens (document order)."""
    # Expand oversize units first; list items keep their run id.
    expanded: list[Unit] = []
    for unit in units:
        budget = max_tokens - (tokenizer.count("- ") if unit.list_run is not None else 0)
        for piece in _split_oversize(unit.text, tokenizer, budget):
            expanded.append(Unit(piece, unit.list_run))

    raw_blocks: list[list[Unit]] = []
    current: list[Unit] = []
    tokens = 0
    for unit in expanded:
        n = tokenizer.count(_render(unit))  # count what is stored, incl. list markers
        starts_list = unit.list_run is not None and (
            not current or current[-1].list_run != unit.list_run
        )
        # Prefer to start a list in a fresh block if the whole run cannot join this one.
        if current and (tokens + n > max_tokens):
            raw_blocks.append(current)
            current, tokens = [], 0
        elif current and starts_list:
            run_tokens = sum(
                tokenizer.count(_render(u)) for u in expanded if u.list_run == unit.list_run
            )
            if tokens + run_tokens > max_tokens and run_tokens <= max_tokens:
                raw_blocks.append(current)
                current, tokens = [], 0
        current.append(unit)
        tokens += n
    if current:
        raw_blocks.append(current)

    # A list run present in more than one block gets a shared list_group_id.
    run_blocks: dict[int, set[int]] = {}
    for b_index, block in enumerate(raw_blocks):
        for unit in block:
            if unit.list_run is not None:
                run_blocks.setdefault(unit.list_run, set()).add(b_index)
    blocks: list[Block] = []
    for b_index, block in enumerate(raw_blocks):
        split_runs = sorted(
            run for run, members in run_blocks.items() if b_index in members and len(members) > 1
        )
        group_id = f"{list_prefix}L{split_runs[0]}" if split_runs else None
        text = "\n".join(_render(unit) for unit in block)
        blocks.append(Block(text, group_id))
    return blocks


def _render(unit: Unit) -> str:
    return f"- {unit.text}" if unit.list_run is not None else unit.text
