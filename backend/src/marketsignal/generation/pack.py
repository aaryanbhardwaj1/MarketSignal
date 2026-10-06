"""Deterministic evidence-pack builder (plan §3 step 6, §13; ADR-0004, ADR-0007).

Between retrieval and generation. Given the ranked parents of one retrieval request it:

1. takes candidates in retrieval rank order (fused order; the Phase 2 default has no reranker),
   de-duplicated by handle;
2. resolves each parent's *canonical* text, hash, locator and source metadata from Postgres in
   the request's workspace scope (RLS + an explicit workspace predicate) - the model never
   decides whether evidence exists, and a handle from another workspace can never enter;
3. keeps the matched child anchor (id and ``char_start/char_end``, D1) for highlighting;
4. shows the whole parent when it fits ``pack_item_max_tokens``, otherwise a window centred on
   the anchor child, cut at whitespace;
5. fills the budget (``pack_max_items``, ``pack_max_tokens``) in rank order, skipping an item
   that does not fit and continuing with smaller ones; ``truncated`` is set when a candidate
   ranked within the item limit was dropped for budget (``PACK_BUDGET_TRUNCATED``);
6. assigns run-local aliases ``E1..En`` in pack order.

Token unit: the parent's stored ``token_count`` (the embedder's WordPiece tokenizer, ADR-0012),
used as a deterministic proxy for model tokens; the real input usage is recorded from the
provider's ``usage`` on every run.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.generation.types import EvidencePack, PackItem
from marketsignal.retrieval.types import ParentCandidate

_PARENTS = """
SELECT p.id, p.handle, p.text, p.token_count, p.content_hash, p.locator_label, p.heading_path,
       s.source_code, s.title, s.source_type, v.source_class
FROM parent_chunks p
JOIN source_versions v ON v.id = p.source_version_id
JOIN sources s ON s.id = v.source_id
WHERE p.workspace_id = :ws AND p.id = ANY(CAST(:ids AS uuid[])) AND s.deleted_at IS NULL
"""


@dataclass(frozen=True, slots=True)
class PackLimits:
    max_items: int = 12
    max_tokens: int = 9000
    item_max_tokens: int = 900
    candidates: int = 24


def anchor_window(
    parent_text: str, token_count: int, anchor: tuple[int, int], max_tokens: int
) -> tuple[str, tuple[int, int] | None, int]:
    """The whole parent if it fits, else a window of about ``max_tokens`` centred on the
    anchor span, widened to whitespace so no word is cut. Returns (text, window, tokens)."""
    if token_count <= max_tokens or not parent_text:
        return parent_text, None, token_count
    chars_per_token = len(parent_text) / max(token_count, 1)
    width = int(max_tokens * chars_per_token)
    start, end = anchor
    centre = (start + end) // 2
    lo = max(0, centre - width // 2)
    hi = min(len(parent_text), lo + width)
    lo = max(0, hi - width)
    # Never cut through the anchor itself.
    lo, hi = min(lo, start), max(hi, end)
    while lo > 0 and not parent_text[lo - 1].isspace():
        lo -= 1
    while hi < len(parent_text) and not parent_text[hi].isspace():
        hi += 1
    window_text = parent_text[lo:hi].strip()
    tokens = max(1, round(len(window_text) / chars_per_token))
    return window_text, (lo, hi), tokens


async def build_pack(
    factory: SessionFactory,
    scope: WorkspaceScope,
    ranked: Sequence[ParentCandidate],
    limits: PackLimits,
) -> EvidencePack:
    candidates: list[ParentCandidate] = []
    seen: set[str] = set()
    prefix = f"{scope.workspace_code}/"
    for parent in ranked:
        if parent.handle in seen or not parent.handle.startswith(prefix):
            continue  # de-duplicate; a foreign handle can never enter (defence in depth)
        seen.add(parent.handle)
        candidates.append(parent)
        if len(candidates) >= limits.candidates:
            break
    if not candidates:
        return EvidencePack(items=(), tokens=0, truncated=False)

    async with scoped_session(factory, scope) as session:
        rows = (
            await session.execute(
                text(_PARENTS),
                {"ws": scope.workspace_id, "ids": [c.parent_id for c in candidates]},
            )
        ).all()
    by_id: dict[uuid.UUID, tuple[object, ...]] = {r[0]: tuple(r) for r in rows}

    items: list[PackItem] = []
    used = 0
    truncated = False
    dropped: list[str] = []
    for position, candidate in enumerate(candidates, start=1):
        row = by_id.get(candidate.parent_id)
        if row is None:  # purged between retrieval and packing: its handle now resolves 410
            continue
        (
            _,
            handle,
            parent_text,
            token_count,
            content_hash,
            label,
            headings,
            code,
            title,
            stype,
            cls,
        ) = row
        anchor = candidate.best_anchor()
        shown, window, tokens = anchor_window(
            str(parent_text),
            int(token_count),  # type: ignore[call-overload]
            (anchor.char_start, anchor.char_end),
            limits.item_max_tokens,
        )
        if len(items) >= limits.max_items:
            break
        if used + tokens > limits.max_tokens:
            if position <= limits.max_items:
                truncated = True
            dropped.append(str(handle))
            continue
        used += tokens
        items.append(
            PackItem(
                alias=f"E{len(items) + 1}",
                rank=len(items) + 1,
                handle=str(handle),
                parent_id=candidate.parent_id,
                source_code=str(code),
                source_title=str(title),
                source_class=str(cls),
                source_type=str(stype),
                locator_label=str(label),
                heading_path=tuple(headings or ()),  # type: ignore[arg-type]
                text=shown,
                window=window,
                tokens=tokens,
                content_hash=str(content_hash).strip(),
                anchor_child_id=anchor.child_id,
                anchor_char_start=anchor.char_start,
                anchor_char_end=anchor.char_end,
                fused_rank=candidate.fused_rank,
                lane_ranks={a.lane: a.rank for a in candidate.anchors},
            )
        )
    return EvidencePack(
        items=tuple(items), tokens=used, truncated=truncated, dropped=tuple(dropped)
    )
