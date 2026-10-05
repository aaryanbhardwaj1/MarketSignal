"""/readyz against real services, running as the non-privileged application role."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.api.app import PrivilegedDatabaseRoleError, create_app
from marketsignal.config import Settings

pytestmark = pytest.mark.integration


async def test_readyz_is_ready_as_app_role(settings: Settings, app_engine: AsyncEngine) -> None:
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/readyz")
    body = response.json()
    assert response.status_code == 200, body
    assert body["checks"]["db_role"]["status"] == "ok"
    assert body["checks"]["migrations"]["status"] == "ok"
    assert body["checks"]["pgvector"]["status"] == "ok"
    assert body["status"] in {"ready", "degraded"}  # degraded only if redis is down


async def test_startup_refuses_superuser_connection(settings: Settings) -> None:
    superuser_url = os.environ.get("MS_TEST_SUPERUSER_DATABASE_URL")
    if not superuser_url:
        pytest.skip("MS_TEST_SUPERUSER_DATABASE_URL not set")
    privileged = settings.model_copy(update={"database_url": SecretStr(superuser_url)})
    app = create_app(privileged)
    with pytest.raises(PrivilegedDatabaseRoleError):
        async with app.router.lifespan_context(app):
            pass
