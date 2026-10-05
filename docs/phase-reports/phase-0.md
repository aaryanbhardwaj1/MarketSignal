# Phase 0 report: repository and local infrastructure

| | |
|---|---|
| Completed | 2026-10-05 |
| Exit criterion | "`docker compose up` → `/readyz` green as `ms_app`; CI green" — **met** |
| CI | GitHub Actions run 37353231890: safety ✅ · backend ✅ · frontend ✅ · container build ✅ |

## Implemented

| Area | What | Commit |
|---|---|---|
| Repo safety | `.gitignore`, reference-material/size/private-content guard, pre-commit hook (guard + gitleaks), gitleaks config | `5d2944b` |
| Design docs | Approved architecture plan v1.1, public product spec, ADRs 0001–0019 + deviation register | `5cdfd07`, `9e6b1e0` |
| API | FastAPI factory, `/healthz`, `/readyz` (database, role guard, migration head, pgvector ≥ 0.8.0, Redis optional), privileged-role startup guard, redacted structured logging, request IDs, `/metrics` | `325554a` |
| Isolation | `ms_owner` / `ms_app` roles, migration 0001 (`app.current_workspace()`, `workspaces`, `workspace_members`, first RLS tenant table), scope listener | `b5fab2c` |
| Dev environment | Compose light/full modes (pgvector 0.8.7-pg18, Redis 8), backend image, `.env.example`, Makefile | `d90543d` |
| Frontend | Next.js 16 scaffold with an API readiness badge | `273700f` |
| MCP spike | SDK v2 contract tests + `docs/spikes/0001-mcp-sdk-v2.md` | `b54d2c5` |
| CI | Safety + gitleaks, backend with real Postgres/Redis services, frontend, image build | `a7e2be5`, `502d26c` |

## Verification performed (not assumed)

| Check | Result |
|---|---|
| Backend lint (`ruff check`), format (`ruff format --check`) | pass |
| Strict mypy (`src/marketsignal`) | pass, 0 issues |
| Unit tests | 25/25 pass (no services) |
| Integration tests as `ms_app` | 7/7 pass |
| Integration non-vacuity: isolation suite run as **superuser** | 5/5 **fail**, as expected; the tests detect an RLS bypass |
| MCP v2 spike | 7/7 pass |
| Full backend suite, local and CI | 39 pass, 0 skipped |
| Role topology (catalog) | `ms_app` and `ms_owner`: `rolsuper=f`, `rolbypassrls=f`; database owned by `ms_owner` |
| Migration | `0001` applied as `ms_owner`; `workspace_corpus_state` has `relrowsecurity=t`, `relforcerowsecurity=t`; the policy applies to both USING and WITH CHECK |
| Native API `/readyz` (light mode) | `ready`, all 5 checks ok |
| Redis stopped | `/readyz` → `degraded`, HTTP 200; returns to `ready` after restart |
| API started with the superuser DSN | refuses to start (`PrivilegedDatabaseRoleError`, exit 3); no password in the output |
| Clean-volume `docker compose --profile full up` | initdb roles → migrate container exits 0 → API container healthy; `/readyz` ready as `ms_app` |
| Frontend from a clean state | lint, typecheck (`next typegen && tsc`), production build pass |
| Secret scan | gitleaks: full history, no leaks (local and CI) |
| Repo guard | passes on tracked files (CI) and on staged files (every commit) |

## Measurements

| Metric | Value |
|---|---|
| Backend image (`python:3.13-slim` + deps) | 462 MB, down from 787 MB after removing the cached uv layer and the `chown -R` layer duplication |
| Idle memory, full stack (api / postgres / redis) | 89 / 72 / 23 MiB |
| Backend test suite wall time (local) | ~3.5 s |

## Deviations from the plan

| Deviation | Status |
|---|---|
| Justfile → **Makefile** | Approved |
| MarketSignal-specific identifier renames (warning codes, agent config names) | Approved |
| Consecutive tool-error threshold **3** (configurable, to be tested in Phase 4) | Approved |
| `astral-sh/setup-uv` pinned by commit SHA (v10.2.0), because that action publishes no floating major tags | Implementation detail; improves supply-chain hygiene |
| Frontend `typecheck` runs `next typegen` first, because route types are generated and gitignored | Implementation detail |
| Phase 0 spikes: the **Anthropic live behaviour check** needs an API key and moves to Phase 3. The **Render pgvector/role check** needs a Render account and moves to the deployment phase. | Deferred, by necessity |

## Unresolved issues and risks

1. **`httpx2`.** Starlette 1.7's test client and the MCP SDK v2 both use `httpx2`. Before I had checked its provenance, an automated safety check stopped me from swapping our own test dependency to it, and that swap was reverted. Provenance has since been checked: a required dependency of the official `mcp` package, published by the httpx author under `github.com/pydantic/httpx2`. It is installed only transitively through `mcp==2.3.0`, and the MCP spike imports it directly because the SDK API requires it. Our own tests stay on `httpx`.
2. **Action version churn.** The other actions use floating major tags. Recommended: SHA-pin them all and enable Dependabot for `github-actions`, `uv` and `npm` (small; planned with Phase 1).
3. **RLS × GIN.** Under FORCE RLS, `@@` cannot use the GIN index. It must be measured with EXPLAIN in Phase 2 (ADR-0001 / plan §8).
4. **Integration tests share the local dev database.** Each test uses a random workspace code and cleans up after itself. A dedicated test database can be added if this ever becomes a problem.

## Next: Phase 1 (ingestion and evidence model)

Proposed sequence, one or more commits per step:

1. Evidence-handle grammar (`evidence/handles.py`), with Hypothesis round-trip and fuzz tests (ADR-0004).
2. Migration 0002: `sources`, `source_versions`, `source_blobs`, `parent_chunks`, `child_chunks`, `chunk_embeddings`, `dataset_tables` / `dataset_rows`, `audit_events`. All with RLS and composite tenant foreign keys, plus negative tests.
3. World model and seed generator: Northstar (~26 sources) plus the Southpeak decoy (6), with fact-ledger anchors.
4. Upload API: container validation, Postgres blob store, versioning semantics, and transactional enqueue (Procrastinate) to the worker.
5. Parsers for PDF / DOCX / PPTX / XLSX / CSV / MD, producing located blocks. Then structure → parents → children (row policy) → handles.
6. Embeddings (fastembed `bge-small-en-v1.5` with a file cache), FTS columns, the health check, and the flip transaction that bumps `corpus_version`.
7. Resolver and evidence endpoint; Sources API, Sources page, workspace create/list.
8. Exit check: the seeded corpus ingests through the API; a planted fact is found by lexical **and** dense search; its handle resolves to exact text with a locator. Seed time and throughput are recorded.
