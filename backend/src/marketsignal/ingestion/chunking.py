"""Derive child retrieval units from parents (ADR-0003, D1).

Contract, enforced by :func:`check_child_contract` and tested:

* every child records ``char_start``/``char_end`` into its parent's text, so the exact
  supporting region can be highlighted and evaluated while the citation stays the parent;
* window children's text is exactly ``parent.text[char_start:char_end]``;
* row children's text is a retrieval rendering (table, context columns, column name) whose span
  points at the verbatim free-text cell inside the parent;
* children are derived *from* parents and never feed back into parent identity, so changing the
  child policy (``chunking_policy_version``) cannot change any evidence handle.
"""

from __future__ import annotations

from collections.abc import Sequence

from marketsignal.domain.enums import ChildKind
from marketsignal.ingestion.models import ChildDraft, ParentDraft, ParentKind
from marketsignal.ingestion.tokenizer import Tokenizer

HEADING_SEPARATOR = " > "


class ChildContractError(AssertionError):
    """A child violates the span contract (programming error, never user input)."""


def heading_text(parent: ParentDraft) -> str:
    return HEADING_SEPARATOR.join(parent.heading_path)


def _windows(
    parent: ParentDraft, parent_ordinal: int, tokenizer: Tokenizer, size: int, overlap: int
) -> list[ChildDraft]:
    spans = tokenizer.spans(parent.text)
    if len(spans) == 0:
        return []
    stride = max(size - overlap, 1)
    children: list[ChildDraft] = []
    start = 0
    while True:
        end = min(start + size, len(spans))
        char_start, char_end = spans.starts[start], spans.ends[end - 1]
        children.append(
            ChildDraft(
                parent_ordinal=parent_ordinal,
                ordinal=len(children),
                kind=ChildKind.WINDOW,
                text=parent.text[char_start:char_end],
                char_start=char_start,
                char_end=char_end,
                token_count=end - start,
                heading_text=heading_text(parent),
            )
        )
        if end == len(spans):
            return children
        start += stride


def build_children(
    parents: Sequence[ParentDraft], tokenizer: Tokenizer, window_tokens: int, overlap_tokens: int
) -> list[ChildDraft]:
    if overlap_tokens >= window_tokens:
        raise ValueError("child overlap must be smaller than the window")
    children: list[ChildDraft] = []
    for ordinal, parent in enumerate(parents):
        if not parent.index_children:
            continue
        if parent.kind is ParentKind.ROW:
            spec = parent.row_child
            if spec is None:
                continue
            children.append(
                ChildDraft(
                    parent_ordinal=ordinal,
                    ordinal=0,
                    kind=ChildKind.ROW,
                    text=spec.text,
                    char_start=spec.char_start,
                    char_end=spec.char_end,
                    token_count=tokenizer.count(spec.text),
                    heading_text=heading_text(parent),
                )
            )
        elif parent.kind is ParentKind.TABLE_SUMMARY:
            children.append(
                ChildDraft(
                    parent_ordinal=ordinal,
                    ordinal=0,
                    kind=ChildKind.SUMMARY,
                    text=parent.text,
                    char_start=0,
                    char_end=len(parent.text),
                    token_count=tokenizer.count(parent.text),
                    heading_text=heading_text(parent),
                )
            )
        else:
            children.extend(_windows(parent, ordinal, tokenizer, window_tokens, overlap_tokens))
    check_child_contract(parents, children)
    return children


def check_child_contract(parents: Sequence[ParentDraft], children: Sequence[ChildDraft]) -> None:
    for child in children:
        parent = parents[child.parent_ordinal]
        if not 0 <= child.char_start < child.char_end <= len(parent.text):
            raise ChildContractError(f"span out of range for parent {child.parent_ordinal}")
        span = parent.text[child.char_start : child.char_end]
        if child.kind is ChildKind.WINDOW and span != child.text:
            raise ChildContractError("window text must equal its parent span")
        if child.kind is ChildKind.ROW and span not in child.text:
            raise ChildContractError("row child must contain its verbatim cell")
