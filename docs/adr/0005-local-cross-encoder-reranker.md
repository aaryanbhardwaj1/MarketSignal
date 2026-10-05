# ADR-0005: Local ONNX cross-encoder reranker (MaxP over parents) with fused-order fallback and hosted-reranker switch

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 2 (reranker, MaxP, fallback); Phase 3 (Render CPU spike sets timeout and pool) (this ADR is updated with measurements when the component is built)
- **Related:** plan §15, §13, §5, §28, §32, §33, §35; ADR-0002, ADR-0003; no approved deviation

## Context

Parent-level RRF (ADR-0002) produces a fused order from ranks alone. The top of that order is what the evidence pack, and therefore the generator, sees. Bi-encoder similarity embeds query and passage independently and is weak at fine ordering; lexical scoring ignores meaning.

Constraints:
- Ingestion and retrieval must not send corpus text to third parties by default (assumption A3), and retrieval should have no per-query model cost (§33).
- Hosts are CPU-only (Render instances; developer laptop).
- Retrieval must stay deterministic and must degrade explicitly, never silently (§28).
- The stage budget is about 2 s for one warm `search_evidence` call (§3.2).

## Decision

Rerank the fused pool with **fastembed `Xenova/ms-marco-MiniLM-L-6-v2`** (ONNX, Apache-2.0) behind a `Reranker` interface.

- **Pool:** top **20 parents**, at most 40 query–passage pairs.
- **Pairs per parent:**
  - parent ≤ 350 tokens (rows, slides, Q&A): one pair, (query, heading + parent text);
  - larger parent: (query, heading + anchor child) for each distinct lane anchor, up to 2.
- **Aggregation:** parent score = max of its pair scores (**MaxP**, Dai & Callan 2019).
- **Execution:** ONNX in a bounded thread pool; `RERANK_THREADS` derived from the container CPU quota; a semaphore prevents oversubscription. On run cancellation, in-flight thread work finishes and its result is discarded.
- **Timeout:** about 1.5× the measured p95 on the target instance, set at the Phase 3 deploy spike.
- **Fallback:** on exception or timeout, keep the fused RRF order and report `RERANKER_UNAVAILABLE` (warning to the user, flag on the run).
- **Downstream use:** collapse keeps the best anchor child; balancing uses a relative floor Δ because raw logits are uncalibrated; pack assembly reuses each pool item's best rerank score and scores only unscored items (using anchor child text), so the pool is never fully re-reranked.
- **Hosted switch:** if rerank p95 on the deployed instance exceeds about 1.5 s, production sets `RERANKER=voyage-rerank-2.5-lite`; dev and CI keep local ONNX. Switching is configuration, not code.

**Measured during planning (development laptop, M2):** ~1.7–2.9 s for 40 pairs of ~180 tokens with 1–2 threads. This is the basis for the 20-parent pool. The switch threshold (~1.5 s) applies to rerank p95 on the deployed instance; the laptop figure suggests it may be exceeded, so the Phase 3 target-instance spike decides whether production stays local.

## Alternatives considered

- **No reranker.** Lowest latency; leaves top-of-list ordering to RRF, which ignores score magnitude and cross-attention.
- **LLM reranking.** Strong relevance judgments, but slow, costly per query, non-deterministic, and it would put an LLM inside the deterministic retrieval layer.
- **Hosted reranker as the primary** (e.g. Voyage rerank). Lower latency on weak CPUs, but sends corpus text to a third party, adds per-query cost and a network dependency, and breaks free, offline CI evals. Kept as the production switch.
- **`bge-reranker-base`.** Larger cross-encoder, about 6× slower on CPU; not viable with this latency budget.
- **Scoring a truncated parent (first window only).** Simpler, but drops evidence that sits later in long parents; MaxP over lane anchors scores the windows retrieval actually matched.

## Tradeoffs accepted

- **Domain mismatch:** the model is trained on MS MARCO web queries, not business documents. Measured in ablations; replaceable by configuration.
- **CPU latency** forces a small pool (20 parents), so Recall@pool caps what reranking can recover.
- **Uncalibrated scores:** logits cannot be used as absolute relevance thresholds; balancing uses relative floors.
- **Memory:** bundling the ONNX models is why the plan sizes api and worker at 2 GB instances (about $80/mo plus Vercel, §32).
- **Environment split risk:** if production switches to a hosted reranker, production ordering may differ from CI's local ordering; eval reports must state which reranker produced them.

## Consequences

**Positive:** better ordering at the top of the list with no per-query cost and no corpus egress by default; deterministic and testable offline; failure degrades to a well-defined fused order.

**Negative:** reranking is likely the largest CPU cost in a warm retrieval call; thread and semaphore configuration must match the host's CPU quota.

**Follow-ups**
- Phase 3 CPU spike: deploy the api image with models, run 10 queries, record embed and rerank p50/p95 and peak RSS, then set the rerank timeout and pool size and decide on the hosted switch.
- Phase 7: tune pool size against Recall@pool and latency; reranker A/B if the ablation shows domain mismatch dominating.

**Verification**
- Unit: MaxP pair construction (≤ 350-token single pair vs up to 2 anchors) and the fused-order fallback.
- Integration: reranker down → fused order returned with `RERANKER_UNAVAILABLE` (named degradation test).
- Phase 2 ablation: hybrid vs hybrid + rerank, on Recall@k and MRR after reranking against Recall@pool, with CIs and paired tests.
- Load test (Phase 8): 20 concurrent runs plus ingestion, p50/p95 per stage including rerank.
- Prometheus stage-latency histograms and degradation counters in production.
