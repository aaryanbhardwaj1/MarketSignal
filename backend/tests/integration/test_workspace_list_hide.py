# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""Test-harness workspaces (codes ``T`` + 10 hex) are hidden from ``GET /api/workspaces`` when
``hide_test_workspaces`` is on, and listed otherwise. Other codes are always listed."""

from __future__ import annotations

import uuid

import pytest

from marketsignal.api.routers.workspaces import TEST_WORKSPACE_CODE
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture

pytestmark = pytest.mark.integration


async def _codes(h: Harness) -> set[str]:
    response = await h.client.get("/api/workspaces")
    assert response.status_code == 200, response.text
    return {w["code"] for w in response.json()}


async def test_hide_test_workspaces(harness: Harness) -> None:
    test_code = await harness.create_workspace()
    visible = "V" + uuid.uuid4().hex[:10].upper()
    created = await harness.client.post("/api/workspaces", json={"code": visible, "name": "V"})
    assert created.status_code == 201, created.text
    harness.workspaces.append(visible)  # purged on teardown

    app = harness.client._transport.app  # type: ignore[attr-defined]
    app.state.settings = app.state.settings.model_copy(update={"hide_test_workspaces": False})
    assert {test_code, visible} <= await _codes(harness)

    app.state.settings = app.state.settings.model_copy(update={"hide_test_workspaces": True})
    codes = await _codes(harness)
    assert visible in codes
    assert test_code not in codes
    assert not any(TEST_WORKSPACE_CODE.match(c) for c in codes)
    # Hidden from the list only: the workspace itself still resolves.
    assert (await harness.client.get(f"/api/workspaces/{test_code}")).status_code == 200
