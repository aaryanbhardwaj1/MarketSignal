# Retrieval deep dive

How MarketSignal turns a question into ranked, citable evidence, and the measurements behind each design choice. Every number here comes from a recorded run under [`eval/baselines/phase2/`](../eval/baselines/phase2/), listed in [`SUMMARY.md`](../eval/baselines/phase2/SUMMARY.md). The methodology is in [`eval/README.md`](../eval/README.md). Decisions are in ADR-0002 (hybrid + RRF), ADR-0003 (parents and children), ADR-0005 (reranker), ADR-0012 (embeddings) and ADR-0013 (evaluation).

## The question this document answers

> *Why is this retrieval system better than vector search alone, and what measurements prove it?*

The short answer, with the caveats the data imposes:

1. **The lexical lane is necessary.** It is the only path for exact tokens:
   - **Respondent and review ids:** with policy `c3`, RV-00655 moves from lexical rank 26 to 2. Dense+rerank never finds it.
   - **Rows whose wording repeats across hundreds of near-duplicates.**
2. **Parent-level hybrid fusion (RRF) beats vector-only on the held-out test split:** hit@10 76.2% vs 47.6%, 6 items gained and 0 lost, exact McNemar p = 0.031; Δrecall@10 +0.26, 95% CI [+0.10, +0.45]. On dev the same comparison is *not distinguishable* (+2 / −1 items).
3. **The cross-encoder reranker improves the top of the list on dev:** ΔMRR +0.110, CI [+0.021, +0.207] vs dense. On test, it raised hit@1 (38.1 → 42.9) but **lowered hit@10** (76.2 → 57.1), because it demotes ID lookups and near-duplicate customer verbatims. The frozen Phase 2 configuration includes it, as decided on dev. The test result is reported, not tuned away; see *Open problem*.
4. **Source balancing and the BGE query instruction were measured and not adopted.** Both were neutral or negative on dev.

The v0 set is small: 44 dev and 21 test items. Every difference below is shown with its interval. Differences whose interval includes zero are reported as *not distinguishable*.

## Pipeline

```
query
 ├─ dense lane    bge-small-en-v1.5 (ONNX, 384-d) → canonical pgvector SQL → top 100 children
 └─ lexical lane  to_tsvector lexemes → OR tsquery → IDF-weighted coverage → top 100 children
        │  (both: active versions only, workspace predicate + RLS, class/source/confidentiality
        │   filters, deterministic order: score, parent handle, child ordinal)
        ▼
 parent-level RRF   children → parents per lane (best child = lane anchor), Σ w / (60 + rank)
        ▼
 rerank pool        top 20 parents (Recall@pool = recall@20)
        ▼
 cross-encoder      ms-marco-MiniLM-L-6-v2; parent ≤ 350 tokens → 1 pair, else ≤ 2 anchor pairs;
                    MaxP; ≤ 40 pairs; bounded thread pool; timeout → fused order + flag
        ▼
 (balancing)        implemented, measured, off
        ▼
 ranked parents     handle · locator · anchor child span (highlight) · stage scores · flags
                    + one row in retrieval_traces per request
```

Code is under `backend/src/marketsignal/retrieval/`: `lanes.py`, `fusion.py`, `rerank.py`, `balance.py`, `pipeline.py` and `traces.py`. The API is `GET /api/workspaces/{ws}/search`. Every parameter is a `MS_*` setting (see `config.py`).

## The evaluation set (v0)

- **Size:** 65 curated questions in 10 categories.
- **Authoring:** written by independent agents that saw only an anchor-free fact digest, never the documents or the retrieval code. Each was critic-vetted.
- **Labels:** every expected parent was located by `freeze-gold` in exactly one active parent. Ten alternate parents that state the same fact were accepted by two independent judges.
- **Split:** grouped 70/30 by shared and related facts and parents (union-find), stratified by category, giving 44 dev and 21 test.
- **Pinning:** the dataset is pinned to `corpus_sha256`, `ledger_sha256` and `items_sha256`. CI checks integrity against a freshly seeded corpus.
- **Reachability:** 4 dev and 4 test items need facts that exist only in **purely numeric rows**. These are child-less parents by design (ADR-0003), so no lane can retrieve them; they belong to the Phase 5 analytics tool. That caps hit@k at 90.9% on dev and 81.0% on test. Results are reported on all items and on the reachable subset (`reachability.json`).
- **Provenance:** questions are `llm_draft_agent_reviewed`; human review by the project owner is pending.

## Baselines (untouched Phase 1 lanes, recorded before any change)

`00-baseline-dev` (dev, n = 44):

| Arm | hit@1 | hit@10 | recall@10 | Recall@pool | MRR | p50 / p95 ms |
|---|---|---|---|---|---|---|
| Dense (bge-small, no instruction) | 56.8 [42.2–70.3] | 81.8 [68.0–90.5] | 78.0 | 83.3 | 0.662 | 10.8 / 13.9 |
| Lexical (`websearch_to_tsquery`) | 4.5 | 4.5 | 4.5 | 4.5 | 0.045 | 2.2 / 2.7 |

The Phase 1 lexical lane requires **every** term, so a full natural-language question almost never matches. That is a genuine baseline of the shipped system, not a strawman. The production lexical lane fixes it by design (below), not by tuning.

## Candidate generation

**Dense.** The canonical query (plan §7):

- runs inside one transaction with transaction-local `hnsw.ef_search` and `iterative_scan`;
- puts every filter inside a `MATERIALIZED` CTE;
- orders outside with `ORDER BY distance + 0, …`.

The production dense lane reproduces the baseline's top-20 **exactly on all 44 dev items**, a correctness check on the rewrite. At this scale (about 2,200 children per corpus), **the planner never chooses the HNSW index**, with or without RLS. It scans the `(workspace_id, source_version_id)` index and computes exact distances in about 1.6 ms. HNSW is usable: the planner chooses it when sequential scans are discouraged. It exists for scale. The CI gate forces exact search (`MS_RETRIEVAL_DENSE_EXACT`), so ANN behaviour cannot make it flaky.

**Lexical** (plan §11):

- **Lexemes** come from `to_tsvector('english', query)`, so stemming and stopwords match the index, and user text never reaches `to_tsquery`.
- **Matching** uses an OR tsquery.
- **Score** = Σ IDF of matched lexemes, with document frequency taken from `tsv_body` (headings excluded) and cached per (workspace, corpus version).
- **Bonus:** quoted phrases add one.
- **Ties** break on heading-damped `ts_rank_cd`, then a stable identity.

Result (`01-lanes-dev`): hit@10 rises **from 4.5% to 77.3%**.

| Dev, n = 44 (`06-final-dev`, policy c3) | hit@1 | hit@10 | Recall@pool | MRR | p50 ms |
|---|---|---|---|---|---|
| Dense | 56.8 | 84.1 | 83.3 | 0.664 | 13 |
| Lexical | 45.5 | 81.8 | 82.2 | 0.579 | 16 |
| Hybrid RRF | 59.1 | 86.4 | **87.9** | 0.693 | 28 |
| Dense + rerank | **70.5** | 86.4 | 83.3 | 0.769 | 598 |
| **Hybrid + rerank (final)** | **70.5** | **88.6** | **87.9** | **0.774** | 669 |

## Where each lane wins (interview material)

Examples come from the recorded runs (dev unless marked test).

- **Dense finds, lexical misses: paraphrase.** *"What portion of young shoppers put more faith in fellow buyers' opinions and influencer demos than in what companies say in their ads?"* (NS-040, low overlap). No distinctive term matches, but the meaning does.
- **Lexical finds, dense misses: identifiers.**
  - *"Pull up review RV-00655"*: dense+rerank never finds it; hybrid+rerank (c3) ranks it 5.
  - *"What does survey respondent R0062 want shown on product pages?"*: lexical rank 21 → 1 after c3.
  - In general, dense embeddings don't represent `RV-00655` as an identity.
- **Both fail: numeric rows.** *"NS-KR2 return rate"*, *"Gen Z conversion rate on the Social Shop channel, September 2026"*. The answer is a child-less numeric row, so no lane can return it by design (analytics tool, Phase 5).
- **Both fail: abstract paraphrase.** *"Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?"* (NS-102). Dense rank 24, lexical rank 28, hybrid+rerank 15: "bespoke" and "small trial" share nothing with "personalization" and "limited test".
- **Near-duplicates.** The survey has about 600 respondents with similar sizing complaints. The right verbatim is found lexically by its identifier and words, but is easily out-scored by its neighbours in both dense and reranked order.
- **Distractors.** Ledger distractor parents (the same metric for another SKU, segment or age band) **never outrank the true parent in any arm** (0/6 dev, 0/1 test).
- **Exact numbers and names.** These are mostly easy for every arm when the number sits in narrative text (single-source fact: 6/6 hit@10 dense). They fail when it sits in a numeric row.

## Parent-level RRF

- **Explicit and pure:** `fusion.py`, about 90 lines, unit-tested.
- **Lane rank** is the parent's position among the lane's distinct parents. The lane anchor is the best child.
- **Score:** `score = Σ w / (k + rank)` with k = 60 and w = 1. Ties break on the best single-lane rank, then the handle.
- **Key test:** dense finds window 2 of P and lexical finds window 3 of P. Parent-level fusion sees one parent supported by both lanes; child-level fusion would see two weak candidates (`test_dense_and_lexical_finding_different_children_of_one_parent_reinforce_it`).

**Measured:**

| | Comparison | Result |
|---|---|---|
| Dev | hybrid vs dense | hit@1 6 / 7, hit@10 1 / 2, ΔMRR +0.029 [−0.073, +0.130]: **not distinguishable** |
| Dev | Recall@pool | 87.9 vs 83.3 (the reranker's ceiling is higher with both lanes) |
| Test | hybrid vs dense | hit@10 **0 / 6, p = 0.031**; Δrecall@10 **+0.262 [+0.095, +0.452]** |

## Cross-encoder reranking

- **Model:** `Xenova/ms-marco-MiniLM-L-6-v2` (ONNX, local).
- **Pairs:** a parent of 350 tokens or less is one pair (rows, slides, short sections). A larger parent gets up to two pairs, one per distinct lane anchor, so the encoder never sees an oversized passage.
- **Scoring:** MaxP over pairs; at most 40 pairs.
- **Failure handling:** a bounded thread pool and timeout. On failure or timeout the fused order is kept and the response carries `RERANKER_UNAVAILABLE`. It never fails a query (tests for outage, timeout, and parents purged mid-request).

| Measured (rerank stage) | Value |
|---|---|
| Rerank latency, dev | p50 597 ms, p95 855 ms (M2 laptop CPU, 20 parents, ≤ 40 pairs) |
| Dev | ΔMRR vs hybrid **+0.123 [+0.038, +0.215]**; hit@1 2 / 9 (p = 0.065) |
| Test | hit@1 38.1 → 42.9; hit@10 76.2 → 57.1; MRR 0.490 → 0.488 |

**What happens on test.** The reranker lifts narrative facts to rank 1:

- R0-003: 4 → 1 (the pilot's dates and stores);
- R0-022: 2 → 1 (the largest Gen Z segment).

It demotes:

- an ID lookup (respondent R0147: 1 → 12);
- near-duplicate customer verbatims (SP-C05 3 → 19, NS-145 4 → 14).

MS MARCO was trained on web passages. It does not treat an exact identifier as decisive, and it cannot separate hundreds of near-identical complaints. ADR-0005 named this domain risk; the test split confirms it.

## Balancing (measured, not adopted)

| Dev | Result |
|---|---|
| Per-source cap 3 + pool cap 7 | hit@10 −1 item, hit@20 −2, ΔMRR −0.008 [−0.023, 0.0] |
| Pool cap only (final cap disabled) | Same loss, so the pool cap causes it |

**Crowding case (it does happen).** *"Compare the average wait for personalized pairs in Northstar's spring pilot with the delivery window Kinetic Lab quotes"* (R0-049): the pilot report fills 7 of the top 10, and the Kinetic Lab evidence sits at 12. Balancing lifts it to 7.

**Why it is net negative.** Many v0 questions need several parents from **one** source ("the memo's recommendations", "in the category-sizing workbook"). The cap pushes those below rank 20:

- NS-100: 7 → 54;
- NS-129: 3 → 36.

Balancing belongs with explicit source and class requests from the agent (Phase 4), where §15's single-source exemption applies. It stays implemented and off.

## BGE query instruction (measured, not adopted)

A/B on dev with everything else held constant:

| Arm | Result with the instruction |
|---|---|
| Dense | hit@10 81.8 → 75.0 (3 items lost, 0 gained, p = 0.25); ΔMRR +0.006 [−0.028, +0.041] |
| Hybrid + rerank | No change on any metric |

There is no evidence of benefit, so `embed_query_instruction` stays empty. It is a query-side setting, so no re-embedding was needed.

## Child policy c3: row identifiers (measured, then approved)

Row children used to carry `{table} | {context} | {free-text}` without the row's identifier columns, so lookups by respondent or review id could not match lexically.

**Experiment** (separate database, dev): prefixing identifiers changed child text only. Parents, handles and spans are unchanged, so the gold set still applies.

- **Lexical:** RV-00655 26 → 2, R0062 21 → 1. ΔMRR +0.045 [+0.001, +0.100].
- **Hybrid:** ΔMRR +0.046 [+0.007, +0.095].
- **Reranked arms:** no regression.

Adopted as policy `c3` after review. **Side effect on test:** dense-only hit@10 fell 57.1 → 47.6 under c3. Identifiers in row embedding text change the row vectors, and the effect cuts both ways (R0147: 60 → 15; SP-C02: 3 → 16).

## Workspace isolation and RLS cost

These are measured with `EXPLAIN (ANALYZE, BUFFERS)` on the exact lane SQL the service sends, for the 44 dev queries (`rls-profile/`).

| Lane | Under forced RLS (ms_app) | Without RLS (superuser control) |
|---|---|---|
| Lexical | p50 11.6 / p95 20.8 ms; **GIN never used (0/44)**; scans the workspace's ~2,330 active children through the btree | p50 11.2 / p95 19.6 ms; GIN used 44/44; ~1,300 rows |
| Dense | p50 1.6 / p95 2.3 ms; exact scan | p50 1.4 / p95 1.7 ms; exact scan |

**Why GIN goes unused.** Under RLS, Postgres will not use a non-leakproof operator (`@@`) as an index condition ahead of the security qual. The lexical lane therefore filters the workspace's rows by the leakproof btree predicate first, then evaluates `@@`.

**Does it matter?** At this scale it costs nothing measurable, because execution time is dominated by IDF scoring, not row access. The RLS model is unchanged.

**When to revisit.** If a workspace grows to the point where scanning its active children costs more than the GIN path, the documented options are:

- a leakproof wrapper reviewed for safety;
- partitioning by workspace;
- a separate search role.

None is justified now.

**Other isolation guarantees:**

- Every lane also carries an explicit `workspace_id` predicate.
- Cross-workspace isolation is tested in every search mode and for traces.
- A catalog test requires every table with `workspace_id` to have ENABLE + FORCE RLS and a policy.

## Traces

Every API search writes one `retrieval_traces` row. It holds:

- dense and lexical candidates (child id, parent handle, rank, score, span);
- the lexical query (lexemes, IDF, phrases, pruned terms);
- fused parents with lane ranks and RRF scores;
- the rerank pool, pair kinds and scores;
- balancing decisions;
- the final handles with their anchor child;
- per-stage timings and degradation flags.

**Properties:**

- **No document text**, so purge needs no change.
- **RLS on, UPDATE revoked.**
- **Written after the read**, in its own transaction, so it never interacts with ingestion locks. A failed write never fails the query.

## Determinism

Rankings are deterministic within a database and **across re-ingestion**. Ties break on (parent handle, child ordinal), never on random child ids.

The fix was itself found by measurement: two identically seeded databases gave different lexical top-20s for 12/44 items. Metrics were unchanged, but the result wasn't reproducible. A regression test ingests one corpus twice and requires identical rankings in every mode.

## Latency

Final config, dev, in-process, M2 laptop CPU:

| Stage | p50 / p95 ms |
|---|---|
| Query embedding | 8.9 / 35 |
| Dense SQL | 13.3 / 28 |
| Lexical prep + SQL | 31.5 / 48 |
| Fusion | 0.6 / 0.7 |
| Hydrate | 1.3 / 1.8 |
| **Rerank** | **597 / 855** |
| **Total** | **669 / 929** |

**The reranker is about 90% of latency.**

**Contention.** Without the reranker, dense SQL is about 4 ms and lexical about 15 ms. Both are slower in reranked runs, consistent with ONNX Runtime worker threads still spinning after inference and contending for the CPU. This needs controlled measurement on the deployment target (plan: Render CPU spike, Phase 3), together with the reranker timeout and the hosted-reranker switch.

## Open problem: the reranker on customer-voice and ID queries

The frozen configuration (hybrid + rerank) was chosen on dev. On test it trades recall@10 for hit@1. Phase 2 does not tune on test.

These candidate iterations would each be measured on dev **with new dev items**, followed by a **fresh test split**, because the current test split has now been seen:

1. **Rerank-aware fusion.** Fuse the cross-encoder rank with the RRF rank (RRF over three "lanes") instead of replacing the order. This keeps lexical exact-ID wins.
2. **Lexical exact-match protection.** Never demote a parent whose child matched an exact identifier or quoted phrase.
3. **A different cross-encoder.** `bge-reranker-base` is a configuration change.
4. **Larger v1 set (plan: ~120 items).** At n = 21, a 4-item swing is 19 points.

## Reproducing

```bash
make reset-db && make migrate
uv --directory backend run python -m marketsignal.evaluation seed        # real upload API, in-process
uv --directory backend run python -m marketsignal.evaluation integrity
uv --directory backend run python -m marketsignal.evaluation run --split dev \
    --arms dense,lexical,hybrid,dense-rerank,hybrid-rerank --reference dense --out ../eval/reports/mine
uv --directory backend run python -m marketsignal.evaluation profile --out ../eval/reports/profile \
    --superuser-dsn postgresql+psycopg://postgres:dev-only-insecure-bootstrap@localhost:5432/marketsignal
```

`run --split test` is refused without `--milestone` and is logged in `eval/test-split-log.jsonl`.
