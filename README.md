# MarketSignal

**An agentic growth-strategy intelligence platform for consulting teams.** It turns fragmented customer, competitor, market, and internal evidence into grounded strategic insights. Every material claim resolves to an exact, immutable evidence handle.

> **Status:** Phases 0–2 are complete; Phase 3 core is implemented, with live validation pending. Phase 0 delivered the repository, local infrastructure, isolation scaffolding and CI ([report](docs/phase-reports/phase-0.md)). Phase 1 delivered ingestion and the evidence model: seven formats through the real upload API, versioned sources, parent/child evidence with exact spans, local embeddings, the evidence resolver and an inspection UI ([report](docs/phase-reports/phase-1.md)). Phase 2 delivered hybrid retrieval with a measured evaluation baseline: a frozen 65-item gold set with a grouped dev/test split, dense and IDF-lexical lanes, parent-level RRF, a local cross-encoder, retrieval traces and a CI retrieval gate ([report](docs/phase-reports/phase-2.md), [deep dive](docs/RETRIEVAL_DEEP_DIVE.md)). Phase 3 core is implemented: standard-mode grounded answers with a deterministic evidence pack, run-local alias citations behind a streaming hold-back gate, a deterministic verifier with one regeneration and an evidence-only fallback, empty-pack abstention, a resumable SSE run stream, purge-safe persistence and the chat UI ([system design](docs/SYSTEM_DESIGN.md), [grounded answering](docs/GROUNDED_ANSWERING.md)). Live validation against the Anthropic API (the provider spike and the grounded evaluation) is pending: no API key is configured yet, so no live answer-quality, latency or token results exist. The approved design is in [`docs/ARCHITECTURE_PLAN.md`](docs/ARCHITECTURE_PLAN.md), and the decisions behind it are in [`docs/adr/`](docs/adr/).

## Quick start (local, light mode)

Requires Docker (OrbStack, Colima or Docker Desktop), [uv](https://docs.astral.sh/uv/), Node 24 and pnpm.

```bash
make up                  # Postgres 18 + pgvector and Redis in containers (creates .env from .env.example)
make sync migrate        # backend deps (Python 3.13) + migrations as the schema-owner role
make api                 # FastAPI on :8000 as the non-privileged ms_app role
make worker              # ingestion worker (Procrastinate, Postgres-backed queue)
curl localhost:8000/readyz
make seed                # upload the fictional Northstar/Southpeak corpus through the real API
make test                # unit + integration tests (integration runs as ms_app, so RLS is enforced)
cd frontend && pnpm install && pnpm dev   # Next.js on :3000
```

To run everything in containers instead: `make up-full`.

## What it is

Consultants ask research questions such as *"Which Gen Z pain points are competitors failing to address?"* or *"Evaluate the hypothesis that Northstar should launch premium personalized products."* MarketSignal answers them in five steps:

1. Retrieve evidence with **hybrid search**: dense vectors plus Postgres full-text, fused with reciprocal rank fusion (RRF), reranked by a cross-encoder, and organized as hierarchical parent/child chunks.
2. Let a **bounded agent** call **governed MCP tools**. The agent has no database or filesystem access, and the workspace comes from trusted context.
3. Synthesize an answer where findings carry citations, inference is labelled as inference, and evidence gaps are stated explicitly.
4. Verify every citation deterministically before the answer is accepted. Each citation must resolve to an **evidence handle** such as `NORTHSTAR/SURVEY-2026@v1:R185`, which points to an exact passage or row.
5. Measure the whole system with an evaluation harness: retrieval metrics, grounding and citation quality, and refusal and isolation behaviour.

The demo engagement uses **Northstar Athletics**, a fictional client. Its competitors and data are fictional too.

## Documentation

| Document | Purpose |
|---|---|
| [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) | Product and engineering specification |
| [`docs/ARCHITECTURE_PLAN.md`](docs/ARCHITECTURE_PLAN.md) | Approved architecture plan: every major decision with its rationale, alternatives and tradeoffs |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records and the spec-deviation register |
| [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md) | End-to-end system as built: components, data model, request flow, isolation, purge, termination states, configuration, what is deferred |
| [`docs/GROUNDED_ANSWERING.md`](docs/GROUNDED_ANSWERING.md) | Evidence pack, prompt and trust policy, alias gate, verifier, abstention, SSE protocol, purge during a run, grounded evaluation |
| [`docs/RETRIEVAL_DEEP_DIVE.md`](docs/RETRIEVAL_DEEP_DIVE.md) | Retrieval pipeline and the measurements behind each choice: baselines, hybrid, reranking, balancing, RLS cost |
| [`eval/README.md`](eval/README.md) | Evaluation methodology: gold set, split, metrics, statistics, test-split discipline |
| [`docs/INGESTION.md`](docs/INGESTION.md) | How a file becomes citable evidence: validation, versioning, parsing, parents and children, embeddings, purge, resolution |
| [`docs/phase-reports/`](docs/phase-reports/) | Per-phase reports with verification results and measurements |

More documents arrive with the phases that implement them: agent and MCP, evaluation, security, deployment, and an interview guide.

## Data and confidentiality

- The repository contains **only synthetic, fictional data**. Do not upload real confidential client data to a deployment that sends text to third-party LLM providers unless an approved data-handling policy covers it.
- MarketSignal applies general engineering patterns learned during prior enterprise RAG work. It contains no code, data, prompts, or internal details from any employer.

## Repository safety

- `scripts/check_repo_safety.sh` blocks large files, archives and other reference-material patterns, private-content markers, and local absolute paths.
- CI runs the same check, plus gitleaks secret scanning.
- To run the checks locally before every commit, enable the bundled hook once per clone:

```bash
git config core.hooksPath .githooks
```
