"""Run arms over a frozen dataset split and collect per-item results.

Each query runs in its own scoped session (as a request would), timed end to end in-process.
One warm-up query per arm runs first and is discarded, so model loading and cold caches do
not distort latency. Results keep the top ``KEEP_TOP`` parents per item for failure analysis.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session, unscoped_session
from marketsignal.evaluation.arms import Arm
from marketsignal.evaluation.dataset import Dataset, GoldItem
from marketsignal.evaluation.metrics import ItemScore, score_item

KEEP_TOP = 20
WARMUP_QUERY = "warm-up query for latency measurement"


@dataclass(frozen=True, slots=True)
class ItemRun:
    item: GoldItem
    score: ItemScore
    parents: list[str]
    timings_ms: dict[str, float]
    flags: tuple[str, ...]
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item.id,
            "fact_ranks": dict(self.score.fact_ranks),
            "top": self.parents[:KEEP_TOP],
            "timings_ms": self.timings_ms,
            "flags": list(self.flags),
            "detail": self.detail,
        }


async def _scopes(factory: SessionFactory, codes: set[str]) -> dict[str, WorkspaceScope]:
    async with unscoped_session(factory) as session:
        rows = (
            await session.execute(
                text("SELECT id, code FROM workspaces WHERE code = ANY(:c)"), {"c": sorted(codes)}
            )
        ).all()
    return {code: WorkspaceScope(ws_id, code) for ws_id, code in rows}


async def run_arm(arm: Arm, items: Sequence[GoldItem], factory: SessionFactory) -> list[ItemRun]:
    scopes = await _scopes(factory, {i.workspace for i in items})
    warm_scope = scopes[items[0].workspace]
    async with scoped_session(factory, warm_scope) as session:
        await arm.run(session, warm_scope, WARMUP_QUERY)
    runs: list[ItemRun] = []
    for item in items:
        scope = scopes[item.workspace]
        start = time.perf_counter()
        async with scoped_session(factory, scope) as session:
            out = await arm.run(session, scope, item.question)
        wall = round((time.perf_counter() - start) * 1000, 2)
        timings = {**out.timings_ms, "wall_ms": wall}
        runs.append(
            ItemRun(
                item, score_item(item, out.parents), out.parents, timings, out.flags, out.detail
            )
        )
    return runs


def select(dataset: Dataset, split: str) -> list[GoldItem]:
    items = list(dataset.split(split))
    if not items:
        raise ValueError(f"split {split!r} is empty")
    return items
