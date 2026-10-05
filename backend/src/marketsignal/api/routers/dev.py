"""Developer-only endpoints (disabled in prod): Phase 1 smoke search for ingestion verification."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request

from marketsignal.api.deps import Factory, Scope, SettingsDep
from marketsignal.api.errors import AppError
from marketsignal.db.session import scoped_session
from marketsignal.providers.embeddings import EmbedderUnavailableError
from marketsignal.retrieval.smoke import dense_search, lexical_search

router = APIRouter(prefix="/api/workspaces/{ws}/dev", tags=["dev"])


@router.get("/search")
async def smoke_search(
    request: Request,
    scope: Scope,
    factory: Factory,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, max_length=400)],
    mode: Literal["lexical", "dense"] = "lexical",
    k: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    if settings.env == "prod" or not settings.dev_endpoints_enabled:
        raise AppError(404, "NOT_FOUND", "not found")
    async with scoped_session(factory, scope) as session:
        if mode == "lexical":
            hits = await lexical_search(session, scope.workspace_id, q, k)
        else:
            embedder = request.app.state.query_embedder()
            try:
                vector = await asyncio.to_thread(embedder.embed_query, q)
            except EmbedderUnavailableError as exc:
                raise AppError(503, "EMBEDDER_UNAVAILABLE", "dense search unavailable") from exc
            hits = await dense_search(
                session,
                scope.workspace_id,
                vector,
                model_id=embedder.model_id,
                dimensions=settings.embed_dimensions,
                k=k,
                ef_search=settings.hnsw_ef_search,
            )
    return {"mode": mode, "query": q, "hits": [h.as_dict() for h in hits]}
