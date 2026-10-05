"""FastAPI application factory."""

from __future__ import annotations

import hmac
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis

from marketsignal.api.errors import install_error_handlers
from marketsignal.api.routers import dev, evidence, health, sources, workspaces
from marketsignal.config import Settings, get_settings
from marketsignal.db.engine import create_engine, create_session_factory
from marketsignal.health import role_is_privileged
from marketsignal.providers.embeddings import Embedder, FastEmbedEmbedder
from marketsignal.telemetry.logging import configure_logging, get_logger

log = get_logger(__name__)


class PrivilegedDatabaseRoleError(RuntimeError):
    """The runtime DB role bypasses row-level security; refusing to serve."""


async def _guard_db_role(app: FastAPI, settings: Settings) -> None:
    """Fail fast if connected as a role that bypasses RLS.

    If the database is unreachable at startup we keep running: ``/readyz`` reports it and the
    orchestrator retries. A *reachable* privileged role, however, is a misconfiguration that
    would make every isolation guarantee false, so startup aborts.
    """
    try:
        privileged = await role_is_privileged(app.state.engine)
    except Exception as exc:
        log.warning("db_role_check_skipped", reason=type(exc).__name__)
        return
    if privileged and not settings.allow_privileged_db_role:
        raise PrivilegedDatabaseRoleError(
            "MS_DATABASE_URL connects as a superuser/BYPASSRLS role; use the ms_app role"
        )


def _lazy_query_embedder(settings: Settings) -> Callable[[], Embedder]:
    """Load the ONNX model on first dense query, not at startup (fast boot, low idle RSS)."""
    embedder: list[Embedder] = []

    def get() -> Embedder:
        if not embedder:
            embedder.append(
                FastEmbedEmbedder(
                    settings.embed_model_id,
                    settings.embed_model_name,
                    settings.embed_dimensions,
                    settings.model_cache_dir,
                    threads=settings.embed_threads,
                )
            )
        return embedder[0]

    return get


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    app.state.engine = create_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.redis = (
        Redis.from_url(settings.redis_url.get_secret_value(), socket_timeout=1.0)
        if settings.redis_url
        else None
    )
    try:
        await _guard_db_role(app, settings)
        log.info("startup_complete", env=settings.env)
        yield
    finally:
        if app.state.redis is not None:
            await app.state.redis.aclose()
        await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title="MarketSignal API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.env == "prod" else "/docs",
        openapi_url=None if settings.env == "prod" else "/openapi.json",
    )
    app.state.settings = settings
    # Overridable seams (tests inject an in-process worker and a deterministic embedder).
    from marketsignal.worker.app import defer_ingestion

    app.state.defer_job = defer_ingestion
    app.state.query_embedder = _lazy_query_embedder(settings)
    install_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        allow_credentials=False,  # bearer tokens, not cookies (ADR-0014)
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request) -> Response:
        token = settings.metrics_token
        if token is not None:
            expected = f"Bearer {token.get_secret_value()}"
            provided = request.headers.get("authorization", "")
            if not hmac.compare_digest(provided.encode(), expected.encode()):
                return Response(status_code=401)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(health.router)
    app.include_router(workspaces.router)
    app.include_router(sources.router)
    app.include_router(evidence.router)
    if settings.env != "prod" and settings.dev_endpoints_enabled:
        app.include_router(dev.router)
    return app
