"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import hmac
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis

from marketsignal.agent.runtime import ResearchAgent
from marketsignal.api.errors import install_error_handlers
from marketsignal.api.routers import (
    dev,
    evidence,
    health,
    results,
    runs,
    search,
    sources,
    workspaces,
)
from marketsignal.config import Settings, check_production_secrets, get_settings
from marketsignal.db.engine import create_engine, create_session_factory
from marketsignal.health import role_is_privileged
from marketsignal.mcp.client import HttpToolTransport
from marketsignal.mcp.server import GovernedMCPServer, build_mcp_app
from marketsignal.providers.embeddings import Embedder, FastEmbedEmbedder
from marketsignal.providers.llm.base import AgentLLM, LLMProvider
from marketsignal.providers.rerankers import FastEmbedCrossEncoder
from marketsignal.retrieval.lanes import DocumentFrequencies
from marketsignal.retrieval.pipeline import QueryEmbeddingCache, RetrievalService
from marketsignal.retrieval.rerank import RerankExecutor
from marketsignal.retrieval.types import RetrievalConfig
from marketsignal.runs.broker import RunBroker
from marketsignal.runs.executor import StandardRunExecutor
from marketsignal.runs.reaper import live_run_ids, orphan_after_s, reap_interrupted_runs
from marketsignal.telemetry.logging import configure_logging, get_logger
from marketsignal.tools.contracts import ToolTransport
from marketsignal.tools.fallback import FallbackToolTransport
from marketsignal.tools.governance import ToolGovernor
from marketsignal.tools.inprocess import InProcessToolTransport

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


def _lazy_llm(settings: Settings) -> Callable[[], LLMProvider]:
    """Build the synthesis provider on first use (never at import or startup)."""
    provider: list[LLMProvider] = []

    def get() -> LLMProvider:
        if not provider:
            if settings.llm_provider == "fake":
                from marketsignal.providers.llm.base import LLMUnavailableError
                from marketsignal.providers.llm.fake import FakeLLM, ScriptedResponse

                # Deterministic offline stand-in: every call is "model unavailable", so runs
                # degrade to evidence-only answers (never an AssertionError from the script).
                unavailable = LLMUnavailableError("fake LLM provider has no scripted response")
                provider.append(FakeLLM([ScriptedResponse(error=unavailable)], repeat_last=True))
            else:
                from marketsignal.providers.llm.anthropic import AnthropicProvider

                provider.append(
                    AnthropicProvider(
                        model=settings.llm_model,
                        api_key=settings.anthropic_api_key,
                        thinking="adaptive" if settings.llm_thinking == "adaptive" else "disabled",
                    )
                )
        return provider[0]

    return get


def _agent_llm(app: FastAPI, settings: Settings) -> Callable[[], AgentLLM]:
    """The research agent's tool-use model: the synthesis provider when it supports agent
    steps (Anthropic), else a stand-in whose every step is "unavailable" (research then falls
    back to the standard gather, PLANNER_UNAVAILABLE_FALLBACK). A provider that cannot be built
    (e.g. no API key) gets the same stand-in, so research degrades like standard mode instead of
    failing the run; only the exception type is logged."""

    def get() -> AgentLLM:
        from marketsignal.providers.llm.base import LLMUnavailableError
        from marketsignal.providers.llm.fake import FakeAgentLLM, ScriptedTurn

        def unavailable(reason: str) -> AgentLLM:
            down = LLMUnavailableError(reason)
            return FakeAgentLLM(lambda _request, _index: ScriptedTurn(content=(), error=down))

        try:
            provider = app.state.llm_provider()
        except Exception as exc:
            log.warning("agent_llm_provider_unavailable", error=type(exc).__name__)
            return unavailable("tool-use model could not be configured")
        if callable(getattr(provider, "step", None)):  # e.g. AnthropicProvider
            return cast(AgentLLM, provider)
        return unavailable("no tool-use model configured")

    return get


def _tool_transport(app: FastAPI, settings: Settings) -> ToolTransport:
    """In-process by default; Streamable HTTP over loopback when ``tools_transport=http``.
    Both run the same governed registry (parity is tested). HTTP is wrapped so a call whose
    transport failed (server never reached) is re-run in process with the same credential and
    flagged TOOLS_TRANSPORT_FALLBACK (plan §27); governor results are never retried."""
    if settings.tools_transport == "http":
        return FallbackToolTransport(
            primary=HttpToolTransport(settings.mcp_base_url),
            fallback=InProcessToolTransport(app.state.tool_governor),
        )
    return InProcessToolTransport(app.state.tool_governor)


async def _start_mcp(server: GovernedMCPServer, stop: asyncio.Event) -> asyncio.Task[None]:
    """Run the MCP session manager (spike 0001: it must be running while /mcp serves) in its
    own task, so its task group is entered and exited in the same task whatever task runs the
    app lifespan."""
    ready = asyncio.Event()

    async def run() -> None:
        async with server.session_manager.run():
            ready.set()
            await stop.wait()

    task = asyncio.create_task(run())
    waiter = asyncio.create_task(ready.wait())
    await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
    waiter.cancel()
    if task.done():
        task.result()  # startup failed: raise it here
    return task


class _DeferredMCP:
    """``/mcp`` forwards to the MCP app built in the lifespan (the governor needs the session
    factory, which exists only once the app starts); before that it answers 503."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        target = getattr(self._app.state, "mcp_asgi", None)
        if target is None:
            response = Response(status_code=503)
            await response(scope, receive, send)
            return
        await target(scope, receive, send)


async def _reap(app: FastAPI) -> None:
    try:
        reaped = await reap_interrupted_runs(
            app.state.session_factory,
            orphan_after_s(app.state.settings),
            exclude=live_run_ids(app.state.run_tasks),
        )
    except Exception as exc:
        log.warning("run_reaper_skipped", reason=type(exc).__name__)
        return
    if reaped:
        log.info("runs_reaped", count=reaped)


async def _reap_periodically(app: FastAPI) -> None:
    """Orphans appear while the API runs (another process died), not only before startup."""
    while True:
        await asyncio.sleep(app.state.settings.run_reaper_interval_s)
        await _reap(app)


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
    reaper: asyncio.Task[None] | None = None
    mcp_task: asyncio.Task[None] | None = None
    mcp_stop = asyncio.Event()
    try:
        await _guard_db_role(app, settings)
        await _reap(app)
        reaper = asyncio.create_task(_reap_periodically(app))
        app.state.tool_governor = ToolGovernor(
            factory=app.state.session_factory,
            settings=settings,
            retrieval=app.state.retrieval_service,
        )
        mcp_server, mcp_asgi = build_mcp_app(
            app.state.tool_governor, settings, allowed_hosts=settings.mcp_allowed_hosts or None
        )
        mcp_task = await _start_mcp(mcp_server, mcp_stop)
        app.state.mcp_asgi = mcp_asgi
        log.info("startup_complete", env=settings.env)
        yield
    finally:
        app.state.mcp_asgi = None
        mcp_stop.set()
        if mcp_task is not None:
            await asyncio.gather(mcp_task, return_exceptions=True)
        if reaper is not None:
            reaper.cancel()
            await asyncio.gather(reaper, return_exceptions=True)
        if app.state.redis is not None:
            await app.state.redis.aclose()
        for task in list(app.state.run_tasks.values()):
            task.cancel()  # each cancelled run still emits done (termination: cancelled)
        if app.state.run_tasks:
            await asyncio.gather(*app.state.run_tasks.values(), return_exceptions=True)
        app.state.rerank_executor.shutdown()
        await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    check_production_secrets(settings)
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
    app.state.rerank_executor = RerankExecutor(
        FastEmbedCrossEncoder(
            settings.rerank_model_name, settings.model_cache_dir, threads=settings.rerank_threads
        ),
        settings.rerank_concurrency,
    )
    # Models load lazily on first use; the embedder is looked up per call so tests can swap it.
    app.state.retrieval_service = RetrievalService(
        RetrievalConfig.from_settings(settings),
        embedder=lambda: app.state.query_embedder(),
        rerank_executor=app.state.rerank_executor,
        df_cache=DocumentFrequencies(settings.lexical_idf_cache_size),
        query_cache=QueryEmbeddingCache(settings.query_embedding_cache_size),
    )
    # Phase 3 runs: in-process broker + task registry; the executor and LLM are looked up per
    # run so tests (and an offline demo) can swap in FakeLLM.
    app.state.run_broker = RunBroker()
    app.state.run_tasks = {}
    app.state.llm_provider = _lazy_llm(settings)
    app.state.agent_llm_provider = _agent_llm(app, settings)
    app.state.mcp_asgi = None
    app.state.run_executor = lambda: StandardRunExecutor(
        app.state.session_factory,
        settings,
        app.state.retrieval_service,
        lambda: app.state.llm_provider(),
        app.state.run_broker,
        agent_factory=lambda: ResearchAgent(
            llm=app.state.agent_llm_provider(),
            transport=_tool_transport(app, settings),
            settings=settings,
        ),
    )
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

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        # Stream tokens travel in ?st=: never leak URLs via Referer; never buffer SSE in proxies.
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            response.headers["X-Accel-Buffering"] = "no"
            response.headers["Cache-Control"] = "no-cache"
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
    app.include_router(search.router)
    app.include_router(runs.router)
    app.include_router(results.router)
    # Governed MCP tools over Streamable HTTP (loopback only unless mcp_public; ADR-0006).
    app.mount("/mcp", _DeferredMCP(app))
    if settings.env != "prod" and settings.dev_endpoints_enabled:
        app.include_router(dev.router)
    return app
