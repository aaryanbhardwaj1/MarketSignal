"""Integration fixtures: a real PostgreSQL 18 + pgvector and Redis (docker compose / CI services).

Tests connect as the runtime role ``ms_app`` — never as a superuser — so row-level security is
actually exercised. Locally, tests skip when services are down; with
``MS_REQUIRE_INTEGRATION=1`` (CI) an unreachable service is a hard failure instead.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from marketsignal.config import Settings, get_settings

pytestmark = pytest.mark.integration


def _unavailable(reason: str) -> None:
    if os.environ.get("MS_REQUIRE_INTEGRATION") == "1":
        pytest.fail(f"integration services required but unavailable: {reason}")
    pytest.skip(f"integration services unavailable: {reason}")


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
async def app_engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(settings.database_url.get_secret_value(), pool_size=1)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        _unavailable(f"postgres as ms_app: {type(exc).__name__}")
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def owner_engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(settings.migrations_database_url.get_secret_value())
    yield engine
    await engine.dispose()


def new_workspace_code() -> str:
    return "T" + uuid.uuid4().hex[:10].upper()


@pytest.fixture
async def two_workspaces(owner_engine: AsyncEngine) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    """Two fresh workspaces, removed afterwards by the owner (FK cascade)."""
    ids: list[uuid.UUID] = []
    async with owner_engine.begin() as conn:
        for _ in range(2):
            row = await conn.execute(
                text("INSERT INTO workspaces (code, name) VALUES (:c, :n) RETURNING id"),
                {"c": new_workspace_code(), "n": "integration test"},
            )
            ids.append(row.scalar_one())
    yield ids[0], ids[1]
    async with owner_engine.begin() as conn:
        await conn.execute(text("DELETE FROM workspaces WHERE id = ANY(:ids)"), {"ids": ids})
