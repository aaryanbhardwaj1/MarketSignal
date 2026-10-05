"""The production retrieval pipeline (plan §11-15).

    query -> dense lane + lexical lane (children, anchors)
          -> parent-level RRF -> rerank pool (optionally source-capped)
          -> cross-encoder MaxP rerank (timeout -> fused order, flagged)
          -> final source/class balancing (optional)
          -> ranked parents, each with its anchor child span

Every stage is recorded in a ``StageTrace`` (candidates, ranks, scores, decisions, timings,
degradation flags). Which stages run is a ``RetrievalConfig``; evaluation arms are configs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.db.scope import WorkspaceScope
from marketsignal.providers.embeddings import Embedder, EmbedderUnavailableError, Vector
from marketsignal.retrieval import balance as bal
from marketsignal.retrieval.fusion import rrf_fuse
from marketsignal.retrieval.lanes import (
    DENSE,
    LEXICAL,
    DocumentFrequencies,
    LaneScope,
    build_lexical_query,
    dense_lane,
    lane_scope,
    lexical_lane,
)
from marketsignal.retrieval.rerank import RerankExecutor, hydrate, rerank_pool
from marketsignal.retrieval.types import (
    ChildHit,
    ParentCandidate,
    RetrievalConfig,
    RetrievalFilters,
    RetrievalResult,
    StageTrace,
)

LEXICAL_FALLBACK = "RETRIEVAL_LEXICAL_FALLBACK"
TRACE_LANE_LIMIT = 100


class QueryEmbeddingCache:
    """In-process LRU keyed by (model, instruction, query) - repeated queries skip the model."""

    def __init__(self, max_entries: int) -> None:
        self._max = max_entries
        self._data: OrderedDict[tuple[str, str, str], Vector] = OrderedDict()

    def get(self, key: tuple[str, str, str]) -> Vector | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key: tuple[str, str, str], value: Vector) -> None:
        if self._max <= 0:
            return
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)


def config_hash(config: dict[str, Any]) -> str:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _lane_trace(hits: Sequence[ChildHit]) -> list[dict[str, Any]]:
    return [
        {
            "rank": h.rank,
            "child_id": str(h.child_id),
            "handle": h.parent_handle,
            "score": round(h.score, 6),
            "span": [h.char_start, h.char_end],
        }
        for h in hits[:TRACE_LANE_LIMIT]
    ]


def _parent_trace(parents: Sequence[ParentCandidate]) -> list[dict[str, Any]]:
    out = []
    for p in parents:
        anchor = p.best_anchor()
        out.append(
            {
                "rank": p.rank,
                "handle": p.handle,
                "source": p.source_code,
                "fused_rank": p.fused_rank,
                "rrf": round(p.rrf_score, 6),
                "rerank": None if p.rerank_score is None else round(p.rerank_score, 4),
                "lanes": {a.lane: a.rank for a in p.anchors},
                "anchor": {
                    "lane": anchor.lane,
                    "child_id": str(anchor.child_id),
                    "span": [anchor.char_start, anchor.char_end],
                },
            }
        )
    return out


class RetrievalService:
    def __init__(
        self,
        config: RetrievalConfig,
        *,
        embedder: Callable[[], Embedder] | None,
        rerank_executor: RerankExecutor | None,
        df_cache: DocumentFrequencies | None = None,
        query_cache: QueryEmbeddingCache | None = None,
    ) -> None:
        self.config = config
        self._embedder = embedder
        self._rerank = rerank_executor
        self._df = df_cache or DocumentFrequencies()
        self._qcache = query_cache or QueryEmbeddingCache(512)
        self.config_hash = config_hash(config.as_dict())

    def with_config(self, config: RetrievalConfig) -> RetrievalService:
        """Same models and caches, different stages/parameters (evaluation arms)."""
        return RetrievalService(
            config,
            embedder=self._embedder,
            rerank_executor=self._rerank,
            df_cache=self._df,
            query_cache=self._qcache,
        )

    async def _query_vector(self, query: str) -> tuple[Vector, bool]:
        assert self._embedder is not None
        embedder = self._embedder()
        key = (embedder.model_id, self.config.query_instruction, query)
        cached = self._qcache.get(key)
        if cached is not None:
            return cached, True
        vector = await asyncio.to_thread(
            embedder.embed_query, f"{self.config.query_instruction}{query}"
        )
        self._qcache.put(key, vector)
        return vector, False

    def _class_partitions(self, filters: RetrievalFilters) -> list[tuple[str, ...] | None]:
        if len(filters.source_classes) >= 2:
            return [(c,) for c in filters.source_classes]
        return [None]

    async def _dense(
        self, session: AsyncSession, scope: LaneScope, query: str, trace: StageTrace
    ) -> list[ChildHit]:
        start = time.perf_counter()
        try:
            vector, hit = await self._query_vector(query)
        except EmbedderUnavailableError:
            trace.flags.append(LEXICAL_FALLBACK)
            trace.timings_ms["embed_ms"] = _ms(start)
            return []
        trace.timings_ms["embed_ms"] = _ms(start)
        trace.stages["query_embedding"] = {"cache_hit": hit}
        start = time.perf_counter()
        partitions = self._class_partitions(scope.filters)
        k = self.config.lane_k if partitions == [None] else self.config.class_lane_k
        hits: list[ChildHit] = []
        for classes in partitions:
            lane = await dense_lane(
                session,
                scope,
                vector,
                model_id=self.config.embed_model_id,
                dimensions=self.config.embed_dimensions,
                k=k,
                ef_search=self.config.ef_search,
                exact=self.config.dense_exact,
                classes=classes,
            )
            hits.extend(lane)
        hits = _merge_partitions(hits) if len(partitions) > 1 else hits
        trace.timings_ms["dense_ms"] = _ms(start)
        trace.stages[DENSE] = _lane_trace(hits)
        return hits

    async def _lexical(
        self, session: AsyncSession, scope: LaneScope, query: str, trace: StageTrace
    ) -> list[ChildHit]:
        start = time.perf_counter()
        stats = await self._df.get(session, scope)
        lq = await build_lexical_query(session, query, stats, df_prune=self.config.lexical_df_prune)
        trace.timings_ms["lexical_prep_ms"] = _ms(start)
        start = time.perf_counter()
        partitions = self._class_partitions(scope.filters)
        k = self.config.lane_k if partitions == [None] else self.config.class_lane_k
        hits: list[ChildHit] = []
        for classes in partitions:
            hits.extend(
                await lexical_lane(
                    session,
                    scope,
                    lq,
                    k=k,
                    phrase_bonus=self.config.lexical_phrase_bonus,
                    classes=classes,
                )
            )
        hits = _merge_partitions(hits) if len(partitions) > 1 else hits
        trace.timings_ms["lexical_ms"] = _ms(start)
        trace.stages["lexical_query"] = {
            "lexemes": list(lq.lexemes),
            "idf": [round(x, 4) for x in lq.idf],
            "phrases": list(lq.phrases),
            "pruned": list(lq.pruned),
        }
        trace.stages[LEXICAL] = _lane_trace(hits)
        return hits

    async def search(
        self,
        session: AsyncSession,
        scope: WorkspaceScope,
        query: str,
        filters: RetrievalFilters | None = None,
    ) -> RetrievalResult:
        cfg = self.config
        filters = filters or RetrievalFilters()
        trace = StageTrace(query=query, config_hash=self.config_hash)
        total = time.perf_counter()
        lanes_scope = await lane_scope(session, scope.workspace_id, filters)
        trace.stages["active_versions"] = len(lanes_scope.active_version_ids)

        lanes: dict[str, list[ChildHit]] = {}
        if cfg.use_dense and self._embedder is not None:
            lanes[DENSE] = await self._dense(session, lanes_scope, query, trace)
        if cfg.use_lexical:
            lanes[LEXICAL] = await self._lexical(session, lanes_scope, query, trace)

        start = time.perf_counter()
        weights = {DENSE: cfg.dense_weight, LEXICAL: cfg.lexical_weight}
        fused = rrf_fuse({k: v for k, v in lanes.items() if v}, weights, cfg.rrf_k)
        decisions = bal.BalanceDecisions()
        if cfg.balance:
            pool = bal.cap_pool(fused, cfg.pool_size, cfg.balance_pool_source_cap, decisions)
        else:
            pool = list(fused[: cfg.pool_size])
        pooled = {p.parent_id for p in pool}
        tail = [p for p in fused if p.parent_id not in pooled]
        trace.timings_ms["fusion_ms"] = _ms(start)
        trace.stages["fused"] = _parent_trace(fused[: max(cfg.pool_size * 2, cfg.top_k)])
        trace.stages["pool"] = [p.handle for p in pool]

        ranked = pool
        if cfg.rerank and self._rerank is not None and pool:
            start = time.perf_counter()
            hydrated = await hydrate(session, pool)
            trace.timings_ms["hydrate_ms"] = _ms(start)
            # A purge can commit between fusion and hydration (READ COMMITTED): drop vanished
            # parents - their handles now resolve to 410 - instead of failing the query.
            vanished = [p.handle for p in pool if p.parent_id not in hydrated.parents]
            if vanished:
                pool = [p for p in pool if p.parent_id in hydrated.parents]
                trace.stages["purged_mid_request"] = vanished
            start = time.perf_counter()
            outcome = await rerank_pool(self._rerank, query, pool, hydrated, cfg)
            trace.timings_ms["rerank_ms"] = _ms(start)
            ranked = outcome.ordered
            trace.stages["rerank"] = {
                "model": self._rerank.reranker.model_id,
                "pairs": [
                    {"handle_id": str(p.parent_id), "kind": p.kind, "score": round(s, 4)}
                    for p, s in zip(outcome.pairs, outcome.scores, strict=False)
                ],
                "pair_count": len(outcome.pairs),
                "reason": outcome.reason,
            }
            if outcome.flag:
                trace.flags.append(outcome.flag)

        ordered = list(ranked) + tail
        if cfg.balance:
            start = time.perf_counter()
            ordered = bal.cap_final(
                ordered,
                cfg.balance_per_source_max,
                decisions,
                single_source=len(filters.source_codes) == 1,
            )
            if filters.source_classes:
                ordered = bal.class_floor(ordered, filters.source_classes, cfg.top_k, decisions)
            trace.timings_ms["balance_ms"] = _ms(start)
            trace.stages["balance"] = {
                "pool_skipped": decisions.pool_skipped,
                "demoted": decisions.demoted,
                "class_promoted": decisions.class_promoted,
            }
        final = tuple(replace(p, rank=i) for i, p in enumerate(ordered, start=1))
        trace.stages["final"] = _parent_trace(final[: max(cfg.top_k, cfg.pool_size)])
        trace.timings_ms["total_ms"] = _ms(total)
        return RetrievalResult(parents=final, trace=trace)


def _merge_partitions(hits: list[ChildHit]) -> list[ChildHit]:
    """Per-class partitions concatenated: one lane order by score, then handle and span start
    (stable across re-ingestion); ranks renumbered.
    (A single partition keeps its SQL order, which includes the lexical tiebreak.)"""
    ordered = sorted(hits, key=lambda h: (-h.score, h.parent_handle, h.char_start))
    return [replace(h, rank=i) for i, h in enumerate(ordered, start=1)]
