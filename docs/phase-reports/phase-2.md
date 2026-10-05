# Phase 2 report: hybrid retrieval and the evaluation baseline

| | |
|---|---|
| Completed | 2026-10-05 |
| Central question | *Can we show, quantitatively and reproducibly, that hybrid retrieval plus reranking is justified over vector-only search on this corpus?* **Partly.** Hybrid beats vector-only on the held-out test split (hit@10 76.2 vs 47.6, p = 0.031). On dev the two are not distinguishable. The reranker helps the top of the list on dev, but on test it trades recall@10 for hit@1. Details below, with every interval. |
| Frozen configuration | Hybrid (dense + IDF lexical) → parent-level RRF (k = 60) → MiniLM-L-6 cross-encoder (MaxP, pool 20) · child policy **c3** · balancing **off** · BGE instruction **off** |
| Methodology | [`eval/README.md`](../../eval/README.md); design and interview narrative in [`docs/RETRIEVAL_DEEP_DIVE.md`](../RETRIEVAL_DEEP_DIVE.md) |
| Recorded runs | [`eval/baselines/phase2/`](../../eval/baselines/phase2/), summarised in [`SUMMARY.md`](../../eval/baselines/phase2/SUMMARY.md). Baselines are never regenerated. |
| CI | Run 37389646958 on `d0baf56`: safety ✅, backend ✅ (259 passed), **retrieval-eval ✅** (seed, `integrity: OK`, dev gate), frontend ✅, container build ✅. The docs commit is verified at push. |

## Exit criteria

| Criterion | Status | Evidence |
|---|---|---|
| v0 dataset versioned and integrity-checked | ✅ | `eval/datasets/retrieval-v0`, pinned by items, corpus and ledger hashes. `integrity` passes locally and in CI against a freshly seeded corpus. |
| Dev/test leakage checks pass | ✅ | Grouped union-find split, 44 dev / 21 test in 40 groups. Unit test plus `integrity`. |
| Dense-only and lexical-only baselines permanently recorded | ✅ | `00-baseline-dev`, before any retrieval change; test baselines in `07-test-milestone-c2` on the untouched c2 index. |
| Production dense and lexical retrieval | ✅ | `retrieval/lanes.py`. Dense reproduces the baseline top-20 on 44/44 items. |
| Parent-level RRF exists and is tested | ✅ | `fusion.py`, including the "dense finds window 2 of P, lexical finds window 3 of P" test. |
| Cross-encoder reranker exists and fails gracefully | ✅ | Outage, timeout, and parent-purged-mid-request tests. The flag is `RERANKER_UNAVAILABLE`. |
| Final parent highlights resolve correctly | ✅ | Every returned anchor is resolved through the evidence API, and the highlight equals the parent slice. The anchor is now the MaxP-winning window. |
| Cross-workspace isolation still passes | ✅ | Every search mode, traces, and a catalog guard for RLS on every `workspace_id` table. |
| RLS search performance measured and documented | ✅ | `rls-profile/`, below. |
| BGE query-instruction A/B documented | ✅ | Not adopted (`04-bge-instruction-dev`). |
| Retrieval traces persisted | ✅ | `retrieval_traces` (migration 0003), one row per API search. |
| Final configuration frozen | ✅ | `06-final-dev`. Unchanged after the review fixes (44/44 identical top-20 in every arm). |
| One-time frozen-test evaluation recorded | ✅ | `07-test-milestone-c2`, `07-test-milestone-c3`; `eval/test-split-log.jsonl`. |
| GitHub Actions green | ✅ | Runs on `4811557` and the review-fix commits. |
| RETRIEVAL_DEEP_DIVE.md, ADR notes, this report | ✅ | ADRs 0001, 0002, 0003, 0005, 0009, 0012 and 0013; ARCHITECTURE_PLAN §0.4. |
| Working tree clean, commits pushed | ✅ | — |

## The dataset (v0)

**Size.** 65 items: 44 dev and 21 test; 59 NORTHSTAR and 6 SOUTHPEAK.

**Categories** (dev / test):

| Category | Dev | Test |
|---|---|---|
| Single-source fact | 6 | 3 |
| Exact number | 7 | 3 |
| Named entity | 3 | 3 |
| Customer free text | 5 | 2 |
| Cross-format | 4 | 1 |
| Keyword-sensitive | 4 | 3 |
| Semantic paraphrase | 5 | 3 |
| Enumeration | 3 | 1 |
| Ambiguous / distractor | 4 | 1 |
| Versioning | 3 | 1 |

**How the items were made:**

1. Questions came from four independent writer agents that saw **only an anchor-free fact digest**: no documents, no retrieval code.
2. A critic agent reviewed each batch.
3. The set was curated from a 71-item pool.
4. Every planted anchor sits in exactly one active parent.
5. Of 16 alternate-parent candidates, 10 were accepted by two independent judges, who agreed on every pair.

**Reachability.** 4 dev and 4 test items need facts that live only in child-less numeric rows. You decided these stay analytics-only (Phase 5). That caps hit@k at 90.9% on dev and 81.0% on test, so every table also reports the reachable subset.

**Human review of the items is still pending.** Provenance is `llm_draft_agent_reviewed`.

## Results

### Dev (n = 44): baselines and the final configuration

| Arm | hit@1 | hit@10 | recall@10 | Recall@pool (@20) | MRR | Reachable hit@10 (n = 40) | p50 / p95 ms |
|---|---|---|---|---|---|---|---|
| A0 Baseline dense (Phase 1, c2) | 56.8 [42.2–70.3] | 81.8 [68.0–90.5] | 78.0 | 83.3 | 0.662 [0.539–0.781] | 90.0 | 10.8 / 13.9 |
| B0 Baseline lexical (Phase 1, AND) | 4.5 | 4.5 | 4.5 | 4.5 | 0.045 | 5.0 | 2.2 / 2.7 |
| A Dense (production, c3) | 56.8 | 84.1 | 80.3 | 83.3 | 0.664 | 92.5 | 13 / 20 |
| B Lexical (IDF, c3) | 45.5 | 81.8 | 78.4 | 82.2 | 0.579 | 90.0 | 16 / 29 |
| C Hybrid RRF (c3) | 59.1 | 86.4 | 83.7 | 87.9 | 0.693 | 95.0 | 28 / 43 |
| D′ Dense + rerank (c3) | 70.5 | 86.4 | 82.2 | 83.3 | 0.769 | 95.0 | 598 / 740 |
| **D/E Hybrid + rerank (c3, final)** | **70.5 [55.8–81.8]** | **88.6 [76.0–95.0]** | **83.3** | **87.9** | **0.774 [0.661–0.879]** | **97.5** | 669 / 929 |

**Paired comparisons** (exact McNemar for hit@k; paired-bootstrap 95% CI for ΔMRR):

| Comparison | hit@1 (gained / lost) | hit@10 (gained / lost) | ΔMRR |
|---|---|---|---|
| Hybrid vs dense | 7 / 6 | 2 / 1 | +0.029 [−0.073, +0.130]: not distinguishable |
| Hybrid + rerank vs dense | 9 / 3 (p = 0.146) | 2 / 0 (p = 0.5) | **+0.110 [+0.021, +0.207]** |
| Hybrid + rerank vs hybrid (c2, `02`) | 9 / 2 (p = 0.065) | — | **+0.123 [+0.038, +0.215]** |

### Test (n = 21): the one-time milestone with the frozen configuration

| Arm | hit@1 | hit@10 | recall@10 | Recall@pool | MRR | Reachable hit@10 (n = 17) |
|---|---|---|---|---|---|---|
| A0 Baseline dense (c2, untouched) | 28.6 [13.8–50.0] | 57.1 [36.5–75.5] | 51.6 | 56.3 | 0.383 | 70.6 |
| B0 Baseline lexical (c2, untouched) | 4.8 | 4.8 | 4.8 | 4.8 | 0.048 | 5.9 |
| C (c2) Hybrid | 28.6 | 61.9 | 56.3 | 56.3 | 0.392 | 76.5 |
| D (c2) Hybrid + rerank | 42.9 | 52.4 | 50.0 | 56.3 | 0.482 | 64.7 |
| A Dense (c3) | 28.6 | 47.6 | 44.4 | 68.3 | 0.373 | 58.8 |
| B Lexical (c3) | 38.1 | 71.4 | 65.9 | 70.6 | 0.457 | 88.2 |
| **C Hybrid (c3)** | 38.1 | **76.2 [54.9–89.4]** | **70.6** | 70.6 | **0.490** | **94.1** |
| D′ Dense + rerank (c3) | 42.9 | 61.9 | 59.5 | 68.3 | 0.494 | 76.5 |
| **E Hybrid + rerank (c3, frozen final)** | **42.9 [24.5–63.5]** | 57.1 [36.5–75.5] | 57.1 | 70.6 | 0.488 [0.294–0.686] | 70.6 |

**Paired on test (c3):**

| Comparison | hit@10 | Δrecall@10 | Other |
|---|---|---|---|
| **Hybrid vs dense** | **+6 / −0, p = 0.031** | **+0.262 [+0.095, +0.452]** | ΔMRR +0.117 [−0.019, +0.269] |
| Hybrid + rerank vs dense | +4 / −2, p = 0.69 | — | ΔMRR +0.115 [−0.016, +0.266] |
| Final vs untouched baseline dense | 57.1 → 57.1 | — | hit@1 28.6 → 42.9, MRR 0.383 → 0.488 |

**What the test split says.**
- Fusion is justified on held-out data.
- **The reranker as configured is not.** It raises hit@1 and leaves MRR unchanged, but lowers hit@10 by 4 items against hybrid.
- The frozen configuration came from dev. It is reported as frozen and was not re-tuned on test.
- The v0 test split has now been used once. It must not guide the next iteration, so a fresh split comes with gold v1.

**Small samples.** At n = 21, one item is 4.8 points. Only the hybrid-vs-dense recall effect clears its interval.

## Measured iterations (dev)

Each change was a single variable, compared pairwise on dev. Run ids refer to `eval/baselines/phase2/`.

| # | Change | Result | Decision |
|---|---|---|---|
| 01 | Production lexical lane (IDF OR) vs Phase 1 AND lane | hit@10 4.5 → 77.3 | Adopted (the approved §11 design) |
| 01 | Parent-level RRF vs dense | +2 / −1 hit@10, ΔMRR not distinguishable | Kept (design; test later confirms) |
| 02 | + Cross-encoder | ΔMRR +0.123 [+0.038, +0.215] | Adopted (test is mixed; see open problem) |
| 03 | Source balancing (cap 3, pool cap 7) | hit@10 −1, hit@20 −2; the pool cap alone causes it | **Not adopted.** Built and off. One crowding case is fixed (R0-049: 12 → 7). |
| 04 | BGE query instruction | Dense hit@10 −3 / +0 (p = 0.25); reranked arm unchanged | **Not adopted** |
| 05 | Row identifiers in row children (separate database) | Lexical RV-00655 26 → 2, R0062 21 → 1; hybrid ΔMRR +0.046 [+0.007, +0.095]; no reranked regressions | **Adopted as c3 after your approval** |
| — | Stable tiebreak (handle, ordinal) instead of random child id | Metrics identical; rankings now identical across re-ingestion | Adopted (bug fix) |

## Retrieval failure examples (interview material)

More are in each run's `report.md` failure buckets.

- **Dense finds, lexical misses.** NS-040 *"What portion of young shoppers put more faith in fellow buyers' opinions…"*: dense 1, lexical 82.
- **Lexical finds, dense misses.** *"Pull up review RV-00655"*: lexical 2, dense never; hybrid + rerank 5, dense + rerank never.
- **Both miss, by design.** Numeric rows: *"NS-KR2 return rate"*, *"Social Shop Gen Z conversion, Sept 2026"*.
- **Both struggle: abstract paraphrase.** NS-102 *"…bespoke products should move beyond a small trial"*: dense 24, lexical 28, hybrid + rerank 15.
- **The reranker demotes the right answer** (test):
  - respondent R0147: hybrid 1 → hybrid + rerank 12;
  - SP-C05 (Southpeak boot sizing): 3 → 19;
  - NS-145: 4 → 14.
- **The reranker promotes the right answer:** R0-003 (pilot dates and stores) 4 → 1; R0-022 (largest Gen Z segment) 2 → 1.
- **Crowding.** The pilot report fills 7 of the top 10 for a Northstar/Kinetic Lab comparison; the Kinetic Lab evidence is at rank 12.
- **Distractors.** Ledger distractor parents never outrank the true parent, in any arm (0/6 dev, 0/1 test).

## RLS and full-text search

`EXPLAIN (ANALYZE, BUFFERS)` of the exact lane SQL for 44 dev queries; superuser runs are the no-RLS control.

| Lane / role | exec p50 / p95 ms | GIN used | HNSW used | Rows scanned (p50) |
|---|---|---|---|---|
| Lexical, `ms_app` (forced RLS) | 11.6 / 20.8 | **0/44** | — | 2,330 |
| Lexical, superuser (no RLS) | 11.2 / 19.6 | 44/44 | — | 1,299 |
| Dense, `ms_app` | 1.6 / 2.3 | — | 0/44 | 4,560 (children + embeddings) |
| Dense, superuser | 1.4 / 1.7 | — | 0/44 | 6,690 |

**Why GIN goes unused.** Under RLS, Postgres won't use the non-leakproof `@@` as an index condition ahead of the security qual. It filters the workspace's rows through the btree first.

**Cost at this scale:** none measurable, because IDF scoring dominates. **The RLS model is unchanged.**

**HNSW** is never chosen at about 2,200 children; an exact scan is cheaper. The index is valid and is chosen when sequential scans are discouraged.

## Corpus and index

| | Value |
|---|---|
| Parents | 2,680 |
| Children / embeddings | 2,230 / 2,230 (Northstar 1,834, Southpeak 396) |
| Active versions | 29 (GENZ-TRENDS v1 superseded) |
| `child_chunks` | 3.3 MB |
| GIN `child_chunks_tsv` | 2.2 MB |
| `chunk_embeddings` | 4.5 MB |
| HNSW index | 4.5 MB |
| Seed, warm embedding cache | about 9 s locally |
| Seed, cold (CI) | 61–93 s |

## Latency (final configuration, dev, M2 laptop CPU, in-process)

| Stage | p50 | p95 |
|---|---|---|
| Query embedding | 8.9 | 35 |
| Dense SQL | 13.3 | 28 |
| Lexical prep + SQL | 31.5 | 48 |
| Fusion | 0.6 | 0.7 |
| Pool hydration | 1.3 | 1.8 |
| **Rerank (≤ 40 pairs)** | **597** | **855** |
| **Total** | **669** | **929** |

- **The reranker is about 90% of latency.** In the CI runner it took p50 943 ms.
- **Contention.** Without the reranker, dense SQL is about 4 ms and lexical about 15 ms. Both are slower in reranked runs, consistent with ONNX Runtime threads contending for the CPU. This is for the Phase 3 target-instance spike.

## Tests and CI

| Suite | Count |
|---|---|
| Backend, local | **258 passed, 1 skipped** (the superuser readiness test needs `MS_TEST_SUPERUSER_DATABASE_URL`; CI sets it). 162 unit and 90 integration tests collected, plus the MCP spike. |
| Backend, CI | **259 passed** on `d0baf56` (run 37389646958); 252 on `4811557`, before the review-fix tests |
| Frontend (vitest) | **56 passed** (7 files; 11 new) |
| Retrieval-eval CI job | Seeds through the real upload API (93 s cold, 10 s with the embedding cache), `integrity: OK`, then gates hybrid + rerank on dev. **CI on Linux reproduced the local dev metrics exactly:** hit@1 70.5, hit@10 88.6, recall@10 83.3, MRR 0.774. |
| Static checks | ruff format and lint, strict mypy (73 files), ESLint, tsc, next build, gitleaks, repo guard |

**Phase 2 test additions:**
- evaluation unit tests: metrics, statistics, split, overlap, dataset;
- fusion, rerank and balance unit tests (20);
- retrieval API integration tests (23): isolation in every mode, traces, active versions, filters, highlights, outages, adversarial lexical input, heading flood, concurrent purge, cross-ingestion determinism, degradation flags, embedding timeout, bounded filters;
- isolation suite: `retrieval_traces` and a catalog guard;
- a parser test for c3.

**CI note.** Re-running an old run on `main` cancels the newer run, because of the per-branch `cancel-in-progress` concurrency group. Phase 1's `208cc04` is now green (attempt 5); see the Phase 1 report.

## Failures encountered and fixes

| # | Failure | Found by | Fix |
|---|---|---|---|
| 1 | The Phase 1 lexical lane (`websearch_to_tsquery`, AND) matched almost no natural-language question | Baseline | The approved IDF OR lane (§11) |
| 2 | Row children omitted identifier columns, so ID lookups were impossible | Dev failure analysis (RV-00655) | Policy c3, after a separate-database experiment and your approval |
| 3 | Lexical tie order depended on random child ids (12/44 items differed across re-ingestion) | Comparing two identically seeded databases | Tiebreak on (handle, ordinal), plus a cross-ingestion regression test |
| 4 | A purge committing between fusion and rerank hydration raised `KeyError` | Concurrent search/purge test (intermittent) | Vanished parents are dropped and recorded in the trace |
| 5 | Intermittent `libc++abi … recursive_mutex` abort (exit 134) at interpreter exit after ONNX work (macOS) | Test runs and the seed CLI | Joined executors, an atexit session release, and `os._exit` after flushing in the eval CLI. Not reproduced in 50 targeted runs; recorded as a risk. |
| 6 | Re-seeding a non-empty database re-uploaded GENZ v1 after v2 (a correct ADR-0016 revert), flipping the active version | My own repro loop | Both seeders refuse a workspace that already has sources |
| 7 | My first lane checks expected the wrong locators, and the first determinism test was vacuous (identical comments become a `constant` column) | Tests failing or passing on old code | Tests corrected; the determinism test is shown to fail on the old tiebreak |
| 8 | Workflow argument misuse (`"__FILE__"`), zsh word splitting, a committed mypy error, and a re-run cancelling a newer CI run | Tooling | Fixed at once; the mypy fix is its own commit |
| 9 | **Adversarial review: 18 findings, 0 refuted**, including: a pooled DB connection held during inference; no embedding timeout; the highlight not being the MaxP winner; class-floor eviction; unbounded class lists; integrity accepting non-active gold parents; results not recording the index policy; `reachability` reading test without the guard; `compare` silently pairing mismatched files | Review workflow (4 reviewers + skeptics) | All fixed in `452c212` and `d0baf56`. Rankings re-verified unchanged (44/44 per arm). |

## Implementation deviations (also in ARCHITECTURE_PLAN §0.4)

- **Tiebreak:** (parent handle, child ordinal), not `child_id`.
- **Lane rank:** distinct-parent position.
- **Collapse:** implicit in fusion; `hit_count` is not computed.
- **Query instruction:** not used (A/B).
- **Balancing:** built, measured, off.
- **Child policy:** c3 (approved).
- **Search phases:** model inference runs outside any database session (three-phase search); the query embedding has a timeout.
- **DF statistics:** over the whole active workspace corpus, independent of request filters.
- **Ablation set:** the ~250-item ablation set was not built; v0 is the only instrument.
- **CI gate:** a dev *regression* gate, not the spec's Recall@10 ≥ 0.85 on test. That target is not met (57.1% frozen, 76.2% hybrid) and is capped at 81% by the numeric-row design.
- **Test reachability:** counts for the test split were computed before the guard existed. They informed only the numeric-row question to you (decided: keep the design). The c3 decision used dev data.
- **Re-embed job** for `ready_degraded` versions: still not built; not needed by any Phase 2 decision.

## Unresolved risks

| Risk | Plan |
|---|---|
| **The reranker demotes ID lookups and near-duplicate verbatims** (the test split contradicts dev on hit@10) | Phase 3 or 7 iteration on dev with new items: rerank-aware fusion (RRF over the rerank rank), exact-match protection, or `bge-reranker-base`. Evaluate on a fresh test split. |
| Small v0 (21 test items); test split now used once | Gold v1 (~120) and a fresh split before Phase 7 tuning; human review of v0 items |
| Recall@10 ≥ 0.85 on test not met; ceiling 81% from numeric rows | Phase 5 analytics answers numeric questions; end-to-end recall measured then |
| Rerank latency (p50 about 0.6 s locally, 0.94 s in CI) and thread contention | Phase 3 Render CPU spike: timeout, thread caps, hosted-reranker switch |
| ONNX exit abort (macOS, intermittent) | Mitigated in the CLI; watch in Linux CI (never seen there) |
| RLS disables GIN for the lexical lane | Measured cost is nil at this scale; revisit beyond about 50k children per workspace |
| HNSW unused at this scale | Exact-vs-ANN check at a larger synthetic scale (Phase 7/8) |
| Balancing is off, so a large source can crowd one query | Revisit with agent-requested sources and classes (Phase 4) |
| Re-embed job, stalled-job reaper | Phase 8 hardening (unchanged) |
| Live Anthropic check, Render spike | Phase 3 |

## Proposed Phase 3: standard mode end to end (plan §38)

1. **Render CPU spike first.** Measure reranker p95 and lane latency on the target instance. Set `rerank_timeout_s` and thread caps, and decide local vs hosted reranker. Also run the live Anthropic check deferred from Phase 0.
2. **Evidence pack.** Up to 12 items and 9,000 tokens. Items come from the pool with their anchors; large parents are centred on the anchor child; the D1 anchor goes into the pack.
3. **Synthesis.** Anthropic plus a deterministic FakeLLM for tests. Run-local `[E#]` aliases (D2), resolved to canonical handles before storage. The answer contract labels findings, inference and gaps.
4. **Alias gate and verifier.** Every cited alias maps to a pack item and resolves (100%). Evidence-only fallback, and abstention when nothing relevant is retrieved.
5. **Runs.** `query_runs`, `run_events` and SSE (D7 order contract), with retrieval traces linked by `query_run_id`.
6. **Chat UI.** SafeMarkdown, citation chips that open the evidence viewer at the anchor, and draft/final states.
7. **Retrieval follow-up (dev only).** Rerank-aware fusion as the first measured iteration, motivated by the test finding.

Exit checks from the plan: 100% of cited handles resolve; no-hit items abstain; answerable items are not abstained; the SSE order contract test passes.

## Commits (Phase 2)

| Commit | Message |
|---|---|
| `1c38c66` | feat(eval): freeze the retrieval-v0 gold set with a grouped dev/test split |
| `e6a4837` | eval: record the untouched Phase 1 dense and lexical baselines on dev |
| `1900f4a` | feat(retrieval): production dense/lexical lanes, parent-level RRF, MaxP reranking, balancing |
| `6d77b12` | feat(retrieval): persisted retrieval traces and the evidence search API |
| `dca59f5` | feat(eval): RLS lane profiler, reachability diagnostic and a dense-rerank arm |
| `ab4e90b` | feat(frontend): search page uses the production retrieval API |
| `ea7da10` | feat(eval): in-process seeding through the real upload API and a metric gate |
| `ec58806` | feat(eval): paired comparison of arms across results files |
| `90c3c31` | fix(eval): type the compare metric functions (mypy no-untyped-call) |
| `3643714` | eval: record Phase 2 dev runs - lanes, reranking, balancing, BGE instruction, RLS profile |
| `c6bde51` | feat(ingestion): experiment switch to index row identifiers in row children |
| `a67004a` | fix: seed only into empty workspaces; release ONNX sessions at exit |
| `d20e488` | eval: record the row-identifier experiment; deterministic eval CLI exit |
| `c76da99` | feat(ingestion): adopt child policy c3 - row identifiers in row children |
| `65f8667` | fix(retrieval): break ranking ties on parent handle and child ordinal |
| `6f7486c` | ci: retrieval-eval job - seed via the real upload API, gold integrity, dev gate |
| `4811557` | eval: Phase 2 one-time test-split milestone and run summary |
| `d0135dc` | docs(phase-1): record the recovered CI result for 208cc04 |
| `452c212` | fix(retrieval): address the Phase 2 adversarial review |
| `d0baf56` | fix(eval): stricter integrity, recorded index state, test-split guards |
| (docs) | docs: Phase 2 report, retrieval deep dive, ADR implementation notes |
