# Ingestion and the evidence model

How a file becomes citable evidence in MarketSignal, as implemented in Phase 1. The design decisions are in [ADR-0003](adr/0003-parent-child-chunks-parent-citation-unit.md) (parents and children), [ADR-0004](adr/0004-evidence-handle-grammar-and-alias-citations.md) (handles), [ADR-0009](adr/0009-workspace-isolation.md) (isolation), [ADR-0010](adr/0010-postgres-native-job-queue.md) (job queue), [ADR-0012](adr/0012-local-embeddings-provider-interface.md) (embeddings) and [ADR-0016](adr/0016-source-versioning-and-purge.md) (versioning and purge). This document describes the code as it is; where the code departs from an ADR, the ADR says so in its *Implementation notes*.

## The path in one picture

```
POST /api/workspaces/{ws}/sources  (multipart: file, source_class, [source_code, title, confidentiality])
  │  validate: size, extension ↔ magic bytes, OOXML container limits, encryption, UTF-8
  │  register: lock source row → idempotency / duplicate / new version → blob + audit
  │  defer Procrastinate job ON THE SAME CONNECTION, then COMMIT   (one transaction)
  ▼  202 {source_id, version, status: queued}   |  200 {created: false} for an idempotent re-upload
worker (queue "ingestion")
  claim (queued → parsing) → parse in a thread with a timeout → parents
  → handles → children (token windows / row units / table summaries) → embed
  → INSERT parents, children, embeddings, dataset tables/rows   (version not yet active)
  → health check on the inactive version
  → flip: lock source, supersede previous, activate, bump corpus version, audit
  ▼  ready | ready_degraded | failed | superseded | purged
GET /api/workspaces/{ws}/evidence/{handle}?child_id=  → exact parent text, locator, provenance, highlight
```

Each status change is committed, so the Sources page shows progress while a job runs.

## Upload validation (`ingestion/validation.py`)

| Check | Rejection |
|---|---|
| Body larger than `upload_max_bytes` (25 MB) | 413 `FILE_TOO_LARGE` |
| Extension not one of `pdf docx pptx xlsx csv md txt` | 415 `UNSUPPORTED_TYPE` |
| Magic bytes disagree with the extension (PDF `%PDF-`, OOXML ZIP, CFB) | 415 `UNSUPPORTED_TYPE` |
| CFB container (`D0 CF 11 E0`), meaning a password-protected OOXML or legacy Office file; PDF with `/Encrypt` | 422 `ENCRYPTED_DOCUMENT` |
| OOXML ZIP: more than `zip_max_entries` (2,000) entries, more than `zip_max_uncompressed_bytes` (200 MB) declared, or any member compressed more than `zip_max_compression_ratio` (100×) | 413 `CONTENT_TOO_LARGE` |
| OOXML ZIP whose `[Content_Types].xml` is missing or does not declare the main part for its type; macro-enabled packages | 415 `UNSUPPORTED_TYPE` |
| Corrupt or truncated OOXML package | 422 `PARSE_FAILED` |
| Text formats containing NUL | 415 `UNSUPPORTED_TYPE` |
| Text formats that are not UTF-8 (a BOM is accepted) | 422 `PARSE_FAILED` |
| Existing source code with a different type | 409 `SOURCE_TYPE_MISMATCH` |

A rejected upload persists nothing: no source, version, blob or job. Filenames are sanitised before they are stored. XML parsing goes through `defusedxml`.

## Registration and versioning (`ingestion/uploads.py`, ADR-0016)

- **Source identity.** If `source_code` is given and exists, the upload is a new version of that source. If it is given and unknown, a new source is created with that code. If it is absent, a code is derived from the filename and suffixed on collision.
- **Version allocation.** The next version number is allocated while holding `SELECT … FOR UPDATE` on the source row.
- **Idempotency.**
  - Bytes identical to the source's live version (current or in flight) are a no-op: the response is `200 {created: false}` with the existing version.
  - Bytes identical to a superseded, failed or purged version create a new version. This covers revert, retry-after-fix and re-adding after a delete.
  - A partial unique index, `source_versions_live_content`, enforces this in the database, so concurrent identical uploads cannot create two live versions.
- **Duplicates across sources.** An upload without a `source_code` whose bytes match a live version of another source returns that version, with `duplicate_of`.
- **Transactional hand-off.** The source row, version row, blob, audit event and the Procrastinate job are written in one transaction. The job is deferred on the upload's own psycopg connection (`task.configure(connection=…)`).
  - A failure after deferral rolls back everything, including the job.
  - The test suite covers this: `test_failed_job_handoff_rolls_back_the_upload`.
- **Retry.** `POST /sources/{id}/retry` re-queues the latest version only if it is `failed`; otherwise it returns 409 `NOT_RETRYABLE`.
- **Delete.** `DELETE /sources/{id}` purges synchronously (see *Purge*).

## Parsing (`ingestion/parsers/`)

Every parser returns `ParsedSource`: ordered `ParentDraft`s, optional `DatasetTable`s, and warnings. Parsing runs in a worker thread under `parse_timeout_s` (120 s), with page, slide and row caps.

| Format | Library | Parent unit | Locator |
|---|---|---|---|
| PDF | pdfplumber (pdfminer.six) | Paragraph group within one page; headings from font size (≥ body + 2 pt); lines ≤ body − 2 pt treated as running headers/footers and dropped | `P{page}.B{n}` |
| DOCX | python-docx | Heading section, block groups; interview `Q:`/`A:` pairs kept together | `S{section}.B{n}`, `S{section}.Q{n}` (`.B{n}` if an answer is split) |
| PPTX | python-pptx | One slide (title, body, tables); speaker notes as a separate parent | `SL{n}`, `SL{n}.N1` |
| XLSX | openpyxl (read-only, values) | One row; one table-summary parent per sheet | `SH{sheet}.R{row}`, `SH{sheet}.T1` |
| CSV | csv (UTF-8, BOM accepted) | One row; one table-summary parent | `R{row}`, `T1` |
| MD / TXT | — | Heading section (or blank-line block group) | `S{section}.B{n}` |

Pages with fewer than `pdf_min_words_per_page` words raise a `PARTIAL_EXTRACTION` warning; scanned PDFs are not OCR'd in Phase 1.

### Structure normalisation (`ingestion/structure.py`)

Blocks are grouped into parents of at most `parent_max_tokens` (800). The count is taken on the *rendered* text, including `- ` list markers.

- An oversize unit is split at sentence boundaries, then by tokens.
- Lists stay whole in one parent when they fit. Larger lists are split and the pieces share a `list_group_id`.
- Parents never cross a page, slide, row or Q&A boundary.

### Tabular rows (`parsers/tabular.py`, chunking policy `c2`)

Each column is profiled and given a role.

| Role | Rule |
|---|---|
| `identifier` | Unique, whitespace-free and ≤ 64 characters. Checked first, so a long record id is never free text. |
| `free_text` | Mean length > 20 characters and at least 50% multi-word values |
| `context` | Low-cardinality text, such as segment or region |
| `constant` | A single value in every row, such as a data notice |
| `numeric`, `date` | Typed values |

- **Row parent text** is `col: value; col: value; …`, rendered from the **original cell text**, so `007` stays `007`.
- **Row child text** (policy `c3`, Phase 2): `{table} | {identifier=…, context=…} | {free-text col}: <verbatim>`. Identifier columns (review or respondent ids, record ids) are included so lookups by id match lexically; the span still covers only the verbatim cell. `row_child_identifiers=false` with `chunking_policy_version=c2` reproduces the previous policy.
- **Retrieval units.** A row is a retrieval unit only if it has a free-text cell. Its child's span covers exactly the verbatim cell inside the parent. Purely numeric rows are resolvable parents with no child (ADR-0003).
- **Table summaries.** Each table gets one summary parent and one summary child, listing columns, roles and the top values of up to `table_summary_max_levels` (12) levels.
- **Analytics data.** `dataset_tables` and `dataset_rows` keep typed values and the row handle for the Phase 5 analytics tool.

## Evidence handles (`evidence/handles.py`, ADR-0004)

```
NORTHSTAR/SURVEY-2026@v1:R148
└─ws────┘ └─source──┘ └v┘ └locator┘          alphabet [A-Z0-9v/@:.-], max 96 chars
```

- Locator units are `SL SH P B S N R Q T`. A computed handle uses `AQ` + 12 hex characters (Phase 5).
- `parse_handle` is strict: it rejects lowercase, leading zeros, unknown units and over-length input.
- `parse_rendered_handle` accepts the bracketed display form.
- The workspace prefix is checked against the route's workspace (`require_workspace`). A mismatch is reported as **404**, never 403, so no handle reveals another workspace's existence.

## Parents and children (`ingestion/chunking.py`, D1)

- **The parent is the citation unit.** Its `text` is authoritative and immutable for the version. `content_hash` is stored with it.
- **Children are internal retrieval windows.** Narrative children are 192-token windows with 32-token overlap, cut on the embedder's own WordPiece offsets (`HuggingFaceTokenizer`) and never crossing the parent.
- **Spans.** Every child stores `char_start`/`char_end` into its parent. For a window, `parent.text[char_start:char_end] == child.text` exactly. For a row child, the span is the verbatim free-text cell, which the child text contains after its table/context header. `check_child_contract` enforces this before anything is written, and the health check verifies it again in the database.
- **Kinds.** Child kinds are `window`, `row` and `summary`.
- **Dense input.** The embedder input is `"{title} › {heading path}\n{child text}"`. Lexical indexing uses generated `tsvector` columns, with the heading weighted A and the body weighted D.

## Embeddings (`providers/embeddings.py`, ADR-0012)

- **Model.** `FastEmbedEmbedder` runs `BAAI/bge-small-en-v1.5` through ONNX on CPU (384-d, L2-normalised). It is loaded lazily, and its tokenizer is reused for chunking.
- **Cache.** `CachedEmbedder` stores vectors in an SQLite file per model under `.cache/embeddings`, keyed by `sha256(model_id, input)`. Re-ingesting unchanged text costs nothing.
- **Storage.** Vectors live in `chunk_embeddings (workspace_id, child_id, model_id)` as an untyped `vector`, with a dimension check per model and a **partial expression HNSW index** per model (`m=16, ef_construction=64`). A second model can therefore be added without a schema change.
- **Embedder outage.** If the model cannot load or fails, the version is still indexed lexically and finishes as `ready_degraded` with the warning `EMBEDDER_UNAVAILABLE`.

## Health check and activation (`ingestion/health.py`, `pipeline.py`)

Before a version becomes current, a sample of `health_sample_size` children is checked on the *inactive* version:

1. **Lexical membership.** The child's `tsv_body` matches `plainto_tsquery` over its own leading words.
2. **Dense self-retrieval.** The child's own vector returns it in the top `health_dense_top_k` (5), tolerating exact-duplicate texts.
3. **Span contract.** The parent substring equals the child text.

If any check fails, the version is `failed` with `HEALTH_CHECK_FAILED` and its content is deleted. Otherwise the **flip** runs in one short transaction:

- lock the source row;
- if a newer version is already current, mark this one `superseded`;
- otherwise supersede the previous version, set `current_version_id`, mark this version `ready` or `ready_degraded`, bump `workspace_corpus_state.version` (the answer-cache key, ADR-0011), and write an audit event.

A superseded version's handles keep resolving, flagged `is_latest: false` with `latest_version`.

## Purge (`ingestion/purge.py`, ADR-0016)

Deleting a source runs one transaction, synchronously:

- lock the source;
- delete every version's parents, children, embeddings, dataset tables and rows, and blob;
- mark the versions `purged`, with `content_hash` and `original_filename` nulled;
- set `sources.deleted_at`;
- bump the corpus version and write an audit event.

The source keeps its code, title and version numbers, so its handles resolve to **410 `SOURCE_DELETED`** with a tombstone and no content.

**A purge always beats an in-flight job.** Every worker write first share-locks the source row (`FOR SHARE`), which serialises with the purge's `FOR UPDATE`. Either the worker's write commits first and the purge deletes it, or the worker sees `deleted_at` and stops without writing. The failure path and the flip follow the same rule, so a purged version is never activated, marked `failed` or given content again. Tests cover a purge before the job, during embedding, during the health check and before the flip, plus a canary sweep of every content table.

Re-uploading to a deleted source restores the source and allocates the next version number.

## Evidence resolution (`evidence/resolver.py`)

`GET /api/workspaces/{ws}/evidence/{handle}?child_id=` responds as follows.

| Case | Response |
|---|---|
| Malformed handle | 400 `MALFORMED_HANDLE` |
| Unknown version or locator, or another workspace's handle | 404 `EVIDENCE_NOT_FOUND` |
| Purged source | 410 `SOURCE_DELETED` + tombstone (source code, title, version, `deleted_at`) |
| Found | 200 (fields below) |

A 200 response contains:

- **Content:** exact parent `text`, `content_hash`, `locator`, `locator_label` (for example `Sheet 'Returns', Row 12`) and `heading_path`.
- **Source:** source metadata, `version_status`, `is_latest` and `latest_version`.
- **Provenance:** source and parent content SHA-256, parser, structure and chunking versions, and embedding model. The source block also carries the original filename, MIME type and `ingested_at`.
- **Context:** the tail of the previous parent and the head of the next, each up to 280 characters.
- **Spans:** every child span.
- **Highlight:** present when `child_id` names one of this parent's children, as `highlight` `{child_id, char_start, char_end, text}`. An unknown `child_id` is not an error; the response simply has no highlight.

Offsets count Unicode code points. The frontend slices by code point (`lib/highlight.ts`).

## Workspace isolation (ADR-0009)

The nine tenant tables have **ENABLE + FORCE** row-level security, with the policy `workspace_id = app.current_workspace()`. The tables are `sources`, `source_versions`, `source_blobs`, `parent_chunks`, `child_chunks`, `chunk_embeddings`, `dataset_tables`, `dataset_rows` and `audit_events`.

- **Scope.** `app.current_workspace()` raises `WORKSPACE_SCOPE_NOT_SET` if no scope is set. The scope is set per transaction (`set_config(…, true)`) by the session listener.
- **Foreign keys.** Cross-table references are composite `(workspace_id, id)`, so a row cannot point at another workspace's row even when written by a privileged role. Primary keys of id-keyed child tables are tenant-scoped, so a key collision cannot reveal another tenant's rows.
- **Roles.** The runtime role `ms_app` is `NOSUPERUSER NOBYPASSRLS`. `audit_events` is append-only for it (no UPDATE or DELETE).
- **Tests.** Integration tests run as `ms_app` against a dedicated `marketsignal_test` database, with explicit negative tests for every tenant table (`test_evidence_model_isolation.py`).

## Statuses and error codes

| Status | Meaning |
|---|---|
| `queued` | Version and blob stored; job enqueued |
| `parsing`, `chunking`, `embedding`, `indexing` | In flight |
| `ready` | Current version with lexical and dense retrieval |
| `ready_degraded` | Current version, lexical only (embedder unavailable) |
| `failed` | `error_code` + `error_detail`; content removed; retryable |
| `superseded` | Replaced by a newer version; handles still resolve |
| `purged` | Source deleted; handles return 410 |

Ingestion error codes are `UNSUPPORTED_TYPE`, `FILE_TOO_LARGE`, `CONTENT_TOO_LARGE`, `ENCRYPTED_DOCUMENT`, `EMPTY_DOCUMENT`, `MALFORMED_SPREADSHEET`, `PARSE_FAILED`, `PARSE_TIMEOUT`, `HEALTH_CHECK_FAILED`, `SOURCE_TYPE_MISMATCH` and `INGEST_EXTRACT_FAILED`, plus the warnings `EMBEDDER_UNAVAILABLE` and `PARTIAL_EXTRACTION`.

Every API error uses the envelope `{"error": {"code", "message", …}}`. This includes request-validation errors (422 `VALIDATION_ERROR` with `fields`) and unknown routes (404 `NOT_FOUND`).

## Pipeline versions

| Setting | Value | Changing it… |
|---|---|---|
| `parser_version` | `p1` | by design (ADR-0003): mints a new version over the same bytes; old handles stay resolvable |
| `structure_version` | `s1` | same as above: parents are defined by structure |
| `chunking_policy_version` | `c3` | by design: rebuilds children, embeddings and tsv only; parent handles and hashes are unchanged |
| `embed_model_id` | `bge-small-en-v1.5` | adds rows for the new model; the HNSW index is per model |

The versions are recorded on every version and returned in provenance. The reindex job that acts on a change is not built in Phase 1; it arrives with Phase 7 tuning.

`c1` → `c2` (Phase 1): identifier columns are never classified as free text. Under `c1`, long `record_id`s made every numeric channel row a retrieval unit.

`c2` → `c3` (Phase 2): row children carry the row's identifier columns (see *Tabular rows*); measured on dev, then approved.

## Configuration

Every tunable parameter is a `MS_*` setting in `config.py`: upload and ZIP limits, parse limits and timeout, pipeline versions, parent and child token sizes, table-summary levels, embedding model, batch, threads and caches, health sample size and top-k, `hnsw_ef_search`, and `dev_endpoints_enabled`, which is forced off in `prod`.

## Running it

```bash
make up            # Postgres (pgvector) + Redis
make migrate
make api           # FastAPI on :8000
make worker        # Procrastinate worker, queue "ingestion"
make seed          # uploads the Northstar/Southpeak corpus through the real API
uv --directory backend run python ../scripts/verify_phase1.py   # Phase 1 exit verification
```

`GET /api/workspaces/{ws}/dev/search?q=&mode=lexical|dense` is the Phase 1 smoke search, kept unchanged because it is the recorded Phase 2 baseline. Production search is `GET /api/workspaces/{ws}/search` (see `docs/RETRIEVAL_DEEP_DIVE.md`).
