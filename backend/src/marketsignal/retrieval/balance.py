"""Deterministic source/class balancing (plan §13, §15).

Two greedy, order-preserving steps:
* **Pool cap** - while filling the rerank pool from the fused list, take at most
  ``pool_source_cap`` parents per source, then fill any remaining pool slots in fused order.
  This stops one large source (hundreds of similar survey rows) from occupying the whole pool
  before the reranker ever sees other sources.
* **Final cap** - in the final ranking, at most ``per_source_max`` parents per source keep
  their place; the overflow is demoted (in order) below the rest rather than dropped. Skipped
  when the request targets a single source.
* **Class floor** - when the request names source classes, each named class with any parent in
  the list gets its best parent into the top-k (plan §15; raw scores are uncalibrated, so the
  rule is positional, not a score threshold).
Every decision is returned for the trace.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from marketsignal.retrieval.types import ParentCandidate


@dataclass
class BalanceDecisions:
    pool_skipped: list[str] = field(default_factory=list)
    demoted: list[str] = field(default_factory=list)
    class_promoted: list[str] = field(default_factory=list)


def cap_pool(
    fused: Sequence[ParentCandidate], pool_size: int, per_source: int, decisions: BalanceDecisions
) -> list[ParentCandidate]:
    counts: Counter[str] = Counter()
    pool: list[ParentCandidate] = []
    skipped: list[ParentCandidate] = []
    for parent in fused:
        if len(pool) >= pool_size:
            break
        if counts[parent.source_code] < per_source:
            counts[parent.source_code] += 1
            pool.append(parent)
        else:
            skipped.append(parent)
    for parent in skipped:  # fill only if the capped pass could not fill the pool
        if len(pool) >= pool_size:
            decisions.pool_skipped.append(parent.handle)
            continue
        pool.append(parent)
    return pool


def cap_final(
    ranked: Sequence[ParentCandidate],
    per_source_max: int,
    decisions: BalanceDecisions,
    *,
    single_source: bool = False,
) -> list[ParentCandidate]:
    if single_source:
        return list(ranked)
    counts: Counter[str] = Counter()
    kept: list[ParentCandidate] = []
    overflow: list[ParentCandidate] = []
    for parent in ranked:
        if counts[parent.source_code] < per_source_max:
            counts[parent.source_code] += 1
            kept.append(parent)
        else:
            overflow.append(parent)
            decisions.demoted.append(parent.handle)
    return kept + overflow


def class_floor(
    ranked: Sequence[ParentCandidate],
    classes: Sequence[str],
    top_k: int,
    decisions: BalanceDecisions,
) -> list[ParentCandidate]:
    out = list(ranked)
    for source_class in classes:
        if any(p.source_class == source_class for p in out[:top_k]):
            continue
        best = next((p for p in out[top_k:] if p.source_class == source_class), None)
        if best is None:
            continue
        out.remove(best)
        out.insert(max(0, top_k - 1), best)
        decisions.class_promoted.append(best.handle)
    return out
