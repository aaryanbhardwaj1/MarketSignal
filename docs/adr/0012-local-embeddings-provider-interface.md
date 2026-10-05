# ADR-0012: Local embeddings behind a provider interface, with a per-model embedding table and a file-backed cache

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 1 (embedder and file cache); dense retrieval SQL in Phase 2 (this ADR is updated with measurements when the component is built)
- **Related:** plan §0.2 (A3), §4, §5, §6 (`chunk_embeddings`), §7, §8, §9, §12, §22, §24, §26, §28, §30, §32; ADR-0001 (Postgres + pgvector), ADR-0002 (hybrid retrieval), ADR-0003 (parent/child chunks), ADR-0005 (local cross-encoder), ADR-0011 (answer cache / corpus_version), ADR-0013 (evaluation); no approved deviation

## Context

Dense retrieval needs an embedding model at ingest time (every child chunk) and at query time (every search). The constraints are:

- **Data posture (A3).** Ingestion should send no corpus text to third parties. Hosted embedders are a policy decision per workspace, not the default.
- **CI must evaluate retrieval for free and deterministically** (§30). It needs no API key and gives the same vectors on every run.
- **Hardware.** Development runs on an 8 GB laptop. Production runs on CPU-only Render instances.
- **Experimentation.** Phase 7 runs a bge-small vs bge-base A/B. Changing models must not destroy the baseline or need a schema migration.
- **pgvector.** A typed `vector(n)` column fixes the dimension. HNSW indexes support `vector` up to 2,000 dimensions and `halfvec` up to 4,000.
- **Re-runs.** Ingest is re-run often (seed regeneration, `freeze-gold`, CI), so re-embedding identical text repeats avoidable work on every run (seed time and embedding throughput are recorded at the Phase 1 exit).

## Decision

**Model and interface.**
- An `Embedder` interface lives in `providers/`. The default implementation is fastembed (ONNX, no torch) running **`BAAI/bge-small-en-v1.5`, 384 dimensions**, locally in both api and worker.
- Query embeddings use the model's query instruction ("Represent this sentence for searching relevant passages: "). Passages are embedded without it.
- Child windows (192 tokens, 32 overlap) are counted with the embedder's tokenizer. Window, contextual header and query stay under the model's 512-token limit (§9).
- The provider factory refuses hosted embedders for workspaces with sources above `internal` unless a flag is set (§24).

**Storage: one table, all models.**
- `chunk_embeddings(child_id, workspace_id, model_id text, embedding vector, PRIMARY KEY (child_id, model_id))`. The `embedding` column is deliberately **untyped**.
- Each model gets its own **partial expression HNSW index**:
  ```sql
  CREATE INDEX ON chunk_embeddings USING hnsw ((embedding::vector(384)) vector_cosine_ops)
    WITH (m = 16, ef_construction = 64) WHERE model_id = 'bge-small-en-v1.5';
  ```
- Every dense query filters `model_id = :active_model` and applies the identical cast, so the planner can match the index. An embedder A/B means embedding a second model and flipping `ACTIVE_EMBED_MODEL`. It needs no `ALTER TYPE`, and the baseline vectors stay in place.
- **Canonical dense query** (§7). It runs inside an explicit transaction, because `SET LOCAL` outside one is silently a no-op. It sets `hnsw.ef_search=100` and `hnsw.iterative_scan=relaxed_order` via `set_config(..., true)`. A `MATERIALIZED` CTE applies the workspace, active-version, confidentiality and optional class filters and returns `LIMIT 100`. The outer `ORDER BY distance + 0, child_id` is required on PG17+. Iterative scan fixes HNSW overfiltering under selective filters.

**Caching.**
- **Ingest:** a file-backed cache keyed by `(model, sha256(text))` at `.cache/embeddings/<model>.parquet`, plus a DB lookup through a btree on `(model_id, text_sha256)`. Only misses are embedded, in batches. CI restores the file cache with `actions/cache`.
- **Query:** an in-process LRU and Redis, keyed by `(model, sha256(query))`. When Redis is down, only the LRU is used.

**Failure behaviour.**
- Query-time failure (exception, timeout or open circuit): the dense lane is skipped and the call returns `RETRIEVAL_LEXICAL_FALLBACK`.
- Ingest-time failure: embeddings stay NULL, the version becomes `ready_degraded` (lexical-only), and a re-embed job is scheduled. Its completion bumps corpus_version (ADR-0011).

## Alternatives considered

- **bge-base-en-v1.5 (768-d), local.** Higher quality ceiling. The plan's selection notes record about 5 docs/s against about 13 for bge-small on an M2, and it needs more memory. It is kept as the Phase 7 A/B arm, which this storage design makes cheap.
- **Hosted embedders (Voyage-4, OpenAI text-embedding-3-small).** Stronger and need no local CPU. Rejected as the default: corpus text would leave the system (A3), CI would need a key and cost money, and determinism would depend on the vendor. The interface keeps them one adapter away.
- **Typed `vector(384)` column with a single index.** Simpler SQL. A model change, however, needs `ALTER TYPE` and a full rewrite, which destroys the baseline needed for a paired A/B.
- **One table per model.** Also avoids ALTER TYPE, but spreads dense SQL across dynamic table names. Per-model partial indexes give the same isolation in one table.
- **IVFFlat or exact scan only.** IVFFlat needs training and has lower recall. An exact scan is O(n). At demo scale (about 3–5k children per workspace) an exact scan takes milliseconds, so HNSW serves the scaling story, and exact search is kept for the CI gate.
- **Dedicated vector database.** Rejected in ADR-0001: one transactional store for text, vectors, filters and RLS.

## Tradeoffs accepted

- A lower quality ceiling than large hosted models. This is measured, not assumed (§26 ablations).
- CPU and RAM on both api and worker. Local models push Render to the 2 GB instances, about $80/mo against about $45 if embedding and reranking were hosted (§32).
- The untyped column puts a burden on every query: a cast that does not match the index silently falls back to a sequential scan. An EXPLAIN-based test guards this.
- A model change means a full re-embed. The cache key includes the model, so stale vectors are never reused.
- The file cache is a second copy of the vectors outside the database. It is a derived artifact, never a source of truth.

## Consequences

**Positive**
- Retrieval eval runs in CI without a key, deterministically, with warm embeddings.
- Embedder A/B experiments are additive and reversible.
- Ingest reruns skip work for unchanged text.

**Negative**
- Model files enlarge the api and worker images or need a cache volume (§31).
- Two ONNX models (embedder, cross-encoder) share CPU on the api. That is the first scaling bottleneck (§34).

**Follow-ups**
- Phase 1 records seed time and embedding throughput.
- The Phase 3 Render CPU spike records embed p50/p95 and peak RSS on the deployed image.
- Phase 7 runs the bge-small vs bge-base ablation with paired statistics.
- The documented scale step is `PARTITION BY LIST (workspace_id)`, or a separate inference service.

**Verification**
- Phase 1 exit: a planted fact is found by dense search (and lexical search) and resolves to exact text.
- Ingest health check on every not-yet-active version: a dense self-match in the top 5 for 5 sampled children.
- Integration: iterative-scan settings are active inside the retrieval transaction; a filtered query returns exactly LIMIT rows; an EXPLAIN test confirms HNSW use; embedder down leads to lexical-only.
- Eval: ANN recall against an exact scan (`enable_indexscan=off`), reported by the harness; the bge-small vs bge-base ablation, mapped to parents before scoring.
