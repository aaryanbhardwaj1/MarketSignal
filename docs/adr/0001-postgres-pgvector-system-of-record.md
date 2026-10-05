# ADR-0001: PostgreSQL + pgvector as the single system of record

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** **Phase 1 implemented** (PostgreSQL 18.6, pgvector 0.8.7; evidence model in migration 0002)
- **Related:** plan §5, §6, §7, §8, §16, §33, §34; ADR-0002, ADR-0003, ADR-0004; no approved deviation

## Context

MarketSignal answers research questions over a per-workspace corpus and must cite every claim with a handle that resolves to the exact stored text (ADR-0004). It has to persist, consistently:

- relational application data: workspaces, sources, versions, conversations, messages, hypotheses, audit events;
- evidence text: parent chunks (the citation unit) and child chunks (the retrieval unit) (ADR-0003);
- dense embeddings, lexical full-text indexes, and typed dataset rows for analytics;
- uploaded file bytes, which the API writes and the worker reads (Render gives the two services no shared disk);
- an ingestion job queue whose enqueue must commit atomically with the source-version row;
- an append-only run event log used for SSE replay, plus retrieval traces and a spend ledger.

Constraints: workspace isolation must be enforced in the database, not only in application code (§6, §23). Resolution must read the same rows retrieval returned; two stores (for example a vector index and a separate text store) can drift, and a handle that resolves to different text than was retrieved breaks the trust model. Demo scale is small (about 26 Northstar sources, roughly 3–5k children per workspace) and the budget is a single small managed deployment.

## Decision

Use **PostgreSQL 18 with pgvector 0.8.7** (`pgvector/pgvector:0.8.7-pg18`) as the only system of record. Redis 8 is used for the answer cache, query-embedding cache and rate limits, and is optional for correctness.

What lives in Postgres:

| Concern | Mechanism |
|---|---|
| App data, versions, evidence text | Tenant tables with `workspace_id`, composite FKs, ENABLE + FORCE RLS (§6) |
| Embeddings | `chunk_embeddings(child_id, model_id, embedding vector)`: untyped `vector`, one **partial expression HNSW index per model** (`m=16, ef_construction=64`), cosine ops |
| Lexical search | Generated `tsv` (heading weight A, body D) and `tsv_body` columns, GIN index (ADR-0002) |
| Jobs | Procrastinate 3.x: SKIP LOCKED + LISTEN/NOTIFY, job deferred on the same psycopg connection as the version insert |
| Blobs | `BlobStore` protocol, default Postgres `bytea` (files ≤ 25 MB); S3-compatible adapter documented |
| Run events | `run_events(run_id, seq)` for replay; LISTEN/NOTIFY for cross-process live tail |
| Traces, spend | `query_runs`, `tool_runs`, `retrieval_traces`; `spend_ledger` with atomic reservations |

Access: SQLAlchemy 2.1 async + psycopg 3 (one driver shared with Procrastinate) + Alembic. Retrieval SQL is explicit `text()`. Roles: `ms_owner` owns schema and migrations; `ms_app` (`NOSUPERUSER NOBYPASSRLS`, DML only) is used by API and worker; `ms_eval` by the eval runner. `/readyz` fails if the connected role is superuser or BYPASSRLS.

Dense query contract (§7): runs inside an explicit transaction, sets `hnsw.ef_search=100` and `hnsw.iterative_scan=relaxed_order` via `set_config(…, true)`, filters on `model_id`, workspace, active version ids and confidentiality, and orders by `distance + 0, child_id` for determinism. An embedder A/B adds rows under a second `model_id` and flips `ACTIVE_EMBED_MODEL`; no `ALTER TYPE`, and the baseline is kept.

## Alternatives considered

- **Dedicated vector database alongside Postgres.** Better ANN tooling at large scale, but evidence text, versions and vectors would live in two stores, requiring dual writes and drift handling, and resolution could disagree with retrieval. Adds a paid service and a second isolation model to prove.
- **Search engine (OpenSearch/Elastic/Vespa) for hybrid candidates.** Native BM25 and hybrid ranking, but a cluster to run and pay for at demo scale. Kept as the documented scaling step, fed by CDC, with Postgres still the system of record (§34).
- **Celery/RQ/Taskiq with a broker.** No transactional enqueue: a version row can commit without its job, or the reverse. Arq is maintenance-only.
- **S3/R2 for blobs now.** Correct at scale, but an extra service and not transactional with the version row. Adapter documented; switch at the §34 trigger.
- **IVFFlat or exact-only search.** IVFFlat needs training and has lower recall. Exact-only is simplest and is what the CI gate uses, but provides no sub-linear scaling story.
- **Schema- or database-per-tenant.** Stronger isolation, heavy migration overhead for a single-principal demo. Per-workspace `PARTITION BY LIST` is the documented next step.

## Tradeoffs accepted

- **Single-node ceiling.** Retrieval, ingestion, queue and replay share one primary.
- **RLS × GIN.** `@@` is not `LEAKPROOF`, so under FORCE RLS the planner filters the workspace's rows sequentially for lexical search instead of using the GIN index. Accepted at demo scale with EXPLAIN evidence; remedy documented (§8).
- **Filtered ANN subtleties.** HNSW post-filters; iterative scan is required, which pins pgvector ≥ 0.8 on the host.
- **Blobs in `bytea`** are the wrong choice at scale; purge leaves WAL and dead tuples until vacuum (documented limitation).
- **Queue load on the primary**, negligible at this scale.

## Consequences

**Positive**
- Ingestion activation is one small transaction: version → ready, previous → superseded, guarded `current_version_id`, corpus-version bump, audit event.
- One resolver over one store serves tools, evidence API, verification, cache revalidation, hypotheses and briefs (§16).
- Isolation is proven by the database (RLS + composite FKs), and one backup covers everything.
- No separate vector DB, broker, search cluster or object store (§33).

**Negative**
- Lexical search is a sequential filter under RLS; the scale-out path requires a narrow `ms_retrieval` role or partitioning.
- HNSW adds build memory and planner subtleties (`SET LOCAL` outside a transaction is silently a no-op).

**Follow-ups**
- Phase 0 spike: confirm Render's pgvector is ≥ 0.8 and its default credential can `CREATE ROLE` without superuser/BYPASSRLS; fallback is Railway with the `pgvector/pgvector` image.
- Scaling triggers (§34): blobs to S3, read replica for retrieval, lexical to `ms_retrieval` or partitions, and candidate generation to a dedicated engine at roughly 50–100M vectors or when filtered multi-tenant ANN degrades after partitioning.

**Verification**
- Integration tests (as `ms_app`): transactional-enqueue rollback leaves no job; iterative-scan settings are active inside the retrieval transaction; a filtered query returns exactly LIMIT rows; EXPLAIN shows HNSW for the ANN path; EXPLAIN-based regression test for the RLS × GIN behaviour.
- RLS negative tests: scope A sees 0 rows of B; cross-workspace INSERT fails WITH CHECK; missing scope errors.
- Eval harness reports ANN recall against an exact scan; the CI gate uses exact search.
- `/readyz` role guard test; ingestion health check on the not-yet-active version (rare-lexeme `tsv @@` membership, dense self-match in top-5, handle resolves to text containing the child).

## Implementation notes (Phase 1, 2026-10-05)

- **One database holds everything.** Sources, versions, blobs (`bytea`), parents, children, embeddings, dataset tables and rows, audit events and the Procrastinate job queue all live in PostgreSQL 18.6 with pgvector 0.8.7 (`pgvector/pgvector:0.8.7-pg18`). No object store is used in Phase 1. The 25 MB upload cap keeps blobs small, and a purge deletes the blob in the same transaction as the derived content.
- **Lexical search** uses generated, stored `tsvector` columns on `child_chunks`: `tsv` weights the heading A and the body D, and `tsv_body` holds the body only. `tsv` has a GIN index.
- **Measured on the seed corpus** (30 uploads, 994 KB): 2,680 parents, 2,230 children and 2,230 embeddings. Total ingestion time is about 60 s on a laptop CPU, of which embedding is about 88% (`docs/phase-reports/phase-1.md`).
- **Not yet measured:** RLS × GIN/HNSW query cost under load. That belongs to Phase 2 retrieval, where the real queries are built.
