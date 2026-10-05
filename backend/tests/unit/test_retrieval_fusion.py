"""Parent-level RRF, MaxP reranking and balancing: pure logic, no database."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from marketsignal.providers.rerankers import FailingReranker, KeywordReranker, SlowReranker
from marketsignal.retrieval import balance as bal
from marketsignal.retrieval.fusion import collapse_lane, rrf_fuse, single_lane
from marketsignal.retrieval.lanes import idf, quoted_phrases
from marketsignal.retrieval.rerank import (
    RERANKER_UNAVAILABLE,
    Hydrated,
    RerankExecutor,
    build_pairs,
    max_p,
    rerank_pool,
)
from marketsignal.retrieval.types import ChildHit, ParentCandidate, RetrievalConfig

PARENTS = {name: uuid.uuid5(uuid.NAMESPACE_URL, name) for name in "PQRSTUVWXYZ"}


def hit(lane: str, rank: int, parent: str, child: int, source: str = "SRC") -> ChildHit:
    return ChildHit(
        lane=lane,
        rank=rank,
        score=1.0 / rank,
        child_id=uuid.uuid5(PARENTS[parent], f"w{child}"),
        parent_id=PARENTS[parent],
        parent_handle=f"WS/{source}@v1:{parent}1",
        source_code=source,
        source_class="customer",
        kind="window",
        char_start=child * 10,
        char_end=child * 10 + 9,
    )


# --- fusion -----------------------------------------------------------------------------------


def test_dense_and_lexical_finding_different_children_of_one_parent_reinforce_it() -> None:
    """The core parent-level case: dense finds window 2 of P, lexical finds window 3 of P."""
    dense = [hit("dense", 1, "Q", 1), hit("dense", 2, "P", 2), hit("dense", 3, "R", 1)]
    lexical = [hit("lexical", 1, "S", 1), hit("lexical", 2, "P", 3), hit("lexical", 3, "Q", 4)]
    fused = rrf_fuse({"dense": dense, "lexical": lexical}, {"dense": 1.0, "lexical": 1.0}, k=60)
    by_parent = {p.parent_id: p for p in fused}
    p = by_parent[PARENTS["P"]]
    assert {a.lane for a in p.anchors} == {"dense", "lexical"}
    assert {a.child_id for a in p.anchors} == {dense[1].child_id, lexical[1].child_id}
    # Q (dense 1, lexical 3) and P (2, 2) both get support from both lanes; S and R from one.
    assert [c.parent_id for c in fused[:2]] == [PARENTS["Q"], PARENTS["P"]]
    assert fused[0].rrf_score == pytest.approx(1 / 61 + 1 / 63)
    assert p.rrf_score == pytest.approx(2 / 62)
    assert all(f.fused_rank == i for i, f in enumerate(fused, start=1))


def test_child_level_fusion_would_have_missed_the_agreement() -> None:
    dense = [hit("dense", 1, "Q", 1), hit("dense", 2, "P", 2)]
    lexical = [hit("lexical", 1, "S", 1), hit("lexical", 2, "P", 3)]
    child_level: dict[uuid.UUID, float] = {}
    for h in dense + lexical:
        child_level[h.child_id] = child_level.get(h.child_id, 0) + 1 / (60 + h.rank)
    assert max(child_level.values()) == pytest.approx(1 / 61)  # no child gets two votes
    fused = rrf_fuse({"dense": dense, "lexical": lexical}, {}, k=60)
    assert fused[0].parent_id == PARENTS["P"]  # parent-level: P is the only agreed parent


def test_lane_rank_is_the_distinct_parent_position_and_anchor_is_the_best_child() -> None:
    lane = collapse_lane(
        "dense", [hit("dense", 1, "P", 1), hit("dense", 2, "P", 2), hit("dense", 3, "Q", 1)]
    )
    assert lane.anchors[PARENTS["P"]].rank == 1
    assert lane.anchors[PARENTS["P"]].child_rank == 1
    assert lane.anchors[PARENTS["Q"]].rank == 2  # not 3: P's second window does not push Q down
    assert lane.anchors[PARENTS["Q"]].child_rank == 3


def test_fusion_is_deterministic_and_ties_break_on_best_rank_then_handle() -> None:
    dense = [hit("dense", 1, "Z", 1), hit("dense", 2, "Y", 1)]
    lexical = [hit("lexical", 1, "Y", 2), hit("lexical", 2, "Z", 2)]
    first = rrf_fuse({"dense": dense, "lexical": lexical}, {}, k=60)
    second = rrf_fuse({"lexical": lexical, "dense": dense}, {}, k=60)
    assert [p.handle for p in first] == [p.handle for p in second]
    assert first[0].rrf_score == first[1].rrf_score
    assert [p.handle for p in first] == ["WS/SRC@v1:Y1", "WS/SRC@v1:Z1"]  # tie -> handle order


def test_weights_and_single_lane_order() -> None:
    dense = [hit("dense", 1, "P", 1)]
    lexical = [hit("lexical", 1, "Q", 1)]
    fused = rrf_fuse({"dense": dense, "lexical": lexical}, {"dense": 2.0, "lexical": 1.0}, k=60)
    assert fused[0].parent_id == PARENTS["P"]
    lane = [hit("dense", i, name, 1) for i, name in enumerate("RPQ", start=1)]
    assert [p.parent_id for p in single_lane("dense", lane)] == [
        PARENTS["R"],
        PARENTS["P"],
        PARENTS["Q"],
    ]


def test_idf_and_phrases() -> None:
    assert idf(100, 1) > idf(100, 50) > 0
    assert quoted_phrases('fit "Fit Promise" and "x" "Fit Promise"') == ("Fit Promise",)


# --- rerank -----------------------------------------------------------------------------------


def _candidate(name: str, *hits: ChildHit, fused_rank: int = 1) -> ParentCandidate:
    fused = rrf_fuse({h.lane: [h] for h in hits}, {}, k=60)[0]
    return ParentCandidate(
        parent_id=fused.parent_id,
        handle=fused.handle,
        source_code=fused.source_code,
        source_class=fused.source_class,
        anchors=fused.anchors,
        fused_rank=fused_rank,
        rank=fused_rank,
    )


def _hydrated(*candidates: ParentCandidate, tokens: int) -> Hydrated:
    return Hydrated(
        parents={c.parent_id: (f"parent text of {c.handle}", tokens, ("H",)) for c in candidates},
        children={
            a.child_id: (f"anchor {a.lane} text of {c.handle}", "")
            for c in candidates
            for a in c.anchors
        },
    )


def test_small_parents_are_one_pair_large_parents_use_distinct_lane_anchors() -> None:
    small = _candidate("P", hit("dense", 1, "P", 1), hit("lexical", 1, "P", 1))
    large = _candidate("Q", hit("dense", 1, "Q", 1), hit("lexical", 1, "Q", 2))
    config = RetrievalConfig()
    pairs = build_pairs([small], _hydrated(small, tokens=100), config)
    assert [p.kind for p in pairs] == ["parent"]
    assert pairs[0].passage.startswith("H\n")
    pairs = build_pairs([large], _hydrated(large, tokens=900), config)
    assert sorted(p.kind for p in pairs) == ["anchor:dense", "anchor:lexical"]
    same_child = _candidate("R", hit("dense", 1, "R", 1), hit("lexical", 1, "R", 1))
    assert len(build_pairs([same_child], _hydrated(same_child, tokens=900), config)) == 1


def test_pair_budget_is_respected() -> None:
    pool = [_candidate(n, hit("dense", 1, n, 1), fused_rank=i) for i, n in enumerate("PQRS", 1)]
    pairs = build_pairs(pool, _hydrated(*pool, tokens=10), RetrievalConfig(rerank_max_pairs=3))
    assert len(pairs) == 3


def test_max_p_takes_the_best_pair_per_parent() -> None:
    large = _candidate("Q", hit("dense", 1, "Q", 1), hit("lexical", 1, "Q", 2))
    pairs = build_pairs([large], _hydrated(large, tokens=900), RetrievalConfig())
    assert max_p(pairs, [0.2, 3.5]) == {large.parent_id: 3.5}


def _pool() -> tuple[list[ParentCandidate], Hydrated]:
    pool = [
        _candidate("P", hit("dense", 1, "P", 1), fused_rank=1),
        _candidate("Q", hit("dense", 2, "Q", 1), fused_rank=2),
    ]
    hydrated = Hydrated(
        parents={
            pool[0].parent_id: ("nothing relevant here", 10, ()),
            pool[1].parent_id: ("knit upper fraying after six weeks", 10, ()),
        },
        children={},
    )
    return pool, hydrated


def test_rerank_reorders_the_pool() -> None:
    pool, hydrated = _pool()
    executor = RerankExecutor(KeywordReranker())
    outcome = asyncio.run(
        rerank_pool(executor, "knit upper fraying", pool, hydrated, RetrievalConfig())
    )
    assert outcome.flag is None
    assert [p.parent_id for p in outcome.ordered] == [pool[1].parent_id, pool[0].parent_id]
    assert outcome.ordered[0].rerank_score == 3.0


@pytest.mark.parametrize(
    ("reranker", "reason"),
    [(FailingReranker(), "simulated outage"), (SlowReranker(0.6), "timeout")],
)
def test_reranker_failure_or_timeout_keeps_fused_order_and_flags(
    reranker: object, reason: str
) -> None:
    pool, hydrated = _pool()
    executor = RerankExecutor(reranker)  # type: ignore[arg-type]
    outcome = asyncio.run(
        rerank_pool(executor, "q", pool, hydrated, RetrievalConfig(rerank_timeout_s=0.2))
    )
    executor.shutdown()
    assert outcome.flag == RERANKER_UNAVAILABLE
    assert outcome.reason == reason
    assert [p.parent_id for p in outcome.ordered] == [p.parent_id for p in pool]


# --- balancing --------------------------------------------------------------------------------


def _ranked(*sources: str) -> list[ParentCandidate]:
    names = "PQRSTUVWXYZ"
    out = []
    for i, source in enumerate(sources):
        c = _candidate(names[i], hit("dense", i + 1, names[i], 1, source=source), fused_rank=i + 1)
        out.append(c)
    return out


def test_pool_cap_lets_other_sources_in_and_fills_when_needed() -> None:
    fused = _ranked("BIG", "BIG", "BIG", "BIG", "OTHER", "BIG")
    decisions = bal.BalanceDecisions()
    pool = bal.cap_pool(fused, pool_size=4, per_source=2, decisions=decisions)
    assert [p.source_code for p in pool] == ["BIG", "BIG", "OTHER", "BIG"]
    assert pool[3] is fused[2]  # the capped third BIG fills the last slot
    assert decisions.pool_skipped == [fused[3].handle, fused[5].handle]


def test_final_cap_demotes_overflow_in_order_without_dropping() -> None:
    ranked = _ranked("A", "A", "A", "A", "B", "A")
    decisions = bal.BalanceDecisions()
    out = bal.cap_final(ranked, per_source_max=3, decisions=decisions)
    assert [p.source_code for p in out] == ["A", "A", "A", "B", "A", "A"]
    assert len(out) == len(ranked)
    assert decisions.demoted == [ranked[3].handle, ranked[5].handle]
    assert bal.cap_final(ranked, 3, bal.BalanceDecisions(), single_source=True) == ranked


def test_class_floor_promotes_a_missing_requested_class() -> None:
    ranked = _ranked("A", "B", "C", "D")
    ranked[3] = ParentCandidate(**{**_fields(ranked[3]), "source_class": "competitor"})
    decisions = bal.BalanceDecisions()
    out = bal.class_floor(ranked, ["competitor"], top_k=2, decisions=decisions)
    assert out[1].source_class == "competitor"
    assert decisions.class_promoted == [ranked[3].handle]


def _fields(c: ParentCandidate) -> dict[str, object]:
    return {f: getattr(c, f) for f in c.__dataclass_fields__}


def test_parents_purged_before_hydration_are_skipped_not_fatal() -> None:
    present = _candidate("P", hit("dense", 1, "P", 1))
    vanished = _candidate("Q", hit("dense", 2, "Q", 1), fused_rank=2)
    pairs = build_pairs([vanished, present], _hydrated(present, tokens=10), RetrievalConfig())
    assert [p.parent_id for p in pairs] == [present.parent_id]
