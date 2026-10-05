# Phase 1 report: ingestion and the evidence model

| | |
|---|---|
| Completed | 2026-10-05 |
| Exit criterion | The seeded corpus goes through the real upload API, and every required format becomes resolvable evidence with lexical and dense retrieval, versioning, isolation and handle-failure safety, verified from a clean database. **Met.** |
| Verification | `scripts/verify_phase1.py` → **PASS**; machine-readable output in [`phase-1-verification.json`](phase-1-verification.json) |
| CI | Run 37362002404 on `b733d18`: safety ✅, backend ✅ (197 passed, 0 skipped), frontend ✅ (46 passed), container build ✅ |
| CI on the final commit (`208cc04`, docs only) | Run 37362833376. Attempts 1–4 (2026-10-05) were blocked by a GitHub Actions incident: hosted runners did not acquire jobs ("The job was not acquired by Runner of type hosted even after multiple attempts"), and githubstatus.com showed Actions as degraded. Attempts 3–4 already passed backend, safety and container build. **Attempt 5, after recovery: safety ✅, backend ✅, frontend ✅, container build ✅.** Recorded during Phase 2; Phase 1 history is unchanged. |
| How it works | [`docs/INGESTION.md`](../INGESTION.md); ADR implementation notes in 0001, 0003, 0004, 0009, 0010, 0012, 0013, 0016 and 0017 |

## Implemented

| Area | What | Commits |
|---|---|---|
| Dependencies | fastembed (ONNX), pdfplumber, python-docx, python-pptx, openpyxl, defusedxml and Procrastinate; reportlab and pyyaml for development only | `933c873` |
| Evidence handles | Grammar `WS/SOURCE@vN:LOCATOR`, strict parser, builder, workspace check; 51 unit tests including property-based tests | `4ade179`, `1a278ba` |
| Schema | Migration 0002: nine tenant tables with ENABLE + FORCE RLS, composite `(workspace_id, id)` foreign keys, tenant-scoped keys, a partial unique "live content" index, generated `tsvector`s, an untyped `vector` with a per-model partial HNSW index, append-only audit, Procrastinate schema | `38d4e95` |
| Ingestion core | Upload validation (magic bytes, OOXML zip-bomb limits, encryption, UTF-8); six parsers (PDF, DOCX, PPTX, XLSX, CSV, MD/TXT); structural normalisation; parent/child chunking with character spans | `a2ea261` |
| Pipeline and API | Upload API with versioning, idempotency and transactional job hand-off; Procrastinate worker; embed, index, health check and guarded flip; evidence resolver; sources, evidence and dev smoke-search routes | `7461d55` |
| Seed corpus | Deterministic world model and generator, 30 uploads in 7 formats, fact ledger (111 facts), byte-exact commit, scoped gitleaks allowlist | `855662f`, `f761133` |
| Seeding and verification | `scripts/seed.py` (real API) and `scripts/verify_phase1.py` (exit verification) | `2a5966d`, `7c1a092` |
| Test isolation | Dedicated `marketsignal_test` database with a guard test | `80d6a11`, `47198af` |
| Real-model test | ONNX bge-small and WordPiece spans end to end, plus paraphrase retrieval | `845f1fb` |
| CI hygiene | Every action pinned to a SHA, ONNX model cache, Dependabot (minor and patch only), ruff in the pre-commit hook | `17c22f9`, `7623d64`, `6b0fba9` |
| Fixes found during verification | Identifier columns never free text (policy `c2`); error envelope for 422/404/405; a purge during ingestion always wins | `305b457`, `ab19b4d`, `b733d18` |
| Frontend | Workspaces, dashboard, sources (upload, status, retry, delete), evidence viewer with code-point-safe highlight, dev search; 46 vitest tests | `b8c52b2` |
| Documentation | INGESTION.md, ADR implementation notes, this report | (docs commit) |

## Exit verification, from a clean database

Procedure:

1. `make reset-db` (fresh volume) and an empty embedding cache.
2. `make migrate`.
3. Native API and worker, real ONNX model.
4. `make seed`.
5. `verify_phase1.py`.

| Required check | Result |
|---|---|
| Seeded corpus through the real upload API | 30 uploads (Northstar 24, Southpeak 6), **0 failures**, 61.0 s wall time for the seed script |
| Every required format processed | PDF 7, DOCX 4, PPTX 4, XLSX 4, CSV 4, Markdown 6, TXT 1 version(s): all `ready`, or `superseded` for GENZ-TRENDS v1 |
| Idempotent re-upload | Same bytes → **200**, `created: false`, the existing version returned; no new version, no job |
| Version update | `GENZ-TRENDS` v1 → v2: v1 `superseded`, v2 `ready`. Four superseded fact pairs resolve on **both** versions, with `is_latest` and `latest_version` set correctly |
| Cross-workspace isolation | 7 Southpeak canaries searched from Northstar: **0 leaks**. A Southpeak handle through the Northstar route → **404**. Rows visible to `ms_app` in the wrong scope: **0** |
| Planted facts from several formats, lexical and dense | See the table below |
| Handle → exact parent text and locator; child-anchor highlight | Every sampled fact resolves to the parent that contains its anchor. `text[char_start:char_end] == highlight.text` holds for every highlight |
| Malformed and foreign handles fail safely | malformed **400** `MALFORMED_HANDLE`; unknown locator **404**; unknown version **404**; foreign workspace prefix **404** (never 403, no existence leak) |
| Purged handle | Live check in a scratch workspace: **200** before delete → **410** `SOURCE_DELETED` with a tombstone after |
| Anchor census (basis for gold v0) | **111 / 111** ledger anchors located in exactly one parent; 0 missing, 0 ambiguous |

### Retrieval by format (Northstar, smoke search, top 5)

| Format | Fact | Anchor | Lexical rank | Dense rank | Resolved locator |
|---|---|---|---|---|---|
| PDF | NS-001 | sentence | 1 | 4 | Page 1, Block 2 |
| PDF | NS-002 | sentence | 1 | 2 | Page 1, Block 2 |
| DOCX | NS-050 | sentence | 1 | 2 | Section 1, Block 4 |
| DOCX | NS-051 | sentence | 1 | 1 | Section 1, Block 5 |
| PPTX | NS-080 | sentence | 1 | 2 | Slide 3 |
| PPTX | NS-081 | sentence (notes) | 1 | 1 | Slide 10, Notes 1 |
| Markdown | NS-100 | sentence | 1 | 1 | Section 1, Block 7 |
| Markdown | NS-101 | sentence | 1 | 1 | Section 1, Block 6 |
| TXT | NS-110 | sentence | 1 | 1 | Section 1, Block 1 |
| TXT | NS-111 | sentence | 1 | 1 | Section 1, Block 1 |
| CSV | NS-143 | free-text row (survey verbatim) | 1 | — | Row 148 (highlight = verbatim cell) |
| CSV | NS-144 | free-text row (survey verbatim) | 1 | 4 | Row 389 |
| CSV | NS-140 | numeric row | n/a by design | n/a | Row 116 |
| XLSX | NS-120 | numeric row | n/a by design | n/a | Sheet 'SKU_Performance', Row 2 |

- **Numeric rows** are resolvable parents but not retrieval units (ADR-0003). They are answered by the Phase 5 analytics tool, so "n/a" is the expected result.
- **No XLSX free-text fact in the ledger.** Every XLSX fact in the ledger is numeric, so XLSX *retrieval* was shown by the format integration test rather than by a ledger fact.
- **Dense misses on survey verbatims.** NS-143 is not in the dense top 5 when queried with its paraphrased statement. The survey holds hundreds of near-identical sizing complaints, a known weakness of single-vector search over many near-duplicates. Hybrid fusion in Phase 2 is designed to cover it, and gold v0 will measure it.
- **Not tuned.** These are untuned single-lane smoke searches, not the Phase 2 pipeline.

## Measurements

Apple M2 laptop; the ONNX model runs on CPU with a cold embedding cache.

**Corpus and chunks**

| Workspace | Uploads | Bytes | Parents | Children | Embeddings | Ingest time (sum) | Embed time | Embed throughput |
|---|---|---|---|---|---|---|---|---|
| NORTHSTAR | 24 | 808,785 | 2,220 | 1,834 | 1,834 | 48.6 s | 42.9 s | 42.8 children/s |
| SOUTHPEAK | 6 | 185,472 | 460 | 396 | 396 | 10.9 s | 9.8 s | 40.4 children/s |
| **Total** | **30** | **994,257** | **2,680** | **2,230** | **2,230** | **59.5 s** | **52.7 s (88%)** | — |

The median ingest time per source is 0.77 s (Northstar) and 0.83 s (Southpeak). Parsing totals 1.9 s.

**By format** (both workspaces; one row per version)

| Format | Versions | Bytes | Parents | Children | Ingest time |
|---|---|---|---|---|---|
| CSV | 4 | 435,475 | 1,824 | 1,704 | 38.4 s |
| PDF | 7 | 84,747 | 120 | 147 | 8.4 s |
| DOCX | 4 | 166,133 | 141 | 150 | 5.5 s |
| PPTX | 4 | 226,196 | 89 | 89 | 2.4 s |
| Markdown | 6 | 29,639 | 63 | 64 | 2.3 s |
| XLSX | 4 | 45,899 | 441 | 67 | 2.1 s |
| TXT | 1 | 6,168 | 2 | 9 | 0.4 s |

- **Survey and review CSVs dominate.** Each verbatim row is a retrieval unit, giving 76% of children and 65% of ingest time.
- **XLSX** has 441 parents but only 67 children: numeric rows have no child, by design (policy `c2`).

**Retrieval smoke latency** (`/dev/search`, Northstar, k=10, warm model, 30 ledger statements, end to end over HTTP)

| Mode | p50 | p95 | max |
|---|---|---|---|
| Lexical (`websearch_to_tsquery` + `ts_rank_cd`) | 5.3 ms | 6.6 ms | 17.8 ms |
| Dense (query embedding + HNSW, `ef_search=100`, iterative scan) | 15.0 ms | 22.3 ms | 34.2 ms |

## Tests

| Suite | Count | Where |
|---|---|---|
| Backend, CI (`b733d18`) | **197 passed, 0 skipped** | unit, integration as `ms_app` against `marketsignal_test`, real-model test, superuser non-vacuity test, MCP spike |
| Backend, local | 196 passed, 1 skipped (the superuser test needs `MS_TEST_SUPERUSER_DATABASE_URL`, which CI sets) | |
| Frontend (vitest) | **46 passed** (6 files) | error parsing, handle URLs, highlight segmentation, status, forms |
| Static checks | ruff format and lint, strict mypy (48 source files, 0 issues), ESLint, `tsc`, `next build`, gitleaks, repo guard | local and CI |

The main Phase 1 suites:

- handle grammar: 51 tests;
- evidence-model isolation: 31 tests, all as `ms_app`, with negative cross-workspace tests for every tenant table;
- ingestion API end to end: 23 tests, covering every format, idempotency and duplicates, versioning, the resolver error contract, upload rejections persisting nothing, type mismatch, embedder outage, parse failure and retry, transactional hand-off rollback, the purge canary sweep, and purge before and during ingestion;
- parser, chunking, validation and embedding unit tests.

## Failures encountered and how they were fixed

| # | Failure | Found by | Fix |
|---|---|---|---|
| 1 | The global primary key on `source_blobs` was a cross-tenant existence oracle: a uniqueness error instead of an FK error | Isolation tests | Tenant-scoped primary keys on id-keyed tables (ADR-0009) |
| 2 | Migration downgrade left Procrastinate functions behind | Manual downgrade → upgrade cycle (there is no automated round-trip test yet) | The downgrade drops all `procrastinate_*` functions |
| 3 | The handle alphabet in the docs omitted the lowercase `v` | Implementing the grammar | Plan, ADR-0004 and docstring corrected |
| 4 | Property tests built over-length handles, hiding failures | Hypothesis | Guard on raw length before constructing |
| 5 | List markers were not counted toward the 800-token parent cap | Chunking tests | Tokens counted on the rendered text |
| 6 | CSV row text was rendered from coerced values (`007` → `7`) | Parser tests | Render the original cell text |
| 7 | A constant `data_notice` column was classified as free text | Seed census | New `constant` column role |
| 8 | `:x::jsonb` is not a bind parameter in SQLAlchemy `text()`, so timings and health were silently not persisted | Verification statistics were empty | `CAST(:x AS jsonb)` |
| 9 | **Test-isolation commit `80d6a11` did not isolate.** The URL helper never rewrote the URLs, so tests ran against the development database | The native dev worker picked up a test job | Fixed in `47198af`, with a guard test; orphan dev job rows removed |
| 10 | CI lint failure (two long lines); the first pre-commit hook used `mapfile`, which bash 3.2 lacks | CI; macOS bash | Lines wrapped; ruff runs in the hook; while-read loop instead |
| 11 | Dependabot npm job failed on major-version bumps | Dependabot run | Majors ignored for npm and uv (reviewed by hand) |
| 12 | gitleaks false positives on fact-ledger `key_value` fields | gitleaks | Allowlist that matches only when both conditions hold, scoped to that file |
| 13 | CSV line endings would have been normalised by git | Byte-exact seed check | `seed_data/generated/** -text` |
| 14 | The verifier's census ignored the sheet name for row anchors | Census review | Fixed |
| 15 | **Long `record_id` identifiers were classified as free text**, so every numeric channel row became a retrieval unit | Reviewing child counts by format | Identifier role checked first; policy `c1` → `c2` (Northstar children 1,954 → 1,834) |
| 16 | Request-validation and routing errors bypassed the error envelope | Frontend integration | Handlers for `RequestValidationError` and HTTP errors |
| 17 | Verification sampled only numeric rows for CSV/XLSX, so tabular *retrieval* was not demonstrated | Self-review of verification coverage | Free-text row facts added (survey verbatims) |
| 18 | **The verifier's cleanup never committed**: a non-autocommit connection turned the `transaction()` blocks into savepoints, and a re-run found a stale scratch workspace | The tombstone check failed on a re-run (`404 → 410`) | Autocommit; drop the scratch workspace before and after |
| 19 | **A purge during ingestion was not respected.** Later status updates overwrote `purged`, indexing could write content for a purged version, and the flip marked it `failed` | Writing the ADR-0016 verification tests | Every worker write share-locks the source (`FOR SHARE` vs the purge's `FOR UPDATE`). Four tests: three fail on the old code, all pass now |

## Decisions and deviations (none changes the approved models)

- **Row highlight.** A row child's span is the verbatim free-text cell. The row parent remains the citation unit. Cell-level metric highlighting arrives with the Phase 5 analytics tool.
- **`child_id` handling.** An unknown `child_id` returns 200 without a highlight, and no highlight is chosen by default.
- **Chunking policy `c2`.** Identifier columns are never free text. It replaced `c1` before any gold labels existed.
- **Embedding cache.** SQLite per model instead of Parquet (ADR-0012): incremental appends with no rewrite.
- **Retry** re-queues the same failed version; purge is synchronous; re-uploading to a deleted source restores it with the next version number (ADR-0016).
- **Phase 1 smoke search** uses `websearch_to_tsquery` + `ts_rank_cd`, dev-only and off in `prod`. It is not Phase 2 retrieval.
- **PDF parsing** uses pdfplumber only. There is no OCR; low-text pages get a `PARTIAL_EXTRACTION` warning.
- **`httpx2`** is left as a transitive dependency of `mcp==2.3.0`. Provenance was verified (`pydantic/httpx2`); application code uses `httpx`.

## Unresolved risks and deferred items

| Item | Risk | Plan |
|---|---|---|
| Stalled-job reaper | A worker killed mid-job leaves the version in an intermediate status; recovery is manual | Phase 8 hardening, before deployment (ADR-0010) |
| Re-embed job for `ready_degraded` | A degraded version stays lexical-only until it is re-uploaded | Phase 2, with the embedding work |
| BGE query instruction not applied | Dense ranking may be below its potential | Phase 2: configurable instruction, A/B on gold v0 |
| RLS × GIN/HNSW cost | Not yet measured under the real filtered queries | Phase 2: `EXPLAIN ANALYZE` on the canonical SQL |
| CPU embedding throughput (about 42 children/s) | Large uploads take minutes; Render's CPU will be slower | The cache makes re-ingestion free; measure in the Render spike; hosted-embedder switch exists by design |
| Survey near-duplicates | Dense single-vector search misses specific verbatims among hundreds of similar ones | Hybrid fusion and reranking in Phase 2, measured on gold v0 |
| Synchronous purge | Slow for very large sources | Move to a job with the same contract if measured purge time needs it |
| Dependabot ignores majors | Major upgrades need manual review | Deliberate; reviewed at phase boundaries |
| `httpx2` transitive dependency | A second HTTP client in the tree | Watch the MCP SDK; remove when upstream drops it |
| Live Anthropic check | Deferred from Phase 0 | Phase 3 |
| Render pgvector and role spike | Deferred from Phase 0 | Deployment phase |
| Reindex job (`parser`, `structure` or `chunking` version change) | A policy change needs re-upload today | Phase 7 tuning |

## Proposed Phase 2 plan: retrieval core and gold v0

Aligned with plan §38 (Phase 2 row) and ADRs 0002, 0005, 0012 and 0013. The order is chosen so that measurement exists before tuning.

1. **`freeze-gold` and gold v0.**
   - Turn census-located ledger facts into gold items (about 40 curated items plus an ablation set), each with `satisfied_by` canonical handles and `parent_content_hash`.
   - Add a CI integrity check: every handle resolves, the anchor is contained, the hash matches.
   - Gold is frozen *before* any retrieval tuning.
2. **Retrieval runner and statistics.**
   - Recall@k and MRR at parent level, with bootstrap CIs and lexical-overlap bins.
   - Baselines: dense-only and lexical-only on the current smoke lanes.
3. **Canonical lanes.**
   - Dense SQL with workspace, active-version, confidentiality and class filters inside the materialized CTE.
   - IDF-weighted FTS lane.
   - `EXPLAIN ANALYZE` under RLS for both lanes.
4. **Parent-level RRF** over child hits, keeping the best anchor child (`char_start/char_end`) per parent. This is the D1 anchor-propagation start.
5. **Local cross-encoder rerank** (MaxP over parents) with fused-order fallback and timeout (ADR-0005). Its latency budget is measured.
6. **Balancing and retrieval traces** (per-stage `(child_id, handle, rank, score, anchor)`).
7. **Embedding follow-ups.** A/B the BGE query instruction on gold v0; build the re-embed job for `ready_degraded` versions.
8. **Ablation report.**
   - dense-only, lexical-only, hybrid, and hybrid + rerank, with CIs;
   - CI eval smoke gate on a small fixed subset.
9. **Exit.**
   - Phase 2 report with measured deltas and latency per stage;
   - RETRIEVAL_DEEP_DIVE draft.

Out of scope for Phase 2 (per D5): neighbour expansion and structural enumeration (Phase 7 tuning iterations), and any generation or LLM dependency (Phase 3).
