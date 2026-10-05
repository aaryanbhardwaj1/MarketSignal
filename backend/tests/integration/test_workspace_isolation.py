"""Row-level-security isolation, exercised as the runtime role ``ms_app``.

These are negative tests: they prove the database refuses cross-workspace access even when
application code is wrong. They would all pass vacuously under a superuser connection, which
is why ``test_runtime_role_cannot_bypass_rls`` exists.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from marketsignal.db.scope import (
    WorkspaceScope,
    WorkspaceScopeNotSetError,
    install_scope_listener,
    workspace_scope,
)

pytestmark = pytest.mark.integration

SET_SCOPE = text("SELECT set_config('app.workspace_id', :ws, true)")


async def _seed_state(engine: AsyncEngine, ws: uuid.UUID, version: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(SET_SCOPE, {"ws": str(ws)})
        await conn.execute(
            text("INSERT INTO workspace_corpus_state (workspace_id, version) VALUES (:ws, :v)"),
            {"ws": ws, "v": version},
        )


async def _insert_state_row(
    engine: AsyncEngine, *, scope: uuid.UUID, row_workspace: uuid.UUID
) -> None:
    async with engine.begin() as conn:
        await conn.execute(SET_SCOPE, {"ws": str(scope)})
        await conn.execute(
            text("INSERT INTO workspace_corpus_state (workspace_id) VALUES (:w)"),
            {"w": row_workspace},
        )


async def test_runtime_role_cannot_bypass_rls(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        row = await conn.execute(
            text(
                "SELECT rolsuper, rolbypassrls, "
                "pg_has_role(current_user, 'ms_owner', 'MEMBER') AS is_owner_member "
                "FROM pg_roles WHERE rolname = current_user"
            )
        )
        rolsuper, rolbypassrls, is_owner_member = row.one()
    assert (rolsuper, rolbypassrls, is_owner_member) == (False, False, False)


async def test_scope_a_sees_only_workspace_a(
    app_engine: AsyncEngine, two_workspaces: tuple[uuid.UUID, uuid.UUID]
) -> None:
    ws_a, ws_b = two_workspaces
    await _seed_state(app_engine, ws_a, 1)
    await _seed_state(app_engine, ws_b, 2)

    async with app_engine.begin() as conn:
        await conn.execute(SET_SCOPE, {"ws": str(ws_a)})
        rows = (await conn.execute(text("SELECT workspace_id FROM workspace_corpus_state"))).all()
        b_count = await conn.execute(
            text("SELECT count(*) FROM workspace_corpus_state WHERE workspace_id = :b"), {"b": ws_b}
        )
    assert [r[0] for r in rows] == [ws_a]
    assert b_count.scalar_one() == 0


async def test_cross_workspace_write_is_rejected_by_with_check(
    app_engine: AsyncEngine, two_workspaces: tuple[uuid.UUID, uuid.UUID]
) -> None:
    ws_a, ws_b = two_workspaces
    with pytest.raises(DBAPIError, match="row-level security"):
        await _insert_state_row(app_engine, scope=ws_a, row_workspace=ws_b)


async def test_unscoped_query_fails_closed_on_fresh_and_reused_connections(
    app_engine: AsyncEngine, two_workspaces: tuple[uuid.UUID, uuid.UUID]
) -> None:
    ws_a, _ = two_workspaces
    # pool_size=1: the second transaction reuses the connection whose GUC was set (then cleared
    # to '' at commit) by the first. Both histories must yield the same explicit error.
    for _ in range(2):
        with pytest.raises(DBAPIError, match="WORKSPACE_SCOPE_NOT_SET"):
            async with app_engine.begin() as conn:
                await conn.execute(text("SELECT count(*) FROM workspace_corpus_state"))
        async with app_engine.begin() as conn:
            await conn.execute(SET_SCOPE, {"ws": str(ws_a)})
            await conn.execute(text("SELECT count(*) FROM workspace_corpus_state"))


async def test_orm_session_sets_scope_per_transaction(
    app_engine: AsyncEngine, two_workspaces: tuple[uuid.UUID, uuid.UUID]
) -> None:
    ws_a, ws_b = two_workspaces
    await _seed_state(app_engine, ws_a, 7)
    await _seed_state(app_engine, ws_b, 9)
    install_scope_listener()

    async with AsyncSession(app_engine) as session:
        with pytest.raises(WorkspaceScopeNotSetError):
            await session.execute(text("SELECT 1"))
        await session.rollback()

        with workspace_scope(WorkspaceScope(ws_a, "A")):
            first = await session.execute(text("SELECT version FROM workspace_corpus_state"))
            assert first.scalars().all() == [7]
            await session.commit()
            # A new (autobegun) transaction after commit is re-scoped by the listener.
            second = await session.execute(text("SELECT current_setting('app.workspace_id')"))
            assert second.scalar_one() == str(ws_a)
            await session.commit()
