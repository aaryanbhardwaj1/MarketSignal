"""Leakage-resistant dev/test split (plan §27: 70/30, grouped).

Items are grouped with union-find. Two items share a group when they share any of:
* a required fact (paraphrases of the same planted fact);
* a related fact: ledger contradiction pairs, superseded pairs and distractor pairs (an item on
  one side of a contradiction teaches the retriever about the other);
* a satisfying parent handle (the same evidence unit).
Whole groups are then assigned to dev or test, stratified by the group's dominant category, in
an order fixed by a hash of the group key and a seed, so the split is deterministic and does
not depend on file order.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import replace

from marketsignal.evaluation.dataset import GoldItem

DEFAULT_TEST_FRACTION = 0.30
DEFAULT_SEED = "retrieval-v0"


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)


def leakage_groups(
    items: Sequence[GoldItem], related_pairs: Iterable[tuple[str, str]] = ()
) -> dict[str, str]:
    """Map item id -> group key (the smallest member key of its connected component)."""
    uf = _UnionFind()
    for a, b in related_pairs:
        uf.union(f"fact:{a}", f"fact:{b}")
    for item in items:
        node = f"item:{item.id}"
        uf.find(node)
        for fact in item.required_facts:
            uf.union(node, f"fact:{fact.fact_id}")
            for handle in fact.handles():
                uf.union(node, f"parent:{handle}")
    roots = {item.id: uf.find(f"item:{item.id}") for item in items}
    # Name each group by its smallest item id: stable and readable.
    members: dict[str, list[str]] = defaultdict(list)
    for item_id, root in roots.items():
        members[root].append(item_id)
    names = {root: f"G-{min(ids)}" for root, ids in members.items()}
    return {item_id: names[root] for item_id, root in roots.items()}


def _order_key(group: str, seed: str) -> str:
    return hashlib.sha256(f"{seed}:{group}".encode()).hexdigest()


def assign_splits(
    items: Sequence[GoldItem],
    related_pairs: Iterable[tuple[str, str]] = (),
    *,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    seed: str = DEFAULT_SEED,
) -> list[GoldItem]:
    groups = leakage_groups(items, related_pairs)
    by_group: dict[str, list[GoldItem]] = defaultdict(list)
    for item in items:
        by_group[groups[item.id]].append(item)

    def dominant(members: list[GoldItem]) -> str:
        counts = Counter(m.category for m in members)
        return min(counts, key=lambda c: (-counts[c], c))

    strata: dict[str, list[str]] = defaultdict(list)
    for group, members in by_group.items():
        strata[dominant(members)].append(group)

    split_of: dict[str, str] = {}
    for groups_in_stratum in strata.values():
        total = sum(len(by_group[g]) for g in groups_in_stratum)
        target = round(total * test_fraction)
        taken = 0
        for group in sorted(groups_in_stratum, key=lambda g: _order_key(g, seed)):
            size = len(by_group[group])
            if taken < target and taken + size <= target + 1:
                split_of[group] = "test"
                taken += size
            else:
                split_of[group] = "dev"
    return [replace(i, split=split_of[groups[i.id]], group=groups[i.id]) for i in items]


def leakage_violations(
    items: Sequence[GoldItem], related_pairs: Iterable[tuple[str, str]] = ()
) -> list[str]:
    """Every reason a fact, related fact or parent appears in both splits (empty = clean)."""
    pairs = list(related_pairs)
    problems: list[str] = []
    groups = leakage_groups(items, pairs)
    for group in sorted(set(groups.values())):
        splits = {i.split for i in items if groups[i.id] == group}
        if len(splits) > 1:
            problems.append(f"group {group} spans {sorted(s or '?' for s in splits)}")
    facts_by_split: dict[str, set[str]] = defaultdict(set)
    handles_by_split: dict[str, set[str]] = defaultdict(set)
    for item in items:
        for fact in item.required_facts:
            facts_by_split[item.split or "?"].add(fact.fact_id)
            handles_by_split[item.split or "?"] |= fact.handles()
    shared = facts_by_split["dev"] & facts_by_split["test"]
    if shared:
        problems.append(f"facts in both splits: {sorted(shared)}")
    shared_handles = handles_by_split["dev"] & handles_by_split["test"]
    if shared_handles:
        problems.append(f"parents in both splits: {sorted(shared_handles)}")
    for a, b in pairs:
        if (a in facts_by_split["dev"] and b in facts_by_split["test"]) or (
            b in facts_by_split["dev"] and a in facts_by_split["test"]
        ):
            problems.append(f"related facts split across dev/test: {a}, {b}")
    if any(i.split not in ("dev", "test") for i in items):
        problems.append("items without a split")
    return problems
