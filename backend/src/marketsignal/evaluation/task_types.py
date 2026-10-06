"""Task-type eligibility annotation (Phase 2 follow-up, approved 2026-10-05).

Some curated questions are answered by facts that live only in purely numeric spreadsheet rows.
Under ADR-0003 those rows are child-less parents: analytics-only by design, so no retrieval lane
can return them. Counting them in retrieval-quality denominators measures the architecture's
routing, not retrieval quality. Each item is therefore annotated:

* ``retrieval``  - every required fact has at least one satisfying parent with retrieval children;
* ``analytics``  - no required fact does (Phase 5 analytics tool);
* ``multi_tool`` - some facts are retrievable, some analytics-only (needs both).

The rule is structural (does the satisfying parent have children in the index?), never based on
retrieval results. The annotation lives beside the frozen dataset (``task-types.json``) so the
v0 items, labels and hashes stay byte-identical; retrieval metrics are reported over
``retrieval`` items, and full-set composition is always reported next to them.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import text

from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.evaluation.dataset import Dataset
from marketsignal.evaluation.gold import index_state, load_workspace

RETRIEVAL = "retrieval"
ANALYTICS = "analytics"
MULTI_TOOL = "multi_tool"
TASK_TYPES = (RETRIEVAL, ANALYTICS, MULTI_TOOL)


def item_task_type(fact_kinds: dict[str, str]) -> str:
    kinds = set(fact_kinds.values())
    if kinds == {RETRIEVAL}:
        return RETRIEVAL
    if kinds == {ANALYTICS}:
        return ANALYTICS
    return MULTI_TOOL


async def classify(dataset: Dataset, factory: SessionFactory) -> dict[str, Any]:
    codes = sorted({i.workspace for i in dataset.items})
    workspaces = {code: await load_workspace(factory, code) for code in codes}
    with_children: set[str] = set()
    for ws in workspaces.values():
        async with scoped_session(factory, ws.scope) as session:
            rows = await session.execute(
                text(
                    "SELECT DISTINCT p.handle FROM parent_chunks p "
                    "JOIN child_chunks c ON c.parent_id = p.id"
                )
            )
            with_children |= {r[0] for r in rows.all()}
    items: dict[str, Any] = {}
    for item in dataset.items:
        facts = {
            f.fact_id: RETRIEVAL if any(h in with_children for h in f.handles()) else ANALYTICS
            for f in item.required_facts
        }
        items[item.id] = {"split": item.split, "task_type": item_task_type(facts), "facts": facts}
    composition = {
        split: dict(Counter(v["task_type"] for v in items.values() if v["split"] == split))
        for split in ("dev", "test")
    }
    return {
        "dataset_version": dataset.version,
        "items_sha256": dataset.manifest.get("items_sha256"),
        "rule": (
            "a fact is 'retrieval' if any satisfying parent has retrieval children in the index, "
            "else 'analytics' (child-less numeric row, ADR-0003); item = retrieval | analytics | "
            "multi_tool (mixed)"
        ),
        "index": await index_state(factory, workspaces),
        "composition": composition,
        "items": items,
    }


def load_task_types(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item_id: v["task_type"] for item_id, v in data["items"].items()}
