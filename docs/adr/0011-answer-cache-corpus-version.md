# ADR-0011: Answer cache keyed on workspace corpus_version with conditional writes

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 8 (this ADR is updated with measurements when the component is built)
- **Related:** plan §0.1, §2, §3 (steps 3 and 9), §6 (`workspace_corpus_state`, `query_runs`), §11, §22, §28, §29, §32.2, §33; ADR-0001 (Postgres as system of record), ADR-0004 (evidence handles), ADR-0009 (workspace isolation), ADR-0012 (embedding caches), ADR-0016 (purge contract); no approved deviation

## Context

A research run costs one or more LLM calls and seconds of latency (standard p50 target < 15 s). Repeated questions are common in a demo and in evaluation, and the latency budget sets a target of < 1 s for a cached answer. The plan lists the answer cache among its cost controls (§33).

A cached answer is a grounded artifact: it contains canonical evidence handles and citation cards. It becomes wrong when the corpus it was built from changes. The corpus changes when an ingest becomes ready, a re-embed completes, a source is deleted or purged, or a source is reclassified. The purge contract (ADR-0016) requires that deleted content can no longer be served, and that includes serving it from the answer cache. Entries made unreachable by a version bump expire within the 24 h TTL (plan §4.3, ADR-0016).

Two more constraints apply:
- Redis is hosted as a separate managed service (Render Key Value in production) and can fail on its own. The system must still be correct without it.
- An agentic run reads the corpus across several tool calls. An ingest can flip a source version in the middle of a run.

## Decision

1. **Per-workspace corpus version.** `workspace_corpus_state(workspace_id pk, version bigint)` is its own row, so bumping it does not contend with workspace metadata locks. It is incremented inside the same small flip transaction that changes active versions: ingest ready, re-embed completion, delete or purge, reclassification. A reader therefore sees the version and the active-version set change together.
2. **Cache key.** `sha256(workspace_id, corpus_version, normalized_query, persona, sorted filters, mode, retrieval_cfg_hash, prompt_version, model ids + efforts)`. Any change to corpus, config, prompts or models produces a different key.
3. **Value:** the final answer, citation cards, pack handles, corpus_version and a run summary.
4. **Implicit invalidation.** Nothing is deleted when the corpus changes. A version bump makes old keys unreachable, and a 24 h TTL reclaims them.
5. **Probe** (run step 3). The probe runs only for context-free turns. On a hit the handles are revalidated (they must resolve in the workspace), `final` and then `done` are streamed, and `cache_status` is recorded in `done` and `query_runs`. A hit whose handles fail revalidation is discarded and treated as a miss.
6. **Write rules** (run step 9). All three must hold:
   - only clean results are written: `completed`, with no degradation flags;
   - turns whose standalone query depended on conversation context are not written;
   - **the write is conditional:** at the end of the run, corpus_version is re-read and the answer is stored only if it still equals `query_runs.corpus_version_start`.
7. **Redis is optional for correctness.** On a connection error or an open circuit the cache is bypassed and `CACHE_UNAVAILABLE` is logged at most once per interval. `/readyz` reports Redis as degraded, not unready. Rate limiting falls back to an in-process limiter with *tighter* per-instance limits (§32.2).
8. The same version also keys the lexical DF/IDF statistics cache `(workspace, corpus_version)`, so lexical scoring and answer caching agree on what "the corpus" is.

**Why the conditional write is sufficient.** All of a run's reads happen before the end-of-run re-read. The version is monotonic and moves atomically with the active-version set. If the re-read equals the start version, every read in the run saw that version, so the answer is consistent with its key. If a bump lands after the re-read but before the Redis `SET`, the entry is stored under the old version's key, which no new probe can reach. No lock or Redis transaction is needed.

## Alternatives considered

- **Explicit invalidation** (delete keys by workspace prefix on every corpus change). Needs a key index or `SCAN`, and has a window in which a run that started before the delete can write a stale entry back. That reintroduces the race the version key removes, and the delete fails exactly when Redis is unhealthy.
- **Semantic (embedding-similarity) answer cache.** Raises the hit rate on paraphrases. Not chosen because near-paraphrases can need different evidence ("Gen Z" vs "Gen Z in footwear"). A false hit is a grounding failure presented with citations, which is worse than a miss.
- **Cache retrieval results instead of answers.** Saves less: synthesis is the dominant cost and latency. Retrieval is already deterministic and fast at demo scale.
- **In-process LRU only.** No extra service, but not shared across api replicas (§34) and lost on every deploy.
- **Cache table in Postgres.** Keeps one store (ADR-0001), but puts cache churn on the primary. Redis is already present for rate limits and query-embedding caching.
- **No answer cache.** Simplest. Gives up the < 1 s cached path and the cost saving on repeated demo questions.

## Tradeoffs accepted

- **Coarse invalidation.** Any corpus change invalidates the whole workspace's cache. Ingests are rare relative to queries at this scale, and per-workspace scoping means Sandbox uploads never invalidate Northstar answers.
- **Exact-match keys only.** Normalization is lexical, so paraphrases miss.
- **Orphaned entries** occupy Redis memory until their TTL expires.
- **Context-dependent follow-ups are never cached.** Correctness wins over hit rate.
- Degraded runs are not cached, so a recovering dependency does not leave degraded answers behind.

## Consequences

**Positive**
- Stale answers cannot be served after a corpus change. This needs no invalidation code path that could fail.
- Deleted or purged content cannot reappear through the cache, because its version is unreachable.
- Redis failure changes cost and latency, never correctness.

**Negative**
- Every corpus-changing code path must bump the version inside its flip transaction. A missed bump would serve stale answers.
- Key composition must include every input that changes an answer. A missing component (for example, a new retrieval knob outside `retrieval_cfg_hash`) would cause false hits.

**Follow-ups**
- Document the key components next to `config_hash` (§26) so a new config field cannot be added without being considered for the key.
- Record cache hit ratio and cached-path latency in the Phase 8 report.

**Verification**
- Unit: "cache keys and conditional cache writes" (§29). A version bump between start and end of a run must skip the write. Each key component must change the key.
- Integration: "Redis down" must bypass the cache, emit `CACHE_UNAVAILABLE` once, and still complete the run.
- Integration: after delete, a repeated question misses the cache (the `corpus_version` bump makes the old key unreachable) and no served answer contains the canary string.
- Every code path that bumps the version (ingest ready, re-embed, delete/purge, reclassify) has a test asserting the bump.
- Metrics: Prometheus cache hit ratio; cached-answer latency against the < 1 s target from `query_runs.timings`.
