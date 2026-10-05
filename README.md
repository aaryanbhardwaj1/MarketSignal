# MarketSignal

**An agentic growth-strategy intelligence platform for consulting teams.** It turns fragmented customer, competitor, market, and internal evidence into grounded strategic insights. Every material claim resolves to an exact, immutable evidence handle.

> **Status:** Phase 0 (repository and local infrastructure). The approved design is in [`docs/ARCHITECTURE_PLAN.md`](docs/ARCHITECTURE_PLAN.md). The decisions behind it are in [`docs/adr/`](docs/adr/).

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

More documents arrive with the phases that implement them: system design, retrieval deep dive, agent and MCP, evaluation, security, deployment, and an interview guide.

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
