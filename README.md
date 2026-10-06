# MarketSignal

**An agentic growth-strategy intelligence platform for consulting teams.** It turns fragmented customer, competitor, market, and internal evidence into grounded strategic insights. Every material claim resolves to an exact, immutable evidence handle.

> **Status:** Phases 0–3 are complete; Phase 4 is implemented and measured live ([report](docs/phase-reports/phase-4.md)); Phase 5 is implemented, awaiting review. Phase 0 delivered the repository, local infrastructure, isolation scaffolding and CI ([report](docs/phase-reports/phase-0.md)). Phase 1 delivered ingestion and the evidence model: seven formats through the real upload API, versioned sources, parent/child evidence with exact spans, local embeddings, the evidence resolver and an inspection UI ([report](docs/phase-reports/phase-1.md)). Phase 2 delivered hybrid retrieval with a measured evaluation baseline: a frozen 65-item gold set with a grouped dev/test split, dense and IDF-lexical lanes, parent-level RRF, a local cross-encoder, retrieval traces and a CI retrieval gate ([report](docs/phase-reports/phase-2.md), [deep dive](docs/RETRIEVAL_DEEP_DIVE.md)). Phase 3 delivered standard-mode grounded answers with a deterministic evidence pack, run-local alias citations behind a streaming hold-back gate, a deterministic verifier with one regeneration and an evidence-only fallback, empty-pack abstention, a resumable SSE run stream, purge-safe persistence and the chat UI, validated live against the Anthropic API ([report](docs/phase-reports/phase-3.md), [system design](docs/SYSTEM_DESIGN.md), [grounded answering](docs/GROUNDED_ANSWERING.md)). Phase 4 adds a deterministic mode router, a bounded research agent (explicit state machine, every bound flagged and tested, append-only transcript, deterministic progress events), four governed tools behind run-scoped capability tokens with a purge-safe audit, in-process and MCP Streamable HTTP transports with a parity test, and verifier precision rules ([research agent](docs/RESEARCH_AGENT.md), [governed tools and MCP](docs/GOVERNED_TOOLS_AND_MCP.md)). Phase 5 adds deterministic structured analytics: the agent chooses what to compute and code computes it (four governed analytics tools, no SQL or code execution, half-even rounding, persisted results), answers cite computed results as `[R#]` with result cards and an exact numeric check, a deterministic task-type router, a citation budget, an injection-safe fallback and a research summary hand-off ([ADR-0020](docs/adr/0020-deterministic-structured-analytics.md)). Its measurements will be in the Phase 5 report (`docs/phase-reports/phase-5.md`). The approved design is in [`docs/ARCHITECTURE_PLAN.md`](docs/ARCHITECTURE_PLAN.md), and the decisions behind it are in [`docs/adr/`](docs/adr/).

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
uv --directory backend run python -m marketsignal.evaluation analytics --split dev --out <dir> --fake   # analytics-v0 offline plumbing run; drop --fake for the live model
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
| [`docs/GROUNDED_ANSWERING.md`](docs/GROUNDED_ANSWERING.md) | Evidence pack, prompt and trust policy, alias gate, verifier (with the Phase 4 precision rules), computed results and `[R#]` citations, citation budget and safe fallback, abstention, SSE protocol, purge during a run, grounded evaluation |
| [`docs/RESEARCH_AGENT.md`](docs/RESEARCH_AGENT.md) | Mode router and the bounded research agent: state machine, bounds and stop reasons, transcript, parallel tool calls, progress events, evidence pool, what is persisted, failure modes |
| [`docs/GOVERNED_TOOLS_AND_MCP.md`](docs/GOVERNED_TOOLS_AND_MCP.md) | Governed tool contract (evidence and analytics tools), capability tokens, governance pipeline, audit, observations, in-process and MCP Streamable HTTP transports, threat model |
| [`docs/RETRIEVAL_DEEP_DIVE.md`](docs/RETRIEVAL_DEEP_DIVE.md) | Retrieval pipeline and the measurements behind each choice: baselines, hybrid, reranking, balancing, RLS cost |
| [`eval/README.md`](eval/README.md) | Evaluation methodology: gold set, split, metrics, statistics, test-split discipline |
| [`docs/INGESTION.md`](docs/INGESTION.md) | How a file becomes citable evidence: validation, versioning, parsing, parents and children, embeddings, purge, resolution |
| [`docs/phase-reports/`](docs/phase-reports/) | Per-phase reports with verification results and measurements |

More documents arrive with the phases that implement them: evaluation, security, deployment, and an interview guide.

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
