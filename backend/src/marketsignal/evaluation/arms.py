"""Evaluation arms: a named retrieval configuration that turns a query into ranked parents.

Every arm returns *distinct parent handles* in rank order (children are mapped to their parent,
first occurrence wins - plan §26), plus stage timings, degradation flags and per-lane detail for
failure analysis. Arms run the production code paths; they never re-implement retrieval.

``baseline-dense`` and ``baseline-lexical`` are the Phase 1 smoke lanes exactly as shipped
(``retrieval/smoke.py``, unchanged): they are the untouched baselines of the Phase 2 report.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.evaluation.metrics import dedupe_parents
from marketsignal.providers.embeddings import Embedder
from marketsignal.retrieval.pipeline import RetrievalService
from marketsignal.retrieval.smoke import dense_search, lexical_search

BASELINE_CHILD_K = 100  # plan §13 lane depth; deep enough to fill 20 distinct parents


@dataclass(frozen=True, slots=True)
class ArmOutput:
    parents: list[str]
    timings_ms: dict[str, float]
    flags: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)


class Arm(Protocol):
    name: str

    def config(self) -> dict[str, Any]: ...

    async def run(
        self, factory: SessionFactory, scope: WorkspaceScope, query: str
    ) -> ArmOutput: ...


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


@dataclass
class BaselineLexicalArm:
    """Phase 1 smoke lexical lane: ``websearch_to_tsquery`` (AND semantics) + ``ts_rank_cd``."""

    name: str = "baseline-lexical"

    def config(self) -> dict[str, Any]:
        return {"arm": self.name, "lane": "smoke.lexical_search", "child_k": BASELINE_CHILD_K}

    async def run(self, factory: SessionFactory, scope: WorkspaceScope, query: str) -> ArmOutput:
        start = time.perf_counter()
        async with scoped_session(factory, scope) as session:
            hits = await lexical_search(session, scope.workspace_id, query, BASELINE_CHILD_K)
        sql_ms = _ms(start)
        parents = dedupe_parents([h.handle for h in hits])
        return ArmOutput(
            parents,
            {"lexical_ms": sql_ms, "total_ms": sql_ms},
            detail={"lexical_children": len(hits)},
        )


@dataclass
class BaselineDenseArm:
    """Phase 1 smoke dense lane: bge-small without a query instruction, HNSW + iterative scan."""

    embedder_factory: Callable[[], Embedder]
    settings: Settings
    name: str = "baseline-dense"

    def config(self) -> dict[str, Any]:
        return {
            "arm": self.name,
            "lane": "smoke.dense_search",
            "child_k": BASELINE_CHILD_K,
            "model": self.settings.embed_model_id,
            "query_instruction": None,
            "ef_search": self.settings.hnsw_ef_search,
        }

    async def run(self, factory: SessionFactory, scope: WorkspaceScope, query: str) -> ArmOutput:
        start = time.perf_counter()
        embedder = self.embedder_factory()
        vector = await asyncio.to_thread(embedder.embed_query, query)
        embed_ms = _ms(start)
        sql_start = time.perf_counter()
        async with scoped_session(factory, scope) as session:
            hits = await dense_search(
                session,
                scope.workspace_id,
                vector,
                model_id=embedder.model_id,
                dimensions=self.settings.embed_dimensions,
                k=BASELINE_CHILD_K,
                ef_search=self.settings.hnsw_ef_search,
            )
        sql_ms = _ms(sql_start)
        parents = dedupe_parents([h.handle for h in hits])
        return ArmOutput(
            parents,
            {"embed_ms": embed_ms, "dense_ms": sql_ms, "total_ms": _ms(start)},
            detail={"dense_children": len(hits)},
        )


@dataclass
class PipelineArm:
    """The production ``RetrievalService`` under one configuration."""

    service: RetrievalService
    name: str

    def config(self) -> dict[str, Any]:
        return {
            "arm": self.name,
            "config_hash": self.service.config_hash,
            **self.service.config.as_dict(),
        }

    async def run(self, factory: SessionFactory, scope: WorkspaceScope, query: str) -> ArmOutput:
        result = await self.service.search(factory, scope, query)
        top = result.parents[:KEEP_DETAIL]
        detail = {
            "lanes": {p.handle: {a.lane: a.rank for a in p.anchors} for p in top},
            "rerank": {p.handle: p.rerank_score for p in top if p.rerank_score is not None},
            "fused_rank": {p.handle: p.fused_rank for p in top},
        }
        if "balance" in result.trace.stages:
            detail["balance"] = result.trace.stages["balance"]
        return ArmOutput(
            [p.handle for p in result.parents],
            dict(result.trace.timings_ms),
            result.flags,
            detail,
        )


KEEP_DETAIL = 20
PIPELINE_ARMS: dict[str, dict[str, Any]] = {
    "dense": {"use_lexical": False, "rerank": False, "balance": False},
    "lexical": {"use_dense": False, "rerank": False, "balance": False},
    "hybrid": {"rerank": False, "balance": False},
    "dense-rerank": {"use_lexical": False, "rerank": True, "balance": False},
    "hybrid-rerank": {"rerank": True, "balance": False},
    "hybrid-rerank-balance": {"rerank": True, "balance": True},
    "hybrid-balance": {"rerank": False, "balance": True},
}
