"""Scoped and unscoped session helpers.

``scoped_session`` is the only way application code touches tenant tables: it binds the
workspace scope for the duration of the block, and the ``after_begin`` listener turns that into
the transaction-local RLS setting for every transaction the session opens.
``unscoped_session`` exists for the two non-tenant tables (workspaces, workspace_members);
RLS still blocks every tenant table inside it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from marketsignal.db.scope import WorkspaceScope, mark_unscoped, workspace_scope

SessionFactory = async_sessionmaker[AsyncSession]


@asynccontextmanager
async def scoped_session(
    factory: SessionFactory, scope: WorkspaceScope
) -> AsyncIterator[AsyncSession]:
    with workspace_scope(scope):
        async with factory() as session:
            yield session


@asynccontextmanager
async def unscoped_session(factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        mark_unscoped(session)
        yield session
