"""Procrastinate worker (ADR-0010).

Jobs carry only ids (workspace_id, source_version_id); the task re-derives the workspace scope
and re-reads the version under RLS, failing closed if it is not visible. Run with::

    uv run procrastinate --app=marketsignal.worker.app.app worker --queues=ingestion

The same process can also be driven in-process (tests, verification scripts) through
:func:`run_pending_jobs`.
"""

from __future__ import annotations

import uuid
from typing import Any

import procrastinate
from sqlalchemy import text

from marketsignal.config import Settings, get_settings
from marketsignal.db.engine import create_engine, create_session_factory
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import unscoped_session
from marketsignal.ingestion.pipeline import IngestionDeps, ingest_version
from marketsignal.ingestion.tokenizer import HuggingFaceTokenizer
from marketsignal.providers.embeddings import CachedEmbedder, EmbeddingCache, FastEmbedEmbedder
from marketsignal.telemetry.logging import configure_logging, get_logger

log = get_logger(__name__)
INGESTION_QUEUE = "ingestion"


def libpq_dsn(sqlalchemy_url: str) -> str:
    """SQLAlchemy URL -> libpq conninfo (Procrastinate uses psycopg directly)."""
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


def build_app(settings: Settings) -> procrastinate.App:
    return procrastinate.App(
        connector=procrastinate.PsycopgConnector(
            conninfo=libpq_dsn(settings.database_url.get_secret_value()),
            kwargs={"application_name": "marketsignal-jobs"},
            min_size=1,
            max_size=4,
        ),
    )


app = build_app(get_settings())
_deps: IngestionDeps | None = None


def set_deps(deps: IngestionDeps | None) -> None:
    """Override the worker's dependencies (tests inject fakes)."""
    global _deps
    _deps = deps


def default_deps(settings: Settings) -> IngestionDeps:
    embedder = FastEmbedEmbedder(
        settings.embed_model_id,
        settings.embed_model_name,
        settings.embed_dimensions,
        settings.model_cache_dir,
        threads=settings.embed_threads,
        batch_size=settings.embed_batch_size,
    )
    cached = CachedEmbedder(
        embedder, EmbeddingCache(settings.embedding_cache_dir, settings.embed_model_id)
    )
    engine = create_engine(settings)
    return IngestionDeps(
        session_factory=create_session_factory(engine),
        settings=settings,
        embedder=cached,
        tokenizer=HuggingFaceTokenizer(embedder.tokenizer),
    )


def _get_deps() -> IngestionDeps:
    global _deps
    if _deps is None:
        settings = get_settings()
        configure_logging(settings.log_level, settings.log_json)
        _deps = default_deps(settings)
    return _deps


async def resolve_scope(deps: IngestionDeps, workspace_id: uuid.UUID) -> WorkspaceScope | None:
    async with unscoped_session(deps.session_factory) as session:
        code = (
            await session.execute(
                text("SELECT code FROM workspaces WHERE id = :id"), {"id": workspace_id}
            )
        ).scalar_one_or_none()
    return WorkspaceScope(workspace_id, code) if code else None


@app.task(name="ingest_source_version", queue=INGESTION_QUEUE, pass_context=False)
async def ingest_source_version(workspace_id: str, source_version_id: str) -> str:
    deps = _get_deps()
    scope = await resolve_scope(deps, uuid.UUID(workspace_id))
    if scope is None:
        log.warning("ingest_job_workspace_missing", workspace_id=workspace_id)
        return "missing"
    status = await ingest_version(deps, scope, uuid.UUID(source_version_id))
    log.info("ingest_job_done", source_version_id=source_version_id, status=status)
    return status


async def defer_ingestion(connection: Any, workspace_id: uuid.UUID, version_id: uuid.UUID) -> int:
    """Enqueue on the caller's connection, inside the caller's transaction."""
    job_id: int = await ingest_source_version.configure(connection=connection).defer_async(
        workspace_id=str(workspace_id), source_version_id=str(version_id)
    )
    return job_id


async def run_pending_jobs() -> None:
    """Process every queued job, then return (tests and verification scripts)."""
    await app.run_worker_async(
        queues=[INGESTION_QUEUE], wait=False, install_signal_handlers=False, listen_notify=False
    )
