# Architecture Decision Records

Each ADR records one significant decision: context, decision, alternatives, tradeoffs, consequences and verification. All ADRs below were accepted on 2026-10-05 with the architecture plan (`docs/ARCHITECTURE_PLAN.md`). Each one is updated with measurements when its component is built.

## Index

| ADR | Title | Status | Phase |
|---|---|---|---|
| [0001](0001-postgres-pgvector-system-of-record.md) | PostgreSQL + pgvector as the single system of record | Accepted | 0–1 |
| [0002](0002-hybrid-retrieval-parent-level-rrf.md) | Hybrid retrieval (dense + IDF-weighted Postgres FTS) with parent-level RRF | Accepted | 2 (core); 7 (neighbor expansion, structural enumeration) |
| [0003](0003-parent-child-chunks-parent-citation-unit.md) | Parent/child chunking; the parent is the citation unit; parents immutable per version | Accepted | 1; anchor propagation 2–3 |
| [0004](0004-evidence-handle-grammar-and-alias-citations.md) | Evidence-handle grammar and run-local `[E#]` alias citations with a streaming hold-back gate | Accepted | 1 (grammar, resolver); 3 (alias layer, gate, verifier) |
| [0005](0005-local-cross-encoder-reranker.md) | Local ONNX cross-encoder reranker (MaxP over parents) with fused-order fallback and hosted-reranker switch | Accepted | 2; 3 (Render CPU spike) |
| [0006](0006-governed-mcp-tool-boundary.md) | Governed MCP tool boundary | Accepted | 4a/4b (Phase 0 spike) |
| [0007](0007-bounded-agent-state-machine.md) | Custom bounded agent state machine | Accepted | 4a (Phase 0 spike) |
| [0008](0008-sse-run-protocol.md) | SSE run protocol over WebSockets | Accepted | 3; 4 (progress events); 9 (deployed-browser check) |
| [0009](0009-workspace-isolation.md) | Workspace isolation in depth | Accepted | 0; each tenant table from 1; hardened in 8 |
| [0010](0010-postgres-native-job-queue.md) | Postgres-native job queue with transactional enqueue | Accepted | 1 |
| [0011](0011-answer-cache-corpus-version.md) | Answer cache keyed on workspace corpus_version with conditional writes | Accepted | 8 |
| [0012](0012-local-embeddings-provider-interface.md) | Local embeddings behind a provider interface, with a per-model embedding table and a file-backed cache | Accepted | 1; 2 (dense retrieval SQL) |
| [0013](0013-evaluation-methodology.md) | Evaluation methodology: world model, frozen fact ledger, deterministic CI gates, judge calibration and statistics | Accepted | 1–2 (gold v0, CI smoke); 7 (gold v1, calibration) |
| [0014](0014-deployment-render-vercel.md) | Deployment on Render + Vercel, token-based browser auth, demo mode and spend ledger (AWS ECS/Fargate documented) | Accepted | 9 (spikes in 0 and 3) |
| [0015](0015-standard-vs-research-modes.md) | Standard (single-pass) and research (agentic) modes, chosen by a deterministic, user-overridable router | Accepted | 3 (standard); 4 (router, research); 7 (ablation) |
| [0016](0016-source-versioning-and-purge.md) | Source versioning semantics and purge contract | Accepted | 1 |
| [0017](0017-fictional-competitor-corpus.md) | Fully fictional demo corpus, including competitors | Accepted | 1 |
| [0018](0018-personas-as-policy-configuration.md) | Personas as policy configuration, not tool restriction | Accepted | 4a/4b |
| [0019](0019-testing-and-load-testing.md) | Testing strategy and load testing | Accepted | 0, extended every phase; 8 (load test) |

## Spec deviation register

Approved deviations from `docs/PRODUCT_SPEC.md`, as recorded in `docs/ARCHITECTURE_PLAN.md` §0.3. Where they differ from the spec, the plan and the ADRs take precedence.

| # | Deviation | Primary ADR | Also referenced in |
|---|---|---|---|
| D1 | Evidence handles cite parent (structural) units instead of `child_chunks`; child-anchor ids and character offsets are kept through traces, pool, pack and citation cards. | [ADR-0003](0003-parent-child-chunks-parent-citation-unit.md) | ADR-0006, ADR-0016 |
| D2 | The generator cites run-local `[E#]` aliases that map deterministically to canonical handles; aliases are never persisted as evidence identities. | [ADR-0004](0004-evidence-handle-grammar-and-alias-citations.md) | — |
| D3 | The agent gets `search_evidence` (full hybrid pipeline) and `search_evidence_keyword` instead of separate semantic, keyword and hybrid tools. | [ADR-0006](0006-governed-mcp-tool-boundary.md) | ADR-0002 |
| D4 | The seed corpus and gold v0 move to Phases 1–2 instead of Phases 9 and 7. | [ADR-0013](0013-evaluation-methodology.md) | ADR-0017 |
| D5 | Core retrieval is built first; neighbor expansion and structural enumeration are added as measured Phase 7 tuning iterations. | [ADR-0002](0002-hybrid-retrieval-parent-level-rrf.md) | — |
| D6 | The demo corpus uses fictional competitors; an optional script fetches real public filings without committing them. | [ADR-0017](0017-fictional-competitor-corpus.md) | — |
| D7 | SSE uses `tool_started`/`tool_completed` with a `kind` field, adds `draft_reset`, and sends `final` before `done`. | [ADR-0008](0008-sse-run-protocol.md) | — |
| D8 | Every tenant route lives under `/api/workspaces/{ws}/…`, including evidence and conversation routes. | [ADR-0009](0009-workspace-isolation.md) | ADR-0014 |
| D9 | All personas share the same read-only tool set and differ in source-class priors, prompt policy and default mode; the allowlist mechanism exists and is tested. | [ADR-0018](0018-personas-as-policy-configuration.md) | ADR-0006 |
| D10 | A deterministic, user-overridable router chooses between a single-pass `standard` mode and an agentic `research` mode; the Phase 7 agent-vs-single-pass ablation is mandatory. | [ADR-0015](0015-standard-vs-research-modes.md) | ADR-0007 |
| D11 | Load testing uses a Locust script, or a documented asyncio script if Locust adds friction. | [ADR-0019](0019-testing-and-load-testing.md) | — |
