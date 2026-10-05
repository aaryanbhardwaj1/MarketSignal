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
    for workspace_id in ids:
        await purge_workspace(owner_engine, workspace_id)


# Dependency order for test cleanup. FORCE RLS applies to the schema owner too, so each delete
# runs inside the workspace's own scope; RESTRICT foreign keys make the order explicit.
_PURGE_ORDER = (
    "DELETE FROM chunk_embeddings",
    "DELETE FROM child_chunks",
    "DELETE FROM parent_chunks",
    "DELETE FROM dataset_tables",
    "DELETE FROM source_blobs",
    "UPDATE sources SET current_version_id = NULL",
    "DELETE FROM source_versions",
    "DELETE FROM sources",
    "DELETE FROM audit_events",
    "DELETE FROM workspace_corpus_state",
)


async def purge_workspace(owner_engine: AsyncEngine, workspace_id: uuid.UUID) -> None:
    async with owner_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": str(workspace_id)}
        )
        for statement in _PURGE_ORDER:
            await conn.execute(text(statement))
        await conn.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": workspace_id})
