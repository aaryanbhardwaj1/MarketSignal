# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""The computed-result endpoint (Phase 5): persisted results, workspace isolation."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import scoped_session, unscoped_session
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture

pytestmark = pytest.mark.integration


async def test_results_endpoint_returns_persisted_result_and_isolates_workspaces(
    harness: Harness,
) -> None:
    """GET /results/{id}: the persisted computed result in its own workspace; 404 elsewhere."""
    ws = await harness.create_workspace()
    other = await harness.create_workspace()
    csv = b"segment,nps\nGen Z,9\nMillennial,6\n"
    assert (await harness.upload(ws, "d.csv", csv, source_code="D")).status_code in (200, 202)
    await harness.drain()
    app = harness.client._transport.app  # type: ignore[attr-defined]
    factory = app.state.session_factory
    async with unscoped_session(factory) as session:
        ws_id = (
            await session.execute(text("SELECT id FROM workspaces WHERE code = :c"), {"c": ws})
        ).scalar_one()
    async with scoped_session(factory, WorkspaceScope(ws_id, ws)) as session:
        rid = (
            await session.execute(
                text(
                    "INSERT INTO analytics_results (workspace_id, source_version_id, table_id, "
                    "tool, spec, result) SELECT workspace_id, source_version_id, id, 'aggregate', "
                    '\'{}\', \'{"rows": [], "dataset": "D:1"}\' FROM dataset_tables LIMIT 1 '
                    "RETURNING id"
                )
            )
        ).scalar_one()
        await session.commit()
    ok = await harness.client.get(f"/api/workspaces/{ws}/results/{rid}")
    assert ok.status_code == 200
    assert ok.json()["kind"] == "result"
    assert ok.json()["result"]["dataset"] == "D:1"
    assert (await harness.client.get(f"/api/workspaces/{other}/results/{rid}")).status_code == 404
    missing = await harness.client.get(f"/api/workspaces/{ws}/results/{uuid.uuid4()}")
    assert missing.status_code == 404
