"""The agent's evidence pool and its hand-off to the shared tail (plan §19; ADR-0007).

The pool holds *handles* only (plus the D1 anchor reported by the tool), never document
text. Order is deterministic: best fused rank first (each search's top hits interleave), then
the step that first found the handle, then first-seen order within that step.

:func:`pool_to_candidates` re-resolves every handle in the run's workspace scope (RLS plus an
explicit predicate) and drops anything that no longer resolves: foreign handles, unknown
handles, and handles whose source was deleted or whose version was purged (ADR-0016, the
same rule ``generation/pack.py`` and ``runs/store.py`` apply).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import text

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.retrieval.types import LaneAnchor, ParentCandidate

AGENT_LANE = "agent"


@dataclass(frozen=True, slots=True)
class PoolItem:
    handle: str
    source_code: str
    source_class: str
    anchor_child_id: str  # "" when the handle came from get_evidence only
    anchor_char_start: int
    anchor_char_end: int
    first_step: int
    best_rank: int
    via_tool: str


def _source_code_of(handle: str) -> str:
    """``{ws}/{CODE}@v{n}:{locator}`` -> ``CODE`` (best effort; re-resolved from the DB)."""
    tail = handle.split("/", 1)[-1]
    return tail.split("@", 1)[0]


class EvidencePool:
    """Deduplicated by handle, bounded by ``max_items`` (new handles beyond it are refused)."""

    def __init__(self, max_items: int) -> None:
        self._max = max_items
        self._items: dict[str, PoolItem] = {}
        self._seq: dict[str, int] = {}
        self._next = 0

    def __len__(self) -> int:
        return len(self._items)

    @property
    def full(self) -> bool:
        return len(self._items) >= self._max

    def _put(self, item: PoolItem) -> bool:
        existing = self._items.get(item.handle)
        if existing is not None:
            if item.best_rank < existing.best_rank and item.anchor_child_id:
                self._items[item.handle] = replace(
                    item, first_step=existing.first_step, via_tool=existing.via_tool
                )
            return True
        if self.full:
            return False
        self._items[item.handle] = item
        self._seq[item.handle] = self._next
        self._next += 1
        return True

    def add_hit(self, hit: dict[str, Any], *, step: int, via_tool: str) -> bool:
        """Add one ``EvidenceHit`` (dumped). Returns False when refused because the pool is full."""
        return self._put(
            PoolItem(
                handle=str(hit["handle"]),
                source_code=str(hit["source_code"]),
                source_class=str(hit["source_class"]),
                anchor_child_id=str(hit["anchor_child_id"]),
                anchor_char_start=int(hit["anchor_char_start"]),
                anchor_char_end=int(hit["anchor_char_end"]),
                first_step=step,
                best_rank=int(hit["fused_rank"]),
                via_tool=via_tool,
            )
        )

    def add_lookup(self, item: dict[str, Any], *, rank: int, step: int) -> bool:
        """Add a found ``ResolvedEvidence``; the anchor is chosen when re-resolved."""
        handle = str(item["handle"])
        if handle in self._items:
            return True
        return self._put(
            PoolItem(
                handle=handle,
                source_code=_source_code_of(handle),
                source_class=str(item.get("source_class") or ""),
                anchor_child_id="",
                anchor_char_start=0,
                anchor_char_end=0,
                first_step=step,
                best_rank=rank,
                via_tool="get_evidence",
            )
        )

    def discard(self, handle: str) -> None:
        """Forget a handle that no longer resolves (NOT_FOUND / SOURCE_DELETED)."""
        self._items.pop(handle, None)

    def items(self) -> tuple[PoolItem, ...]:
        return tuple(
            sorted(
                self._items.values(),
                key=lambda i: (i.best_rank, i.first_step, self._seq[i.handle]),
            )
        )


_RESOLVE = """
WITH req AS (
    SELECT * FROM unnest(CAST(:handles AS text[]), CAST(:children AS uuid[])) AS r(handle, child_id)
)
SELECT p.handle, p.id, s.source_code, v.source_class,
       a.id, a.char_start, a.char_end, f.id, f.char_start, f.char_end
FROM req
JOIN parent_chunks p ON p.workspace_id = :ws AND p.handle = req.handle
JOIN source_versions v ON v.id = p.source_version_id AND v.workspace_id = :ws
JOIN sources s ON s.id = v.source_id AND s.workspace_id = :ws
LEFT JOIN child_chunks a
       ON a.workspace_id = :ws AND a.parent_id = p.id AND a.id = req.child_id
LEFT JOIN LATERAL (
    SELECT c.id, c.char_start, c.char_end FROM child_chunks c
    WHERE c.workspace_id = :ws AND c.parent_id = p.id
    ORDER BY c.ordinal LIMIT 1
) f ON true
WHERE s.deleted_at IS NULL AND v.status <> 'purged'
  AND (cardinality(CAST(:classes AS text[])) = 0 OR v.source_class = ANY(CAST(:classes AS text[])))
"""


def _uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value) if value else None
    except ValueError:
        return None


async def pool_to_candidates(
    factory: SessionFactory,
    scope: WorkspaceScope,
    pool: Sequence[PoolItem],
    *,
    source_classes: Sequence[str] = (),
) -> list[ParentCandidate]:
    """Resolve pooled handles to ranked :class:`ParentCandidate` s for ``build_pack``.

    Keeps pool order (ranks 1..n). Drops foreign, unknown, deleted and purged handles, and,
    when ``source_classes`` is non-empty (the run's class filter), handles of any other class
    (enforced here from the database's class, whatever the tools returned). The
    anchor is the tool-reported child if it still belongs to that parent, otherwise the
    parent's first child; spans always come from the database.
    """
    prefix = f"{scope.workspace_code}/"
    wanted: list[PoolItem] = []
    seen: set[str] = set()
    for item in pool:
        if item.handle in seen or not item.handle.startswith(prefix):
            continue
        seen.add(item.handle)
        wanted.append(item)
    if not wanted:
        return []
    async with scoped_session(factory, scope) as session:
        rows = (
            await session.execute(
                text(_RESOLVE),
                {
                    "ws": scope.workspace_id,
                    "handles": [i.handle for i in wanted],
                    "children": [_uuid_or_none(i.anchor_child_id) for i in wanted],
                    "classes": sorted({str(c) for c in source_classes}),
                },
            )
        ).all()
    by_handle = {str(r[0]): tuple(r) for r in rows}
    candidates: list[ParentCandidate] = []
    for item in wanted:
        row = by_handle.get(item.handle)
        if row is None:
            continue
        _, parent_id, code, cls, a_id, a_start, a_end, f_id, f_start, f_end = row
        child = (a_id, a_start, a_end) if a_id is not None else (f_id, f_start, f_end)
        if child[0] is None:
            continue  # a parent without children cannot be anchored (never expected)
        rank = len(candidates) + 1
        anchor = LaneAnchor(
            lane=AGENT_LANE,
            rank=rank,
            child_rank=item.best_rank,
            child_id=child[0],
            char_start=int(child[1]),
            char_end=int(child[2]),
            score=0.0,
        )
        candidates.append(
            ParentCandidate(
                parent_id=parent_id,
                handle=item.handle,
                source_code=str(code),
                source_class=str(cls),
                anchors=(anchor,),
                fused_rank=rank,
                rank=rank,
            )
        )
    return candidates
