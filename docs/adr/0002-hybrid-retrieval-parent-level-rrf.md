# ADR-0002: Hybrid retrieval (dense + IDF-weighted Postgres FTS) with parent-level RRF

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** **Phase 2 implemented and measured** (dense + IDF lexical lanes, parent-level RRF, rerank pool; balancing built but off); neighbor expansion and structural enumeration remain Phase 7 iterations
- **Related:** plan §11, §12, §13, §14, §15, §26; ADR-0001, ADR-0003, ADR-0005; approved deviation D5 (also D3 for the tool surface)

## Context

Research questions over a consulting corpus mix two kinds of signal:

- **Exact tokens:** prices (`$129`), segment names (`Gen Z`), competitor and product names, quoted phrases. Dense embeddings blur these.
- **Paraphrase:** "customers find it too expensive" vs. "price sensitivity". Lexical matching misses these.

Retrieval units are child windows inside parent units (ADR-0003). A long parent can be found by dense search through one window and by lexical search through another; that agreement is the strongest relevance signal hybrid retrieval offers, and child-level fusion discards it.

The spec requires a scored Phase 2 comparison against a dense-only baseline. Retrieval must be deterministic and traced, because evaluation scores the production code path and the CI gate must not flake. The lexical layer must run on any managed Postgres (ADR-0001).

## Decision

One deterministic pipeline, exposed to the agent as `search_evidence`; exact matching is a separate `search_evidence_keyword` tool (D3).

1. **Dense lane:** top 100 children by cosine distance (canonical SQL, ADR-0001), query embedded with the bge query instruction.
2. **Lexical lane:** top 100 children, Postgres FTS with **IDF-weighted coverage scoring** ("BM25-lite"):
   - query lexemes come from `to_tsvector('english', :q)` in Postgres, so stemming and stopwords match the index; user text never reaches `to_tsquery`; quoted phrases use `phraseto_tsquery`;
   - `idf(t) = ln(1 + (N − df + 0.5)/(df + 0.5))`, df/N from `ts_stat` over body-only `tsv_body` (copied headings do not inflate DF), cached per (workspace, corpus_version);
   - `score = Σ idf(t)·[tsv @@ t]` + phrase bonus; ties by damped `ts_rank_cd`, then `child_id`; only terms with DF > 90% are pruned, never to an empty query.
3. **Per-class lanes:** with two or more `source_classes`, each lane runs once per class (`LIMIT 40`) and the union is fused, so class coverage is guaranteed at candidate generation.
4. **Parent-level RRF:** within each lane, dedupe to `parent_id`, keeping the best-ranked child as the lane's **anchor**; `score(p) = Σ w_lane/(k + rank_lane(p))`, `k = 60`, `w = 1.0` (configurable, ablated); ties by best single-lane rank then parent handle; per-source cap ≈ 1/3 of the pool; cut to the top **20 parents**.
5. Cross-encoder rerank (ADR-0005), collapse (keeps the best anchor child and `hit_count`), then greedy source/class balancing (≤ 3 parents per source; requested classes keep their best item within a relative floor).
6. **Phase 7, only if measured to help:** neighbor expansion (top-2 narrative anchors touching a parent edge, ≤ 4 additions, `expansion_kind=adjacent`) and structural enumeration (list intent or `intent="enumeration"`, siblings by `list_group_id`/heading group, budget-capped, `expansion_kind=sibling_list`).

Every ranked SQL with a LIMIT ends in `ORDER BY score DESC, child_id`. Traces record each child's dense rank, lexical rank and anchor flags. If the embedder fails, the dense lane is skipped and the call returns `RETRIEVAL_LEXICAL_FALLBACK`.

Sizes above are initial values (§13), tuned in Phase 7 on Recall@pool and latency.

## Approved spec deviation

- **Spec position (D5):** all retrieval augmentations are built in Phase 2.
- **Approved change:** build the core pipeline first (dense + lexical, parent-level RRF, rerank, collapse, balancing). Add neighbor expansion and structural enumeration as **measured tuning iterations**.
- **Rationale:** this produces the required before/after iterations from observed failures rather than from speculation, and keeps each augmentation removable if it does not help.
- **Conditions:** each iteration follows the §26 protocol: hypothesis written beforehand from a dev-split failure analysis; one change per iteration; paired comparison on dev; frozen config evaluated once on test at milestones; per-iteration report.
- Approved 2026-10-05.

## Alternatives considered

- **Dense-only.** Weak on exact numbers, names and quoted terms; it is the required baseline, not the design.
- **Lexical-only.** Misses paraphrase and customer-voice wording.
- **Weighted score fusion.** Needs cosine distances and lexical scores normalized onto one scale; brittle as the corpus changes. RRF is rank-based and needs no calibration.
- **Learned fusion.** No training data.
- **Child-level RRF.** Loses the agreement signal when lanes hit different windows of the same parent.
- **Reranker-only over the lane union.** Leaves no fused order to fall back on when the reranker is down.
- **BM25 extensions.** pg_textsearch is not available on managed providers (Phase 7 local experiment behind `LexicalRetriever`); ParadeDB is AGPL; OpenSearch is a separate cluster (ADR-0001).
- **All augmentations in Phase 2 (spec).** Rejected per D5: unmeasured complexity and no before/after evidence.

## Tradeoffs accepted

- IDF-weighted coverage has **no TF saturation or length normalization**; it is not true BM25.
- RRF ignores score magnitude; acceptable because the cross-encoder re-scores the fused pool.
- A 20-parent pool caps achievable recall; Recall@pool is the reranker's ceiling.
- Lexical search is a sequential filter under FORCE RLS at demo scale (ADR-0001).
- Neighbor and structural expansion may never ship if they do not measurably help; enumeration questions may be weaker until then.

## Consequences

**Positive:** exact-token and paraphrase queries are both served; fusion is deterministic and explainable; the ablation story (dense-only → hybrid → +rerank) is built into the design.

**Negative:** two lanes (and per-class lanes) multiply SQL round trips; the IDF table must be recomputed on every corpus-version change.

**Follow-ups:** Phase 7 tuning iterations (neighbor, structural, lane weights, candidate sizes, pg_textsearch BM25 experiment), each with a written hypothesis.

**Verification**
- Unit: parent-level RRF agreement test (dense finds window 2, lexical window 3 of the same parent); lexical builder adversarial inputs (`gen z`, `$129`, `ratio:3`, `(x`, `& |`, `O'Brien`, stopwords only); Hypothesis property (arbitrary text never raises, same ordered IDs); heading-flood and keyword-stuffing ranking tests.
- Phase 2 exit report: dense-only vs lexical-only vs hybrid vs +rerank, with Wilson/bootstrap CIs and lexical-overlap hardness bins; every arm maps children to parents and dedupes before scoring.
- Metrics: Recall@k, hit@k, MRR, nDCG@10, Recall@pool, Recall@pack, source-class coverage; paired McNemar / paired bootstrap between configs.
- CI retrieval eval smoke on the dev split with **exact search** and floors = baseline − max(run-to-run noise, paired MDD).
- Target (spec gate, not yet measured): Recall@10 ≥ 0.85 on the curated test split after tuning, reported with a CI.

## Implementation notes (Phase 2, 2026-10-05)

Code: `retrieval/{lanes,fusion,rerank,balance,pipeline,traces}.py`; API `GET /api/workspaces/{ws}/search`. All numbers are from `eval/baselines/phase2/` (v0: 44 dev and 21 test items). See `docs/RETRIEVAL_DEEP_DIVE.md`.

- **Built as decided.**
  - Both lanes return 100 children, filtered to active versions, with an explicit workspace predicate on top of RLS, class/source/confidentiality filters, and anchor spans.
  - Per-class lanes (40 each) are used when two or more classes are requested.
  - Parent-level RRF uses k = 60 and w = 1 (both configurable). The rerank pool is 20 parents.
- **Deviation: tiebreak.** Ties break on **(parent handle, child ordinal)**, not `child_id`. Child ids are random per ingestion, so two identically seeded databases ranked lexical ties differently (12/44 dev items had a different top-20; metrics were unchanged). A regression test requires identical rankings across re-ingestion.
- **Clarification: lane rank.** A parent's rank in a lane is its position among the lane's *distinct* parents. The anchor is the lane's best child; the raw child rank is kept in the trace.
- **Deviation: query instruction.** It is **not** used. The A/B is recorded in ADR-0012.
- **Measured: lexical lane.** IDF-weighted OR scoring replaced the Phase 1 `websearch_to_tsquery` (AND) smoke lane. Dev hit@10 went from 4.5% to 77.3% (`01-lanes-dev`).
- **Measured: hybrid RRF vs dense.**
  - Dev: not distinguishable (hit@10 +2 / −1 items, ΔMRR +0.029 [−0.073, +0.130]). Recall@pool 87.9 vs 83.3.
  - **Test: hit@10 76.2 vs 47.6 (+6 / −0 items, exact McNemar p = 0.031), Δrecall@10 +0.26 [+0.10, +0.45]** (`07-test-milestone-c3`).
  - The lexical lane is the only path for exact identifiers (RV-00655: dense never; hybrid + rerank rank 5).
- **Measured: balancing (built, off by default).**
  - Per-source cap 3 plus a pool cap of 7: net negative on dev (hit@10 −1 item, hit@20 −2). The pool cap alone causes the loss, because the reranker often lifts a parent from deep within one source's list.
  - It fixes a real crowding case (R0-049: Kinetic Lab evidence from rank 12 to 7), but hurts single-source enumeration questions. Revisit with agent-supplied source and class requests (Phase 4).
- **Collapse.** Explicit collapse is implicit in parent-level fusion; `hit_count` is not computed. The anchor is the best lane's child.
- **Measured: cost.** The lexical lane is p50 about 15 ms (IDF scoring dominates), dense SQL about 4 ms, fusion under 1 ms.
- **Frozen Phase 2 configuration:** hybrid + rerank, child policy c3, balancing off, no instruction.
