# ADR-0016: Source versioning semantics and purge contract

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 1 (this ADR is updated with measurements when the component is built)
- **Related:** plan §4.2, §4.3, §16 (also §6, §10, §22, §23, §29); ADR-0001, ADR-0003, ADR-0004, ADR-0009, ADR-0010, ADR-0011; approved deviation D1 (context only)

## Context

Every answer cites evidence through an immutable handle `WORKSPACE/SOURCE@vVERSION:LOCATOR` that resolves to one parent (structural) unit (ADR-0003, ADR-0004). Two requirements conflict:

1. **Citation stability.** A handle must never re-point to different text. Stored answers, hypothesis links, gold labels and briefs depend on that.
2. **Deletion.** A user who deletes a source expects its content to be gone, including from citations that were already stored.

Re-uploads are common too: the same file uploaded twice, a corrected file, a reverted file, a retry after a parse failure, two identical uploads racing. Each needs a defined result. A new parser or structure version must also not silently change the parents behind existing handles.

## Decision

**Versioning (§4.2).**
- *Target source.* An upload with an existing `source_code` becomes a new version of that source. Otherwise a new source is created, with its code taken from a filename slug plus a suffix on collision. An upload without `source_code` whose bytes match an active version of a *different* source returns that version with `duplicate_of`, and no work is done.
- *Idempotency.* Bytes identical to the target's current or in-flight version return `200` with the existing version. Bytes identical to a superseded, failed or purged version mint a **new** vN, so revert and retry-after-fix both work. Embedding reuse (keyed on model and text hash) keeps that cheap.
- *Allocation.* The version number is assigned under `SELECT … FROM sources WHERE id=$1 FOR UPDATE`. A partial unique index on `(source_id, content_hash, parser_version, structure_version) WHERE status NOT IN ('failed','superseded','purged')` blocks concurrent duplicates at the database.
- *Immutability.* Parents are immutable once a version is `ready`. A reindex may rebuild only children, embeddings and `tsv` (`chunking_policy_version` or `embedding_model` changes). A `parser_version` or `structure_version` change mints a new version over the same bytes (`reason=reindex`), and the old version stays resolvable.
- *Guarded flip.* `sources.current_version_id` only moves forward. A slow v2 that finishes after v3 is marked `superseded`.
- The upload transaction writes the source, the `source_versions` row (`queued`), the blob and the job together (ADR-0010), so there is no dual-write window.

**Purge (§4.3): privacy wins over immutability.**
- `sources` and `source_versions` rows are never hard-deleted. A purge sets `deleted_at` and `status=purged` and nulls `content_hash`, `original_filename` and `error_detail`. `source_code`, `title` and `version` remain so a tombstone can be shown.
- In **one transaction** the purge job:
  - deletes `parent_chunks`, `child_chunks`, `chunk_embeddings`, `dataset_tables`, `dataset_rows` and the blob. These tables reference `source_versions` with `ON DELETE RESTRICT`, so nothing is removed by an implicit cascade;
  - nulls `analytic_results.result/row_refs` and `hypothesis_evidence.quote`;
  - strips excerpt text from stored citation cards that point at the purged handles;
  - bumps `workspace_corpus_state.version` and writes an `audit_event`.
- The corpus-version bump makes affected answer-cache keys unreachable (ADR-0011). Those entries expire within the 24 h TTL.
- Answer prose is kept as a derived artifact, and the README says so. WAL, dead tuples and evaluation outputs are documented limitations.

**Resolution order (§16).** `EvidenceResolver.resolve` does the following, in this order:
1. Parse the handle against the grammar (`MALFORMED` on failure).
2. Check the workspace code against the scope (`NOT_FOUND` on mismatch, which reveals nothing).
3. Look up `source_versions`. If the version is purged, return `410 SOURCE_DELETED` with metadata.
4. Only then look up `parent_chunks`, or `analytic_results` for `AQ` handles.

A tombstone is an explicit, resolved state, not a fake citation. The acceptance criterion "100% of rendered citations resolve" counts a tombstone as resolved-deleted, and the UI renders it as "source deleted". Hypothesis links to superseded or purged versions are flagged (§37.2).

## Alternatives considered

- **Mutable sources (overwrite parents in place on re-upload).** This is simpler, but handles would re-point to new text, so stored citations, gold labels and hypothesis links could silently become wrong. Rejected because it breaks the core trust property.
- **Content-addressed handles (a hash in the handle).** These are stable by construction, but they are unreadable to a consultant and cannot express "v2 of the same document". The grammar keeps a human-meaningful version plus a stored `parent_content_hash` for drift detection.
- **Hard-delete the source and version rows.** Stored citations would then return `NOT_FOUND`, which looks the same as a fabricated or foreign handle. A tombstone separates "deleted by the user" from "never existed".
- **Soft delete that keeps content (hide it from retrieval only).** This fails the user's privacy expectation, and the text would remain reachable through the resolver, briefs and stored cards.
- **Cascading foreign keys (`ON DELETE CASCADE`).** Less code, but deletion of evidence would become implicit and easy to trigger by accident. `RESTRICT` plus one explicit purge transaction makes every removal deliberate and auditable.
- **Rewrite stored answer prose on purge.** Rewriting generated text cannot be made faithful automatically. It is kept as a derived artifact and the limitation is documented instead.

## Tradeoffs accepted

- Old versions accumulate storage until they are purged. Immutability is paid for in rows and embeddings.
- The purge does not make the cluster forensically clean. WAL, dead tuples (until vacuum) and evaluation outputs can still hold text, and that is documented rather than solved.
- Answer prose that paraphrases purged evidence survives. Citations inside it render as tombstones.
- Up to 24 h of unreachable cache entries can remain in Redis. They cannot be served, because the key includes the bumped corpus version.
- Version allocation takes a row lock on the source, which serializes uploads to one source. That is acceptable at upload rates.

## Consequences

**Positive**
- A handle is a permanent identifier. Chunk tuning never invalidates citations or gold labels, and parser changes are visible as new versions.
- Re-upload behaviour is fully specified, idempotent and race-safe in the database, not only in application code.
- Deletion is one auditable transaction with a single, well-defined user-visible outcome (`410` plus tombstone).

**Negative**
- More states to test: `ready_degraded`, `superseded`, `purged`, and stale-version flags on hypotheses.
- Purge must stay in step with the schema. Any new table that copies evidence text must be added to the purge transaction.

**Follow-ups**
- Add a schema-review checklist item: every new column that holds document-derived text names its purge behaviour.
- Confirm which `run_events` payloads carry excerpt text. They fall under the 30-day retention job; if that is not acceptable, add them to the purge transaction.
- Decide whether the ingest embedding file cache and the query-embedding cache (vectors keyed by text hash, no text) are evicted on purge, and document the decision.
- Confirm that the worker's flip transaction refuses to activate a version whose source was purged while it was in flight, and add a test for it.

**Verification**
- Integration: *delete → purge contract*. A canary string is gone from every table, the handle returns `410`, and the blob is gone.
- Integration: *revert*, *retry-after-fail* and *concurrent identical uploads* produce the specified versions and no duplicate.
- Integration: the *transactional-enqueue rollback* leaves no job.
- Unit: *resolver ordering, including tombstones*. A purged version returns `SOURCE_DELETED` before any parent lookup.
- Eval gate: citation validity stays at 100%, with tombstones counted as resolved-deleted.
- In demo mode, `demo_read_only` workspaces return `POLICY_DENIED` for delete.
