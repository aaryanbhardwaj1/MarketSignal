"""``search_evidence``: the production hybrid pipeline (dense + lexical, parent-level RRF,
reranker off - the Phase 2 decision) over the run's workspace, as typed evidence hits."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import text

from marketsignal.db.session import scoped_session
from marketsignal.retrieval.pipeline import RetrievalService
from marketsignal.retrieval.types import ParentCandidate, RetrievalFilters
from marketsignal.tools.contracts import EvidenceHit, SearchEvidenceIn, SearchEvidenceOut
from marketsignal.tools.env import ToolEnv
from marketsignal.tools.impl.common import snippet

DEFAULT_TOP_K = 8

_HYDRATE = """
SELECT x.handle, p.locator_label, s.title, c.text
FROM unnest(CAST(:handles AS text[]), CAST(:children AS uuid[])) AS x(handle, child)
JOIN parent_chunks p ON p.workspace_id = :ws AND p.handle = x.handle
JOIN child_chunks c ON c.workspace_id = :ws AND c.id = x.child AND c.parent_id = p.id
JOIN source_versions v ON v.id = p.source_version_id
JOIN sources s ON s.id = v.source_id
"""


def production_service(service: RetrievalService) -> RetrievalService:
    """The tool never enables the experimental reranker, whatever the service was built with."""
    if not service.config.rerank:
        return service
    return service.with_config(service.config.with_(rerank=False))


async def search_evidence(env: ToolEnv, args: SearchEvidenceIn) -> SearchEvidenceOut:
    top_k = args.top_k or DEFAULT_TOP_K
    filters = RetrievalFilters.of(
        [c.value for c in args.source_classes or ()],
        args.source_codes or (),
        env.max_confidentiality,
    )
    service = production_service(env.retrieval)
    result = await service.search(env.factory, env.scope, args.query, filters, top_k=top_k)
    parents = list(result.parents[:top_k])
    details = await _hydrate(env, parents)
    hits = [
        _hit(p, details[p.handle]) for p in parents if p.handle in details
    ]  # a parent purged between the lanes and hydration is dropped, never invented
    return SearchEvidenceOut(
        hits=hits,
        classes_found=dict(sorted(Counter(h.source_class.value for h in hits).items())),
        warnings=sorted(set(result.flags)),
    )


async def _hydrate(env: ToolEnv, parents: list[ParentCandidate]) -> dict[str, tuple[Any, ...]]:
    if not parents:
        return {}
    async with scoped_session(env.factory, env.scope) as session:
        rows = await session.execute(
            text(_HYDRATE),
            {
                "ws": env.scope.workspace_id,
                "handles": [p.handle for p in parents],
                "children": [p.best_anchor().child_id for p in parents],
            },
        )
        return {str(r[0]): tuple(r) for r in rows.all()}


def _hit(p: ParentCandidate, row: tuple[Any, ...]) -> EvidenceHit:
    anchor = p.best_anchor()
    return EvidenceHit(
        handle=p.handle,
        source_code=p.source_code,
        source_title=str(row[2]),
        source_class=p.source_class,
        locator_label=str(row[1]),
        snippet=snippet(str(row[3])),
        anchor_child_id=str(anchor.child_id),
        anchor_char_start=anchor.char_start,
        anchor_char_end=anchor.char_end,
        dense_rank=p.lane_rank("dense"),
        lexical_rank=p.lane_rank("lexical"),
        fused_rank=p.fused_rank or p.rank or 1,
    )
