# ADR-0010: Postgres-native job queue with transactional enqueue

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 1 (ingestion worker, transactional enqueue, stalled-job reaper); re-embed and purge jobs as their features land (this ADR is updated with measurements when the component is built)
- **Related:** plan §4, §4.2, §4.3, §5, §6, §34; ADR-0001 (Postgres as single system of record), ADR-0009 (workspace isolation), ADR-0016 (purge and versioning); no approved deviation

## Context

Uploads are parsed, chunked, embedded and indexed asynchronously by a separate worker, so the API returns `202` quickly and an out-of-memory parse kills only the worker. Background work also includes re-embedding, purge, stalled-job reaping and nightly maintenance (retention of run events and traces, the demo Sandbox reset).

The core correctness problem is the **dual write**: the upload must create `sources`, `source_versions(status=queued)` and the blob, and also enqueue a job. If these are separate systems:
- commit-then-enqueue can crash between the two, leaving a version queued forever;
- enqueue-then-commit can run a job against rows that were rolled back.

Other constraints: no shared disk between API and worker on the hosting platform, a small budget (each extra managed service costs money), and one Python package with one database driver.

## Decision

Use **Procrastinate 3.x**, a Postgres-native task queue, on the same PostgreSQL 18 instance and the same psycopg 3 driver as the application.

**Transactional enqueue.** One transaction writes `sources` (if new) + `source_versions(status=queued)` + the blob (Postgres `bytea` BlobStore, ≤ 25 MB) + the Procrastinate job. The job is deferred on the same psycopg connection, so its `NOTIFY` fires only on commit. A rollback leaves neither rows nor a job. There is no dual write.

**Job dispatch.** Workers claim jobs with `SELECT … FOR UPDATE SKIP LOCKED` and wake on LISTEN/NOTIFY, so there is no polling delay and no separate broker.

**Job contract (ingestion).**
- Arguments are IDs only: `workspace_id`, `source_version_id`. No document content or paths.
- The job prologue constructs a `WorkspaceScope` from the arguments, so the `after_begin` hook sets `app.workspace_id` and RLS applies (ADR-0009). It re-reads the version and **fails on 0 rows**: a purged or foreign-workspace version is never processed.
- The pipeline is idempotent. New parents, children and embeddings are written while the version is not yet active, a health check runs on that inactive version, and a small **flip transaction** then makes it `ready` (or `ready_degraded`), marks the previous version `superseded`, moves `sources.current_version_id` forward only (guarded), bumps `workspace_corpus_state.version` and writes an audit event.
- Version allocation is serialized under `SELECT … FROM sources WHERE id=$1 FOR UPDATE`, and a partial unique index on `(source_id, content_hash, parser_version, structure_version)` `WHERE status NOT IN ('failed','superseded','purged')` (i.e. queued, in-progress and ready versions) blocks duplicate concurrent uploads.

**Failure handling.**
- Parse or validation failure → `status=failed` with a UI-visible `error_code`.
- Embedding failure → `ready_degraded` (lexical-only) and a scheduled re-embed job; its completion bumps the corpus version.
- Stalled jobs → a periodic reaper retries up to 2 times (attempts tracked on `source_versions`), then marks the version `failed`.
- The worker runs with an explicit memory limit (compose `mem_limit`, platform instance size).

**Other job types.** Re-embed, purge (one transaction deleting chunks, embeddings, dataset rows and the blob, and bumping the corpus version), the stalled-job reaper, nightly retention deletion of `run_events` / `tool_runs` / `retrieval_traces` older than 30 days, and the nightly Sandbox reset.

**Roles.** Procrastinate's schema is created by `ms_owner`. Its tables hold no tenant data and have no RLS; `ms_app` gets grants only.

## Alternatives considered

- **Celery (Redis or RabbitMQ broker).** Mature, but needs a broker and reintroduces the dual write: a job enqueued to the broker is not part of the Postgres transaction. Making Redis required for correctness also contradicts the design rule that Redis is optional.
- **RQ.** Redis-backed; same dual-write and Redis-dependency problem.
- **Taskiq.** Async-native, but broker-based; same transactional gap.
- **Arq.** Redis-based and maintenance-only.
- **Hand-rolled outbox table + poller.** Achieves transactional enqueue, but we would reimplement locking, retries, scheduling and LISTEN/NOTIFY wakeups that Procrastinate already provides.
- **asyncpg as the app driver.** Faster, but Procrastinate would still use psycopg, so the app would run two drivers and the job could not be deferred on the same connection as the application's writes.

## Tradeoffs accepted

- Queue load lands on the primary database. Negligible at demo scale, where uploads are occasional.
- Throughput ceiling is lower than a dedicated broker; acceptable because ingestion is low-volume and latency-tolerant.
- psycopg 3 is slightly slower than asyncpg.
- Blobs in `bytea` inflate the database; the documented switch to S3-compatible storage behind `BlobStore` applies at scale.

## Consequences

**Positive**
- Upload and job are atomic: either both exist or neither does.
- One fewer service to deploy, secure and pay for; Redis stays optional.
- Jobs run under the same RLS as the API, with scope re-established from job arguments.
- Job state, versions and blobs can be inspected with SQL in one place.

**Negative**
- Long-running jobs hold a worker slot and, during the flip, a short transaction on the primary.
- Procrastinate's API is a dependency we pin and must track across major versions.

**Follow-ups**
- Record measured seed time and ingestion throughput (Phase 1 exit criterion) and queue latency from job enqueue to `parsing`.
- At scale (§34): autoscale workers on queue depth; move blobs to S3.

**Verification**
- Integration: a transactional-enqueue rollback leaves no job and no version rows.
- Integration: upload → ready → retrieve → resolve, seeded through the real upload API.
- Integration: revert, retry-after-fail and concurrent identical uploads produce one version and no duplicate work.
- Integration: delete → purge contract (canary string gone everywhere, handle returns 410, blob gone).
- Isolation: the worker cannot read another workspace's children; a job for a missing or foreign version fails on 0 rows.
- Degradation: `EMBEDDER_UNAVAILABLE` → `ready_degraded` plus a scheduled re-embed job has a named test.
