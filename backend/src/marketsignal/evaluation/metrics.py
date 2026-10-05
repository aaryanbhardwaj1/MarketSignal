"""Parent-level retrieval metrics (plan §26).

Every arm produces a ranked list of *distinct parent handles* (children mapped to parents, first
occurrence wins), so dense-only, lexical-only and fused arms are scored identically.

Per item, each required fact gets the 1-based rank of its first satisfying parent (or None):
* recall@k  = share of the item's required facts satisfied within the top k;
* hit@k     = at least one required fact satisfied within the top k;
* RR        = 1 / rank of the first satisfied fact (0 when none is found in the list).
Aggregates are means over items. ``k = pool`` (the fused top-20) is Recall@pool.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from marketsignal.evaluation.dataset import GoldItem

DEFAULT_KS = (1, 3, 5, 10, 20)


@dataclass(frozen=True, slots=True)
class ItemScore:
    item_id: str
    fact_ranks: Mapping[str, int | None]

    def recall_at(self, k: int) -> float:
        found = sum(1 for r in self.fact_ranks.values() if r is not None and r <= k)
        return found / len(self.fact_ranks)

    def hit_at(self, k: int) -> bool:
        return any(r is not None and r <= k for r in self.fact_ranks.values())

    def reciprocal_rank(self, cutoff: int | None = None) -> float:
        ranks = [r for r in self.fact_ranks.values() if r is not None]
        if cutoff is not None:
            ranks = [r for r in ranks if r <= cutoff]
        return 1.0 / min(ranks) if ranks else 0.0


def dedupe_parents(handles: Sequence[str]) -> list[str]:
    """Child-level handle list -> distinct parents in first-occurrence order."""
    seen: set[str] = set()
    out: list[str] = []
    for handle in handles:
        if handle not in seen:
            seen.add(handle)
            out.append(handle)
    return out


def score_item(item: GoldItem, ranked_parents: Sequence[str]) -> ItemScore:
    position = {h: i for i, h in enumerate(ranked_parents, start=1)}
    ranks: dict[str, int | None] = {}
    for fact in item.required_facts:
        hits = [position[h] for h in fact.handles() if h in position]
        ranks[fact.fact_id] = min(hits) if hits else None
    return ItemScore(item.id, ranks)


def aggregate(scores: Sequence[ItemScore], ks: Sequence[int] = DEFAULT_KS) -> dict[str, float]:
    n = len(scores)
    if n == 0:
        return {"n": 0}
    out: dict[str, float] = {"n": n}
    for k in ks:
        out[f"recall@{k}"] = sum(s.recall_at(k) for s in scores) / n
        out[f"hit@{k}"] = sum(s.hit_at(k) for s in scores) / n
    out["mrr"] = sum(s.reciprocal_rank() for s in scores) / n
    out["mrr@10"] = sum(s.reciprocal_rank(10) for s in scores) / n
    return out
