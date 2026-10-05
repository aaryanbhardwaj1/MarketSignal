"""Retrieval data types shared by lanes, fusion, reranking, balancing and traces.

Children are retrieval units; parents are what is returned and cited (D1). Every parent result
carries its *anchor* child (the child responsible for its strongest match) and that child's
``char_start/char_end`` into the parent, so the exact supporting span can be highlighted.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from marketsignal.config import Settings
from marketsignal.domain.enums import Confidentiality, SourceClass

CONFIDENTIALITY_ORDER = (
    Confidentiality.PUBLIC,
    Confidentiality.INTERNAL,
    Confidentiality.CONFIDENTIAL,
    Confidentiality.RESTRICTED,
)


def allowed_confidentiality(maximum: Confidentiality) -> list[str]:
    return [c.value for c in CONFIDENTIALITY_ORDER[: CONFIDENTIALITY_ORDER.index(maximum) + 1]]


MAX_SOURCE_CODES = 20


class InvalidFiltersError(ValueError):
    """A request's filters are malformed (unknown class, too many sources)."""


@dataclass(frozen=True, slots=True)
class RetrievalFilters:
    source_classes: tuple[str, ...] = ()
    source_codes: tuple[str, ...] = ()
    max_confidentiality: Confidentiality = Confidentiality.RESTRICTED

    @classmethod
    def of(
        cls,
        source_classes: Iterable[str] = (),
        source_codes: Iterable[str] = (),
        max_confidentiality: Confidentiality = Confidentiality.RESTRICTED,
    ) -> RetrievalFilters:
        """De-duplicated (order kept) and bounded: each class is at most one lane partition, and
        the source list is capped, so one request cannot fan out into unbounded lane queries."""
        classes = tuple(dict.fromkeys(source_classes))
        known = {c.value for c in SourceClass}
        if any(c not in known for c in classes):
            raise InvalidFiltersError("unknown source class")
        codes = tuple(dict.fromkeys(source_codes))
        if len(codes) > MAX_SOURCE_CODES:
            raise InvalidFiltersError(f"at most {MAX_SOURCE_CODES} sources per request")
        return cls(classes, codes, max_confidentiality)


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    """One retrieval configuration. Eval arms are variants of this; its dict is hashed."""

    use_dense: bool = True
    use_lexical: bool = True
    lane_k: int = 100
    class_lane_k: int = 40
    rrf_k: int = 60
    dense_weight: float = 1.0
    lexical_weight: float = 1.0
    pool_size: int = 20
    top_k: int = 10
    dense_exact: bool = False
    ef_search: int = 100
    query_instruction: str = ""
    embed_timeout_s: float = 5.0
    lexical_df_prune: float = 0.9
    lexical_phrase_bonus: float = 1.0
    rerank: bool = True
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    rerank_max_pairs: int = 40
    rerank_parent_max_tokens: int = 350
    rerank_anchors_per_parent: int = 2
    rerank_max_chars: int = 2000
    rerank_timeout_s: float = 8.0
    balance: bool = False
    balance_per_source_max: int = 3
    balance_pool_source_cap: int = 7
    embed_model_id: str = "bge-small-en-v1.5"
    embed_dimensions: int = 384

    @classmethod
    def from_settings(cls, s: Settings) -> RetrievalConfig:
        return cls(
            lane_k=s.retrieval_lane_k,
            class_lane_k=s.retrieval_class_lane_k,
            rrf_k=s.retrieval_rrf_k,
            dense_weight=s.retrieval_dense_weight,
            lexical_weight=s.retrieval_lexical_weight,
            pool_size=s.retrieval_pool_size,
            top_k=s.retrieval_top_k,
            dense_exact=s.retrieval_dense_exact,
            ef_search=s.hnsw_ef_search,
            query_instruction=s.embed_query_instruction,
            embed_timeout_s=s.embed_query_timeout_s,
            lexical_df_prune=s.lexical_df_prune,
            lexical_phrase_bonus=s.lexical_phrase_bonus,
            rerank=s.rerank_enabled,
            rerank_model=s.rerank_model_name,
            rerank_max_pairs=s.rerank_max_pairs,
            rerank_parent_max_tokens=s.rerank_parent_max_tokens,
            rerank_anchors_per_parent=s.rerank_anchors_per_parent,
            rerank_max_chars=s.rerank_max_chars,
            rerank_timeout_s=s.rerank_timeout_s,
            balance=s.balance_enabled,
            balance_per_source_max=s.balance_per_source_max,
            balance_pool_source_cap=s.balance_pool_source_cap,
            embed_model_id=s.embed_model_id,
            embed_dimensions=s.embed_dimensions,
        )

    def with_(self, **changes: Any) -> RetrievalConfig:
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ChildHit:
    """One child from one lane, in that lane's rank order (1-based)."""

    lane: str
    rank: int
    score: float
    child_id: uuid.UUID
    parent_id: uuid.UUID
    parent_handle: str
    source_code: str
    source_class: str
    kind: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class LaneAnchor:
    lane: str
    rank: int  # the parent's rank in this lane (distinct-parent position)
    child_rank: int  # the anchor child's raw rank in the lane
    child_id: uuid.UUID
    char_start: int
    char_end: int
    score: float


@dataclass(frozen=True, slots=True)
class ParentCandidate:
    parent_id: uuid.UUID
    handle: str
    source_code: str
    source_class: str
    anchors: tuple[LaneAnchor, ...]  # one per lane that found the parent, best lane first
    rrf_score: float = 0.0
    fused_rank: int = 0
    rerank_score: float | None = None
    rank: int = 0  # final rank after rerank / balance

    def best_anchor(self) -> LaneAnchor:
        return self.anchors[0]

    def lane_rank(self, lane: str) -> int | None:
        return next((a.rank for a in self.anchors if a.lane == lane), None)


@dataclass
class StageTrace:
    """Explains one request: per-stage candidates, decisions, timings and degradation flags."""

    query: str
    config_hash: str
    corpus_version: int | None = None  # read in the retrieval transaction, stored with the trace
    stages: dict[str, Any] = field(default_factory=dict)
    timings_ms: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    parents: tuple[ParentCandidate, ...]  # final order; the pool head is reranked
    trace: StageTrace
    trace_id: uuid.UUID | None = None

    @property
    def flags(self) -> tuple[str, ...]:
        return tuple(self.trace.flags)
