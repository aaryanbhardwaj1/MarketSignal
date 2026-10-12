# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""Demo snapshot round trip on the test database (FakeLLM only, own harness workspace).

A research run (governed ``aggregate`` + evidence search, so tool runs, a persisted analytics
result and result/evidence citations) and a standard run (retrieval trace with child anchors)
are exported, their rows deleted, and re-imported: every row comes back identical (token events
aside, which the snapshot drops), a second import is a no-op, the export is byte-stable, and a
changed parent hash aborts the import before anything is written. The workspace is then dropped
with the reset script, narrowed to this workspace's own code."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.providers.llm.fake import FakeLLM
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_results_answers import (
    ANSWER,
    _aggregate_turns,
    _install_agent,
    _upload_csv,
)
from tests.integration.test_runs_api import (
    FACT,
    GOOD,
    OTHER,
    _ask,
    _install,
    _scoped,
    _seed,
    _stream,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import _demo_common as common
import demo_export
import demo_import
import demo_reset

pytestmark = pytest.mark.integration

_BY_RUN = {
    "query_runs": "id = ANY(CAST(:runs AS uuid[]))",
    "run_events": "run_id = ANY(CAST(:runs AS uuid[])) AND type <> 'token'",
    "tool_runs": "query_run_id = ANY(CAST(:runs AS uuid[]))",
    "verification_attempts": "query_run_id = ANY(CAST(:runs AS uuid[]))",
    "retrieval_traces": "query_run_id = ANY(CAST(:runs AS uuid[]))",
    "analytics_results": "query_run_id = ANY(CAST(:runs AS uuid[]))",
    "conversations": "id = ANY(CAST(:convs AS uuid[]))",
    "messages": "conversation_id = ANY(CAST(:convs AS uuid[]))",
}


async def _dump(engine: AsyncEngine, ws: str, convs: list[str], runs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    async with engine.begin() as conn:
        await _scoped(conn, ws)
        for table, where in _BY_RUN.items():
            rows = await conn.execute(
                text(f"SELECT to_jsonb(t) FROM {table} t WHERE {where}"),
                {"runs": runs, "convs": convs},
            )
            out[table] = sorted((dict(r[0]) for r in rows.all()), key=repr)
    return out


async def _delete_runs(engine: AsyncEngine, ws: str, convs: list[str], runs: list[str]) -> None:
    async with engine.begin() as conn:
        await _scoped(conn, ws)
        params = {"runs": runs, "convs": convs}
        for table in ("retrieval_traces", "analytics_results"):  # no cascade from query_runs
            await conn.execute(
                text(f"DELETE FROM {table} WHERE query_run_id = ANY(CAST(:runs AS uuid[]))"),
                params,
            )
        await conn.execute(
            text("DELETE FROM conversations WHERE id = ANY(CAST(:convs AS uuid[]))"), params
        )


async def _token_events(engine: AsyncEngine, ws: str, runs: list[str]) -> int:
    async with engine.begin() as conn:
        await _scoped(conn, ws)
        found = await conn.execute(
            text(
                "SELECT count(*) FROM run_events WHERE type = 'token' "
                "AND run_id = ANY(CAST(:runs AS uuid[]))"
            ),
            {"runs": runs},
        )
        return int(found.scalar_one())


async def _make_runs(h: Harness, ws: str) -> tuple[list[str], list[str]]:
    _install(h, FakeLLM([ANSWER], repeat_last=True))
    _install_agent(h, _aggregate_turns(search=True))
    research_conv, research = await _ask(h, ws, "Average NPS by segment?", mode="research")
    await _stream(h, research["stream_url"])
    _install(h, FakeLLM([GOOD], repeat_last=True))
    standard_conv, standard = await _ask(h, ws, "What frustrates Gen Z buyers?")
    await _stream(h, standard["stream_url"])
    return [research_conv, standard_conv], [research["run_id"], standard["run_id"]]


async def test_export_delete_import_round_trip_and_drift_abort(
    harness: Harness, owner_engine: AsyncEngine
) -> None:
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    await _upload_csv(harness, ws)
    convs, runs = await _make_runs(harness, ws)

    before = await _dump(owner_engine, ws, convs, runs)
    assert before["analytics_results"]
    assert before["tool_runs"]
    assert before["retrieval_traces"]
    assert before["verification_attempts"]
    assert len(before["messages"]) == 4
    assert await _token_events(owner_engine, ws, runs) > 0

    snapshot = await demo_export.export_snapshot(owner_engine, ws, convs)
    demo_export.check_safe(snapshot)
    rendered = demo_export.render(snapshot)
    assert "workspace_id" not in rendered
    assert '"type": "token"' not in rendered
    assert '"anchor_child_id": "child:' in rendered
    assert '"child_id": "child:' in rendered
    assert '"dataset_ref"' in rendered
    assert '"source_version_id"' not in rendered
    again = await demo_export.export_snapshot(owner_engine, ws, convs)
    assert demo_export.render(again) == rendered  # byte-identical rerun

    await _delete_runs(owner_engine, ws, convs, runs)
    assert all(not rows for rows in (await _dump(owner_engine, ws, convs, runs)).values())

    report = await demo_import.import_snapshot(owner_engine, snapshot, workspace_code=ws)
    assert report.inserted["query_runs"] == 2
    assert report.inserted["analytics_results"] == 1
    assert await _dump(owner_engine, ws, convs, runs) == before
    assert await _token_events(owner_engine, ws, runs) == 0

    repeat = await demo_import.import_snapshot(owner_engine, snapshot)
    assert sum(repeat.inserted.values()) == 0  # idempotent
    assert sum(repeat.skipped.values()) == sum(len(v) for v in before.values())

    with pytest.raises(common.SnapshotError, match="not"):
        await demo_import.import_snapshot(owner_engine, snapshot, workspace_code="NORTHSTAR")

    # Corpus drift: the live parent of a cited passage changes -> abort, nothing written.
    await _delete_runs(owner_engine, ws, convs, runs)
    cited = next(
        c["handle"]
        for m in before["messages"]
        for c in m["citations"]
        if c.get("kind", "evidence") == "evidence"
    )
    async with owner_engine.begin() as conn:
        await _scoped(conn, ws)
        await conn.execute(
            text("UPDATE parent_chunks SET content_hash = repeat('0', 64) WHERE handle = :h"),
            {"h": cited},
        )
    with pytest.raises(common.SnapshotError, match="parent hash"):
        await demo_import.import_snapshot(owner_engine, copy.deepcopy(snapshot))
    assert all(not rows for rows in (await _dump(owner_engine, ws, convs, runs)).values())

    # A second workspace's rows must survive the reset of the first (explicit workspace filters).
    bystander = await harness.create_workspace()
    await _seed(harness, bystander, FACT, OTHER)
    async with owner_engine.connect() as conn:
        bystander_id = await common.workspace_id(conn, bystander)
    bystander_before = await demo_reset.counts(owner_engine, bystander_id)
    assert bystander_before["sources"] > 0

    dropped = await demo_reset.reset(owner_engine, only=[ws], yes=True, dry_run=False)
    assert dropped == [ws]
    assert await demo_reset.counts(owner_engine, bystander_id) == bystander_before
    async with owner_engine.connect() as conn:
        gone = await conn.execute(
            text("SELECT count(*) FROM workspaces WHERE code = :c"), {"c": ws}
        )
        assert gone.scalar_one() == 0
