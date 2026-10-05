# MarketSignal — Architecture Plan

| | |
|---|---|
| Version | 1.1 (approved; v1.0 was revised after a 7-lens adversarial review: 91 findings, 35 critical/high independently verified) |
| Date | 2026-10-04 (library/model versions verified current as of this date) |
| Status | **APPROVED** 2026-10-05: deviations D1–D11 approved, with the added requirements recorded in §0.3. Decisions are recorded as ADRs in `docs/adr/`. |
| Convention | Each significant decision gives **Decision · Why · Alternatives · Tradeoff**. Prior enterprise legal-research RAG work (Visa internship) is referred to only through generic architectural patterns. |

> Confidentiality note: this document is written to be safe for a public repository. It does not reproduce any employer-internal names, metrics, configuration, or corpus details.

---

## Table of contents

0. Summary, assumptions, spec deviations
1. Repository structure
2. Component architecture (+ MCP placement, frontend views)
3. Query lifecycle (+ answer contract, modes, latency budget)
4. Ingestion lifecycle (+ upload hardening, versioning, purge contract)
5. Technology selections
6. PostgreSQL schema
7. pgvector strategy
8. Indexing strategy
9. Parent/child document model
10. Evidence-handle grammar (+ alias layer)
11. Lexical retrieval
12. Semantic retrieval
13. Candidate-generation sizes
14. Fusion (RRF)
15. Reranking, collapse, balancing, expansion
16. Source-resolution system
17. MCP server and tool governance
18. Concrete MCP tool schemas
19. Bounded agent state machine (+ LLM call envelope)
20. Conversation and context management
21. Streaming / SSE protocol
22. Caching and invalidation
23. Workspace isolation
24. Prompt injection and data trust boundaries
25. Observability
26. Evaluation architecture
27. Gold-set strategy
28. Failure and degradation behavior
29. Testing strategy
30. CI pipeline
31. Local development environment
32. Deployment architecture (+ browser auth boundary, demo mode)
33. Cost-conscious decisions
34. Scaling path
35. Major risks
36. ADRs
37. Personas, Growth Opportunity Workspace, opportunity brief, analytics
38. Phases, estimates, and the interview cut line

---

## 0. Summary

### 0.1 Architecture in one paragraph

A Next.js frontend calls a FastAPI service over REST and Server-Sent Events. Every research request becomes a persisted **run**. A deterministic **router** picks the mode:
- **standard**: one retrieval pass, then synthesis.
- **research**: a **bounded agent state machine**.

The agent's LLM reaches data only through a **governed MCP tool server**. The server is mounted in the same service, accepts loopback connections only, and authenticates every call with a run-scoped capability token. The workspace is read from the token's claims and is never a tool argument.

Tools are stateless. They call a deterministic retrieval and evidence layer on **PostgreSQL 18 + pgvector 0.8.7**:
1. Dense HNSW candidates and lexical (Postgres FTS, IDF-weighted) candidates.
2. **RRF fusion at the parent level**.
3. A **local ONNX cross-encoder** reranks the fused list.
4. **Collapse**, then source/class balancing.
5. Optional neighbor or enumeration expansion.

Evidence is cited at the **parent (structural) unit** through an **immutable, grammar-validated evidence handle**. The generator writes per-answer aliases (`[E3]`). These are mapped back to handles deterministically and verified before the answer is final.

Ingestion runs in a separate worker fed by a **Postgres-native job queue**. Redis holds an answer cache keyed on a per-workspace **corpus version**, plus rate limits. Redis is optional for correctness.

Evaluation uses a versioned gold set derived from a synthetic **world model with planted facts**, frozen against the real ingested corpus. CI gates only on deterministic metrics. LLM-judged metrics are reported with uncertainty.

### 0.2 Assumptions (non-blocking; changing them later is cheap unless marked)

| # | Assumption | Cost to change later |
|---|---|---|
| A1 | Single demo principal. The schema supports membership and roles (`workspace_members`). | Low |
| A2 | Anthropic Claude is the LLM provider: Sonnet 5.5 for agent and synthesis, Opus 5.5 for judging. It sits behind `LLMProvider`. | Low |
| A3 | Embeddings and reranking run locally (ONNX via fastembed), so ingestion sends no corpus text to third parties. | Low (behind interface). Changing the embedding model means re-embedding. |
| A4 | The whole demo corpus is synthetic and fictional, including the competitors. Real public filings are an optional, uncommitted add-on. | Low |
| A5 | The repository will become public on GitHub. Nothing confidential is committed. | High if violated (irreversible) |
| A6 | Hosted demo is Vercel + Render. AWS ECS is a documented reference architecture. | Medium |
| A7 | Python 3.13 (managed by uv), Node 24, Docker runtime to be installed (OrbStack or Colima). | Low |
| A8 | English-only corpus and FTS configuration. | Medium |
| A9 | Interview timing is unknown, so work is ordered to reach an interview-ready **M1** milestone first (§38). | n/a |

### 0.3 Approved spec deviations (D1–D11)

| # | Spec says | Proposal | Why |
|---|---|---|---|
| D1 | `evidence_handle` lives on `child_chunks` | Cite **parents**, which are structure-derived units. Children are internal retrieval windows. **Approval requirement:** child-anchor metadata and character offsets (`char_start/char_end` into the parent) are preserved through retrieval traces, the evidence pool, the pack, and stored citation cards. Retrieval therefore stays child-granular, and the exact supporting span can be highlighted and evaluated, while the citation points to the stable parent. | Child boundaries move whenever chunk size is tuned, which would orphan handles and gold labels. Parents (page block, slide, row, Q&A pair) are stable and are units a consultant can verify. |
| D2 | "Answer generator must reference handles exactly" | The generator cites per-answer aliases `[E1]..[En]`. These are mapped deterministically to canonical handles before storage or rendering. **Approval requirement:** aliases are strictly run-local and are never persisted as evidence identities. Before any final storage or rendering, every alias must resolve deterministically to a canonical handle from the *current run's* evidence pack. An alias that does not resolve is removed and recorded as a warning; it is never guessed. | The model can only reference pack items, so a fabricated handle cannot be produced. It also uses fewer tokens and verification is trivial. Stored answers contain only canonical handles. |
| D3 | Expose `search_evidence_semantic`, `_keyword`, `_hybrid` | The agent gets `search_evidence` (the full hybrid pipeline) and `search_evidence_keyword` (exact matching). Dense-only search exists internally for ablations. | Overlapping tools make tool selection worse and would let the model skip fusion and reranking. |
| D4 | Seeded demo in Phase 9, gold sets in Phase 7 | The seed corpus and gold v0 move to Phases 1–2. | Spec Phase 2 already requires a scored gold set compared against a dense-only baseline. |
| D5 | All retrieval augmentations in Phase 2 | Build the core pipeline first. Add neighbor expansion and structural enumeration as **measured tuning iterations**. | This yields the required before/after iterations from real failures. |
| D6 | Public competitor documents | Use fictional competitors. An optional script fetches real public filings, which are not committed. | Synthetic customer voice that criticizes real brands is a fabricated claim about real companies. Fictional data also avoids licensing issues and keeps the demo deterministic. |
| D7 | SSE events `search_started/…` | Use `tool_started/tool_completed` with a `kind` field, add `draft_reset`, and send `final` before `done`. | One event family covers every tool, and the verified `final` answer supersedes the streamed draft. |
| D8 | `GET /api/evidence/{handle}` and unscoped conversation routes | **Every tenant route lives under `/api/workspaces/{ws}/…`** | Workspace authority must come from the route and the principal. Without it, RLS scope cannot be set before the first read. |
| D9 | Personas influence "tool availability" | All personas share the same read-only tool set. They differ in source-class priors, prompt policy and default mode. The allowlist mechanism exists and is tested. | Restricting read-only tools lowers answer quality and gains no security. |
| D10 | Every query goes through the agent (implied) | A `standard` single-pass mode plus an agentic `research` mode, chosen by a deterministic router that the user can override. **Approval requirement:** the router stays deterministic (no LLM) and user-overridable. The Phase 7 agent-vs-single-pass ablation is mandatory and is the evidence for when agentic orchestration is worth its cost. | The spec's latency target is under 15 s. Phase 7 measures the agent's benefit through an ablation. |
| D11 | Load test with Locust/k6 | A Locust script, or a documented asyncio script if Locust adds friction. | Either one serves spec §26.4. |

### 0.4 Implementation deviations (recorded as phases complete)

These refine the plan without changing the approved evidence, versioning, parent/child, isolation or ingestion models. Each one is detailed in the named ADR's *Implementation notes*. Where this register and the text below disagree, the register wins.

| Phase | Plan text | As built | ADR |
|---|---|---|---|
| 1 | Ingest embedding cache at `.cache/embeddings/<model>.parquet` plus a DB lookup (§22) | One SQLite file per model (`<model>.sqlite3`). The DB reuse index exists, but the lookup is not used yet | 0012 |
| 1 | Query embedding uses the bge query instruction (§12) | Not applied yet (fastembed adds none). Phase 2 makes it configurable and A/B-tests it on gold v0 | 0012 |
| 1 | Stalled-job reaper and re-embed job in the worker (§4) | Deferred: reaper to Phase 8 hardening; re-embed to Phase 2. `ready_degraded` and the manual retry are built | 0010 |
| 1 | Row child `{table} \| {context} \| {free-text col}: <verbatim>`; span into the row parent not specified | The child text is as planned. Its span into the authoritative `col: value; …` row parent is the verbatim free-text cell. Identifier columns are never free text (policy `c2`) | 0003 |
| 1 | Retry, purge execution | Retry re-queues the same failed version; purge is synchronous; re-uploading to a deleted source restores it with the next version | 0016 |
| 1 | Purge vs in-flight ingestion (follow-up) | Every worker write share-locks the source; a purge at any point wins and the version stays `purged` | 0016 |
| 1 | Integration tests against the service database | A dedicated `marketsignal_test` database, created by the init script, with a guard test | 0009 |

---

## 1. Repository structure

```
MarketSignal/                    # NOTE: private notes and non-public reference material are kept OUTSIDE this tree
├── README.md                    # pitch, diagram, quick start, evidence-handle explainer, eval snapshot, limitations, privacy
├── docker-compose.yml           # postgres(pgvector) · redis · api(+mcp) · worker · frontend (profile "ui")
├── .env.example  .gitignore  .dockerignore (per build context)  Makefile  (Justfile → Makefile: approved Phase 0 deviation; no extra tool to install)
├── .github/workflows/           # ci.yml (every PR), eval-full.yml (manual; needs LLM key)
├── docs/
│   ├── ARCHITECTURE_PLAN.md (this)  ARCHITECTURE.md  SYSTEM_DESIGN.md  RETRIEVAL_DEEP_DIVE.md  INGESTION.md
│   ├── AGENT_AND_MCP.md  EVALUATION.md  DEPLOYMENT.md  SECURITY.md  TRADEOFFS.md  DEMO.md  PRIOR_WORK_PATTERNS.md
│   ├── INTERVIEW_GUIDE.md       # ≥50 deep-dive Q&A (the spec's INTERVIEW_QA.md)
│   ├── PRODUCT_SPEC.md          # product specification
│   ├── adr/NNNN-*.md            # context / decision / alternatives / tradeoffs / consequences
│   └── phase-reports/           # per phase: implemented, deviations, measurements, open issues, next
├── backend/                     # one Python package; uv; Python 3.13
│   ├── pyproject.toml  uv.lock  Dockerfile  alembic.ini
│   ├── migrations/              # Alembic: extensions, roles/grants, RLS policies, indexes
│   ├── db/init/01_roles.sql     # ms_owner / ms_app roles (compose initdb + CI setup)
│   ├── src/marketsignal/
│   │   ├── config.py            # pydantic-settings; every tunable; config_hash()
│   │   ├── domain/              # pydantic models, enums, DegradationCode, TerminationState
│   │   ├── evidence/            # handles.py (grammar), resolver.py, citations.py (alias map + verification)
│   │   ├── db/                  # engine, WorkspaceScope (+set_config hook), ORM models, repositories (scope-required)
│   │   ├── storage/             # BlobStore protocol: Postgres (default) | S3-compatible (documented/optional)
│   │   ├── ingestion/           # validate (container checks), parsers/*, structure, parents, children, pipeline, tasks
│   │   ├── providers/           # embeddings, rerankers, llm/{base, anthropic, fake}, embedding_cache
│   │   ├── retrieval/           # query, dense, lexical, fusion, rerank, collapse, balance, neighbors, structural, pipeline, trace
│   │   ├── analytics/           # op DSL, schema inference, executor (polars), computed handles
│   │   ├── tools/               # governance registry + tool implementations (transport-agnostic)
│   │   ├── mcp_server/          # MCPServer adapter, capability-token verifier, loopback guard, stdio entrypoint
│   │   ├── agent/               # router, state machine, bounds, LLM envelope, context, prompts/, personas/
│   │   ├── generation/          # pack builder, synthesis, alias hold-back gate, verifier, evidence-only fallback
│   │   ├── hypotheses/          # dual-track workflow, stance classifier, strength rules, briefs
│   │   ├── runs/                # run manager, run_events log, live fan-out
│   │   ├── cache/               # answer cache + key builder
│   │   ├── telemetry/           # structlog (+redaction), traces, Prometheus
│   │   ├── evaluation/          # datasets, freeze-gold, metrics, judge, runners, stats, reports (CLI `ms-eval`)
│   │   ├── api/                 # app factory, routers, deps (principal, scope), error mapping
│   │   └── worker/              # Procrastinate app, task registration, stalled-job reaper
│   └── tests/                   # unit/ integration/ contract/ (+ runtime fixture factories; no committed binaries)
├── eval/                        # datasets/ (versioned JSONL + manifest), baselines/ (CI-generated), reports/
├── seed_data/                   # world_model.yaml, generator/, generated/{northstar,southpeak}/, fact_ledger(.resolved).json
├── frontend/                    # Next.js (App Router) + TS + Tailwind + shadcn/ui + TanStack Query
├── scripts/                     # seed, freeze-gold, fetch_public_filings (optional), bench, loadtest
└── infra/                       # render.yaml (primary), aws/ (reference design doc; optional IaC)
```

**Decision: one Python package with multiple entrypoints (api, worker, mcp-stdio, ms-eval).**
- *Why:* evaluation must score the real production path. Retrieval, tools, agent and eval share types. One image keeps deployment simple.
- *Alternatives:* a multi-package uv workspace, or separate services.
- *Tradeoff:* module boundaries are not enforced by the compiler. An import-linter in CI enforces them instead: `agent` cannot import `db` or `retrieval`, `tools` is the only path to services, and `generation` cannot import `tools`.

---

## 2. Component architecture

```
 Browser ─▶ Next.js (Vercel) ──REST (Bearer session token, CORS allowlist)──────┐
    │                                                                            ▼
    └──── SSE: EventSource(api origin, ?st=<run stream token>) ─────────▶ FastAPI "api" (Render)
                                                                         ├─ Routers (all tenant routes under /api/workspaces/{ws})
                                                                         ├─ Router: standard | research
                                                                         ├─ RunManager ─ run_events (Postgres) ─ live fan-out
                                                                         ├─ Agent state machine ──MCP client (loopback, capability token)──┐
                                                                         ├─ Generation: pack → synthesize → alias gate → verify            │
                                                                         ├─ /mcp  MCPServer (loopback-only) ◀────────────────────────────────┘
                                                                         │       └─ Tool governance registry ─▶ Retrieval · Evidence · Analytics · Hypotheses
                                                                         └─ Answer cache (Redis, optional)
 "worker" (Render) ─ Procrastinate ─ ingestion pipeline / re-embed / purge / stalled-job reaper
 PostgreSQL 18 + pgvector: app data · chunks · embeddings · FTS · blobs · jobs · run events · traces · spend ledger
 Redis: answer cache · query-embedding cache · rate-limit counters
 Models: local ONNX embedder + cross-encoder (api & worker) · Anthropic Claude (agent, synthesis, stance, judge)
```

| Component | Responsibility | Must NOT |
|---|---|---|
| API | Authentication and authorization, validation, run lifecycle, SSE, persistence | Let unverified model output reach storage or the UI as final |
| Router | Choose standard or research mode from deterministic cues, with user override | Call the LLM |
| Agent runtime | Choose tools, own the run's evidence pool (handles), stop within bounds | Write user-facing prose, touch the DB or filesystem, choose the workspace |
| MCP server + governance | Be the only tool surface; verify the token, apply the allowlist, validate input, enforce timeout, cap output, normalize errors, audit | Accept workspace, path or SQL from arguments; keep per-run state |
| Retrieval layer | Deterministic, traced candidate generation and ranking | Call an LLM |
| Generation | Build the pack, synthesize, gate aliases, verify, fall back | Cite anything outside the pack |
| Worker | Ingest, re-embed, purge, reap stalled jobs; idempotent | Serve queries |
| Postgres | Single system of record, including the evidence text used for resolution | — |
| Redis | Caching and rate limits | Be required for correctness |

### 2.1 MCP placement

**Decision:** the MCP server is its own module and ASGI app, mounted in the API service at `/mcp`. It accepts **loopback clients only** unless `MCP_PUBLIC=true` is set. The agent reaches it over loopback Streamable HTTP with a capability token. A stdio entrypoint serves local MCP clients such as Claude Desktop and Claude Code; this is described honestly as *trusted local mode*, not as an authentication mechanism.

**Why:** the governed boundary is about protocol and authorization: it is the model's only path to data. It is not about process isolation. Mounting avoids a third paid service, and the server stays independently deployable (same image, different command). The MCP spec revision 2026-07-28 is stateless, so any replica can serve any call, provided tools hold no session state (§17).

**Alternatives:**
- A separate MCP container: a stronger process boundary, but one more service and more cost.
- Plain in-process calls: no protocol boundary.
- Anthropic's hosted MCP connector: needs a public URL and is not eligible for zero data retention (ZDR).

**Tradeoff:** a bug inside the process could bypass the boundary. This is mitigated by import-linter rules, a contract test that the agent's data access goes only through the MCP client, and an in-process transport used in tests.

**Delivery:** Phase 4a uses an in-process transport over the same registry. Phase 4b switches to Streamable HTTP, and a parity test confirms both behave the same. An SDK regression therefore cannot block the demo.

### 2.2 Frontend views (spec §23)

| View | Shows | Backing endpoints | Phase |
|---|---|---|---|
| Workspaces list/create | name, client, persona | `GET/POST /api/workspaces` | 1 |
| Workspace dashboard | source counts by class, ingestion status, recent conversations, hypotheses, eval/health summary | `GET /api/workspaces/{ws}/summary` | 1 → grows |
| Sources | name, class, format, status, parent/child counts, last indexed, error category, delete/reindex, upload | `…/sources`, `DELETE …/sources/{id}`, `POST …/sources/{id}/reindex` (polls while non-terminal) | 1 |
| Research chat | persona selector, mode toggle, history, streamed draft ("Draft — verifying…"), progress events, citation chips (pending → verified), expandable citation cards, source-class filters, upload, "save to hypothesis" | conversations, runs, SSE | 3 (core) / 4 (persona, progress, filters) |
| Evidence viewer (drawer + deep link) | exact parent text with highlighted anchor span, locator, prev/next context, source metadata, class, provenance, retrieval ranks for the run, back-link, tombstone state | `GET …/evidence/{handle}?run_id=` | 3 |
| Hypothesis page | statement, support/contradict/context lists, gaps, synthesis with strength basis, analysis time, **stale badge** (corpus changed), rerun, "export brief" | hypotheses API, briefs export | 6 |
| Dev: runs | run trace: stages, candidates before/after rerank, pack, tokens, timings, flags | `GET …/runs/{id}` | 4 |
| Dev: evals | metrics with CIs, ablations, baseline diff, failing items | evaluations API | 7 |

All model output renders through a single `SafeMarkdown` component, specified in §24.

---

## 3. Query lifecycle

1. `POST /api/workspaces/{ws}/conversations/{cid}/runs {question, persona?, mode?: auto|standard|research, source_classes?}`. The API validates the session token, then the membership-checked scope dependency resolves `{ws}` and calls `set_config('app.workspace_id', …, true)`. It inserts a `query_runs` row (`running`), appends `run_started` to `run_events`, and returns `202 {run_id, stream_url (includes a short-lived stream token)}`. Target: under 150 ms.
2. The client opens `EventSource(stream_url)`. Replay works from `Last-Event-ID` or `?last_event_id`.
3. **Cache probe.** Runs only for context-free turns. Key: workspace, corpus_version, normalized query, persona, filters, mode, retrieval_cfg_hash, prompt_version, model ids. On a hit, revalidate handles and stream `final` then `done`.
4. **Router.** Precedence, highest first: an explicit request `mode` of `standard` or `research`; an explicit request `auto` (cue rules, overriding the persona default); the persona's default mode (§37.1); and, when that default is `auto` or there is no persona, the cue rules. The cue rules select `research` for: hypothesis or "evaluate" wording, comparison ("vs", "compared", "which competitors"), numeric/analytic cues ("how many", "%", "trend", "by segment"), two or more class cues, or a follow-up that needs earlier context. Everything else goes to `standard`.
5. **Gather.**
   - *standard*: normalize the query, run `search_evidence`, and run a keyword search for any quoted or capitalized entities, all through the same registry.
   - *research*: run the agent loop (§19). Each tool call emits `tool_started` and `tool_completed` events with deterministic summaries. Tool `structured_content` is merged into the **run-scoped evidence pool**, which holds handles with their anchor child id and character offsets (D1), best scores, expansion kinds, classes and provenance. The LLM sees only compact observations.
6. **Pack (deterministic).**
   - Reuse each pool item's best rerank score. Score only unscored items, using their anchor child text, so the pool is never fully re-reranked.
   - Collapse, then balance.
   - Protect analytics, structural and explicitly resolved items.
   - Resolve full parent text from Postgres by handle. Use a child-centred window if a parent exceeds its per-item budget.
   - Fill the token budget. Each requested class reserves its best item first.
   - Assign aliases `E1..En` and emit `evidence`.
   - If the pack is empty, terminate as `no_relevant_evidence`. No generation call is made; the response is a deterministic message plus suggested source classes.
7. **Synthesis (streamed).** Output passes through the **alias hold-back gate** before any `token` event (§21). A valid alias triggers `citation` on its first use. An unknown alias is removed before emission and raises a `warning`.
8. **Verification (deterministic)** against the answer contract (§3.1). On failure:
   - Apply deterministic repairs first: strip unknown aliases, URLs and images; drop uncited non-heading sentences.
   - If a *structural* failure remains and the time budget allows, emit `draft_reset` and regenerate once.
   - Otherwise fall back to evidence-only.
9. `final` (canonical answer with handles, citation cards, parsed sections, verification report) → persist the message → conditional cache write (§22) → `done {termination_state, flags, timings}`, which is **always the last event**.
10. Telemetry: the `query_runs` row is finalized. `tool_runs`, `retrieval_traces` and `run_events` were already written. Prometheus histograms are updated.

### 3.1 Answer contract

Answers use fixed headings so that a deterministic parser can check them.

| Section | Rule |
|---|---|
| **Answer** | 2–4 sentences. Each sentence ends with at least one alias or is tagged `[inference]`. |
| **Key findings** | Bullets. Each carries at least one alias. Numbers must appear in the cited evidence (numeric faithfulness, with normalized %, currency and thousands formats). |
| **Conflicting evidence** | Required when the pack contains opposing stances. Omitted otherwise. |
| **Interpretation** | Optional synthesis. Every sentence is tagged `[inference]`. No new numbers. |
| **Gaps & unknowns** | Required when the pack is truncated, a requested class is missing, or the evidence is thin. No aliases and no numbers. |
| *Hypothesis mode* | Adds **Supporting**, **Contradicting**, **Strength (rule-derived basis)** and **What would reduce uncertainty**. |

Global rules:
- Any sentence outside **Gaps** that contains a number needs an alias, or it is tagged `[inference]`, and then only numbers that appear in the pack are allowed.
- No URLs, images, HTML or raw internal IDs.
- Citation count per answer is capped at 20.
- `final.sections` carries the parsed structure. The UI renders evidence, inference and gaps in visibly different styles, which implements the spec's evidence/inference/gap distinction (spec §11.3).

A **runtime LLM claim-support check** is out of MVP scope; spec §16.3 marks it optional. The offline judge (§26) and the deterministic numeric check mitigate the gap.

### 3.2 Modes and latency budget (spec §25)

| Stage | Target |
|---|---|
| `run_started` after POST | < 1 s |
| Retrieval stage (one `search_evidence`), warm | < 2 s |
| First synthesis token: standard / research | ~4 s / ~8 s |
| End-to-end p50: standard / research | < 15 s / ~25 s |
| Cached answer | < 1 s |
| Run deadline | 60 s: gather budget 35 s, remainder for synthesis |

Measured p50 and p95 for each stage come from `query_runs.timings` and the load test, and are published in the engineering report.

**Decision:** two modes with deterministic routing.
- *Why:* the agent pays off on multi-hop, cross-class and analytic questions, and costs latency everywhere else.
- *Alternatives:* agent-always, or an LLM router (costs another call).
- *Tradeoff:* router rules can misroute. The user can override them, and the Phase 7 **agent-vs-single-pass ablation** measures the real benefit and answers "why an agent?" with numbers.

---

## 4. Ingestion lifecycle

```
POST /api/workspaces/{ws}/sources  (multipart: file, source_class, title?, confidentiality?, source_code?)
  → validate:  extension allowlist ∧ size ≤ 25 MB ∧ filename sanitised (metadata only; never a path)
  → validate_container():
       PK\x03\x04 → zip central directory: ≤ 2,000 entries, Σ file_size ≤ 200 MB, per-entry ratio ≤ 100;
                    [Content_Types].xml main part must match the extension (docx/xlsx/pptx); macro-enabled → UNSUPPORTED_TYPE
       D0 CF 11 E0 on an OOXML extension → ENCRYPTED_DOCUMENT;  PDF header + /Encrypt → ENCRYPTED_DOCUMENT
       CSV/TXT/MD → UTF-8 / UTF-8-SIG decode check
  → sha256 → version resolution (§4.2) → idempotent no-op if identical to the target source's current/in-flight version
  → ONE transaction: sources (if new) + source_versions(status=queued) + blob (Postgres BlobStore) + Procrastinate job
    (job deferred on the same psycopg connection → NOTIFY fires on commit; no dual-write)
  → 202 {source_id, source_code, version, status_url}

Worker (job args: workspace_id, source_version_id; job transaction sets scope from args, re-reads the version, fails on 0 rows)
  parse (format parser, wall-clock timeout, page/slide/row caps) → normalized Block stream with locators     status=parsing
  → structure (headings, lists, tables, Q&A, slides, rows; column typing for tables)
  → parents (structural units; cap 800 tokens; never cross a page/slide/row/Q&A boundary)                     status=chunking
  → children (narrative: 192-token windows, 32 overlap, inside one parent; rows: compact serialization; §9)
  → handles + content hashes; dataset tables/rows (typed) for structured files
  → embeddings: file-backed cache (model, sha256(text)) → embed misses in batches                             status=embedding
  → write parents/children/embeddings/dataset rows (version NOT yet active)                                   status=indexing
  → health check on the not-yet-active version: 5 sampled children: rare-lexeme `tsv @@ q` membership, dense self-match in top-5,
    handle resolves to parent text containing the child text
  → flip transaction (small): version → ready (or ready_degraded), previous → superseded, sources.current_version_id (guarded),
    workspace_corpus_state.version += 1, audit_event                                                          status=ready
Failure → status=failed + error_code (UI-visible). Embedding failure → ready_degraded (lexical-only) + scheduled re-embed job
(re-embed completion bumps corpus_version). Stalled jobs → periodic reaper: retry ≤ 2 (tracked on source_version) else failed.
```

| Format | Parser (license) | Parent unit | Locator | Handle example |
|---|---|---|---|---|
| PDF | pypdf `extraction_mode="layout"` (BSD); pdfplumber/pdfminer.six ≥ 20251230 (MIT) for tables and line gaps | paragraph group within one page (heading path kept) | page, block | `NORTHSTAR/BRAND-STRATEGY@v1:P4.B2` |
| DOCX | python-docx (MIT) | heading section → paragraph group; interview Q&A pair | section, block / Q&A | `NORTHSTAR/INTERVIEWS@v1:S3.Q7` |
| PPTX | python-pptx (MIT) | slide (title + body + tables); notes kept separate | slide, notes | `NORTHSTAR/Q3-REVIEW@v1:SL6`, `…:SL6.N1` |
| XLSX | openpyxl (MIT; read_only, data_only; defusedxml installed) | one row (header-qualified); a table-summary unit per sheet | sheet, row (Excel numbering), table | `NORTHSTAR/PRODUCT-PERF@v1:SH2.R12`, `…:SH2.T1` |
| CSV | stdlib csv (sniffed dialect; UTF-8/UTF-8-SIG) | one row; table summary | row (header = row 1), table | `NORTHSTAR/SURVEY-2026@v1:R185` |
| MD/TXT | stdlib | heading section → paragraph group | section, block | `NORTHSTAR/TRENDS-NOTE@v1:S2.B1` |

PyMuPDF is excluded because of its AGPL licence. OCR is out of scope: a page whose extracted text falls below a configurable minimum word count (`PDF_MIN_WORDS_PER_PAGE`, calibrated on the synthetic corpus in Phase 1) raises a `PARTIAL_EXTRACTION` warning.

Error categories, all shown on the Sources page: `UNSUPPORTED_TYPE, FILE_TOO_LARGE, CONTENT_TOO_LARGE, PARSE_FAILED, PARSE_TIMEOUT, ENCRYPTED_DOCUMENT, EMPTY_DOCUMENT, MALFORMED_SPREADSHEET, EMBEDDER_UNAVAILABLE, DB_UNAVAILABLE`.

The worker runs with an explicit memory limit (compose `mem_limit`, and the Render instance size), so an out-of-memory kill restarts only the worker.

### 4.1 Format notes

- **PDF paragraphs.** pypdf's default text extraction drops blank lines. Layout mode with a line-gap heuristic is pinned to `parser_version`.
- **Tables.** Column types are inferred (numeric, date, categorical, free_text) from a sample with explicit rules. Mixed or unparseable columns fall back to `categorical` and are flagged.
- **Rows.** Free-text columns (string, mean length over 20 characters or high cardinality) and context columns (low-cardinality strings) are separated from numeric columns. See §9 for how rows become retrieval units.

### 4.2 Versioning semantics (spec §12.5)

- **Target source.** If the upload carries `source_code` and that source exists, the upload is a *new version* of it. Otherwise a new source is created, with its code derived from a filename slug and a suffix added on collision. If no `source_code` is given and the bytes match an active version of a *different* source, that version is returned with `duplicate_of` and no work is done.
- **Idempotency.** Bytes identical to the target's current or in-flight version return `200` with the existing version. Bytes identical to a superseded, failed or purged version create a *new* vN. Revert and retry-after-fix both work, and embedding reuse keeps them cheap.
- **Allocation.** The version number is assigned under `SELECT … FROM sources WHERE id=$1 FOR UPDATE`. A partial unique index on `(source_id, content_hash, parser_version, structure_version) WHERE status NOT IN ('failed','superseded','purged')` blocks duplicates.
- **Parents are immutable once a version is ready.** A reindex may rebuild only children, embeddings and tsv (`chunking_policy_version` or `embedding_model` changes). A change to `parser_version` or `structure_version` mints **a new version over the same bytes** (`reason=reindex`), and the old version stays resolvable. A handle therefore never re-points to different text.
- **Guarded flip.** `current_version_id` moves only forward. A slow v2 that finishes after v3 is marked superseded.

### 4.3 Purge contract (deletion)

Privacy wins over immutability.

- `sources` and `source_versions` rows are never hard-deleted. A purge sets `deleted_at` and `status=purged` and nulls `content_hash`, `original_filename` and `error_detail`. `source_code`, `title` and `version` remain so a tombstone can be shown.
- In **one transaction** the purge job deletes `parent_chunks`, `child_chunks`, `chunk_embeddings`, `dataset_tables`, `dataset_rows` and the blob. (These tables reference `source_versions` with `ON DELETE RESTRICT`, so deletion is always explicit.) The same transaction nulls `analytic_results.result/row_refs` and `hypothesis_evidence.quote`, strips excerpt text from stored citation cards that point at the purged handles, bumps the corpus version and writes an audit event.
- Cache entries that become unreachable expire within the 24 h TTL.
- Answer prose is kept as a derived artifact, and the README says so. WAL, dead tuples and evaluation outputs are documented limitations.

**Resolution order:**
1. Parse the handle.
2. Look up the `source_versions` row.
3. If it is purged, return `410 SOURCE_DELETED` with metadata.
4. Only then look up `parent_chunks`.

A tombstone is an explicit, resolved state, not a fake citation. The acceptance criterion "100% of rendered citations resolve" counts a tombstone as resolved-deleted, and the UI renders it as "source deleted".

---

## 5. Technology selections (verified current 2026-10-04)

| Concern | Choice | Why | Alternatives | Tradeoff accepted |
|---|---|---|---|---|
| Python | **3.13** via **uv** | Broadest wheel coverage (3.14 blocks some libraries) | 3.14, 3.12 | Install uv-managed 3.13 |
| API | **FastAPI ≥ 0.140.13** + native `fastapi.sse.EventSourceResponse` | Async, Pydantic-native, built-in SSE (with spec-compliant fixes) | sse-starlette, Litestar | — |
| DB | **PostgreSQL 18 + pgvector 0.8.7** (`pgvector/pgvector:0.8.7-pg18`) | One transactional store for app data, text, vectors, FTS, jobs, blobs and events | Dedicated vector DB, search engine | Single-node ceiling (§34) |
| DB access | SQLAlchemy 2.1 async + **psycopg 3** + Alembic; retrieval SQL written as explicit `text()` | One driver for the app and Procrastinate. Explicit SQL is easy to explain. | asyncpg (faster, but a second driver) | Slightly slower driver |
| Jobs | **Procrastinate 3.x** | Transactional enqueue, no extra broker, SKIP LOCKED + LISTEN/NOTIFY | Celery, RQ, Taskiq, Arq (maintenance-only) | Queue load on the primary (negligible at this scale) |
| Blobs | `BlobStore` → **Postgres bytea** (≤ 25 MB per file) | No shared disk between api and worker on Render, no extra service, transactional with the version row | S3/R2 (adapter documented) | Wrong choice at scale. §34 gives the switch point. |
| Cache | Redis 8 | Answer cache, query-embedding cache, rate limits; optional by design | In-process LRU only | One more service |
| Embeddings | **fastembed (ONNX) `BAAI/bge-small-en-v1.5` (384-d)** behind `Embedder`, with a file-backed cache | Local, free, deterministic, runs in CI, no torch. ~13 docs/s on M2 against ~5 for bge-base. | bge-base 768-d (Phase 7 A/B), Voyage-4, OpenAI 3-small | Lower ceiling than large hosted models. Measured. |
| Reranker | **fastembed `Xenova/ms-marco-MiniLM-L-6-v2`** cross-encoder behind `Reranker`, with configured threads | Real cross-encoder, Apache-2.0, CPU-viable | bge-reranker-base (6× slower), Voyage rerank-2.5-lite (hosted, prod switch), none | Domain mismatch and CPU latency (measured: ~1.7–2.9 s for 40 pairs of ~180 tokens with 1–2 threads), hence a pool of about 20 |
| Lexical | **Postgres FTS** with IDF-weighted coverage scoring ("BM25-lite") behind `LexicalRetriever` | Portable to every managed Postgres and deterministic | pg_textsearch BM25 (Postgres licence; not on managed providers; Phase 7 experiment), ParadeDB (AGPL), OpenSearch | No TF saturation |
| LLM | **Anthropic** via `LLMProvider`: agent and synthesis `claude-sonnet-5-5` (explicit effort), judge `claude-opus-5-5`, `FakeLLM` for tests | Native tool use with strict schemas, prompt caching | OpenAI, Bedrock | Provider dependency, kept swappable by the adapter |
| MCP | **`mcp` SDK 2.3.x (`MCPServer`)**, spec 2026-07-28, Streamable HTTP + stdio, exact pin | Official SDK; stateless spec | FastMCP 1.x (security fixes only), custom JSON-RPC | v2 is days old, so a Phase 0 spike, a thin adapter and an in-process fallback |
| Agent | **Custom explicit state machine** | Every bound is visible and unit-testable with FakeLLM | LangGraph, Anthropic tool_runner (beta), PydanticAI | We own about 500 lines of loop code |
| Analytics | **polars** over typed rows of an immutable version | Fast, typed, no SQL surface | DuckDB, pandas, SQL over JSONB | Extra dependency |
| Frontend | Next.js / React 19 / TS / Tailwind / shadcn-ui / TanStack Query / native EventSource / react-markdown | Spec default. EventSource gives reconnect and Last-Event-ID for free. | WebSockets, Redux | — |
| Observability | structlog JSON (with redaction) + persisted traces + `prometheus_client` | Debuggable without a platform | OpenTelemetry + Jaeger (later) | No distributed-trace UI |
| Seed generation (dev only) | reportlab (BSD), python-docx, python-pptx, openpyxl, templates over `world_model.yaml` | Byte-reproducible seeds | LLM-written prose (optional, committed) | Template prose is less natural |
| Security tooling | gitleaks, pip-audit/`uv` audit, Dependabot, defusedxml | — | — | — |

---

## 6. PostgreSQL schema

**Roles.**
- `ms_owner` owns the schema and runs migrations and Procrastinate's schema.
- `ms_app` is `LOGIN NOSUPERUSER NOBYPASSRLS`, owns nothing, and holds DML grants only. Both the API and the worker connect as `ms_app`.
- `ms_eval` is used only by the eval runner and dev-gated eval endpoints.

Startup and `/readyz` fail if the current role has `rolsuper OR rolbypassrls`.

**Tenant tables.** Every tenant table has `workspace_id`, `UNIQUE (workspace_id, id)`, composite foreign keys `(workspace_id, x_id) → parent(workspace_id, id)`, and **ENABLE + FORCE RLS** with `USING/WITH CHECK (workspace_id = app.current_workspace())`. The database itself therefore proves that a child cannot belong to another tenant's parent.

```
-- not tenant-RLS'd (read only via membership-checked repository used by the scope dependency)
workspaces(id uuid pk, code text unique CHECK (code ~ '^[A-Z][A-Z0-9]{1,15}$'), name, description, default_persona,
           llm_max_confidentiality enum default 'confidential', demo_read_only bool default false, created_at, updated_at)
workspace_members(workspace_id, principal_id, role, primary key(workspace_id, principal_id))

-- tenant tables (RLS)
workspace_corpus_state(workspace_id pk, version bigint not null default 0)          -- own row: no lock contention with metadata
sources(id, workspace_id, source_code CHECK (~ '^[A-Z0-9]{1,12}(-[A-Z0-9]{1,12}){0,5}$'), title, source_type,
        current_version_id, deleted_at, created_at, unique(workspace_id, source_code))
source_versions(id, workspace_id, source_id, version int, source_class, confidentiality, content_hash char(64) null,
        original_filename null, mime_type, byte_size, status enum(queued,parsing,chunking,embedding,indexing,ready,ready_degraded,
        failed,superseded,purged), reason enum(upload,reindex), error_code, error_detail, attempts int,
        parser_version, structure_version, chunking_policy_version, parent_count, child_count, health jsonb, created_at, ready_at,
        unique(source_id, version))
  + partial unique (source_id, content_hash, parser_version, structure_version) WHERE status NOT IN ('failed','superseded','purged')
source_blobs(source_version_id pk, workspace_id, bytes bytea)
parent_chunks(id, workspace_id, source_version_id, handle text, ordinal, locator jsonb, heading_path text[], text, token_count,
        content_hash, list_group_id, confidentiality, metadata jsonb, unique(workspace_id, handle))
child_chunks(id, workspace_id, parent_id, source_version_id, source_class, confidentiality, ordinal, kind enum(window,row,summary),
        text, heading_text text not null default '', char_start, char_end, token_count, text_sha256,
        tsv tsvector GENERATED ALWAYS AS (
              setweight(to_tsvector('english'::regconfig, coalesce(heading_text,'')),'A')
           || setweight(to_tsvector('english'::regconfig, coalesce(text,'')),'D')) STORED,
        tsv_body tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig, coalesce(text,''))) STORED,
        metadata jsonb)
chunk_embeddings(child_id, workspace_id, model_id text, embedding vector /* untyped; cast per model */, primary key(child_id, model_id))
dataset_tables(id, workspace_id, source_version_id, sheet_ordinal, name, columns jsonb /* name, type, role(free_text|context|numeric|date) */, row_count)
dataset_rows(id, workspace_id, table_id, row_number, parent_handle, values jsonb)
analytic_results(id, workspace_id, handle unique-per-ws, source_version_id, spec jsonb, result jsonb null, row_refs jsonb null, created_at)
conversations(id, workspace_id, persona, title, rolling_summary, summary_through_message_id, created_at, updated_at)
messages(id, workspace_id, conversation_id, role, content (canonical handles), citations jsonb /* incl. parent_content_hash */,
        sections jsonb, status enum(complete,incomplete,failed), query_run_id, model, usage jsonb, created_at)
query_runs(id, workspace_id, conversation_id, mode, original_query, normalized_query, standalone_query, persona, tool_plan_summary text[],
        retrieved_handles text[], reranked_handles text[], pack_handles text[], cited_handles text[], context_tokens, models jsonb,
        usage jsonb, cache_status, timings jsonb, termination_state, degradation_flags text[], config_hash, prompt_version,
        corpus_version_start bigint, error_class, status, created_at, finished_at)
run_events(run_id, workspace_id, seq int, type, payload jsonb, created_at, primary key(run_id, seq))
tool_runs(id, workspace_id, query_run_id, step, tool_name, input_sanitized jsonb, status, error_category, duration_ms, result_count,
        result_handles text[], created_at)
retrieval_traces(id, workspace_id, query_run_id, tool_run_id, query, stages jsonb /* per stage: (child_id, parent handle, rank, score, anchor) */,
        timings jsonb, flags text[], created_at)
hypotheses(id, workspace_id, title, statement, description, author, status enum(draft,investigating,reviewed), analyst_notes,
        synthesis jsonb, evidence_gaps jsonb, strength jsonb, analyzed_corpus_version bigint, last_analyzed_at, created_at, updated_at)
hypothesis_evidence(id, workspace_id, hypothesis_id, handle, parent_content_hash, stance enum(support,contradict,context),
        created_by enum(agent,user,evaluation), rationale, quote null, created_at, unique(hypothesis_id, handle, stance))
audit_events(id, workspace_id, actor, action, target, metadata jsonb, created_at)

-- eval schema (separate role; no ms_app grants)
eval.evaluation_runs(id, kind enum(retrieval,e2e,behavioral,judge_calibration), dataset_name, dataset_version, dataset_sha256,
        corpus_sha256, config jsonb, config_hash, git_sha, status, metrics jsonb, started_at, finished_at)
eval.evaluation_results(id, run_id, item_id, split, category, tags text[], outputs jsonb, metrics jsonb, passed, latency_ms, usage jsonb)

-- ops
spend_ledger(month date pk, cap_usd numeric, spent_usd numeric, reserved_usd numeric)   -- not tenant data
procrastinate_* (managed by Procrastinate; no RLS; app/worker role grants only)
```

**Scope plumbing.**
- `app.current_workspace()` is a STABLE plpgsql function. It returns `NULLIF(current_setting('app.workspace_id', true), '')::uuid` and raises `WORKSPACE_SCOPE_NOT_SET` when the setting is missing, so both pool-history failure modes produce the same error.
- An SQLAlchemy `after_begin` listener runs `SELECT set_config('app.workspace_id', :ws, true)` from the `WorkspaceScope` contextvar, and raises if there is no scope. Every autobegun or per-stage transaction is therefore re-scoped. Never use `SET` with a bind parameter: it is a syntax error.
- Retention: `run_events`, `tool_runs` and `retrieval_traces` older than 30 days are deleted by a nightly job.

**Why:** isolation is enforced in the schema, not only in application code. Versioned, immutable evidence keeps citations trustworthy.

**Alternatives:** schema-per-tenant or database-per-tenant (stronger isolation, heavy migrations); application-only scoping (one bug away from a leak).

**Tradeoff:** RLS costs some performance (§8) and needs careful role plumbing (§23).

---

## 7. pgvector strategy

- `chunk_embeddings.embedding` is an **untyped `vector`** column. Each model has its own **partial expression HNSW index**, and every dense query filters on `model_id = :active_model` and casts the same way. An embedder A/B is then "embed a second model and flip `ACTIVE_EMBED_MODEL`": no ALTER TYPE, and the baseline is never destroyed.
  ```sql
  CREATE INDEX ON chunk_embeddings USING hnsw ((embedding::vector(384)) vector_cosine_ops)
    WITH (m = 16, ef_construction = 64) WHERE model_id = 'bge-small-en-v1.5';
  ```
- **Canonical dense query.** It runs inside an explicit transaction. `SET LOCAL` outside a transaction is silently a no-op.
  ```sql
  SELECT set_config('hnsw.ef_search','100',true), set_config('hnsw.iterative_scan','relaxed_order',true);
  WITH dense AS MATERIALIZED (
    SELECT e.child_id, c.parent_id, (e.embedding::vector(384)) <=> :q AS distance
    FROM chunk_embeddings e JOIN child_chunks c ON c.id = e.child_id
    WHERE e.model_id = 'bge-small-en-v1.5' AND e.workspace_id = :ws
      AND c.source_version_id = ANY(:active_version_ids)              -- tiny set, read in the same txn
      AND c.confidentiality <= :max_conf                               -- LLM-facing paths only (§24)
      /* AND c.source_class = ANY(:classes) — only when filtered */
    ORDER BY distance LIMIT 100)
  SELECT child_id, parent_id, distance FROM dense ORDER BY distance + 0, child_id;   -- "+ 0" required on PG17+
  ```
- **Why HNSW plus iterative scan.** Filtered approximate nearest-neighbour search *overfilters*: HNSW returns `ef_search` candidates and only then applies the filter. Iterative scan fixes this. At demo scale (~3–5k children per workspace) an exact scan takes milliseconds, so HNSW serves the *scaling story*, not demo latency.
- **Measured guard.** The eval harness reports ANN recall against an exact scan, with the same query and `enable_indexscan=off`. EXPLAIN is checked to confirm the "ANN" run used HNSW. The **CI gate uses exact search** (§30) so that HNSW graph randomness never makes the gate flaky.
- **Alternatives:**
  - IVFFlat: needs training, lower recall.
  - Exact only: simplest, O(n).
  - `PARTITION BY LIST (workspace_id)`: the documented next step for many or large tenants.
- **Tradeoff:** HNSW costs build memory and post-filter subtleties, in exchange for sub-linear search.
- **Dimension ceiling:** `vector` HNSW indexes go up to 2,000 dimensions, `halfvec` up to 4,000.

## 8. Indexing strategy

| Index | Purpose |
|---|---|
| Per-model partial expression HNSW on `chunk_embeddings` | Dense candidates |
| btree `(model_id, text_sha256)` via join on child | Embedding reuse lookup (with the file cache) |
| GIN `(tsv)` | Lexical candidates. **Caveat:** see below. |
| btree `(workspace_id, source_version_id)` on child_chunks | Workspace and active-version filter, exact-scan path |
| btree `(parent_id)` on child_chunks | Collapse and highlight |
| unique `(workspace_id, handle)` on parent_chunks | Resolution in O(log n) |
| btree `(source_version_id, ordinal)` on parent_chunks | Neighbor expansion |
| btree `(workspace_id, conversation_id, created_at)` on messages | History |
| PK `(run_id, seq)` on run_events; btree `(query_run_id)` on tool_runs and retrieval_traces | Replay, trace views |

**RLS × GIN caveat.** `@@` (`ts_match_vq`) is not `LEAKPROOF`. Under FORCE RLS the planner will not promote `tsv @@ q` into a GIN index condition ahead of the security-barrier policy, so for `ms_app` lexical search filters the workspace's rows sequentially.
- **Decision (demo scale):** accept this, back it with EXPLAIN evidence and an EXPLAIN-based regression test, and document it. At 3–5k children it costs milliseconds.
- **Scale remedy, documented:** move lexical candidate SQL to a narrow SELECT-only `ms_retrieval` role that bypasses RLS and is used only by the scope-enforcing lexical repository with an explicit `workspace_id` predicate. Alternatively, partition by workspace. `ALTER FUNCTION … LEAKPROOF` needs superuser and is unavailable on managed Postgres.
- The HNSW `ORDER BY` is not a filter condition, so it is unaffected; this was verified.

---

## 9. Parent/child document model

- **Parent is the citation unit.** It is stable, derived from document structure, shown to the user and sent to the generator.
- **Child is the retrieval unit.** Its internal id is `parent_handle#w{n}` and it never appears in an answer.
- Parents never cross a page, slide, row or Q&A boundary. The cap is 800 tokens: larger units are split at paragraph or sentence boundaries into consecutive blocks.
- **Narrative children** are 192-token windows with 32-token overlap, inside one parent, with tokens counted by the embedder's tokenizer.
  - Retrieval text is `heading_text` + window. The dense input gets a contextual header (`{source title} › {heading path}`), so isolated windows keep their topic.
  - 192 + header + query stays under both the 512-token embedder limit and the cross-encoder window.
- **Rows** (the row-flood fix):
  - A row with a non-empty free-text cell gets one child: `{table} | {context col=val, …} | {free-text col}: <verbatim>`.
  - A purely numeric row gets a **parent only**. It is resolvable and available to analytics, but it is **not** a retrieval unit, because numeric questions go to the analytics tool.
  - Each sheet's **table-summary parent** has one embedded child: title, column names, roles and descriptions, row count, and categorical levels.
- **Lists:** a list is kept whole inside one parent when it fits the cap. Larger lists share a `list_group_id`, which structural enumeration uses.
- `char_start` and `char_end` on a child map into the parent text, so the evidence viewer can highlight the matched span.
- **Retrieval ranks parents** (§14). Generation receives parent text, or a window centred on the anchor child when a parent exceeds its per-item budget.

**Decision:** cite parents.
- *Why:* tuning chunk size must not orphan handles or invalidate gold labels. Parents are what a consultant verifies ("slide 6", "row 185", "p.4 ¶2").
- *Alternatives:* cite children (precise, but unstable); cite whole documents (useless provenance).
- *Tradeoff:* a citation can span more text than the exact supporting sentence. The highlighted anchor span narrows it in the UI.

## 10. Evidence-handle grammar

Canonical form `WORKSPACE/SOURCE@vVERSION:LOCATOR`, rendered `[NORTHSTAR/SURVEY-2026@v1:R185]`.

```
handle   = ws "/" src "@v" ver ":" loc                    ; total length ≤ 96
ws       = [A-Z][A-Z0-9]{1,15}                            ; immutable workspace code
src      = [A-Z0-9]{1,12} ( "-" [A-Z0-9]{1,12} ){0,5}     ; immutable per-workspace source code
ver      = [1-9][0-9]{0,3}                                ; source version (content or structure change)
loc      = unit ( "." unit ){0,3} | "AQ" HEX{12}          ; structural locator | computed analytics result
unit     = kind [1-9][0-9]{0,6}
kind     = "SL" | "SH" | "P" | "B" | "S" | "N" | "R" | "Q" | "T"    (slide, sheet, page, block, section, notes, row, Q&A, table)
```

Example handles by format:

| Format | Example handle |
|---|---|
| PDF | `NORTHSTAR/BRAND-STRATEGY@v1:P4.B2` |
| DOCX interview | `NORTHSTAR/INTERVIEWS@v1:S3.Q7` |
| PPTX slide / notes | `NORTHSTAR/Q3-REVIEW@v1:SL6` · `…:SL6.N1` |
| CSV row | `NORTHSTAR/SURVEY-2026@v1:R185` |
| XLSX row / table summary | `NORTHSTAR/PRODUCT-PERF@v1:SH2.R12` · `…:SH2.T1` |
| Analytics result | `NORTHSTAR/PRODUCT-PERF@v1:AQ3F9A0C21B7D4` |

Cell references resolve through row handle + column name. The column appears in the locator label and the citation card, so the grammar needs no column unit.

| Required property (spec §11) | How it is met |
|---|---|
| Deterministic | A pure function of workspace code, source code, version and structural locator. `AQ` = `sha256(normalized_spec ‖ source_version_id)[:12]`. |
| Unique | The workspace prefix makes it system-unique, and `unique(workspace_id, handle)` enforces that in the database. |
| Resolvable by backend code | One resolver (§16). No model is involved. |
| Stable | Parents are immutable per version (§4.2). Chunk tuning never touches handles. Parser or structure changes mint new versions. |
| Associated with workspace and source | Syntactically (prefix) and in the database (composite FKs). |
| Safe to render | The alphabet is `[A-Z0-9v/@:.-]` (the lowercase `v` appears only in the `@v` version marker), so no markdown or HTML can be expressed. |
| Invalid ⇒ rejected | `MALFORMED_HANDLE`. Never fuzzy-matched. |
| Valid ⇒ exact evidence | Parent text + locator + provenance. `parent_content_hash` is stored with every citation, so drift is detectable ("evidence changed"). |

Grammar tests: Hypothesis round-trip (`format(parse(h)) == h`), fuzzing (arbitrary strings never raise unexpected errors and never resolve), and length and alphabet limits.

### 10.1 Alias layer (D2)

Each pack item gets an alias `E1..En` for that answer only. The model may emit only `[E\d{1,2}]`. The hold-back gate (§21) and the verifier map aliases to canonical handles. Aliases are never persisted as evidence identities; `run_events` keeps them only as run-scoped SSE display records (see ADR-0004).

**Alternative considered: Anthropic `search_result` blocks with `citations.enabled`.**
- They are GA and guarantee valid pointers, with `cited_text` spans.
- *Why not primary:*
  - The core trust primitive should not depend on one vendor's feature, given the spec's provider adapter.
  - FakeLLM and offline eval paths must behave identically.
  - Native citations attach to text blocks rather than inline positions.
  - They cannot be combined with structured outputs.
- Verification stays ours either way: native citations do not force every claim to be cited.
- *Phase 7:* an optional A/B of alias vs native citations on citation precision, latency and tokens.

## 11. Lexical retrieval

- **Indexed text.** Weighted `tsv` (heading `A`, body `D`) for matching, plus a body-only `tsv_body` for document frequencies, so copied headings don't inflate DF.
- **Query lexemes come from Postgres, never from Python tokens.**
  - Python handles only NFKC, lowercasing and extraction of quoted phrases.
  - Lexemes come from `SELECT DISTINCT lexeme FROM unnest(to_tsvector('english', :q))`, so stemming and stopwords match the index exactly.
  - The OR query is `string_agg(quote_literal(lexeme),' | ')::tsquery`. Quoted phrases use `phraseto_tsquery('english', :phrase)` combined with `||`.
  - User text never reaches `to_tsquery`. An empty or NULL query returns no lexical candidates; it is not an error.
- **IDF-weighted coverage scoring ("BM25-lite": IDF, no TF saturation).**
  - `idf(t) = ln(1 + (N − df + 0.5)/(df + 0.5))`, with df and N from `ts_stat` over `tsv_body`, cached per (workspace, corpus_version).
  - `score = Σ idf(t) · [tsv @@ t]`. Phrase matches get a bonus. Ties are broken by `ts_rank_cd('{0.1,0.2,0.3,0.3}', tsv, q, 1)` (heading weight damped), then by child id.
  - Only near-universal terms (DF > 90%) are pruned, and the query is never pruned to empty.
- **Determinism.** Every ranked SQL with a LIMIT ends with `ORDER BY score DESC, child_id`. Top 100 children.
- **Tests.**
  - A heading-flooded section and a keyword-stuffed chunk: the genuinely relevant child must rank first.
  - Adversarial inputs (`gen z`, `$129`, `ratio:3`, `(x`, `& |`, `O'Brien`, stopwords only).
  - A Hypothesis property: arbitrary text never raises and always gives the same ordered IDs.
- **`search_evidence_keyword` tool.** Exact, phrase or all-terms modes.
  - Candidates come from `tsv @@` without a LIMIT, then raw text is checked (so `"$129"` and `"Gen Z"` match literally).
  - Returns *exhaustive* counts per source (grep-like), plus the top hits.
- **Why FTS rather than a BM25 extension:** it is portable to every managed Postgres and deterministic. IDF weighting closes most of the gap.
- **Experiment:** pg_textsearch BM25 locally in Phase 7, behind the same interface.

## 12. Semantic retrieval

- The query embedding uses the model's query instruction (bge: "Represent this sentence for searching relevant passages: "). It is cached in-process (LRU) and in Redis, keyed by (model, sha256(query)).
- The canonical SQL is in §7: top 100 children with the workspace, active-version and confidentiality filters, plus class filters when given.
- **Per-class lanes.** When the call carries two or more `source_classes`, the dense and lexical lanes run once per class (`LIMIT 40` each) and their union is fused. Class coverage is therefore guaranteed at candidate generation, not hoped for after reranking.
- If the embedder fails (exception, timeout or open circuit), the dense half is skipped and the call returns `RETRIEVAL_LEXICAL_FALLBACK`.

## 13. Candidate-generation sizes

Initial values, tuned in Phase 7 against recall@pool and latency.

| Stage | Size | Rationale |
|---|---|---|
| Dense | 100 children, deduped to parents | Wide net; cheap |
| Lexical | 100 children, deduped to parents | Same |
| Fused | parents; per-source cap ≈ 1/3 of the rerank pool | Prevents one large source from crowding the pool |
| Rerank pool | **20 parents** (≤ 40 pairs) | Measured CPU cost: ~1.7–2.9 s for 40 pairs at ~180 tokens with 1–2 threads on an M2 |
| After rerank and collapse | ≤ 20 parents | |
| Tool result (top-k) | 8 (max 12) | |
| Neighbor additions | ≤ 4 (Phase 7, only if measured to help) | |
| Evidence pack | ≤ 12 items, ≤ 9,000 tokens | Synthesis budget |

**Recall@pool** is the recall over the fused top-20 parents. It is the reranker's ceiling: candidate sizes are tuned on it, and the reranker is tuned on Recall@k and MRR after reranking.

## 14. Fusion (RRF) at the parent level

1. Each lane (dense, lexical; per class when applicable) returns ranked children.
2. Within each lane, dedupe to `parent_id` and keep the best-ranked child as that lane's **anchor**. The parent's rank in that lane is the anchor's rank.
3. `score(p) = Σ_lanes w_lane / (k + rank_lane(p))` with `k = 60` (Cormack et al. 2009) and `w = 1.0`. Weights are configurable and ablated.
4. Ties are broken by best single-lane rank, then by parent handle, which keeps fusion deterministic.
5. Apply the per-source cap, then cut to the top 20 parents.

Traces record each child's dense rank, lexical rank and anchor flags.

**Why parent-level:** RRF's signal is *agreement between retrievers*. If dense finds window 2 of parent P and lexical finds window 3, fusing children misses that both found P. A unit test covers exactly this case.

**Why RRF:** it is rank-based, so cosine distances and lexical scores never need calibrating against each other.

**Alternatives:**
- Weighted score fusion: needs normalization and is brittle.
- Learned fusion: no training data.
- Reranker-only over the union: leaves no fused order to fall back on.

**Tradeoff:** RRF ignores score magnitude. That is acceptable because the cross-encoder re-scores.

## 15. Reranking, collapse, balancing, expansion

**Rerank.**
- Pairs:
  - A parent of 350 tokens or less (rows, slides, Q&A) is scored as one pair: (query, heading + parent text).
  - A larger parent is scored as (query, heading + anchor child) for each distinct lane anchor, up to 2.
  - Parent score is the maximum of its pair scores (**MaxP**, Dai & Callan 2019).
- Execution: ONNX in a bounded thread pool, with `RERANK_THREADS` taken from the container's CPU quota and a semaphore against oversubscription.
- Timeout: about 1.5× the measured p95 on the target instance, set at the Phase 3 deploy spike. On failure or timeout the fused order is kept and the call reports `RERANKER_UNAVAILABLE`.
- **Why a cross-encoder:** a bi-encoder embeds query and passage independently. A cross-encoder attends across both, which fixes ordering at the top, and the top is what the generator sees.
- **Alternatives:** no reranker, LLM reranking (slow, costly, non-deterministic), a hosted reranker (production switch if CPU p95 is too high), bge-reranker-base.
- **Tradeoff:** the MS MARCO training domain differs from business documents. This is measured, and switching is a configuration change.

**Collapse.**
- Parent-level ranking makes collapse mostly implicit. It remains an explicit step that keeps the best-scoring anchor child, for highlighting, and the `hit_count`.

**Source and class balancing.** Greedy and deterministic.
- At most 3 parents per source, unless the call targets a single source or the parents are structural-enumeration siblings.
- Each requested class keeps its best item if that item is within the class-local top-k or within Δ of the class's best score. This is a relative floor; raw logits are uncalibrated.
- Requested classes come only from explicit tool arguments, set by the agent, persona or user.

**Neighbor expansion** (Phase 7, if measured to help).
- For the top-2 anchors in narrative formats whose anchor touches the parent's edge, add the previous or next parent.
- At most 4 additions, marked `expansion_kind=adjacent`.

**Structural enumeration** (Phase 7, if measured to help).
- Triggered by list intent (regex, or the agent's `intent="enumeration"` argument).
- Includes every sibling parent of the top parent's `list_group_id` or heading group, budget-capped, marked `expansion_kind=sibling_list`.

## 16. Source-resolution system

`EvidenceResolver.resolve(scope, handle, run_id?)`:
1. Parse with the grammar. Malformed returns `MALFORMED`.
2. The handle's `ws` must equal the scope's workspace code. If not, return NOT_FOUND, which reveals nothing about other workspaces.
3. Look up `source_versions`. Purged returns `410 SOURCE_DELETED` with metadata.
4. Look up `parent_chunks` by (workspace_id, handle), or `analytic_results` for `AQ` handles.
5. Return:
   - `{handle, text, content_hash, locator{…, label}}`
   - `source{title, type, class, filename, version, status, confidentiality, ingested_at}`
   - `context{prev_excerpt, next_excerpt}`
   - `highlights[]` and `retrieval{dense_rank, lexical_rank, fused_rank, rerank_score}`, both only when `run_id` is given
   - `provenance{parser/structure/chunker versions}`

One resolver, backed by Postgres, serves the `get_evidence` tool, the evidence API, verification, cache-hit revalidation, hypothesis links and briefs. Resolution reads the same rows that retrieval returns. Two separate stores (an on-disk corpus and a vector store) can drift out of sync, so there is only one.

## 17. MCP server and tool governance

- `MCPServer("marketsignal")` exposes the tools of a **transport-agnostic governance registry**. Each entry has a Pydantic input model, a Pydantic output model, an implementation, a timeout, result caps and a required capability.
- **Tools are pure request → response.** No per-run state lives in the MCP server. The evidence pool and call budgets belong to the agent runtime (§19). Optional defence in depth: an atomic `UPDATE query_runs SET tool_calls = tool_calls + 1 WHERE id = :run AND tool_calls < :max RETURNING …`.
- **Trusted context.** The API mints a capability token: HS256 with a dedicated `MCP_TOKEN_KEY`, the algorithm pinned, `aud=mcp`, `iss`, `iat`, `nbf`, `exp` set to the run deadline, `jti=run_id`, `sub=principal`, `ws`, `wsc`, `persona`, `tools=[…]`, `max_conf`.
  - The verifier checks signature and claims, allows ±5 s clock skew, and confirms the run is still `running`, which revokes the token on cancel or done.
  - The server builds `ToolContext` from the claims. **No tool schema contains workspace, user, path or SQL fields.**
- **Governance pipeline per call:**
  1. Verify the token.
  2. Check the tool against `claims.tools`.
  3. Strictly validate input.
  4. Run under `asyncio.wait_for(timeout)` with Postgres `SET LOCAL statement_timeout`.
  5. Cap output (items and characters; flag `TRUNCATED`).
  6. Normalize errors to `VALIDATION_ERROR | POLICY_DENIED | NOT_FOUND | TIMEOUT | UNAVAILABLE | INTERNAL`.
  7. Write a `tool_runs` audit row.
  8. Return typed `structured_content`, with document-derived text marked untrusted.
- **Network exposure:** `/mcp` rejects non-loopback clients unless `MCP_PUBLIC=true`. Authorization and cookie headers are redacted from all logs.
- **LLM-facing schemas:** a `to_anthropic_tool()` adapter does the following:
  - strips keywords that strict mode does not support (min/max length, ranges, `maxItems`);
  - turns `oneOf` into `anyOf` and drops `discriminator`;
  - sets `additionalProperties: false` everywhere;
  - uses required-but-nullable fields;
  - sorts tools by name so the prompt cache stays stable.

  Server-side Pydantic validation remains the security boundary. A keyed CI contract test sends the full tool array with `strict: true` to `count_tokens`.

## 18. Concrete MCP tool schemas

```python
# --- catalog ---
class ListSourcesIn(BaseModel):                 # list_sources
    source_classes: list[SourceClass] | None
class SourceCard(BaseModel):
    source_code: str; title: str; source_class: SourceClass; source_type: SourceType; status: IngestStatus
    version: int; parent_count: int
    tables: list[TableCard]          # structured datasets: name, columns[{name, type, role}], row_count

class GetSourceMetadataIn(BaseModel):           # get_source_metadata
    source_code: SourceCode

# --- retrieval ---
class SearchEvidenceIn(BaseModel):              # search_evidence (full hybrid pipeline)
    query: str                                  # 2..400 chars (validated server-side)
    source_classes: list[SourceClass] | None    # ≥2 ⇒ per-class lanes
    source_codes: list[SourceCode] | None       # ≤10
    top_k: int | None                           # default 8, max 12
    intent: Literal["auto", "enumeration"] | None
class EvidenceHit(BaseModel):
    handle: Handle; source_code: str; source_title: str; source_class: SourceClass; locator_label: str
    snippet: str                                # ≤280 chars of the anchor child (untrusted)
    anchor_child_id: str                        # child window that matched (D1 anchor)
    anchor_char_start: int; anchor_char_end: int  # anchor span offsets into the parent text
    expansion_kind: Literal["none", "adjacent", "sibling_list"]   # "none" = direct hybrid hit
    dense_rank: int | None; lexical_rank: int | None; fused_rank: int; rerank_score: float | None
class SearchEvidenceOut(BaseModel):
    hits: list[EvidenceHit]; classes_found: dict[SourceClass, int]; warnings: list[DegradationCode]

class KeywordSearchIn(BaseModel):               # search_evidence_keyword
    terms: list[str]                            # 1..6 terms, each 1..60 chars
    match: Literal["all", "any", "phrase"] | None
    source_classes: list[SourceClass] | None; source_codes: list[SourceCode] | None
    limit: int | None                           # default 10, max 20
class KeywordSearchOut(BaseModel):
    total_matches: int; matches_by_source: dict[str, int]   # exhaustive
    hits: list[EvidenceHit]; warnings: list[DegradationCode]

class GetEvidenceIn(BaseModel):                 # get_evidence
    handles: list[str]                          # 1..8; parsed server-side; malformed reported per item
class ResolvedEvidence(BaseModel):
    handle: str; found: bool; miss_reason: Literal["MALFORMED", "NOT_FOUND", "SOURCE_DELETED"] | None
    text: str | None                            # truncated observation text; the pack re-resolves full text by handle
    locator_label: str | None; source_title: str | None; source_class: SourceClass | None

# --- analytics (flattened for strict-mode compatibility) ---
class StructuredMetricsIn(BaseModel):           # query_structured_metrics
    source_code: SourceCode; table: str
    op: Literal["describe", "aggregate", "top_n", "compare", "pct_change"]
    metrics: list[MetricSpec] | None            # {column, fn ∈ sum|mean|median|count|min|max}, ≤4
    group_by: list[str] | None                  # ≤2
    filters: list[FilterSpec] | None            # {column, op ∈ eq|ne|in|gt|gte|lt|lte|between|contains, value}, ≤5
    sort: SortSpec | None; limit: int | None    # ≤50
    segment_column: str | None; segment_a: str | None; segment_b: str | None          # compare
    period_column: str | None; from_period: str | None; to_period: str | None          # pct_change
    n: int | None; direction: Literal["top", "bottom"] | None; label_column: str | None # top_n
class StructuredMetricsOut(BaseModel):
    handle: Handle                              # computed AQ… (deterministic)
    columns: list[str]; rows: list[list[str | float | int | None]]   # ≤50
    row_count_scanned: int; contributing_rows_sample: list[Handle]   # ≤10
    spec_normalized: dict; warnings: list[DegradationCode]

# --- hypothesis (composite deterministic workflow; §37.2) ---
class AnalyzeHypothesisIn(BaseModel):           # analyze_hypothesis_evidence
    statement: str                              # 10..600 chars
    source_classes: list[SourceClass] | None
class StancedEvidence(BaseModel):
    handle: Handle; stance: Literal["support", "contradict", "context"]; quote: str; rationale: str
    source_class: SourceClass; quote_verified: bool
class StrengthLabel(BaseModel):
    label: Literal["strong_support", "moderate_support", "contested", "leans_against", "insufficient"]
    basis: str                                  # rendered from counts, e.g. "5 supporting passages from 3 sources across 2 classes…"
class AnalyzeHypothesisOut(BaseModel):
    support: list[StancedEvidence]; contradict: list[StancedEvidence]; context: list[StancedEvidence]
    gaps: list[str]; strength: StrengthLabel; warnings: list[DegradationCode]

# --- harness-local (not an MCP data tool) ---
class FinishResearch(BaseModel):                # finish_research — the only way the agent ends gathering
    sufficient: bool; gaps: list[str]
```

Column and table names are checked against the inferred schema, so they are never interpolated into SQL. Analytics run in polars over the immutable version's typed rows. There is no SQL surface at all.

## 19. Bounded agent state machine (research mode)

```
INIT ─▶ AGENT_STEP ──tool_use──▶ EXECUTE (all tool_use blocks; excess beyond budget → POLICY_DENIED results) ─▶ OBSERVE ─┐
  │         ▲                                                                                                          │
  │         └──────────────────────── bounds / deadline checks ◀──────────────────────────────────────────────────────┘
  │   finish_research | end_turn | bound hit | gather deadline
  ▼
(end_turn with zero successful searches ⇒ deterministic fallback search, PLANNER_NO_TOOL_FALLBACK)
BUILD_PACK ─(empty)─▶ TERMINATE(no_relevant_evidence)
  │
  ▼
SYNTHESIZE ─▶ VERIFY ─(structural fail ∧ time left)─▶ draft_reset ─▶ SYNTHESIZE(feedback) ─▶ VERIFY
  │              └─(fail again | LLM down | refusal | max_tokens)─▶ EVIDENCE_ONLY
  ▼
FINAL ─▶ DONE(termination_state)
```

| Bound (config) | Default | On hit |
|---|---|---|
| `AGENT_STEP_LIMIT` | 4 (research) | Stop gathering and proceed to BUILD_PACK with the evidence gathered so far. Flag `AGENT_STEP_BUDGET_EXHAUSTED`. |
| `AGENT_MAX_TOOL_CALLS` | 10 | Same. Excess parallel calls return `POLICY_DENIED`. |
| `AGENT_MAX_CONSECUTIVE_TOOL_ERRORS` | 3 | Circuit opens; proceed to BUILD_PACK with the evidence gathered so far. `TOOL_CIRCUIT_OPEN`. |
| Duplicate (tool, canonical args) | 2nd repeat | Repeated call; stop gathering. `AGENT_REPEAT_CALL_STOPPED`. |
| `TOOL_TIMEOUT_S` | 8 (analytics 5) | `TOOL_TIMEOUT`, counted as an error. |
| `OBS_MAX_TOKENS` | 1,000 | Observation truncated. |
| `AGENT_MAX_CONTEXT_TOKENS` | 40,000 (counts replayed thinking + tools) | **Stop gathering** → BUILD_PACK. `AGENT_CONTEXT_LIMIT`. Never edits history. |
| `EVIDENCE_POOL_MAX` | 40 parents | Stop gathering. |
| `PACK_MAX_ITEMS / PACK_MAX_TOKENS` | 12 / 9,000 | Budget fill. `PACK_BUDGET_TRUNCATED`. |
| `RUN_DEADLINE_S` (gather 35) | 60 | Gather timeout → proceed to BUILD_PACK with the evidence gathered so far. Overall timeout → `timeout`. |
| Agent effort / max_tokens | `low` / 4,096 | Fixed within the route, for cache stability. |
| Synthesis effort / max_tokens | `low` / 8,000 | Length is controlled by the answer contract, not by the cap. |

Rules:
- **Append-only transcript.** Each assistant response's full `content` (thinking blocks, including empty ones, plus text and tool_use) is resent unchanged on every step of the run. Sonnet 5.5 binds thinking blocks to the exact prefix, and editing earlier tool results invalidates them. If mid-run trimming is ever needed, use server-side context editing. Client-side stubs are never used.
- **Nothing the model reasons is shown or stored.** Thinking and any agent text are excluded from UI, logs and the DB once the run ends. Progress events are built deterministically from tool arguments. Model-derived query text appears in summaries as quoted plain text truncated to about 80 characters.
- **Tool use.** Native tool use with strict schemas and `tool_choice=auto`. Forced tool choice returns 400 on Sonnet/Opus 5.5. The harness-local `finish_research` tool is the expected way to end. An `end_turn` with prose means the prose is discarded; the agent's `max_tokens` keeps that cheap.
- **Deterministic fallback.** If the first LLM call fails, run the `standard` gather path (`PLANNER_UNAVAILABLE_FALLBACK`).
- **Thinking configuration** is pinned explicitly (adaptive, explicit effort). Any prefix-binding behaviour control is set explicitly in tests and production, so behaviour does not depend on account defaults. *Phase 0 spike verifies the current API surface for this.*

**LLM call envelope.** One wrapper handles every LLM call:
- Per-call `timeout = min(phase budget, remaining deadline)`.
- SDK `max_retries=0`, with one policy of our own: retry 429, 529 or 5xx once with jitter, only if budget remains.
- `stop_reason` handling: `refusal` → `MODEL_REFUSAL` → evidence-only; `max_tokens` → `GENERATION_TRUNCATED` (not counted as a citation failure).
- Spend reservation (§32.3) before the call, reconciled against `usage` afterwards.
- Cancellation: one cancel scope per run. Tool SQL is bounded by `statement_timeout` and ONNX work by a semaphore, so running thread work finishes but its result is discarded.

Termination states:

| State | Meaning |
|---|---|
| `completed` | Normal completion |
| `completed_with_limited_evidence` | Answer produced, but gaps flagged or evidence thin |
| `no_relevant_evidence` | Empty pack; abstained |
| `generation_unavailable` | Evidence-only response |
| `retrieval_degraded` | Any retrieval degradation flag set |
| `tool_failure` | Circuit open and the pack is empty |
| `timeout` | Deadline hit with no usable evidence gathered |
| `cancelled` | User cancelled |

Precedence: `cancelled > timeout > tool_failure > no_relevant_evidence > generation_unavailable > retrieval_degraded > completed_with_limited_evidence > completed`. Flags carry the details.

## 20. Conversation and context management

- The agent writes retrieval queries from the question plus a **compact conversation state**, never from the full transcript.
- Conversation state is built deterministically from previous verified answers, with no extra LLM call:
  - a rolling summary of at most 400 tokens, taken from each answer's **Answer** section and finding headings;
  - the last 2 user questions;
  - up to 20 previously cited handles, each with a one-line label.
- **Agent context:** a static system prompt and tool definitions (prompt-cached; the cache breakpoint sits on the last tool and the system block), then the state, the question and the step pairs. Observations are compact. Full evidence text never enters the agent context.
- **Synthesis context:** the cached system prompt, the pack (≤ 9k tokens), the question and a one-paragraph summary.
- **Result:** per-turn input tokens are O(pack + bounded state), independent of conversation length. An eval item checks this with a 30-turn synthetic conversation.

## 21. Streaming / SSE protocol

**Endpoints:**
- `POST /api/workspaces/{ws}/conversations/{cid}/runs` returns `202 {run_id, stream_url}`.
- `GET /api/workspaces/{ws}/runs/{rid}/events?st=<stream token>[&last_event_id=n]`
- `POST /api/workspaces/{ws}/runs/{rid}/cancel`

**Stream token.** HS256, `aud=sse`, `run_id`, `ws`, `sub`, `exp` = run max duration + 15 min replay window. It is redacted from access logs, and responses send `Referrer-Policy: no-referrer`.

**Event format.** Every event carries `id: <seq>`, `event: <type>`, `data: {"run_id", "seq", "ts", …}`. A `: ping` heartbeat is sent every 15 s.

| Event | Payload | Notes |
|---|---|---|
| `run_started` | conversation_id, persona, mode | |
| `status` | phase ∈ routing/planning/searching/analyzing/synthesizing/verifying, message | Deterministic text, never model reasoning |
| `tool_started` | step, tool, kind ∈ search/keyword/resolve/catalog/analytics/hypothesis, summary | Sanitized arguments |
| `tool_completed` | step, tool, status, result_count, classes_found, duration_ms | |
| `evidence` | item_count, classes, truncated | Pack assembled |
| `draft_reset` | attempt, reason | Client clears the draft before a regeneration |
| `token` | attempt, text | Passed through the alias hold-back gate; coalesced to ~100 ms |
| `citation` | attempt, alias, handle, source_title, source_class, locator_label | Once per alias when validated |
| `warning` | code, message | |
| `final` | message_id, content (canonical), citations[], sections, verification | **Source of truth.** Replaces the draft. |
| `error` | code, message, retryable | |
| `done` | termination_state, flags, cache_status, timings | **Always last** |

**Alias hold-back gate.** Text is held from a `[` only while it can still become `[E\d{1,2}]`, so at most 4 characters are ever held. It is unit-tested with randomized delta splits.

**Replay log.** Events are appended to `run_events` in Postgres.
- A live tail goes through in-process fan-out, with LISTEN/NOTIFY for subscribers in other processes.
- Replay sends `seq > Last-Event-ID`.
- A startup reaper marks orphaned `running` runs as interrupted and emits `done`.

The run executes independently of its subscribers: a disconnect is not a cancel. A partial answer is persisted as `incomplete`, without unverified citations. Responses set `X-Accel-Buffering: no`, and the frontend connects to the API origin directly, because dev proxies buffer SSE.

**Why SSE over WebSockets:** traffic is one-way, server to client. SSE runs over plain HTTP (proxies, HTTP/2, auth), and EventSource reconnects automatically with Last-Event-ID. Client actions are ordinary POSTs. WebSockets would add bidirectional connection state that nothing here needs.

**Why stream a draft before verification:** perceived latency under 2 s versus 8–15 s of silence. The draft is labelled as unverified, chips stay pending until validated, `final` replaces the draft, and an evidence-only fallback clears it.
- *Alternative:* buffer until `final`. Safest, but slow.
- *Tradeoff:* the user can briefly see a sentence that verification removes. The labelling makes this explicit.

## 22. Caching and invalidation

| Cache | Key | Value | Invalidation | On Redis failure |
|---|---|---|---|---|
| Answer | sha256(workspace_id, corpus_version, normalized_query, persona, sorted filters, mode, retrieval_cfg_hash, prompt_version, model ids + efforts) | final answer, citation cards, pack handles, corpus_version, run summary | **Implicit**: a corpus_version bump makes old keys unreachable. TTL 24 h. Config, prompt and model changes change the key. | Bypass. `CACHE_UNAVAILABLE` logged at most once per interval. |
| Query embedding | (model, sha256(text)) | vector | Model change | In-process LRU only |
| Embedding reuse (ingest) | (model, sha256(text)) in a **file-backed cache** (`.cache/embeddings/<model>.parquet`; CI `actions/cache`) plus DB lookup | vector | Model change | n/a |
| Lexical DF stats | (workspace, corpus_version) | idf table | corpus_version | Recompute |

Write rules:
- Only clean results are cached (`completed`, no degradation flags).
- Turns whose standalone query depended on conversation context are not cached.
- The **write is conditional:** re-read corpus_version at the end of the run and store only if it equals `corpus_version_start`, so an answer never mixes corpus versions under one key.

What bumps corpus_version: ingest becoming ready, re-embed completion, delete or purge, and reclassification.

## 23. Workspace isolation (defense in depth)

1. **Route.** Every tenant route is `/api/workspaces/{ws}/…`. The principal must be a member (single demo principal now). A contract test asserts that every non-health, non-auth route contains `{ws}`.
2. **Repositories.** Every data-access function requires a `WorkspaceScope`, which only the authorizing dependency or the worker job prologue can construct. No unscoped helpers exist, and a test enumerates the repositories to prove it.
3. **Postgres RLS** under the non-superuser, non-BYPASSRLS `ms_app` role (§6), with ENABLE + FORCE on all tenant tables. Scope is set per transaction with `set_config(…, true)` in an `after_begin` hook. Missing scope means `WORKSPACE_SCOPE_NOT_SET` and the operation fails closed.
4. **Composite foreign keys** make cross-tenant references structurally impossible.
5. **Tools** take the workspace from capability-token claims only.
6. **Handles.** The workspace code is in the handle and must match the scope. A foreign handle returns NOT_FOUND, so its existence is never revealed.
7. **Cache keys** include `workspace_id`. Run event streams are bound to `ws` (404 on mismatch).
8. **Tests (deterministic, CI, as `ms_app`):**
   - with scope A, workspace B's rows count 0;
   - a cross-workspace INSERT fails WITH CHECK;
   - with no scope, the query errors;
   - the worker cannot read another workspace's children;
   - the dense and lexical lanes never return B's ids.
9. **Behavioral evaluation.** A decoy workspace (*Southpeak Outdoor*, 6 docs with canary facts) must never leak into Northstar answers, and the reverse. Checked deterministically from traces and answers.

## 24. Prompt injection and data trust boundaries

**Trust zones:**
- **Trusted:** system prompts, tool schemas, server config, token claims.
- **Semi-trusted:** the user's question. It expresses intent but cannot change policy.
- **Untrusted:** all document content, tool outputs, filenames and titles, and LLM output until verified.

**Controls:**
1. **Limit blast radius first.** Tools are read-only and workspace-pinned, with no network, filesystem or write tools. A successful injection cannot exfiltrate across workspaces or take actions.
2. **Delimit evidence.** Evidence is wrapped as `<evidence alias="E3" class="customer">…</evidence>`. Attributes come only from server values. Document text has `& < > "` escaped, and closing tags are neutralized.
3. **Constrain output.** Only `[E#]` citations are accepted. A shared `SafeMarkdown` renders both draft and final:
   - react-markdown with `allowedElements=[p, strong, em, ul, ol, li, h3, h4, code, blockquote]`, `unwrapDisallowed`, `skipHtml`;
   - **no `img` or `a`** (the default rehype-sanitize schema allows remote images, so it is not sufficient);
   - plus a CSP `default-src 'self'; img-src 'self' data:; connect-src 'self' <api origin>`.

   This blocks markdown-image exfiltration from the *draft* as well as the final answer.
4. **Ingestion heuristics.** An injection-pattern scanner sets `metadata.suspected_injection`, shown as a badge. The text stays citable data. The scanner is evaluated on held-out phrasings.
5. **Confidentiality.** `workspaces.llm_max_confidentiality` (default `confidential`) caps LLM exposure. It is carried in the capability token as `max_conf` and enforced as a SQL predicate in every LLM-facing tool and in pack assembly. Restricted content can appear only in UI-side evidence views.
   - The provider factory refuses hosted embedders or judges for workspaces with sources above `internal` unless a flag is set.
   - A behavioral test asserts a restricted canary never appears in any recorded LLM request (FakeLLM transcript).
6. **Vendor posture.** The README states that the demo is synthetic-only, the LLM vendor's data-retention posture, and why a custom MCP client loop is used: the hosted MCP connector is not ZDR-eligible.

## 25. Observability

- Structured JSON logs (structlog) correlated by `run_id` and `workspace_id`. A processor redacts `authorization`, `cookie`, `st` and token claims.
- Persisted traces:
  - `query_runs`: mode, timings per stage, tokens, cache status, flags, termination state, config hash, citations.
  - `tool_runs`: per call.
  - `retrieval_traces`: candidates per stage before and after rerank, plus the pack.
  - `run_events`: what the user saw.
- Prometheus `/metrics` (protected): stage-latency histograms, tool error counters, cache hit ratio, LLM tokens and spend, degradation counts.
- A dev **Runs** page renders a full trace. No model reasoning is stored. OpenTelemetry is a documented later step.

---

## 26. Evaluation architecture

- **Code path.** `marketsignal.evaluation` (CLI `ms-eval`) runs the **production pipeline code**.
- **Runners:**
  - `retrieval`: deterministic, local models, no LLM, exact search in CI.
  - `e2e`: needs an LLM key; manual or nightly.
  - `behavioral`.
  - `judge_calibration`.
- **Ablations (retrieval):**
  - lane and pipeline variants: dense-only, lexical-only, hybrid (RRF), + rerank, + balance, + neighbor/structural;
  - ANN vs exact, full vs compact row serialization, bge-small vs bge-base, BM25 experiment.
  - **Every arm maps child lists to parents and dedupes by first occurrence before scoring**, so the arms are compared fairly.
- **Agent ablation (e2e):** agent vs single-pass on cross-source and hypothesis items. Measures class coverage, agent evidence recall, correctness, latency and tokens.

**Metric definitions.** Gold uses `required_facts[{fact_id, grade 1|2, stance?, satisfied_by: [parent handles]}]`.
- Recall@k and hit@k: share of grade-2 facts with ≥ 1 satisfying handle in the top-k distinct parents.
- MRR: from the first grade-2 hit.
- nDCG@10: gain = grade, each fact counted once.
- **Recall@pool:** recall over the fused top-20 parents (the reranker's ceiling).
- **Recall@pack:** recall over the final pack after balancing and expansion.
- **Agent evidence recall:** recall over the union of a run's packs, read from traces. No judge needed.
- Source-class coverage on cross-source items.
- Breakdowns **by category, by source class and by format** (PDF / DOCX / PPTX / rows).

**Grounding metrics.**

| Metric | Method | Gated? |
|---|---|---|
| Citation validity (resolves, in workspace) | Deterministic | Yes, 100% |
| Citation-in-pack | Deterministic | Yes, 100% |
| Numeric faithfulness | Deterministic | Yes |
| Finding-citation coverage | Deterministic | Yes |
| **Citation support precision**: share of (claim, cited passage) pairs where the passage supports the claim | LLM judge (NLI) | Reported |
| **Citation recall vs gold**: share of required facts whose satisfying handle is cited | Deterministic | Reported |
| **Unsupported-claim rate**: factual sentences with no citation, or with only unsupported citations | Deterministic + judge | Reported |

**Generation metrics.**
- Deterministic answer correctness: ledger facts (entity + value) must appear in the answer.
- LLM-judged faithfulness and answer relevancy, using RAGAS-style definitions implemented in-house and documented. No more metrics than these.

**Behavioral metrics.** Scored over *all* items.
- Labels: answer / qualify / abstain / resist. They come from the answer contract's structure and `termination_state`. The judge only flags prose that contradicts the status.
- Gated: **abstain/qualify recall ≥ 0.90** on insufficient-evidence items, and **over-refusal ≤ 0.10** on answerable items.
- **Injection:**
  - counted only when the trace shows the injected parent reached a pack (exposure rate reported);
  - k = 5 runs per item;
  - four attack goals: output canary, citation hijack, tool-argument steering, policy/format override;
  - reported as attack success rate with a rule-of-three bound.
- **Isolation:** deterministic (canary strings and foreign handles in traces and answers), target 0.
- Refusal rate (`MODEL_REFUSAL`) is reported.

**Judge.**
- `claude-opus-5-5`: a different model from the generator, though same-family bias is not excluded.
- Binary supported/unsupported (plus partial) under strict JSON. The judge prompt version and effort are part of `config_hash`.
- **Calibration set:** about 100–120 claim/passage pairs, roughly 50/50 supported vs unsupported. Unsupported pairs are generated from the ledger (distractor numbers, swapped entity or segment, superseded values); about 40 are hand-labelled from real outputs.
- Reported: judge sensitivity and specificity with Wilson CIs, measured precision alongside the judge's false-positive rate, and a flip rate across 3 re-judges. The Batch API is used.
- **CI gates only on deterministic metrics.**

**Statistics.**
- Every rate gets a Wilson 95% CI. MRR and nDCG get bootstrap CIs.
- Configs are compared with **paired tests on the same items** (exact McNemar for hit@k, paired bootstrap for continuous metrics).
- EVALUATION.md states the **minimum detectable difference** at the current n (about 15 points at n ≈ 100). Smaller deltas are reported as "not distinguishable".
- Cells with n < 10 are reported as k/n. The test split is never broken down by category.

**Tuning protocol (≥ 2 documented iterations).**
1. Hypothesis written down beforehand, from a failure analysis on **dev**.
2. One change per iteration.
3. Paired comparison on dev.
4. Frozen config evaluated once on **test** at milestones.
5. Per-iteration report.

**Reports.** JSON plus Markdown, including:
- `config_hash`: retrieval config, prompts, models and efforts, dataset version, corpus sha256, git sha;
- metrics with CIs, ablation tables, latency and tokens;
- the diff against the baseline, with regressions highlighted;
- failing items.

## 27. Gold-set strategy

**World model → corpus.** `seed_data/world_model.yaml` defines:
- segments and pain points, with prevalence;
- competitors' positioning (fictional: *Vantage Athletic*, *Kinetic Lab*, *Pace & Co.*);
- product, channel and category metrics;
- planted contradictions, superseded values and gaps.

Template generators render the documents in every format. A **fact ledger** records each fact as `fact_id → (source_code, anchor, surface forms)`:
- *anchor*: a unique planted sentence for narrative text, or a row key (sheet + key-column value);
- *surface forms*: value + unit + entity, plus a few alternate spellings.

**Freeze against reality.** `ms-eval freeze-gold`:
1. Ingest a fresh seed through the **real pipeline**.
2. Find the active parent(s) containing each anchor (after normalization) and fill in `satisfied_by` handles.
3. Record any surface-form matches outside the hinted source *for review*, without auto-adding them, so distractors are never labelled relevant.
4. Write the resolved ledger and dataset, with `parser_version`, `structure_version` and `corpus_sha256` in the manifest.

**Integrity (CI):**
- Every `satisfied_by` handle resolves **and** its parent text contains the fact's anchor or a surface form.
- Each anchor matches exactly one active parent.
- `content_hash` matches.
- No `llm_draft` item lacks human review.
- Dataset and corpus sha256 match the manifest.

**Question independence.**
- Questions are written in a separate step from the world-model fact record only, without seeing the rendered text. Provenance is recorded.
- Each item gets a retriever-independent **lexical-overlap hardness score**: the share of shared non-stopword lemmas plus the longest shared n-gram. Items are binned low/mid/high, and **every ablation is reported per bin**.
- **Fresh-seed holdout (Phase 7, retrieval-only):** re-sample the world model with new names, numbers and template variants, regenerate, auto-derive the gold set, and run the frozen config once. The gap from dev measures how far the system has overfit the corpus.

**Item schema:**
`id, version, split, query | turns[], workspace, persona, category, tags, required_facts[{fact_id, grade, stance?, satisfied_by[]}], expected_source_classes, reference_answer?, expected_behavior ∈ answer|qualify|abstain|resist, hypothesis?, canaries[], provenance ∈ generated|human|llm_draft_reviewed`.

**Categories (spec §20.2):** single-source fact, cross-source synthesis, exact number, named entity, enumeration, ambiguous, insufficient evidence, contradiction, prompt injection, hypothesis support/contradiction, customer-voice (rows), isolation, long-conversation follow-up.

**Size and splits.**
- v0 has about 40 curated items by the end of Phase 2. Results are **directional**, with CIs shown.
- v1 has about 120 curated items by Phase 7. These are the spec §20.4 gate set.
- A ledger-generated **ablation set** of about 250 template-plus-paraphrase retrieval queries is clearly labelled easier and never used for gates.
- **Dev/test split 70/30, grouped by fact_id or source group**, so no planted fact appears in both splits.

**Spec §20.4 quality gates adopted:**
- 100% of returned citations resolve.
- 0 cross-workspace leaks.
- Recall@10 ≥ 0.85 on the curated test split after tuning, reported with a CI and alongside Recall@pack.
- Citation precision ≥ 0.90, judge-dependent and reported together with the judge's specificity.
- Abstain/qualify recall ≥ 0.90 and over-refusal ≤ 0.10.
- All deterministic contract tests pass.

If the corpus makes a gate unrealistic, the reason and an evidence-based replacement are documented.

**Corpus composition** (spec §4: 20–40 sources, ≥ 4 classes, ≥ 2 structured datasets, ≥ 1 deck):

| Class | Northstar sources (~26 total) |
|---|---|
| Internal | brand strategy PDF; Q3 strategy review PPTX; product performance XLSX; channel performance CSV; FY plan memo MD |
| Customer | survey CSV (~600 respondents with verbatims); interviews DOCX (12, Q&A); reviews CSV (~800); Gen Z focus-group DOCX; support-themes PDF |
| Competitor | 3 fictional competitors × {positioning/web snapshot MD or PDF, investor deck PPTX or annual-report excerpt PDF} |
| Market | Gen Z athletic trends PDF (v1 and v2, superseded); personalization willingness-to-pay study PDF; category sizing XLSX; channel-shift note MD |
| Planted | 2 injection carriers (a review row and a competitor page); contradiction pairs |

Southpeak decoy: 6 docs with canaries. Sandbox: empty, for visitor uploads.

---

## 28. Failure and degradation behavior

| Failure | Detection | Behavior | Code | User sees |
|---|---|---|---|---|
| Postgres down | Connection or statement error | Fail fast. Never answer from the LLM alone. | `DB_UNAVAILABLE` | Error banner |
| Redis down | Connection error or open circuit | Bypass cache. In-process rate limit with *tighter* limits. | `CACHE_UNAVAILABLE` | Nothing (logged) |
| Embedder fails (query) | Exception, timeout or circuit | Lexical-only | `RETRIEVAL_LEXICAL_FALLBACK` | "Retrieval degraded" |
| Embedder fails (ingest) | Same | NULL embeddings, `ready_degraded`, re-embed job | `EMBEDDER_UNAVAILABLE` | Badge on the source |
| Reranker fails | Exception or timeout | Fused order | `RERANKER_UNAVAILABLE` | Warning |
| No hits or empty pack | Pack empty | Abstain and suggest source classes | `EVIDENCE_EMPTY` | "Insufficient evidence" |
| LLM down (planning) | Envelope error | Standard gather path | `PLANNER_UNAVAILABLE_FALLBACK` | Warning |
| Agent ends without searching | Zero successful searches | Fallback search | `PLANNER_NO_TOOL_FALLBACK` | — |
| LLM down (synthesis) | Envelope error | Evidence-only: ranked cards with extractive snippets | `LLM_SYNTHESIS_UNAVAILABLE` | Evidence cards, no prose |
| Refusal or truncation | `stop_reason` | `draft_reset` → evidence-only | `MODEL_REFUSAL` / `GENERATION_TRUNCATED` | Warning |
| Tool timeout or errors | wait_for or error category | Counts toward the circuit; proceed to BUILD_PACK with the evidence gathered so far | `TOOL_TIMEOUT`, `TOOL_CIRCUIT_OPEN` | Warning |
| Verification fails | Verifier | Repair → regenerate once (if time) → evidence-only | `CITATION_VERIFICATION_FAILED` | Warning |
| Context over budget | Token budget | Deterministic truncation by rank, class reservation first | `PACK_BUDGET_TRUNCATED` / `AGENT_CONTEXT_LIMIT` | Dev detail |
| Sources still indexing | Status | Answer over the ready sources | `SOURCES_PENDING` | "N sources still indexing" |
| Upload parse failure | Parser or container check | Source marked failed, with a category | `INGEST_EXTRACT_FAILED` (+ category) | Sources page |
| MCP unreachable | Client error | Fall back to the in-process transport over the same registry (no model choice changes) | `TOOLS_TRANSPORT_FALLBACK` | Warning (dev) |
| Spend cap reached | Ledger reservation refused | Evidence-only | `BUDGET_EXHAUSTED` | Notice |

Per-dependency circuit breakers move between closed, open and half-open. **Every code has a named test.** Nothing degrades silently.

## 29. Testing strategy

**Unit tests (no I/O):**
- Handle grammar: Hypothesis round-trip and fuzz.
- Resolver ordering, including tombstones.
- Scope enforcement.
- Parsers, using fixtures built at runtime by factories, including bomb, encrypted, macro and truncated files.
- Parent and child builders, row serialization, locators.
- Lexical query builder: adversarial inputs and determinism.
- Parent-level RRF, including the agreement test.
- MaxP rerank and its fallback.
- Balancing with relative floors.
- Cache keys and conditional cache writes.
- Alias gate with randomized delta splits.
- Verifier: sections, numeric faithfulness, inference tags.
- Degradation mapping and termination precedence.
- Analytics DSL: rejects unknown columns or ops; deterministic `AQ` hashes.
- Strength rules.
- **Agent bounds with FakeLLM scripted transcripts:** step limit, circuit breaker, repeated-call stop, context limit, `end_turn`-without-search fallback, parallel-call budget, refusal, `max_tokens`.
- **Byte-identical request prefix** across agent steps.
- SSE event-order contract.

**Integration tests** (Postgres + pgvector + Redis, connected as `ms_app`):
- upload → ready → retrieve → resolve;
- standard and research runs with FakeLLM through real Streamable HTTP MCP and token auth;
- no-hit;
- embedder down → lexical-only; reranker down; Redis down;
- RLS negative tests;
- delete → purge contract (a canary string is gone everywhere, the handle returns 410, the blob is gone);
- revert, retry-after-fail and concurrent identical uploads;
- the transactional-enqueue rollback leaves no job;
- SSE resume with `last_event_id`;
- iterative-scan settings are active inside the retrieval transaction;
- a filtered query returns exactly LIMIT rows;
- an EXPLAIN test for HNSW use.

**Contract tests:**
- OpenAPI snapshot, SSE JSON schemas, MCP tool-schema snapshot. A tool-definition change also invalidates prompt caches.
- Route-scoping test.
- Strict-schema `count_tokens` check (keyed, optional).

**Eval regression:** the retrieval runner on the dev split in CI, with floors (§30).

**Frontend:**
- vitest: chip parsing, SSE reducer, SafeMarkdown strips `img`, `a` and HTML.
- Playwright smoke, ask → stream → open citation, against a FakeLLM backend.
- Manual Safari and incognito check on the deployed URL.

**Load:** 20 concurrent runs plus concurrent ingestion; p50 and p95 per stage.

**Coverage target:** 80% on the backend core packages.

## 30. CI pipeline (GitHub Actions)

`ci.yml` runs on every PR and push. Budget: under 15 minutes with a warm cache.
1. ruff, mypy (strict on `evidence`, `retrieval`, `tools`, `agent`, `generation`), eslint, tsc, and the import-linter contracts.
2. gitleaks, pip-audit / `uv` audit, a check that rejects files over 5 MB, and a check that rejects reference-material path patterns.
3. Backend unit tests.
4. Backend integration tests with service containers `pgvector/pgvector:0.8.7-pg18` and `redis:8`. A setup step runs `db/init/01_roles.sql`, and the tests connect as `ms_app`.
5. **Retrieval eval smoke:**
   - full seeded corpus, dev-split queries;
   - **exact search**, so HNSW randomness never affects the gate;
   - local ONNX models and the embedding file cache restored from `actions/cache`.

   Floors are the baseline minus max(measured run-to-run noise, paired MDD). The run also fails on newly failing items from a pinned canary subset. **Baselines are generated in CI on the same runner image**, and a baseline may change only in a PR that includes the diff report.
6. Gold integrity checks.
7. Frontend lint, typecheck, test and build.
8. Docker builds for api/worker and frontend, with explicit build contexts and `.dockerignore`.

`eval-full.yml`: manual dispatch with the `ANTHROPIC_API_KEY` secret. Runs e2e, behavioral and judge calibration, and uploads the report artifact.

## 31. Local development environment

**Prerequisite:** a Docker runtime. On this 8 GB / 94%-full-disk machine, OrbStack or Colima (lighter than Docker Desktop) with a VM of about 4 GB.

`docker compose up` starts:
- **postgres:** `pgvector/pgvector:0.8.7-pg18`, `shared_buffers=128MB`, initdb role script.
- **redis:** 8.
- **api:** uvicorn, with `/mcp` mounted. Models are baked into the image or kept in a named cache volume.
- **worker:** Procrastinate, with `mem_limit`.
- **frontend:** under profile `ui`.

`just seed` loads Northstar and Southpeak through the **real upload API**, so seeding exercises ingestion.

Health endpoints:
- `/healthz` (liveness).
- `/readyz`: DB reachable, migrations at head, app role is not superuser or BYPASSRLS, models loaded. Redis being down is reported as degraded, not as unready.

**Light mode (recommended on this laptop):** Postgres and Redis run in Docker, while api and worker run natively with `uv run` and Next runs natively.

**Memory:** about 2.5–3.5 GB in total. The single-command path is `just demo`, which runs `compose up`, migrations, seed and frontend.

## 32. Deployment architecture

**Recommended: Vercel (frontend) + Render (api web service, worker background service, Render Postgres with pgvector, Render Key Value).**
- **Cost:** about $80/mo plus Vercel. Local models need the 2 GB instances for both api and worker. About $45 is possible only if embedding and reranking are hosted and the instances fit in 512 MB.
- **What you get:** one `render.yaml` blueprint, managed TLS, no NAT or public-IPv4 traps, deploy on merge, and `alembic upgrade head` as a pre-deploy step.
- **Preconditions, checked in a Phase 0 spike:**
  - Render's pgvector version is at least 0.8 (needed for iterative scans).
  - The default credential can `CREATE ROLE` and is not superuser or BYPASSRLS.
  - If either fails, the fallback is Railway with the `pgvector/pgvector` image.
- **CPU spike at the end of Phase 3:** deploy the api image with models and run 10 queries. Record embed and rerank p50/p95 and peak RSS, then set the rerank timeout and pool. If rerank p95 is above about 1.5 s, use `RERANKER=voyage-rerank-2.5-lite` in production and keep local ONNX in dev and CI.

**AWS ECS/Fargate: reference architecture, documented and optional to build.**
- ECS Express Mode or CDK, ARM Fargate tasks in public subnets with no NAT gateway.
- ALB with idle timeout ≥ 300 s, plus 15 s SSE heartbeats.
- RDS PostgreSQL (verify the pgvector version), ElastiCache Serverless Valkey, S3 (through the `BlobStore` adapter), Secrets Manager, ECR.
- About $75–85/mo without NAT, about $140+/mo with NAT, and noticeably more IaC and networking work.
- Copilot CLI reached end of support on 2026-06-12, so it is not used.

**Why Render is primary:** the interview evaluates system design, retrieval, agent governance and evaluation. Days spent on VPC, ALB and IAM add little signal. The AWS design is still documented with a diagram and a cost table, and the same containers and environment config deploy there without code changes.

**Operations:**
- Secrets live in the platform secret stores.
- Migrations follow expand/contract and run before deploy.
- Health checks use `/readyz`.
- Rollback means redeploying the previous image, which works because migrations stay backward-compatible.
- Demo data is seeded by a one-off job.

### 32.1 Browser auth boundary (Vercel and Render are different sites)

`vercel.app` and `onrender.com` are both on the Public Suffix List, so a cookie would be third-party, and Safari ITP blocks third-party cookies. **No cookies are used:**
- `POST /api/auth/demo` checks the passcode and returns a signed session token. The SPA keeps it in memory and in sessionStorage.
- REST calls send `Authorization: Bearer <token>` directly to the API. CORS has an exact origin allowlist, never `*`, and needs no credentials mode.
- SSE uses the run-scoped stream token in the URL (§21).
- No cookies means CSRF does not apply. An Origin check is still enforced on non-GET routes as defence in depth.
- *Alternative:* a same-origin Vercel rewrite with a first-party cookie, or custom `app.`/`api.` subdomains.

**Phase 9 exit check:** ask → stream → final → reconnect mid-run, tested manually in Safari and in Chrome incognito against the deployed URL.

### 32.2 Demo mode (public URL)

- The session token carries a random `session_id`. Rate limits are fixed-window counters in Redis, per session and per IP. If Redis is down, an in-process limiter applies *tighter* limits, documented as per-instance.
- Seeded workspaces are `demo_read_only`, so upload, delete and reindex return `POLICY_DENIED`. Visitor uploads go to a **Sandbox** workspace with per-session quotas, which is reset nightly. Northstar answers never cite Sandbox content, which also demonstrates isolation.
- `/docs` and `/openapi.json` are disabled or gated in production. `/metrics` requires a token. `/mcp` accepts loopback only.

### 32.3 Spend control

- **Postgres spend ledger.** Before each LLM call, an atomic `UPDATE … SET reserved = reserved + :worst_case WHERE spent + reserved + :worst_case <= cap RETURNING` reserves the worst-case cost. After the call, the reservation is reconciled against `usage`. If no reservation is possible, the run goes evidence-only with `BUDGET_EXHAUSTED`.
- **Backstop:** a dedicated Anthropic Console workspace with a monthly spend limit for the deployed key.

## 33. Cost-conscious decisions

- Local embeddings and reranker, so no per-query model cost for retrieval.
- Sonnet 5.5 at low effort by default. Opus only for judging.
- A standard single-pass mode for simple questions.
- Prompt caching of the static system prompt and the tool definitions, which are byte-stable and name-sorted.
- An answer cache, and a bounded evidence pack.
- Batch API for judge runs.
- No NAT gateways.
- A single Postgres for data, vectors, text search, jobs, blobs and events: no separate vector DB, broker, search cluster or object store.
- End-to-end evals run manually. Retrieval evals are free in CI.

## 34. Scaling path

- **100 users:** one api and one worker. Postgres with 1–2 GB. The bottleneck is LLM latency and cost.
- **10k users:**
  - Stateless api replicas. `run_events` plus LISTEN/NOTIFY already support multiple replicas.
  - The reranker and embedder become a CPU bottleneck; move them to a separate inference service or a hosted reranker.
  - A Postgres read replica for retrieval.
  - Lexical moves to the `ms_retrieval` role or to per-workspace partitions (the RLS × GIN caveat).
  - Blobs move to S3.
  - Workers autoscale on queue depth.
  - LLM rate limits are managed through queueing, model routing and caching.
- **1M users or large corpora:**
  - Shard by tenant: Citus, or a database per large tenant.
  - Move candidate generation to an engine with native hybrid search (OpenSearch, Vespa or Elastic), fed by CDC from Postgres. **Postgres remains the system of record for evidence text and handles**, so resolution never depends on the search index.
  - GPU inference, and an LLM gateway with quotas.
- **When to leave Postgres for search:** at roughly 50–100M vectors; when filtered ANN across many tenants degrades even after partitioning; or when ranking or faceting needs exceed what portable Postgres offers.
- **Stays synchronous:** run creation, evidence resolution. **Asynchronous:** ingestion, re-embedding, purge, eval runs, cache warming.

## 35. Major risks

| Risk | Impact | Mitigation |
|---|---|---|
| Interview date vs scope | Unfinished system | M1 cut line (§38), phase estimates, re-plan if a phase slips more than 50% |
| Non-public material leaks into the public repo | Irreversible | Private notes and all non-public reference material are kept outside the repository; `.dockerignore`; CI size, path and content checks plus gitleaks block accidental commits; prior-work references stay at résumé level |
| Synthetic corpus too easy or circular | Inflated metrics | Question independence, overlap bins, distractors, fresh-seed holdout, grouped split |
| Gold labels drift from real locators | Wrong evaluation | Anchors + `freeze-gold` + content-checking integrity tests |
| LLM API specifics (thinking binding, effort, strict schemas) | Runtime 400s, truncation | Phase 0 spike, append-only transcript, explicit effort, schema adapter, keyed contract test |
| CPU rerank latency on hosted instances | Slow or degraded demo | Pool of 20, thread config, deploy spike, hosted-reranker switch |
| RLS misconfiguration (superuser bypass) | False isolation confidence | Role topology, readiness guard, negative tests as `ms_app` |
| New SDK majors (mcp 2.x, anthropic 1.x) | API churn | Exact pins, thin adapters, in-process transport fallback |
| Judge non-determinism and bias | Noisy metrics | Deterministic gates, calibration with negatives, reported FPR |
| 8 GB RAM / 94%-full disk | Slow or unstable development | Light mode, small Postgres config, image pruning, embedding cache |
| Render pgvector version, role privileges | Feature or isolation gaps | Phase 0 spike, Railway fallback |
| Public demo abuse | Cost blow-up | Demo gate, rate limits, spend ledger, console limit |
| Haiku 4.5 retirement (≥ 2026-10-15) | Broken model id | Not used |

## 36. ADRs

Each ADR is a one-paragraph stub in Phase 0 and is completed when its component is built. The ADR index and the spec deviation register are kept in `docs/adr/README.md`.

| ADR | Topic |
|---|---|
| 0001 | PostgreSQL + pgvector as the single system of record (incl. blobs, jobs, events) |
| 0002 | Hybrid retrieval with parent-level RRF and IDF-weighted FTS |
| 0003 | Parent/child chunks; the parent is the citation unit; immutable parents per version |
| 0004 | Evidence-handle grammar, alias citation layer (vs native citations), hold-back gate |
| 0005 | Local ONNX cross-encoder (MaxP) with fused-order fallback; hosted-reranker switch |
| 0006 | MCP governed boundary: mounted, loopback-only, capability tokens, stateless tools |
| 0007 | Custom bounded agent state machine; append-only transcript; finish_research |
| 0008 | SSE (POST run + GET events, Postgres replay log, stream token) over WebSockets |
| 0009 | Workspace isolation: scoped repositories + RLS under a non-owner role + composite FKs |
| 0010 | Postgres-native job queue (Procrastinate) with transactional enqueue |
| 0011 | Answer cache keyed on corpus_version with conditional writes |
| 0012 | Local embeddings via provider interface; per-model embedding table |
| 0013 | Evaluation: world model + freeze-gold, deterministic CI gates, judge calibration, statistics |
| 0014 | Deployment: Render + Vercel, token-based browser auth, demo mode (AWS documented) |
| 0015 | Standard vs research modes with deterministic routing |
| 0016 | Purge contract and source versioning semantics |
| 0017 | Fictional competitor corpus (D6) |
| 0018 | Personas as policy configuration, not tool restriction (D9) |
| 0019 | Testing strategy and load testing (D11) |

---

## 37. Product capabilities in detail

### 37.1 Personas (spec §5)

Personas are configuration only: YAML files in `agent/personas/`.

| Persona | Priority classes (soft prior) | Default mode | Prompt policy |
|---|---|---|---|
| Growth Strategy | market, internal financial/performance, customer, competitor | research | Where to play; size and attractiveness; separate evidence from thesis |
| Customer Insights | customer (survey, interviews, reviews) | standard | Prevalence and segment differences; quote verbatims; no causal overreach |
| Brand Strategy | internal brand, competitor, customer perception | research | Positioning vs perception gaps; whitespace |
| Marketing Strategy | channel datasets, customer, competitor marketing | research | Channel and message effectiveness, with the metrics behind them |
| Generalist | none | auto | Minimal bias |

**How a persona affects retrieval:** when a call carries no explicit `source_classes`, balancing gives the persona's priority classes a *guaranteed slot*, subject to the relative relevance floor. It is **never a hard filter**. All personas get the same read-only tools (D9).
- *Why a soft prior:* it changes emphasis without hiding evidence.
- *Alternatives:* a hard filter (misses cross-class evidence) or prompt-only (weak, and not measurable).
- *Tradeoff:* it adds a little ranking complexity. A small Phase 7 persona ablation measures the effect.

### 37.2 Growth Opportunity Workspace (spec §7)

A **deterministic workflow**, exposed both as `POST /api/workspaces/{ws}/hypotheses/{id}/analyze` (a run with SSE) and as the `analyze_hypothesis_evidence` tool.

1. **Reformulate.** An LLM call with structured output produces 3 support queries, 3 challenge (disconfirmation) queries and the relevant classes. A template fallback applies if the LLM is unavailable.
2. **Retrieve.** Each query runs through the standard pipeline in parallel (top 8). Results are unioned per track and deduped by parent.
3. **Classify stance.** One LLM call with structured output covers up to 24 candidates and returns `{stance ∈ support|contradict|context|irrelevant, quote, rationale}`. A **deterministic verbatim-quote check** follows: the normalized quote must be a substring of the parent text, otherwise the item is downgraded to context with `QUOTE_NOT_FOUND`. An abstain option is allowed.
4. **Strength.** Transparent rules over distinct sources and classes, a quantitative-evidence flag and support vs contradiction counts. **No probabilities.**

   | Label | Rule |
   |---|---|
   | `strong_support` | ≥3 supporting sources across ≥2 classes, including quantitative evidence, and ≤1 contradicting source |
   | `moderate_support` | ≥2 supporting sources, and support > contradiction |
   | `contested` | Both sides have ≥2 sources |
   | `leans_against` | Contradiction ≥2 sources and > support |
   | `insufficient` | Otherwise |

   The `basis` text is rendered from the counts.
5. **Gaps.** Required evidence classes (customer, competitor, market, quantitative) with no stanced items become deterministic gaps. LLM-suggested next research questions are labelled as suggestions.
6. **Synthesis** uses the answer contract in hypothesis mode and is verified.
7. **Persistence and rerun.**
   - Agent-created links are replaced on rerun; user-created links are kept.
   - Links to superseded or purged versions are flagged.
   - `analyzed_corpus_version` drives the UI's stale badge.

**Why a workflow rather than an agent:** it guarantees that *both* tracks run, which is the whole point of the feature, and it makes analyses reproducible for evaluation.
- *Alternative:* let the agent decide. It may skip the challenge track.
- *Tradeoff:* less flexibility, which is acceptable because hypothesis analysis has a fixed shape.

### 37.3 Opportunity brief (spec §6.6)

`GET /api/workspaces/{ws}/briefs/export?hypothesis_id=…|conversation_id=…&handles=…&format=md` assembles a fixed template with these sections:
- question or opportunity statement
- evidence-backed findings
- supporting evidence
- contradictory evidence
- assumptions and gaps
- recommended next research questions
- a citations appendix (handle, locator label and excerpt, from the resolver)

Only the statement and the findings summary go through pack → synthesize → verify. Gaps and next questions are labelled as non-evidence. The brief carries a "decision support, not a decision" statement and is stamped with the corpus_version.

PDF comes from a print-CSS view rather than server-side rendering. Briefs are generated on demand; a `briefs` table is added only if saved briefs become necessary. A test asserts that every citation resolves and every section is present. Delivered in Phase 6.

### 37.4 Structured analytics (spec §24)

- Typed operations are listed in §18.
- Column types are inferred with explicit rules. Errors: `UNKNOWN_COLUMN`, `TYPE_MISMATCH`, `UNSUPPORTED_OP`, `EMPTY_RESULT`.
- Execution uses polars over the immutable version's rows. Each version's rows are cached in an LRU.
- Results carry a deterministic `AQ` handle, a normalized spec, a sample of contributing row handles and the count scanned.
- Resolving the `AQ` handle returns the stored spec and result. Verification can re-execute it.
- **Numeric matching:** relative tolerance 0.5%. Percentages, currency and thousands formats are normalized before matching.

---

## 38. Phases, estimates, and the interview cut line

Estimates are focused working days with Claude implementing and the user reviewing. If any phase slips by more than 50%, re-plan.

| Phase | Deliverables | Exit criterion (verified, not assumed) | Est. |
|---|---|---|---|
| **0** | `git init`; uv/Python 3.13; FastAPI and Next skeletons; compose (PG + pgvector, Redis) with role init; Alembic baseline with RLS scaffolding and readiness guard; health checks; CI skeleton; ADR stubs. **Spikes:** MCP v2 mount + JWT + loopback client call; Anthropic thinking/effort/strict-tool surface; Render pgvector version and role privileges. | `docker compose up` → `/readyz` green as `ms_app`; CI green; spike notes recorded | 1.5 |
| **1** | World model + generator (Northstar + 6-doc Southpeak); container validation; parsers (6 formats); structure → parents → children (row policy); handles; embeddings + file cache; FTS columns; resolver + evidence endpoint; Sources API + Sources page; workspace create/list | Seeded corpus ingests through the API; a planted fact is found by lexical **and** dense search and resolves to exact text with locator; seed time and throughput recorded | 3.5 |
| **2** | Dense + lexical (canonical SQL), parent-level RRF, rerank (MaxP) + fallback, balancing, retrieval traces, `freeze-gold`, gold v0 (~40) + ablation set, retrieval runner + stats + ablations, CI eval smoke | Report: dense-only vs lexical-only vs hybrid vs +rerank, with CIs and overlap bins | 3 |
| **3** | Standard mode end to end: pack, synthesis (Anthropic + FakeLLM), alias gate, verifier (answer contract), evidence-only fallback, abstention; runs + `run_events` + SSE; chat UI (SafeMarkdown, chips, draft/final); evidence viewer; **Render CPU spike** | 100% of cited handles resolve; no-hit items abstain; answerable items are not abstained; SSE order contract test passes | 3 |
| **4a/4b** | Governance registry → agent state machine over the in-process transport (FakeLLM tests) → Streamable HTTP + capability tokens (parity test); router; personas; progress events; dev Runs page | Demo 2 query makes at least 2 tool calls across at least 2 classes and is grounded; bounds tests pass | 3 |
| **M1** | **Interview-ready core:** Demos 1, 2, 5 and 6 (Phase 2 ablation as the before/after) from a clean seed; SYSTEM_DESIGN, RETRIEVAL_DEEP_DIVE, AGENT_AND_MCP, PRIOR_WORK_PATTERNS; DEMO.md; INTERVIEW_GUIDE skeleton (grows each phase); recorded backup demo video | Rehearsed demo works from a clean environment | 1 |
| **5** | Analytics DSL + tool, computed handles, mixed synthesis | Demo 3 works, with row and aggregate provenance | 1.5 |
| **6** | Hypotheses CRUD, dual-track workflow, stance + quote check, strength rules, gaps, hypothesis page, opportunity brief export | Demo 4 end to end; brief exports with all citations resolving | 2.5 |
| **7** | Gold v1 (~120, grouped split), judge calibration, grounding/generation/behavioral metrics, ≥2 tuning iterations under the protocol, agent-vs-single-pass ablation, fresh-seed holdout | Reproducible report; quality gates documented with CIs | 3 |
| **8** | Answer cache, circuit breakers, injection suite (exposure-conditioned, k=5), isolation hardening, load test, error UX | Dependency-failure demos produce explicit fallbacks | 2 |
| **9** | Render/Vercel deployment, demo mode, spend ledger, full docs (INTERVIEW_GUIDE ≥50 Q&A), polish | Clean-environment deployed demo, checked in Safari and incognito | 2 |

**Total:** about 27 days. **M1** lands after about 15 days.

**Every phase ends with these steps:**
1. Run the tests.
2. Run typecheck and lint.
3. Exercise the feature for real.
4. Write a phase report: what was implemented, deviations, measurements, open issues and what comes next.
5. Update the architecture docs.
6. Add or update eval cases.
