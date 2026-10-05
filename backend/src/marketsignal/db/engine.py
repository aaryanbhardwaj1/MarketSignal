"""Async SQLAlchemy engine and session factory (psycopg 3)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from marketsignal.config import Settings
from marketsignal.db.scope import install_scope_listener


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        pool_pre_ping=True,
        connect_args={
            # Server-side guard: no single statement may run away with the pool.
            "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
            "application_name": "marketsignal",
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    install_scope_listener()
    return async_sessionmaker(engine, expire_on_commit=False)
