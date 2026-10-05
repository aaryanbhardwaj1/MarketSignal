"""Cross-encoder reranking of the fused pool (plan §15, ADR-0005).

Pairs per pool parent:
* parent ≤ ``rerank_parent_max_tokens`` (rows, slides, Q&A, short sections): one pair,
  (query, heading + parent text);
* larger parent: (query, heading + anchor child text) for each distinct lane anchor, up to
  ``rerank_anchors_per_parent`` - the cross-encoder never sees an oversized parent.
Parent score = max of its pair scores (MaxP, Dai & Callan 2019). At most ``rerank_max_pairs``
pairs are scored, in fused order.

Execution: a dedicated bounded thread pool (``rerank_concurrency`` workers) and a timeout. On
timeout or failure the fused order is kept and the request is flagged ``RERANKER_UNAVAILABLE``;
reranking never fails a query. A timed-out call finishes in its worker and is discarded.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.providers.rerankers import Reranker, RerankerUnavailableError
from marketsignal.retrieval.types import ParentCandidate, RetrievalConfig

RERANKER_UNAVAILABLE = "RERANKER_UNAVAILABLE"
HEADING_SEPARATOR = " > "


@dataclass(frozen=True, slots=True)
class Hydrated:
    parents: dict[uuid.UUID, tuple[str, int, tuple[str, ...]]]  # id -> (text, tokens, headings)
    children: dict[uuid.UUID, tuple[str, str]]  # id -> (text, heading_text)


async def hydrate(session: AsyncSession, pool: Sequence[ParentCandidate]) -> Hydrated:
    parent_ids = [p.parent_id for p in pool]
    child_ids = sorted({a.child_id for p in pool for a in p.anchors}, key=str)
    prows = await session.execute(
        text(
            "SELECT id, text, token_count, heading_path FROM parent_chunks "
            "WHERE id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": parent_ids},
    )
    crows = await session.execute(
        text(
            "SELECT id, text, heading_text FROM child_chunks WHERE id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": child_ids},
    )
    return Hydrated(
        parents={r[0]: (r[1], int(r[2]), tuple(r[3] or ())) for r in prows.all()},
        children={r[0]: (r[1], r[2] or "") for r in crows.all()},
    )


@dataclass(frozen=True, slots=True)
class Pair:
    parent_id: uuid.UUID
    kind: str  # "parent" or "anchor:<lane>"
    child_id: uuid.UUID | None
    passage: str


def build_pairs(
    pool: Sequence[ParentCandidate], hydrated: Hydrated, config: RetrievalConfig
) -> list[Pair]:
    pairs: list[Pair] = []
    for parent in pool:
        if len(pairs) >= config.rerank_max_pairs:
            break
        if parent.parent_id not in hydrated.parents:
            continue  # purged after fusion (pipeline drops it); never fail the query
        ptext, tokens, headings = hydrated.parents[parent.parent_id]
        heading = HEADING_SEPARATOR.join(headings)
        if tokens <= config.rerank_parent_max_tokens:
            passage = f"{heading}\n{ptext}" if heading else ptext
            pairs.append(Pair(parent.parent_id, "parent", None, passage[: config.rerank_max_chars]))
            continue
        seen: set[uuid.UUID] = set()
        for anchor in parent.anchors:
            if anchor.child_id in seen or len(seen) >= config.rerank_anchors_per_parent:
                continue
            if len(pairs) >= config.rerank_max_pairs:
                break
            seen.add(anchor.child_id)
            if anchor.child_id not in hydrated.children:
                continue
            ctext, cheading = hydrated.children[anchor.child_id]
            head = cheading or heading
            passage = f"{head}\n{ctext}" if head else ctext
            pairs.append(
                Pair(
                    parent.parent_id,
                    f"anchor:{anchor.lane}",
                    anchor.child_id,
                    passage[: config.rerank_max_chars],
                )
            )
    return pairs


def max_p(pairs: Sequence[Pair], scores: Sequence[float]) -> dict[uuid.UUID, float]:
    best: dict[uuid.UUID, float] = {}
    for pair, score in zip(pairs, scores, strict=True):
        best[pair.parent_id] = max(score, best.get(pair.parent_id, float("-inf")))
    return best


class RerankExecutor:
    """Bounded, timed execution of a (synchronous, CPU-bound) reranker."""

    def __init__(self, reranker: Reranker, concurrency: int = 1) -> None:
        self.reranker = reranker
        self._pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="rerank")

    async def score(self, query: str, passages: Sequence[str], timeout_s: float) -> list[float]:
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self._pool, self.reranker.score, query, list(passages))
        return await asyncio.wait_for(future, timeout=timeout_s)

    def shutdown(self, *, wait: bool = True) -> None:
        """Join the worker (default) so no thread outlives its owner into interpreter exit."""
        self._pool.shutdown(wait=wait, cancel_futures=True)


@dataclass(frozen=True, slots=True)
class RerankOutcome:
    ordered: list[ParentCandidate]
    pairs: list[Pair]
    scores: list[float]
    flag: str | None
    reason: str | None


async def rerank_pool(
    executor: RerankExecutor,
    query: str,
    pool: Sequence[ParentCandidate],
    hydrated: Hydrated,
    config: RetrievalConfig,
) -> RerankOutcome:
    pairs = build_pairs(pool, hydrated, config)
    try:
        scores = await executor.score(query, [p.passage for p in pairs], config.rerank_timeout_s)
    except TimeoutError:
        return RerankOutcome(list(pool), pairs, [], RERANKER_UNAVAILABLE, "timeout")
    except RerankerUnavailableError as exc:
        return RerankOutcome(list(pool), pairs, [], RERANKER_UNAVAILABLE, str(exc))
    except Exception as exc:  # any reranker bug degrades, never fails the query
        return RerankOutcome(list(pool), pairs, [], RERANKER_UNAVAILABLE, type(exc).__name__)
    best = max_p(pairs, scores)
    rescored = [_with_score(p, best.get(p.parent_id)) for p in pool]
    # Unscored parents (beyond the pair budget) keep fused order after the scored ones.
    ordered = sorted(
        rescored,
        key=lambda p: (p.rerank_score is None, -(p.rerank_score or 0.0), p.fused_rank),
    )
    return RerankOutcome(ordered, pairs, list(scores), None, None)


def _with_score(parent: ParentCandidate, score: float | None) -> ParentCandidate:
    from dataclasses import replace

    return replace(parent, rerank_score=score)
