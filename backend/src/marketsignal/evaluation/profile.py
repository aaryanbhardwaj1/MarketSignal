"""Profile the production retrieval lanes under forced RLS (Phase 2 exit item).

For each query, the *exact* lane statements the production ``RetrievalService`` sends (captured
at the cursor, with their bound parameters) are replayed under ``EXPLAIN (ANALYZE, BUFFERS,
FORMAT JSON)``:
* as ``ms_app`` inside the workspace scope - RLS enabled and forced, as in production;
* as a superuser (RLS bypassed) - the control, when a superuser DSN is given.
Reported per lane and role: execution time p50/p95, whether the GIN (``child_chunks_tsv``) or
HNSW index was used, rows read from ``child_chunks`` / ``chunk_embeddings``, and the plan shape.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.db.scope import WorkspaceScope
from marketsignal.evaluation.dataset import GoldItem
from marketsignal.evaluation.stats import percentile
from marketsignal.retrieval.pipeline import RetrievalService

LANE_MARKERS = {"dense": "WITH dense AS MATERIALIZED", "lexical": "WITH terms AS"}
HNSW_SETTINGS = "set_config('hnsw.ef_search'"


@dataclass
class Captured:
    lane: str
    statement: str
    params: Any
    settings: tuple[str, Any] | None  # the preceding transaction-local HNSW set_config


@dataclass
class Capture:
    statements: list[Captured] = field(default_factory=list)
    _pending_settings: tuple[str, Any] | None = None

    def hook(self, conn: Any, cursor: Any, statement: str, params: Any, *_: Any) -> None:
        if HNSW_SETTINGS in statement:
            self._pending_settings = (statement, params)
            return
        for lane, marker in LANE_MARKERS.items():
            if marker in statement:
                settings = self._pending_settings if lane == "dense" else None
                self.statements.append(Captured(lane, statement, params, settings))
                self._pending_settings = None


def _walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("Plans", []):
        yield from _walk(child)


def summarize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    root = plan["Plan"]
    nodes = list(_walk(root))
    index_names = sorted({n.get("Index Name", "") for n in nodes if n.get("Index Name")})
    scanned: dict[str, int] = defaultdict(int)
    for n in nodes:
        rel = n.get("Relation Name")
        if rel in ("child_chunks", "chunk_embeddings") and "Scan" in n.get("Node Type", ""):
            loops = int(n.get("Actual Loops", 1))
            scanned[rel] += (
                int(n.get("Actual Rows", 0)) + int(n.get("Rows Removed by Filter", 0))
            ) * loops
    return {
        "execution_ms": round(float(plan["Execution Time"]), 3),
        "planning_ms": round(float(plan["Planning Time"]), 3),
        "gin_used": any("tsv" in name for name in index_names),
        "hnsw_used": any("hnsw" in name for name in index_names),
        "indexes": index_names,
        "node_types": sorted({n["Node Type"] for n in nodes}),
        "rows_scanned": dict(scanned),
    }


async def _explain(
    engine: AsyncEngine, captured: Captured, scope: WorkspaceScope | None
) -> dict[str, Any]:
    async with engine.connect() as conn, conn.begin():
        if scope is not None:
            await conn.execute(
                text("SELECT set_config('app.workspace_id', :ws, true)"),
                {"ws": str(scope.workspace_id)},
            )
        if captured.settings is not None:
            await conn.exec_driver_sql(captured.settings[0], captured.settings[1])
        result = await conn.exec_driver_sql(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + captured.statement, captured.params
        )
        raw = result.scalar_one()
    plan = raw[0] if isinstance(raw, list) else json.loads(raw)[0]
    return summarize_plan(plan)


async def profile_lanes(
    service: RetrievalService,
    items: Sequence[GoldItem],
    scopes: dict[str, WorkspaceScope],
    app_engine: AsyncEngine,
    superuser_engine: AsyncEngine | None,
) -> dict[str, Any]:
    capture = Capture()
    event.listen(app_engine.sync_engine, "before_cursor_execute", capture.hook)
    factory_items: list[tuple[GoldItem, list[Captured]]] = []
    try:
        from marketsignal.db.engine import create_session_factory

        factory = create_session_factory(app_engine)
        for item in items:
            before = len(capture.statements)
            await service.search(factory, scopes[item.workspace], item.question)
            factory_items.append((item, capture.statements[before:]))
    finally:
        event.remove(app_engine.sync_engine, "before_cursor_execute", capture.hook)

    rows: list[dict[str, Any]] = []
    for item, statements in factory_items:
        for captured in statements:
            row: dict[str, Any] = {"item_id": item.id, "lane": captured.lane}
            row["rls"] = await _explain(app_engine, captured, scopes[item.workspace])
            if superuser_engine is not None:
                row["no_rls"] = await _explain(superuser_engine, captured, None)
            rows.append(row)
    return {"queries": len(items), "plans": rows, "summary": summarize(rows)}


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for lane in ("dense", "lexical"):
        for role in ("rls", "no_rls"):
            plans = [r[role] for r in rows if r["lane"] == lane and role in r]
            if not plans:
                continue
            times = [p["execution_ms"] for p in plans]
            scanned = [sum(p["rows_scanned"].values()) for p in plans]
            out[f"{lane}/{role}"] = {
                "n": len(plans),
                "execution_ms_p50": round(percentile(times, 0.5), 3),
                "execution_ms_p95": round(percentile(times, 0.95), 3),
                "gin_used": sum(1 for p in plans if p["gin_used"]),
                "hnsw_used": sum(1 for p in plans if p["hnsw_used"]),
                "rows_scanned_p50": int(percentile(scanned, 0.5)),
                "rows_scanned_max": max(scanned),
                "node_types": sorted({t for p in plans for t in p["node_types"]}),
                "indexes": sorted({i for p in plans for i in p["indexes"]}),
            }
    return out
