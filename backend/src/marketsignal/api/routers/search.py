"""Evidence search: the production retrieval pipeline over one workspace.

``GET /api/workspaces/{ws}/search?q=…`` returns ranked *parents* (citable evidence), each with its
canonical handle, locator, source, the anchor child's span inside the parent (for highlighting
via ``/evidence/{handle}?child_id=``), a short snippet around that span, stage ranks/scores and
the request's degradation flags. The full stage trace is persisted to ``retrieval_traces`` and
referenced by ``trace_id``; it is not part of the response.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from marketsignal.api.deps import Factory, Scope, SettingsDep
from marketsignal.db.session import scoped_session
from marketsignal.domain.enums import Confidentiality, SourceClass
from marketsignal.retrieval.pipeline import RetrievalService
from marketsignal.retrieval.traces import persist_trace
from marketsignal.retrieval.types import ParentCandidate, RetrievalFilters

router = APIRouter(prefix="/api/workspaces/{ws}/search", tags=["search"])
SNIPPET_CONTEXT = 120
MODES: dict[str, dict[str, bool]] = {
    "full": {},
    "hybrid": {"rerank": False},
    "dense": {"use_lexical": False, "rerank": False},
    "lexical": {"use_dense": False, "rerank": False},
}


async def _hydrate(
    factory: Factory, scope: Any, parents: list[ParentCandidate]
) -> dict[uuid.UUID, dict[str, Any]]:
    if not parents:
        return {}
    async with scoped_session(factory, scope) as session:
        rows = await session.execute(
            text(
                "SELECT p.id, p.locator_label, p.text, s.title, s.source_type "
                "FROM parent_chunks p JOIN source_versions v ON v.id = p.source_version_id "
                "JOIN sources s ON s.id = v.source_id WHERE p.id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": [p.parent_id for p in parents]},
        )
        return {
            r[0]: {"locator_label": r[1], "text": r[2], "title": r[3], "type": r[4]}
            for r in rows.all()
        }


def _snippet(text_: str, start: int, end: int) -> dict[str, Any]:
    lo, hi = max(0, start - SNIPPET_CONTEXT), min(len(text_), end + SNIPPET_CONTEXT)
    return {
        "text": text_[lo:hi],
        "mark_start": start - lo,
        "mark_end": min(end, hi) - lo,
        "truncated_left": lo > 0,
        "truncated_right": hi < len(text_),
    }


@router.get("")
async def search(
    request: Request,
    scope: Scope,
    factory: Factory,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, max_length=400)],
    k: Annotated[int, Query(ge=1, le=50)] = 10,
    mode: Literal["full", "hybrid", "dense", "lexical"] = "full",
    source_class: Annotated[list[SourceClass] | None, Query()] = None,
    source: Annotated[list[str] | None, Query(max_length=20)] = None,
    max_confidentiality: Confidentiality = Confidentiality.RESTRICTED,
) -> dict[str, Any]:
    base: RetrievalService = request.app.state.retrieval_service
    service = base.with_config(base.config.with_(**MODES[mode])) if MODES[mode] else base
    filters = RetrievalFilters(
        source_classes=tuple(c.value for c in source_class or ()),
        source_codes=tuple(source or ()),
        max_confidentiality=max_confidentiality,
    )
    async with scoped_session(factory, scope) as session:
        result = await service.search(session, scope, q, filters)
    trace_id = (
        await persist_trace(factory, scope, result, origin="api")
        if settings.retrieval_trace_persist
        else None
    )
    top = list(result.parents[:k])
    meta = await _hydrate(factory, scope, top)
    items = []
    for parent in top:
        info = meta.get(parent.parent_id)
        if info is None:  # purged between retrieval and hydration: the handle now 410s
            continue
        anchor = parent.best_anchor()
        items.append(
            {
                "rank": parent.rank,
                "handle": parent.handle,
                "locator_label": info["locator_label"],
                "source_code": parent.source_code,
                "source_title": info["title"],
                "source_type": info["type"],
                "source_class": parent.source_class,
                "anchor": {
                    "child_id": str(anchor.child_id),
                    "lane": anchor.lane,
                    "char_start": anchor.char_start,
                    "char_end": anchor.char_end,
                },
                "snippet": _snippet(info["text"], anchor.char_start, anchor.char_end),
                "scores": {
                    "rrf": round(parent.rrf_score, 6),
                    "rerank": parent.rerank_score,
                    "fused_rank": parent.fused_rank,
                    "lanes": {a.lane: a.rank for a in parent.anchors},
                },
            }
        )
    return {
        "query": q,
        "mode": mode,
        "items": items,
        "flags": list(result.flags),
        "trace_id": str(trace_id) if trace_id else None,
        "timings_ms": result.trace.timings_ms,
    }
