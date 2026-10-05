"""Parent-level reciprocal rank fusion (plan §14, ADR-0002).

1. Within each lane, children collapse to their parent; the best-ranked child is that lane's
   *anchor* for the parent, and the parent's lane rank is its position among the lane's
   distinct parents.
2. ``score(p) = Σ_lanes w_lane / (k + rank_lane(p))``.
3. Ties break by the best single-lane rank, then by parent handle (deterministic).

Fusing at the parent level is what lets RRF see *agreement*: if dense finds window 2 of parent
P and lexical finds window 3 of P, child-level fusion would treat them as two weak candidates;
parent-level fusion sees one parent supported by both retrievers.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from marketsignal.retrieval.types import ChildHit, LaneAnchor, ParentCandidate


@dataclass(frozen=True, slots=True)
class LaneParents:
    lane: str
    anchors: dict[uuid.UUID, LaneAnchor]  # parent_id -> anchor in this lane
    meta: dict[uuid.UUID, tuple[str, str, str]]  # parent_id -> (handle, source_code, class)


def collapse_lane(lane: str, hits: Sequence[ChildHit]) -> LaneParents:
    anchors: dict[uuid.UUID, LaneAnchor] = {}
    meta: dict[uuid.UUID, tuple[str, str, str]] = {}
    for hit in sorted(hits, key=lambda h: h.rank):
        if hit.parent_id in anchors:
            continue
        anchors[hit.parent_id] = LaneAnchor(
            lane=lane,
            rank=len(anchors) + 1,
            child_rank=hit.rank,
            child_id=hit.child_id,
            char_start=hit.char_start,
            char_end=hit.char_end,
            score=hit.score,
        )
        meta[hit.parent_id] = (hit.parent_handle, hit.source_code, hit.source_class)
    return LaneParents(lane, anchors, meta)


def rrf_fuse(
    lanes: Mapping[str, Sequence[ChildHit]], weights: Mapping[str, float], k: int
) -> list[ParentCandidate]:
    collapsed = [collapse_lane(name, hits) for name, hits in lanes.items()]
    meta: dict[uuid.UUID, tuple[str, str, str]] = {}
    per_parent: dict[uuid.UUID, list[LaneAnchor]] = {}
    for lane in collapsed:
        meta.update(lane.meta)
        for parent_id, anchor in lane.anchors.items():
            per_parent.setdefault(parent_id, []).append(anchor)

    scored: list[tuple[float, int, str, uuid.UUID]] = []
    for parent_id, anchors in per_parent.items():
        score = sum(weights.get(a.lane, 1.0) / (k + a.rank) for a in anchors)
        scored.append((score, min(a.rank for a in anchors), meta[parent_id][0], parent_id))
    scored.sort(key=lambda s: (-s[0], s[1], s[2]))

    out: list[ParentCandidate] = []
    for position, (score, _, handle, parent_id) in enumerate(scored, start=1):
        # Best lane first: highest weighted contribution, then lane name for determinism.
        anchors = sorted(
            per_parent[parent_id], key=lambda a: (-weights.get(a.lane, 1.0) / (k + a.rank), a.lane)
        )
        _, source_code, source_class = meta[parent_id]
        out.append(
            ParentCandidate(
                parent_id=parent_id,
                handle=handle,
                source_code=source_code,
                source_class=source_class,
                anchors=tuple(anchors),
                rrf_score=score,
                fused_rank=position,
                rank=position,
            )
        )
    return out


def single_lane(lane: str, hits: Sequence[ChildHit]) -> list[ParentCandidate]:
    """A one-lane arm: collapse to parents in lane order (RRF with one lane is monotone)."""
    return rrf_fuse({lane: hits}, {lane: 1.0}, k=60)
