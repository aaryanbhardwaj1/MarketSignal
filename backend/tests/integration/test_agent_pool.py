# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""pool_to_candidates against real Postgres: scoped resolution, anchors, purge and foreign drops."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.agent.pool import AGENT_LANE, PoolItem, pool_to_candidates
from marketsignal.db.engine import create_engine, create_session_factory
from marketsignal.db.scope import WorkspaceScope
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture

pytestmark = pytest.mark.integration


async def _seed(h: Harness, ws: str, code: str, *paragraphs: str) -> None:
    body = "# Notes\n\n" + "".join(f"## Part {i}\n\n{p}\n\n" for i, p in enumerate(paragraphs))
    response = await h.upload(ws, f"{code.lower()}.md", body.encode(), source_code=code)
    assert response.status_code in (200, 202), response.text
    await h.drain()


_CHILD = "SELECT c.id FROM child_chunks c WHERE c.parent_id = p.id ORDER BY c.ordinal"
_PARENTS_SQL = (
    f"SELECT p.id, p.handle, s.source_code, ({_CHILD} LIMIT 1) AS first_child, "
    f"({_CHILD} DESC LIMIT 1) AS last_child "
    "FROM parent_chunks p JOIN source_versions v ON v.id = p.source_version_id "
    "JOIN sources s ON s.id = v.source_id WHERE p.workspace_id = :ws ORDER BY p.handle"
)


async def _parents(engine: AsyncEngine, ws: str) -> tuple[uuid.UUID, list[dict[str, Any]]]:
    async with engine.begin() as conn:
        ws_id = (
            await conn.execute(text("SELECT id FROM workspaces WHERE code = :c"), {"c": ws})
        ).scalar_one()
        await conn.execute(
            text("SELECT set_config('app.workspace_id', :w, true)"), {"w": str(ws_id)}
        )
        result = await conn.execute(text(_PARENTS_SQL), {"ws": ws_id})
        rows = result.mappings().all()
    return ws_id, [dict(r) for r in rows]


def _item(handle: str, child: uuid.UUID | str | None, rank: int) -> PoolItem:
    return PoolItem(
        handle=handle,
        source_code="?",
        source_class="?",
        anchor_child_id=str(child) if child else "",
        anchor_char_start=0,
        anchor_char_end=1,
        first_step=1,
        best_rank=rank,
        via_tool="search_evidence",
    )


async def test_pool_to_candidates_resolves_scoped_and_drops_purged_and_foreign(
    harness: Harness, owner_engine: AsyncEngine
) -> None:
    ws = await harness.create_workspace()
    other = await harness.create_workspace()
    await _seed(harness, ws, "MEMO", "Fit runs small for Gen Z buyers.", "Returns doubled in Q3.")
    await _seed(harness, ws, "NOTES", "Competitor sizing guide is clearer.")
    await _seed(harness, other, "MEMO", "Other workspace content.")
    ws_id, parents = await _parents(owner_engine, ws)
    _, foreign = await _parents(owner_engine, other)
    memo = [p for p in parents if p["source_code"] == "MEMO"]
    notes = [p for p in parents if p["source_code"] == "NOTES"]
    assert len(memo) >= 2
    assert notes
    assert foreign

    factory = create_session_factory(create_engine(harness.settings))
    scope = WorkspaceScope(workspace_id=ws_id, workspace_code=ws)
    pool = (
        _item(notes[0]["handle"], notes[0]["last_child"], 1),  # tool-reported anchor kept
        _item(memo[0]["handle"], None, 2),  # get_evidence-only: first child
        _item(memo[-1]["handle"], foreign[0]["first_child"], 3),  # anchor not of this parent
        _item(foreign[0]["handle"], foreign[0]["first_child"], 4),  # foreign handle
        _item(f"{ws}/NOPE@v1:S1.B1", None, 5),  # unknown
        _item(notes[0]["handle"], None, 6),  # duplicate
    )
    cands = await pool_to_candidates(factory, scope, pool)
    assert [c.handle for c in cands] == [notes[0]["handle"], memo[0]["handle"]] + (
        [memo[-1]["handle"]] if memo[-1]["handle"] != memo[0]["handle"] else []
    )
    assert [c.rank for c in cands] == list(range(1, len(cands) + 1))
    assert cands[0].parent_id == notes[0]["id"]
    assert cands[0].source_code == "NOTES"
    assert cands[0].best_anchor().child_id == notes[0]["last_child"]
    assert cands[0].best_anchor().lane == AGENT_LANE
    assert cands[0].source_class == "customer"
    assert cands[1].best_anchor().child_id == memo[0]["first_child"]
    assert cands[-1].best_anchor().child_id == memo[-1]["first_child"]
    assert all(c.best_anchor().char_end > c.best_anchor().char_start for c in cands)

    sources = (await harness.client.get(f"/api/workspaces/{ws}/sources")).json()
    memo_id = next(s["source_id"] for s in sources if s["source_code"] == "MEMO")
    assert (
        await harness.client.delete(f"/api/workspaces/{ws}/sources/{memo_id}")
    ).status_code == 200
    after = await pool_to_candidates(factory, scope, pool)
    assert [c.handle for c in after] == [notes[0]["handle"]]
    assert await pool_to_candidates(factory, scope, ()) == []


async def test_pool_to_candidates_enforces_the_runs_source_classes(
    harness: Harness, owner_engine: AsyncEngine
) -> None:
    """H-0/H-19: with a class filter, handles of other classes are dropped (the database's
    class decides, not what the tool reported)."""
    ws = await harness.create_workspace()
    await _seed(harness, ws, "MEMO", "Fit runs small for Gen Z buyers.")
    body = b"# Market\n\n## Part 0\n\nCompetitor sizing guide is clearer.\n"
    response = await harness.upload(ws, "mkt.md", body, source_code="MKT", source_class="market")
    assert response.status_code in (200, 202), response.text
    await harness.drain()
    ws_id, parents = await _parents(owner_engine, ws)
    memo = next(p for p in parents if p["source_code"] == "MEMO")
    mkt = next(p for p in parents if p["source_code"] == "MKT")
    factory = create_session_factory(create_engine(harness.settings))
    scope = WorkspaceScope(workspace_id=ws_id, workspace_code=ws)
    pool = (_item(mkt["handle"], None, 1), _item(memo["handle"], None, 2))
    scoped = await pool_to_candidates(factory, scope, pool, source_classes=("customer",))
    assert [c.handle for c in scoped] == [memo["handle"]]
    both = await pool_to_candidates(factory, scope, pool, source_classes=())
    assert [c.handle for c in both] == [mkt["handle"], memo["handle"]]
