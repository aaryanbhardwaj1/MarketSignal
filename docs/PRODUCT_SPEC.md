# MarketSignal
## Product and Engineering Specification

**Project:** MarketSignal — Agentic Growth Strategy Intelligence Platform  
**Primary purpose:** Build an interview-ready, technically deep full-stack AI system that applies enterprise research-RAG architecture patterns to a growth-strategy / management-consulting domain.  
**Status:** Public product specification. Approved implementation deviations D1–D11 are recorded in `docs/ARCHITECTURE_PLAN.md` §0.3 and `docs/adr/`; where they differ, the plan and ADRs take precedence.  

---

# 0. Executive Summary

Build **MarketSignal**, an evidence-grounded AI research and decision-support platform for strategy consultants. The system should help a consultant ingest fragmented market, customer, competitor, and internal-client evidence; ask complex research questions; investigate multiple source classes through controlled tools; and produce concise strategic synthesis in which material factual claims resolve back to exact source evidence.

This project intentionally applies architectural patterns learned from prior enterprise legal-research RAG work (during a Visa internship) to a new domain. It does not copy or derive from any employer source code, data, prompts, corpus contents, internal endpoints, or credentials (see §2.6).

The goal is not to create a generic “chat with PDFs” application. The goal is to create a system that is defensible in a deep software-engineering interview: retrieval architecture, agent orchestration, tool boundaries, data modeling, document ingestion, source provenance, streaming APIs, caching, evaluation, observability, graceful degradation, security, testing, and deployment should all be real architectural concerns.

The engineer has meaningful freedom over implementation details. However, the **architectural invariants** defined in this document must be preserved unless there is a technically compelling reason to deviate, and any deviation must be documented in an Architecture Decision Record (ADR).

## Core architectural invariants

1. **Hybrid retrieval**: combine semantic/vector retrieval with lexical/keyword retrieval; do not rely on vector similarity alone.
2. **Hierarchical chunking**: maintain smaller retrieval windows and larger parent context units so retrieval can be precise while generation receives coherent context.
3. **Reranking and fusion**: fuse lexical and semantic candidates, then rerank and collapse/expand evidence before generation.
4. **Immutable evidence handles**: every cited passage must have a stable, machine-resolvable identifier that maps back to exact source content and provenance.
5. **Controlled agent/tool boundary**: the LLM must not have unrestricted database access. It interacts with data through an allowlisted tool surface, preferably exposed through MCP or an equivalently explicit tool-governance layer.
6. **Bounded agentic orchestration**: support multi-step tool use with hard bounds, timeouts, circuit-breaker behavior, and deterministic fallbacks.
7. **Grounded generation**: the answer layer must synthesize from retrieved evidence and produce citation-backed claims. Unsupported factual claims must be prevented or explicitly qualified.
8. **Streaming UX**: use a streaming transport, preferably Server-Sent Events (SSE), for user-visible progress states, tool activity summaries, citations, and answer tokens. Do not expose hidden chain-of-thought.
9. **Evaluation harness**: include gold sets and quantitative metrics across retrieval, grounding/citation quality, answer quality, and refusal behavior.
10. **Auditability and observability**: trace queries, tool calls, retrieval results, latency, errors, model/token usage, and citation resolution.
11. **Graceful degradation**: retrieval, embedding, reranking, generation, cache, and ingestion failures should have explicit fallback behaviors rather than ambiguous failures.
12. **Workspace isolation**: engagement/client workspaces must be logically isolated so data from one workspace cannot leak into another.

---

# 1. Product Vision

MarketSignal is an **AI-powered growth-strategy research workspace** for consulting teams.

A consultant working on a client engagement typically needs to synthesize evidence scattered across many places: customer research, internal strategy documents, survey results, reviews, interviews, annual reports, investor presentations, competitor materials, market studies, spreadsheets, and prior analyses. Traditional search can find documents, but it does not reliably answer cross-source strategic questions. Generic LLM chat interfaces can summarize documents, but they often lack rigorous provenance, explicit source controls, reproducible retrieval, and useful evaluation.

MarketSignal should bridge that gap.

The product should allow a consultant to create an engagement workspace, ingest a set of research sources, and ask questions such as:

- “What are the strongest unmet needs among Gen Z customers?”
- “Which of those needs appear underserved by the major competitors?”
- “What evidence supports or contradicts the hypothesis that customers will pay more for personalization?”
- “How does the company’s current positioning differ from the positioning implied by customer feedback?”
- “Generate a one-page evidence-backed opportunity brief for the team.”

The system must respond as an evidence-driven research assistant, not as an oracle. It should search, compare, retrieve, verify, synthesize, and cite.

## Product promise

**Every material factual claim should be traceable to source evidence.**

The product should optimize for:

- fast cross-source research;
- transparent evidence provenance;
- strategic synthesis rather than simple summarization;
- clear distinction between evidence, inference, and unsupported speculation;
- repeatable evaluation;
- strong engineering architecture that can scale from a demo into an enterprise product.

---

# 2. Origin and Motivation

## 2.1 Prior-work context

The author previously worked on enterprise legal-research RAG during a Visa internship. That work addressed a general problem that recurs across knowledge-intensive domains: high-value users need trustworthy answers across fragmented, authoritative sources, and a general-purpose LLM cannot simply be allowed to invent answers or directly touch source systems.

MarketSignal is an independent project. It carries forward the generalizable *patterns* from that experience — not its implementation — and applies them to strategy research. The patterns are:

- a trust contract between retrieval and generation, built on stable, resolvable evidence identifiers;
- multi-stage hybrid retrieval rather than single-pass vector search;
- bounded, governed agents that reach data only through an explicit tool surface;
- evaluation discipline across retrieval, grounding, generation, and behavior.

## 2.2 Trust contract between retrieval and generation

The most important principle is a **trust contract** between retrieval and generation:

1. the system discovers evidence through controlled tools;
2. retrieved evidence has stable identifiers;
3. final synthesis references those identifiers;
4. identifiers can be deterministically resolved to exact source material;
5. source resolution does not depend on the LLM “remembering” or recreating text;
6. missing evidence should result in a qualified answer or refusal rather than fabrication.

MarketSignal treats this contract as a core invariant for strategy research.

## 2.3 Multi-stage retrieval shape

MarketSignal uses a multi-stage retrieval flow rather than a single top-k vector search:

**normalize query → lexical candidates + semantic candidates → rank fusion → cross-encoder rerank → parent collapse → optional neighboring context → source/corpus balancing → final evidence pack → grounded generation**

Each stage is specified in §13.

## 2.4 Bounded-agent philosophy

In MarketSignal, the agent runs a bounded ReAct-style loop and interacts with a controlled tool catalog rather than gaining unrestricted backend access. MarketSignal requires hard limits on its execution; the specific controls are defined in §15.3.

The agent may decide which evidence classes or analytical tools are necessary, but the system remains deterministic at its boundaries.

## 2.5 Evaluation philosophy

“The answer sounds good” is not sufficient. MarketSignal uses gold sets and metrics across multiple layers, including retrieval, generation, grounding/citation quality, and refusal behavior (§20).

## 2.6 Explicit non-copying boundary

MarketSignal contains no employer source code, data, prompts, credentials, internal endpoints, corpus contents, or other internal details, and none may be added. All seed data is synthetic, fictional, or publicly available.

The project demonstrates reusable architectural principles applied independently to another domain.

---

# 3. Domain Translation (Enterprise Research → Strategy Research)

The same trust, retrieval and agent patterns apply to strategy research. Generic enterprise-research concepts map to MarketSignal as follows.

| Generic enterprise research concept | MarketSignal equivalent |
|---|---|
| Authoritative document corpus | Market/customer/competitor/client evidence corpus |
| Research question | Strategy / growth research question |
| Role-aware retrieval policy | Workstream-aware retrieval and prompt policy (personas, §5) |
| Citation identifier | Evidence handle |
| Exact source-text resolution | Exact evidence passage resolution |
| Document ingestion | Research document / spreadsheet / deck ingestion |
| Cross-document comparison | Cross-source / cross-competitor comparison |
| Source authority | Source credibility and provenance |
| Confidential document uploads | Confidential client/engagement uploads |
| Research memo | Strategy research brief / opportunity brief |
| Hallucination prevention | Unsupported-insight prevention |

The implementation should feel like a **domain-generalization of the enterprise research-RAG pattern**, not an unrelated portfolio project.

---

# 4. Demo Engagement and Seed Scenario

Use one coherent fictional client engagement so the demo is easy to understand and technically reproducible.

## Fictional client

**Northstar Athletics** — a fictional athletic apparel and footwear company attempting to identify its next major growth opportunity among younger consumers.

The company wants to understand:

- unmet customer needs;
- competitor positioning;
- product/category whitespace;
- evidence for and against premium personalization;
- where the strongest growth opportunity may exist.

## Seed evidence classes

Create a representative but manageable engagement corpus.

### A. Northstar internal evidence — synthetic

Examples:

- `Northstar_Brand_Strategy.pdf`
- `Northstar_Customer_Survey.csv`
- `Northstar_Product_Performance.xlsx`
- `Northstar_Customer_Interviews.docx`
- `Northstar_Q3_Strategy_Review.pptx`
- `Northstar_Channel_Performance.csv`

Generate this data synthetically. Make it realistic enough for multi-source reasoning but clearly fictional.

### B. Public competitor evidence

Use publicly available, legally redistributable or downloadable material where practical, such as public filings, annual reports, investor materials, and public webpages from a small set of companies. If licensing or automation becomes a distraction, ship cached metadata and require users to download public documents themselves rather than committing copyrighted source files to the repository.

> Implementation note: per approved deviation D6 (`docs/ARCHITECTURE_PLAN.md` §0.3), the seeded corpus uses fictional competitors (e.g., Vantage Athletic, Kinetic Lab, Pace & Co.); an optional script can fetch real public filings without committing them.

### C. Market research — synthetic or openly licensed

Include a small number of synthetic or openly licensed industry/consumer trend documents.

### D. Customer voice — synthetic

Create a dataset of synthetic customer reviews, survey responses, and interview excerpts. The purpose is to demonstrate retrieval and analysis, not to scrape a platform unnecessarily.

## Target corpus size for a polished demo

Aim for enough information to stress the retrieval system without creating an unnecessary ingestion burden:

- roughly 20–40 source documents/files;
- at least 4 source classes;
- at least 2 structured datasets;
- at least 1 slide deck;
- enough extracted parent/child chunks to produce meaningful retrieval competition;
- at least 75–150 gold evaluation questions once the system is stable.

Do not optimize for raw corpus size. Optimize for **retrieval diversity and architectural depth**.

---

# 5. Primary Users and Workstream Personas

MarketSignal should support **workstream personas** that influence default source priorities, tool availability, prompt policy, and retrieval behavior.

These personas are not separate models. They are configuration and policy layers.

> Implementation note: per approved deviation D9 (`docs/ARCHITECTURE_PLAN.md` §0.3), all personas share the same read-only tool set; they differ in source-class priors, prompt policy and default mode. The tool-allowlist mechanism exists and is tested.

## 5.1 Growth Strategy

Typical questions:

- Where should the client play?
- Which customer segments or categories offer attractive opportunities?
- What evidence supports a particular growth thesis?

Priority evidence:

- market research;
- financial / category performance;
- customer research;
- competitor documents;
- company strategy materials.

## 5.2 Customer Insights

Typical questions:

- What needs are customers expressing?
- What themes recur across segments?
- Which complaints are most prevalent?

Priority evidence:

- surveys;
- customer interviews;
- reviews;
- segmentation studies;
- customer-support themes.

## 5.3 Brand Strategy

Typical questions:

- How does current brand positioning compare with customer perception?
- What themes differentiate competitors?
- Where is there positioning whitespace?

Priority evidence:

- brand strategy documents;
- messaging and campaign material;
- competitor positioning;
- customer perception research.

## 5.4 Marketing Strategy

Typical questions:

- Which channels or messages appear most effective?
- How do segment behaviors differ?
- What marketing opportunities are evidence-backed?

Priority evidence:

- channel/campaign datasets;
- audience research;
- customer research;
- competitor marketing material.

## 5.5 Generalist

Searches across all available engagement evidence with minimal source bias.

---

# 6. Core User Workflows

## 6.1 Create an engagement workspace

A user should be able to:

1. create a workspace;
2. name the fictional or real client/project;
3. choose a workstream persona;
4. upload or seed evidence sources;
5. wait for ingestion/indexing state to become ready;
6. begin a conversation.

## 6.2 Ask an evidence-backed research question

Example:

> What are Northstar’s strongest unmet needs among Gen Z customers?

System flow:

1. validate workspace and permissions;
2. classify/query-plan at a high level;
3. select one or more retrieval tools;
4. run hybrid retrieval;
5. fuse and rerank candidates;
6. resolve parent context / neighboring evidence;
7. assemble bounded evidence pack;
8. generate answer using evidence handles;
9. verify handles exist and resolve;
10. stream answer and citation cards;
11. record telemetry and evaluation-ready trace.

## 6.3 Ask a cross-source comparison question

Example:

> Which customer needs are least addressed by the major competitors?

The agent should recognize that one retrieval pass may not be sufficient. It may search customer evidence, then competitor evidence, then compare.

## 6.4 Evaluate a strategic hypothesis

Example:

> Assess the hypothesis that Northstar should launch a premium personalized product line for Gen Z.

The system should explicitly search for:

- supporting evidence;
- contradictory evidence;
- missing evidence / uncertainty.

The final answer should distinguish these categories instead of producing a one-sided conclusion.

## 6.5 Open a citation

A user clicks an evidence handle and sees:

- source title;
- source type;
- page / slide / row / section locator;
- exact passage or structured record;
- relevant surrounding context;
- provenance metadata;
- retrieval method and optional relevance metadata;
- workspace/source classification.

## 6.6 Generate an opportunity brief

The user can convert a research thread or selected evidence set into an exportable structured brief containing:

- research question / opportunity statement;
- evidence-backed findings;
- supporting evidence;
- contradictory evidence;
- assumptions / evidence gaps;
- recommended next research questions;
- citations.

Do not turn this into automatic executive decision-making. It is decision support for human consultants.

---

# 7. Signature Feature: Growth Opportunity Workspace

This feature is what differentiates MarketSignal from a conventional enterprise RAG chatbot.

Users can create a **growth opportunity hypothesis**, for example:

> “Gen Z customers will pay a meaningful premium for personalization if it also reduces product-discovery friction.”

A hypothesis should have:

- title;
- description;
- author;
- workspace;
- status (`draft`, `investigating`, `reviewed`);
- supporting evidence links;
- contradicting evidence links;
- neutral/contextual evidence links;
- evidence gaps;
- analyst notes;
- generated synthesis;
- timestamps.

## 7.1 Dual-sided evidence retrieval

For hypothesis analysis, the system should deliberately execute two search tracks:

**Support track**
- reformulate the hypothesis into evidence-seeking queries;
- retrieve passages likely to support it.

**Contradiction track**
- reformulate the hypothesis into challenge/disconfirmation queries;
- retrieve evidence that weakens, limits, or contradicts it.

Then synthesize:

- strongest supporting evidence;
- strongest contradictory evidence;
- unresolved evidence gaps;
- what additional data would most reduce uncertainty.

Avoid presenting an arbitrary model-generated numeric “truth probability.” If an evidence-strength label is displayed, derive it transparently from evidence coverage and quality rules and explain the basis.

---

# 8. High-Level Architecture

The target architecture should resemble the following:

```text
                                ┌────────────────────────────┐
                                │       Next.js Web App      │
                                │ Chat / Sources / Hypothesis│
                                └─────────────┬──────────────┘
                                              │ HTTPS + SSE
                                              ▼
                                ┌────────────────────────────┐
                                │       FastAPI Gateway      │
                                │ Auth / REST / SSE / Jobs   │
                                └───────┬─────────┬──────────┘
                                        │         │
                           query/agent  │         │ uploads/jobs
                                        ▼         ▼
                              ┌────────────────┐  ┌─────────────────┐
                              │ Agent Runtime  │  │ Ingestion Worker │
                              │ bounded ReAct  │  │ parse/chunk/embed│
                              └───────┬────────┘  └────────┬────────┘
                                      │                    │
                                      ▼                    │
                              ┌────────────────┐           │
                              │ MCP / Tool     │           │
                              │ Governance     │           │
                              └───────┬────────┘           │
                                      │                    │
                         ┌────────────┼─────────────┐      │
                         ▼            ▼             ▼      │
                  semantic search lexical search analytics │
                         │            │             │      │
                         └────────────┼─────────────┘      │
                                      ▼                    ▼
                              ┌────────────────────────────┐
                              │ Retrieval / Evidence Layer │
                              │ fusion / rerank / resolve  │
                              └─────────────┬──────────────┘
                                            │
                      ┌─────────────────────┼──────────────────────┐
                      ▼                     ▼                      ▼
              ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
              │ PostgreSQL   │      │   pgvector   │      │    Redis     │
              │ app + FTS    │      │ embeddings   │      │ cache/locks  │
              └──────────────┘      └──────────────┘      └──────────────┘
                                            │
                                            ▼
                              ┌────────────────────────────┐
                              │ Evaluation + Telemetry     │
                              │ gold sets / traces / stats │
                              └────────────────────────────┘
```

This is the default architecture. The implementation may refine service boundaries, but the separation of concerns should remain clear.

---

# 9. Recommended Technology Direction

These are **strong defaults**, not absolute mandates.

## Frontend

- Next.js
- TypeScript
- React
- Tailwind CSS or equivalent component styling system
- SSE client for answer/event streaming
- client-side cache such as TanStack Query where useful

## Backend

- Python
- FastAPI
- Pydantic
- async request handling
- SSE endpoint for conversational streaming

## Data

- PostgreSQL as the authoritative application database
- pgvector for dense embeddings
- Postgres full-text search or a well-encapsulated lexical retrieval implementation
- Redis for answer caching, short-lived locks, rate limiting, or job coordination as needed

## Agent / AI layer

- MCP is preferred for the tool boundary because it makes tool governance explicit and is a strong interview discussion point.
- LLM provider should be configurable through an adapter/interface.
- Embedding model should be configurable.
- Cross-encoder/reranker should be configurable.

## Background processing

Choose a simple, production-plausible approach:

- FastAPI background worker for a minimal local build, or
- Celery/RQ/Arq/Taskiq if durable jobs are needed.

Prefer architectural clarity over introducing infrastructure for its own sake.

## Local development

Provide Docker Compose for at least:

- PostgreSQL + pgvector;
- Redis;
- API;
- optional worker;
- frontend if convenient.

One command should bring up a demo-capable environment after configuration.

---

# 10. Data Model

The exact ORM and migration framework are implementation decisions. The following entities should exist conceptually.

## 10.1 `workspaces`

Fields should include:

- `id`
- `name`
- `description`
- `default_persona`
- `created_at`
- `updated_at`

For a portfolio build, authentication can initially assume one user, but the schema should not make workspace isolation impossible to add later.

## 10.2 `sources`

Represents a logical source asset.

Suggested fields:

- `id`
- `workspace_id`
- `title`
- `source_type` (`pdf`, `docx`, `pptx`, `xlsx`, `csv`, `web`, `note`, etc.)
- `source_class` (`internal`, `customer`, `competitor`, `market`, `financial`, etc.)
- `original_filename`
- `uri` or storage key
- `content_hash`
- `ingestion_status`
- `confidentiality`
- `metadata_json`
- `created_at`

## 10.3 `parent_chunks`

Larger coherent units used for generation context.

Fields:

- `id`
- `source_id`
- `workspace_id`
- `ordinal`
- `locator_json`
- `text`
- `token_count`
- `metadata_json`
- `content_hash`

## 10.4 `child_chunks`

Smaller retrieval units.

Fields:

- `id`
- `parent_chunk_id`
- `source_id`
- `workspace_id`
- `ordinal`
- `text`
- `token_count`
- lexical-search representation / tsvector
- embedding vector
- `evidence_handle`
- `locator_json`
- `metadata_json`

> Implementation note: per approved deviation D1 (`docs/ARCHITECTURE_PLAN.md` §0.3), the evidence handle is assigned to the parent (structural) unit, not to `child_chunks`. Children remain internal retrieval windows, and child-anchor metadata with character offsets into the parent is preserved through retrieval traces, the evidence pool, the pack and stored citation cards.

## 10.5 `conversations`

- `id`
- `workspace_id`
- `persona`
- `title`
- timestamps

## 10.6 `messages`

- `id`
- `conversation_id`
- role
- content
- structured citations
- model metadata
- timestamps

## 10.7 `query_runs`

One row per executed research request.

Track:

- original query;
- normalized query;
- persona;
- tool plan summary;
- retrieved handle IDs;
- reranked handle IDs;
- context token count;
- model/provider;
- cache status;
- timings;
- termination reason;
- degradation flags;
- success/failure state.

## 10.8 `tool_runs`

Track every externally visible tool invocation:

- query run;
- tool name;
- sanitized input;
- status;
- duration;
- result count;
- error category.

Do not persist model hidden chain-of-thought.

## 10.9 `hypotheses`

See the Growth Opportunity Workspace section.

## 10.10 `hypothesis_evidence`

Links a hypothesis to an evidence handle with one of:

- `support`
- `contradict`
- `context`

Also record how the link was created (`agent`, `user`, `evaluation`).

## 10.11 `evaluation_runs` and `evaluation_results`

Persist evaluation configuration, dataset version, model/retrieval versions, metrics, and per-question output so regressions are traceable.

---

# 11. Evidence Handle System — Central Trust Primitive

This is a non-negotiable part of MarketSignal.

Each retrievable piece of evidence must receive an immutable, structured handle that can be parsed and resolved without involving the model.

Example conceptual formats:

```text
[NORTHSTAR:SURVEY_2026:ROW_184]
[VANTAGE_ATHLETIC:FY2026_ANNUAL_REPORT:P42:C3]
[NORTHSTAR:INTERVIEWS:P7:C2]
[KINETIC_LAB:POSITIONING:SECTION_4:C1]
```

The exact grammar is an implementation decision, but it must satisfy these properties:

1. deterministic;
2. unique within the system;
3. resolvable through backend code;
4. stable across ordinary queries;
5. associated with workspace and source metadata;
6. safe to render in answers;
7. invalid handles are rejected, never guessed;
8. a valid handle can return exact evidence plus source locator.

## 11.1 Citation contract

The generation layer should receive evidence in a structured form similar to:

```json
{
  "handle": "[NORTHSTAR:SURVEY_2026:ROW_184]",
  "source_title": "Northstar Customer Survey 2026",
  "source_class": "customer",
  "locator": {"row": 184},
  "text": "...exact retrieved evidence..."
}
```

The answer generator must reference handles exactly.

> Implementation note: per approved deviation D2 (`docs/ARCHITECTURE_PLAN.md` §0.3), the generator cites run-local aliases (`[E1]..[En]`) that are mapped deterministically to canonical handles from the current run's evidence pack before storage or rendering. Aliases are never persisted as evidence identities, and an alias that does not resolve is removed with a warning.

A deterministic post-generation pass must:

- parse handles;
- reject or strip malformed/unresolvable handles;
- confirm every handle belongs to the current workspace;
- optionally verify that cited claims are textually/semantically supported;
- convert handles into citation-card metadata for the frontend.

## 11.2 No fabricated citations

A citation that does not resolve is a correctness failure. The UI must never quietly render a fake citation.

## 11.3 Claim-evidence distinction

The final answer should distinguish:

- **Evidence** — directly supported by source content.
- **Synthesis / inference** — a reasonable interpretation derived from evidence.
- **Unknown / gap** — not supported by current evidence.

This makes the product useful to consultants while preserving epistemic clarity.

---

# 12. Ingestion Pipeline

The ingestion system should be treated as production infrastructure, not a single helper function.

## 12.1 Supported formats for MVP

Required:

- PDF
- DOCX
- CSV
- XLSX
- PPTX
- plain text / markdown

Optional/stretch:

- image OCR / vision extraction
- webpage snapshot ingestion

## 12.2 Ingestion stages

Recommended flow:

```text
upload
  → validate MIME/type/size
  → hash / idempotency check
  → parse content
  → normalize structure
  → split into parent chunks
  → derive child retrieval windows
  → create locators and evidence handles
  → generate embeddings
  → prepare lexical index
  → persist metadata
  → mark ready
  → run health/sample retrieval check
```

## 12.3 Hierarchical chunking

Do not use arbitrary fixed-size chunks only.

Parent chunks should preserve coherent document structure where possible:

- section/subsection;
- paragraph groups;
- slide;
- spreadsheet table region;
- interview question/answer block;
- survey row cluster where appropriate.

Child chunks should be smaller retrieval windows derived from parent content.

Retrieval should generally rank child chunks. Generation should usually receive the associated parent or a controlled expansion around the child.

## 12.4 Structured-file provenance

CSV/XLSX evidence should preserve row/column/table context.

PPTX evidence should preserve slide number and, where possible, object/text-block context.

PDF/DOCX evidence should preserve page/section location where available.

The citation experience must not degrade to “this came from some spreadsheet.”

## 12.5 Idempotency

Re-uploading the same unchanged document should not duplicate chunks or embeddings.

Use content hashes and explicit source-version behavior.

## 12.6 Ingestion errors

Record structured error categories such as:

- unsupported type;
- parse failed;
- encrypted document;
- empty document;
- embedding unavailable;
- database unavailable;
- malformed spreadsheet;
- content too large.

Failures must be visible to the UI.

---

# 13. Retrieval Engine

The retrieval engine is a major interview focus and should be implemented with enough transparency to explain each stage.

## 13.1 Stage 1 — Query normalization

Normalize conversational noise while preserving semantics.

Support:

- standalone user query;
- query plus limited conversational context;
- workspace/persona filters;
- source-class constraints;
- optional explicit source filters.

Do not blindly concatenate the entire conversation into every retrieval query.

## 13.2 Stage 2 — Dense retrieval

Embed the query and retrieve top candidate child chunks from pgvector, filtered to the current workspace.

Return rank, distance/similarity, handle, parent ID, and source metadata.

## 13.3 Stage 3 — Lexical retrieval

Run keyword/full-text retrieval against the same workspace.

The implementation may use PostgreSQL FTS or a separate lexical component, but it must remain testable and deterministic.

Lexical retrieval is particularly important for:

- named competitors;
- product names;
- acronyms;
- specific numbers;
- quoted terms;
- exact terminology.

## 13.4 Stage 4 — Rank fusion

Fuse lexical and semantic rankings using Reciprocal Rank Fusion (RRF) or a similarly defensible rank-fusion algorithm.

Keep the fusion logic explicit and testable.

## 13.5 Stage 5 — Cross-encoder reranking

Rerank the fused candidate set with a cross-encoder or equivalent model.

The reranker should be behind an interface and should have a graceful fallback. If unavailable, preserve the fused ranking rather than failing the query.

## 13.6 Stage 6 — Parent collapse

Multiple high-scoring child chunks may belong to the same parent context. Collapse duplicates intelligently so the context window is not wasted on repeated fragments.

Keep the best-scoring child as the anchor and bring in its parent context.

## 13.7 Stage 7 — Neighbor expansion

When helpful, include adjacent context around the highest-value passages. This is particularly useful when a child chunk lands in the middle of a narrative, table explanation, or interview answer.

The neighbor policy should be bounded and configurable.

## 13.8 Stage 8 — Source/corpus balancing

A single large source should not always dominate the top-k results simply because it contains many semantically similar chunks.

Implement a diversification rule that can:

- limit excessive same-source duplication;
- preserve the strongest items;
- ensure multiple evidence classes are represented for cross-source questions;
- be disabled when the query explicitly targets one source.

## 13.9 Stage 9 — Structural enumeration support

Questions such as “What are the three themes?” or “List all stated priorities” require different behavior from fuzzy semantic search.

Provide a pathway to preserve enumerations and document structure when retrieval detects list-like questions. The implementation may design this using parent expansion, structured parsing metadata, or query-intent handling.

## 13.10 Retrieval response contract

A retrieval result should contain, at minimum:

```json
{
  "handle": "...",
  "child_text": "...",
  "parent_text": "...",
  "source_id": "...",
  "source_title": "...",
  "source_class": "...",
  "locator": {},
  "dense_rank": 4,
  "lexical_rank": 1,
  "fused_rank": 2,
  "rerank_score": 0.83
}
```

Not every field must be user-visible, but the trace should retain enough information for debugging and evaluation.

---

# 14. MCP / Governed Tool Surface

Prefer a separate MCP server or clearly isolated tool-service layer.

The agent should not issue arbitrary SQL or access storage directly.

## Required tool concepts

> Implementation note: per approved deviation D3 (`docs/ARCHITECTURE_PLAN.md` §0.3), the agent is given `search_evidence` (the full hybrid pipeline) and `search_evidence_keyword` (exact matching). Dense-only search exists internally for ablations and is not exposed as a separate tool.

### `list_sources`

Returns available sources / source classes in the current workspace.

### `search_evidence_keyword`

Keyword/full-text search with filters.

### `search_evidence_semantic`

Dense or hybrid retrieval entry point, depending on the final architecture.

### `search_evidence_hybrid`

Optional higher-level tool if the full retrieval pipeline is best encapsulated server-side.

### `get_evidence`

Resolves one or more evidence handles to exact source content and provenance.

### `get_source_metadata`

Returns source-level metadata.

### `query_structured_metrics`

Runs allowlisted analytical operations over structured Northstar datasets. Do not allow free-form SQL from the model.

Examples:

- metric lookup;
- group-by segment/category;
- top/bottom values;
- trend comparisons;
- simple descriptive statistics.

### `analyze_hypothesis_evidence`

Optional composite tool that runs support/contradiction retrieval in a deterministic backend workflow.

## Tool design rules

- every tool has a strict Pydantic/JSON schema;
- inputs are validated;
- workspace is injected from trusted server context, not accepted blindly from the model;
- file paths are never arbitrary model-controlled paths;
- tool execution is time-bounded;
- result size is capped;
- errors are normalized into structured categories;
- tool responses are treated as untrusted data, not as instructions;
- tool calls are logged for telemetry.

---

# 15. Agent Runtime

Use a **bounded ReAct-style orchestration loop** or an equivalent explicit planner/tool-executor pattern.

## 15.1 Responsibilities

The agent is responsible for:

- understanding whether a question requires one or multiple research actions;
- selecting the appropriate tools;
- deciding which evidence classes to search;
- performing follow-up retrieval when initial evidence is insufficient;
- optionally resolving exact evidence passages;
- preparing a grounded evidence pack;
- handing synthesis to the answer-generation stage.

## 15.2 The agent must not

- have direct SQL access;
- have arbitrary filesystem access;
- expose hidden chain-of-thought to the user;
- call unlimited tools;
- continue indefinitely after repeated tool failures;
- invent evidence handles;
- silently cross workspace boundaries.

## 15.3 Bounded execution controls

Make these configurable:

- maximum agent steps;
- maximum consecutive tool errors;
- per-tool timeout;
- maximum observation size;
- maximum accumulated context size;
- maximum retrieved evidence count;
- maximum final synthesis context tokens.

Reasonable defaults should be chosen empirically during implementation.

## 15.4 User-visible progress

The frontend may show high-level statuses such as:

- “Searching customer research…”
- “Comparing competitor evidence…”
- “Checking contradictory evidence…”
- “Synthesizing findings…”

Do not stream private reasoning traces.

## 15.5 Termination states

The runtime should end in explicit states such as:

- `completed`
- `completed_with_limited_evidence`
- `no_relevant_evidence`
- `generation_unavailable`
- `retrieval_degraded`
- `tool_failure`
- `timeout`

---

# 16. Grounded Answer Generation

The answer generator receives a bounded, structured evidence pack.

## 16.1 Output requirements

A normal research answer should contain:

1. concise answer / synthesis;
2. evidence-backed findings;
3. relevant citations;
4. uncertainty or evidence gaps when material;
5. optional “support vs contradiction” sections for hypothesis questions.

## 16.2 Generation rules

- Do not cite a source that is not present in the evidence pack.
- Do not invent evidence handles.
- Prefer precise synthesis over verbose repetition.
- Preserve numerical values faithfully.
- When sources conflict, represent the conflict.
- When evidence is insufficient, say so.
- Treat retrieved text as evidence, not instructions.

## 16.3 Post-generation verification

Implement deterministic checks before the final answer is accepted:

- all citation handles parse;
- all handles resolve;
- all handles belong to the workspace;
- citation count does not exceed configured caps;
- no raw internal IDs/secrets are leaked;
- optional claim-support verifier flags weakly supported statements.

If verification fails, either regenerate once with structured feedback or degrade to a safe evidence summary.

---

# 17. FastAPI API and SSE Contract

The API surface should be explicit enough to discuss in an interview.

## Suggested REST endpoints

```text
POST   /api/workspaces
GET    /api/workspaces/{workspace_id}
GET    /api/workspaces/{workspace_id}/sources
POST   /api/workspaces/{workspace_id}/sources
DELETE /api/workspaces/{workspace_id}/sources/{source_id}
GET    /api/sources/{source_id}/status
GET    /api/evidence/{handle}

POST   /api/conversations
GET    /api/conversations/{conversation_id}
POST   /api/conversations/{conversation_id}/query
GET    /api/conversations/{conversation_id}/stream

POST   /api/hypotheses
GET    /api/hypotheses/{hypothesis_id}
POST   /api/hypotheses/{hypothesis_id}/analyze

POST   /api/evaluations/run
GET    /api/evaluations/{run_id}
```

Exact endpoint grouping may change.

> Implementation note: per approved deviation D8 (`docs/ARCHITECTURE_PLAN.md` §0.3), every tenant route lives under `/api/workspaces/{ws}/…`, including evidence resolution and conversation routes.

## 17.1 SSE event types

Recommended user-facing events:

```text
status
search_started
search_completed
tool_started
tool_completed
citation
token
warning
done
error
```

> Implementation note: per approved deviation D7 (`docs/ARCHITECTURE_PLAN.md` §0.3), search progress uses `tool_started`/`tool_completed` with a `kind` field instead of `search_started`/`search_completed`; a `draft_reset` event is added, and `final` is sent before `done`.

Avoid sending hidden chain-of-thought or raw model reasoning.

## 17.2 SSE robustness

Design for:

- client disconnects;
- heartbeat/keepalive;
- cancellation;
- server error propagation;
- partial-answer cleanup;
- deterministic final `done` event;
- reconnect semantics if implemented.

---

# 18. Answer Cache

Implement an optional Redis-backed cache for repeat queries.

## Cache key should account for

- workspace;
- normalized query;
- persona;
- source/index version;
- prompt version;
- model version;
- retrieval configuration version.

A cached answer must not survive a corpus update if that would make citations stale.

Cache value should include citations and all metadata required to render the answer without re-querying the model.

Expose cache hit/miss in telemetry.

---

# 19. Graceful Degradation

A strong interview system explicitly defines what happens when dependencies fail.

Create normalized degradation/error codes, for example:

- `DB_UNAVAILABLE`
- `EVIDENCE_EMPTY`
- `RETRIEVAL_LEXICAL_FALLBACK`
- `RERANKER_UNAVAILABLE`
- `LLM_SYNTHESIS_UNAVAILABLE`
- `PACK_BUDGET_TRUNCATED`
- `SOURCES_PENDING`
- `INGEST_EXTRACT_FAILED`
- `CACHE_UNAVAILABLE`
- `TOOL_TIMEOUT`

## Examples

### Embedding service unavailable

Fall back to lexical retrieval and mark the response as retrieval-degraded.

### Reranker unavailable

Use fused rank order.

### Redis unavailable

Bypass cache; do not block core answering.

### No relevant evidence

Do not generate a confident strategy answer from model prior knowledge. Return that current workspace evidence is insufficient and optionally suggest what source class would help.

### Generation provider unavailable

Return ranked evidence cards or a structured evidence-only response instead of a fabricated answer.

### Context budget exceeded

Apply deterministic truncation based on ranked evidence and record `PACK_BUDGET_TRUNCATED` in telemetry.

---

# 20. Evaluation System

Evaluation is a major requirement, not a future enhancement.

The system should support an offline, reproducible evaluation harness with versioned gold datasets.

## 20.1 Evaluation families

### A. Retrieval

Measure at least:

- Recall@K
- MRR
- hit rate
- source-diversity where applicable

Retrieval metrics should be deterministic and should not require an LLM judge.

### B. Grounding / citation

Measure:

- citation validity / resolvability;
- citation precision (does the cited evidence support the claim?);
- citation relevance;
- citation recall / evidence coverage where the gold set makes it measurable;
- unsupported-claim rate.

Where practical, combine deterministic checks with an LLM judge rather than using an LLM judge alone.

### C. Generation

Use RAGAS-style or equivalent metrics such as:

- faithfulness;
- answer relevance;
- context precision;
- context recall;
- answer correctness when a reference answer exists.

### D. Behavioral

Measure:

- correct refusal / evidence-insufficient behavior;
- cross-workspace isolation;
- resistance to retrieved prompt injection;
- correct handling of contradictory evidence;
- correct abstention from unsupported claims.

## 20.2 Gold-set categories

Build a versioned dataset containing categories such as:

- single-source fact lookup;
- cross-source synthesis;
- exact-number retrieval;
- named-entity queries;
- enumeration/list queries;
- ambiguous questions;
- insufficient-evidence questions;
- contradiction questions;
- adversarial prompt-injection cases;
- hypothesis support/contradiction cases.

Every evaluation item should specify:

- query;
- workspace/persona;
- expected relevant source(s) or handles where applicable;
- reference answer if appropriate;
- expected behavior;
- tags/categories.

## 20.3 Baseline and regression reporting

Every meaningful retrieval/prompt/model change should be comparable to a baseline.

Produce a machine-readable report plus human-readable summary containing:

- configuration hash;
- dataset version;
- metric values;
- latency;
- token usage;
- regressions/improvements;
- failing examples.

## 20.4 Initial quality gates

Use these as starting gates, not immutable scientific thresholds:

- 100% returned citation handles resolve;
- 0 known cross-workspace citation leaks;
- retrieval Recall@10 target >= 0.85 on the curated gold set after tuning;
- citation precision target >= 0.90 on evaluated supported claims;
- refusal/evidence-insufficient correctness target >= 0.90 on behavioral cases;
- all deterministic contract tests pass before accepting a model/retrieval change.

If the corpus makes these thresholds unrealistic, document the reason and establish evidence-based replacements.

---

# 21. Observability and Telemetry

A query should be debuggable after the fact without storing hidden chain-of-thought.

Track:

- request/query ID;
- workspace;
- persona;
- query hash or text where appropriate;
- retrieval timings by stage;
- candidate counts;
- top handles before/after rerank;
- number of parent chunks passed to generation;
- context token count;
- model/token usage;
- tool call count;
- cache hit/miss;
- degradation flags;
- citation count;
- end-to-end latency;
- error class;
- termination state.

Provide a developer-facing evaluation/telemetry page or simple dashboard if time permits.

Do not make a complex observability platform a prerequisite for the MVP. Structured logs plus persisted query traces are sufficient initially.

---

# 22. Security and Governance

Even though this is a portfolio project, implement enterprise-relevant controls that are easy to explain.

## Required controls

- workspace-scoped queries at every data-access layer;
- allowlisted tools only;
- no arbitrary SQL from the model;
- no arbitrary filesystem path access;
- MIME/type and upload-size validation;
- secrets only through environment configuration;
- no secrets committed to Git;
- prompt-injection defense: retrieved/source content is untrusted data;
- source content cannot redefine system/tool policy;
- citation resolver validates workspace ownership;
- structured audit trail for uploads, retrieval, and model/tool runs;
- configurable model providers;
- clear README statement that real confidential client data should not be uploaded to third-party models without an approved data policy.

## Optional controls

- simple auth using Clerk/Auth.js/Supabase Auth or equivalent;
- role-based workspace access;
- signed object-store URLs;
- malware scanning for uploads;
- PII tagging / redaction.

Do not allow optional enterprise security work to block the core interview build.

---

# 23. Frontend Requirements

The UI should feel like a polished consulting research product rather than a developer console.

## Required views

### 23.1 Workspace dashboard

Show:

- engagement name;
- source counts by class;
- ingestion status;
- recent conversations;
- hypotheses;
- evaluation/health status (optional summary).

### 23.2 Research chat

Include:

- persona selector;
- conversation history;
- streamed answer;
- high-level progress/status events;
- inline evidence handles;
- expandable citation cards;
- source-filter controls;
- attachment/upload action;
- button to save evidence/findings to a hypothesis.

### 23.3 Evidence viewer

When a citation is clicked, show:

- exact source passage;
- locator;
- surrounding context;
- source metadata;
- source class;
- link/back-navigation to answer.

### 23.4 Sources page

Show:

- file/source name;
- source class;
- format;
- ingestion status;
- chunk count;
- last indexed time;
- errors;
- delete/reindex actions.

### 23.5 Growth Opportunity / Hypothesis page

Show:

- hypothesis statement;
- supporting evidence;
- contradicting evidence;
- neutral/context evidence;
- evidence gaps;
- synthesis;
- analysis timestamp;
- option to rerun analysis after corpus updates.

## UI principle

Do not overbuild visual design before the architecture works. Prioritize clarity, citation trust, and demo reliability.

---

# 24. Structured Analytics Capability

A consulting system should not treat every spreadsheet cell as unstructured text only.

For the Northstar structured datasets, add a narrow analytical tool capable of allowlisted operations such as:

- filter by segment/category/date;
- aggregate sum/mean/count;
- calculate percentage change;
- sort top/bottom categories;
- compare two segments;
- return source row/cell references.

The agent can use this tool when a question is numerical.

Do not expose unrestricted Python execution or arbitrary SQL to the model.

Returned analytical results should also carry provenance, ideally resolvable to dataset/row/cell references.

---

# 25. Performance and Context Management

The project should explicitly address token and latency efficiency, because they are central to running RAG and agent systems in production.

## Required design concerns

- do not send all retrieved text blindly to the model;
- deduplicate/collapse evidence;
- cap parent context size;
- limit conversational history;
- summarize or selectively retain prior turns when needed;
- cache repeated queries;
- cap agent steps;
- allow smaller/cheaper models for query planning or routing if useful;
- keep retrieval and generation model configuration separate.

## Performance objectives

Treat these as engineering targets rather than guarantees:

- first user-visible SSE status event: < 1 second locally under normal conditions;
- common retrieval stage: ideally < 2 seconds after warm-up;
- common end-to-end answer: aim for < 15 seconds depending on model provider;
- cached response: sub-second where practical;
- no unbounded context growth across long conversations.

Record actual measured benchmarks in the final engineering report.

---

# 26. Testing Strategy

The repository should contain meaningful tests. The interview value is in demonstrating that correctness-sensitive AI infrastructure can be tested.

## 26.1 Unit tests

At minimum test:

- evidence-handle parser/formatter;
- citation resolver;
- workspace scoping;
- chunking utilities;
- source locator creation;
- RRF/fusion implementation;
- rerank fallback logic;
- parent collapse;
- neighbor expansion;
- cache-key construction;
- prompt/citation postprocessing;
- graceful-degradation state mapping;
- structured analytics allowlist.

## 26.2 Integration tests

Test:

- upload → parse → chunk → embed → retrieve;
- query → tools → retrieval → generation → citation resolution;
- no-hit behavior;
- embedding failure → lexical fallback;
- reranker failure → fused-rank fallback;
- Redis failure → uncached operation;
- workspace isolation;
- source deletion/reindex invalidating cache/index state;
- SSE event order/termination.

## 26.3 Evaluation regression tests

Run a smaller deterministic subset in CI and the full evaluation set manually or in a separate workflow.

## 26.4 Load / latency test

A lightweight Locust/k6 test is desirable once the core system is stable. Demonstrate concurrent chat requests and ingestion isolation rather than attempting unrealistic internet-scale claims.

---

# 27. Developer Experience and Repository Quality

The repo itself should be interview-ready.

## Required repository artifacts

```text
README.md
ARCHITECTURE.md
SYSTEM_DESIGN.md
EVALUATION.md
SECURITY.md
DEMO.md
docs/adrs/
frontend/
backend/
mcp/ or tools/
eval/
scripts/
seed_data/
tests/
docker-compose.yml
.env.example
```

Exact monorepo structure may differ.

## README must include

- one-paragraph product description;
- architecture diagram;
- quick start;
- demo credentials if local-only;
- seed-data instructions;
- example queries;
- explanation of evidence handles;
- technology stack;
- evaluation snapshot;
- limitations;
- privacy/confidentiality disclaimer.

## Architecture Decision Records

Create ADRs for major choices, for example:

- Why PostgreSQL + pgvector?
- Why hybrid retrieval rather than vector-only?
- Why hierarchical chunks?
- Why RRF?
- Why a reranker?
- Why MCP / governed tools?
- Why SSE rather than WebSockets for answer streaming?
- Why Redis cache?
- Why bounded ReAct instead of an unconstrained agent?
- How are evidence handles designed?
- How is workspace isolation enforced?

Each ADR should state:

- context;
- decision;
- alternatives considered;
- tradeoffs;
- consequences.

These ADRs are extremely important for interview preparation.

---

# 28. CI/CD and Deployment

## CI

Use GitHub Actions or equivalent for:

- formatting/linting;
- backend tests;
- frontend tests/typecheck;
- deterministic retrieval/citation tests;
- small evaluation smoke suite;
- container build validation.

## Deployment

Choose a deployment that is easy to explain and demo reliably.

Possible architecture:

- frontend: Vercel;
- API/worker: Render, Fly.io, Railway, AWS ECS/Fargate, or similar;
- managed Postgres with pgvector;
- managed Redis.

If continuity with prior AWS experience is desired, ECS/Fargate is a strong option, but deployment complexity should not jeopardize interview readiness.

Document:

- network/service boundaries;
- environment variables;
- database migrations;
- health checks;
- rollback approach;
- seed/demo data deployment.

---

# 29. Demo Script the Final Product Must Support

The project is being built for a technical interview. The demo must therefore exercise the architecture intentionally.

## Demo 1 — Basic retrieval and citations

Ask:

> What are the strongest recurring pain points among Northstar’s Gen Z customers?

Show:

- status streaming;
- hybrid retrieval;
- answer with multiple evidence handles;
- click a handle and resolve exact source content.

## Demo 2 — Cross-source agentic research

Ask:

> Which of those pain points are the major competitors failing to address?

Show:

- multiple tool calls/source classes;
- cross-source evidence;
- source diversification;
- grounded comparison.

## Demo 3 — Structured + unstructured evidence

Ask:

> Does Northstar’s product-performance data support what customers say they value most?

Show:

- spreadsheet analytics tool;
- document retrieval;
- joint synthesis;
- provenance from both structured and unstructured data.

## Demo 4 — Hypothesis challenge

Ask:

> Evaluate the hypothesis that Northstar should introduce premium personalized products for Gen Z.

Show:

- support search;
- contradiction search;
- evidence gaps;
- hypothesis workspace.

## Demo 5 — Failure behavior

Temporarily disable the reranker or embedding provider in a dev mode and show graceful fallback.

This is a strong system-design discussion point.

## Demo 6 — Evaluation dashboard/report

Show:

- gold set;
- retrieval metrics;
- citation validity;
- a before/after comparison from one tuning iteration.

This demonstrates that the system was engineered, not merely prompted.

---

# 30. Interview-Readiness Deliverables

The work is not complete when the app “works.” Produce documentation that enables the engineer to explain it deeply.

## Required final interview artifacts

### A. `SYSTEM_DESIGN.md`

Explain the entire request path from user input through final citation resolution.

### B. `ARCHITECTURE.md`

Component diagram and responsibilities.

### C. `RETRIEVAL_DEEP_DIVE.md`

Explain:

- child vs parent chunks;
- lexical retrieval;
- vector retrieval;
- RRF;
- reranking;
- source balancing;
- neighbor expansion;
- token budget;
- failure modes.

### D. `AGENT_AND_MCP.md`

Explain:

- why agentic behavior is needed;
- tool schemas;
- permissions;
- bounded loop;
- circuit-breaker behavior;
- prompt-injection defense;
- why the model does not touch the DB directly.

### E. `EVALUATION.md`

Show:

- gold-set design;
- metrics;
- baseline;
- tuning iterations;
- examples of failures and fixes.

### F. `TRADEOFFS.md`

For every major design, document at least one alternative and why it was not chosen.

### G. `DEMO.md`

A deterministic 5–10 minute interview demo script.

### H. `INTERVIEW_QA.md`

Create at least 50 likely deep-dive questions with concise answers, covering:

- architecture;
- retrieval;
- vector databases;
- keyword search;
- chunking;
- reranking;
- agent design;
- MCP;
- SSE;
- caching;
- context management;
- evaluation;
- hallucination prevention;
- security;
- failure handling;
- scalability;
- deployment;
- tradeoffs;
- what would change at 10x and 100x scale.

The engineer should be able to study this file before the interview.

---

# 31. Implementation Phases

The preferred approach is to build a stable vertical slice early, then deepen it.

## Phase 0 — Repository and local infrastructure

Deliver:

- monorepo structure;
- FastAPI skeleton;
- Next.js skeleton;
- Postgres/pgvector;
- Redis;
- migrations;
- Docker Compose;
- health checks;
- base CI.

Exit criterion: all services start locally and health checks pass.

## Phase 1 — Ingestion + evidence model

Deliver:

- file upload;
- parsing for core formats;
- parent/child chunking;
- evidence handles;
- embeddings;
- lexical indexing;
- source page;
- citation resolver.

Exit criterion: upload a document, retrieve a known passage, and resolve its handle exactly.

## Phase 2 — Hybrid retrieval

Deliver:

- dense search;
- lexical search;
- RRF;
- reranker;
- parent collapse;
- neighbor expansion;
- source balancing;
- retrieval telemetry;
- retrieval unit tests.

Exit criterion: a gold retrieval set can be scored and compared against dense-only baseline.

## Phase 3 — Grounded answering

Deliver:

- evidence pack builder;
- answer generator;
- deterministic citation verification;
- no-hit behavior;
- basic chat UI;
- SSE streaming.

Exit criterion: cited answers resolve to exact evidence and no-hit questions abstain correctly.

## Phase 4 — Agent + governed tools

Deliver:

- MCP/tool server;
- bounded orchestration loop;
- tool error handling;
- multi-source research;
- user-visible progress events.

Exit criterion: cross-source demo query executes multiple controlled tools and produces a grounded result.

## Phase 5 — Structured analytics

Deliver:

- allowlisted CSV/XLSX analytical tool;
- row/cell provenance;
- mixed structured/unstructured synthesis.

Exit criterion: demo query combines spreadsheet statistics with document evidence.

## Phase 6 — Growth Opportunity Workspace

Deliver:

- hypothesis CRUD;
- support/contradiction retrieval;
- evidence classification;
- evidence gaps;
- synthesis page.

Exit criterion: Demo 4 works end-to-end.

## Phase 7 — Evaluation and tuning

Deliver:

- gold sets;
- retrieval metrics;
- grounding metrics;
- behavioral tests;
- baseline report;
- at least two documented tuning iterations.

Exit criterion: regression report is reproducible and quality gates are documented.

## Phase 8 — Hardening

Deliver:

- Redis cache;
- graceful degradation;
- prompt-injection tests;
- improved workspace isolation;
- load testing;
- observability;
- error UX.

Exit criterion: common dependency failures produce explicit fallback behavior.

## Phase 9 — Interview polish

Deliver:

- seeded Northstar demo;
- architecture diagrams;
- ADRs;
- interview Q&A;
- deterministic demo script;
- deployment;
- polished README.

Exit criterion: the project can be demonstrated from a clean environment without manual debugging.

---

# 32. Implementation Freedom

The implementation should make and document decisions for:

- exact LLM provider/model;
- embedding model;
- reranker model;
- ORM/migration framework;
- exact schema names;
- chunk sizes/overlap;
- RRF candidate counts;
- reranker candidate count;
- context budget;
- model routing;
- background job framework;
- object storage provider;
- authentication library;
- UI component library;
- deployment provider;
- metrics/logging library;
- whether lexical search uses Postgres FTS or a separate component.

However, those decisions should be driven by measurable tradeoffs rather than convenience alone.

Whenever choosing among alternatives, prefer:

1. correctness and explainability;
2. demo reliability;
3. architectural similarity to the proven enterprise research-RAG patterns this project is based on (§2);
4. maintainability;
5. performance/cost optimization;
6. novelty for novelty’s sake last.

---

# 33. What the Implementation Must Not Simplify Away

Do not turn the project into:

- a one-file Streamlit app;
- a simple vector-store chatbot;
- direct “upload PDF → send chunks to model” flow;
- a framework demo with no explicit retrieval logic;
- an unconstrained autonomous agent;
- a UI-only mockup;
- a hard-coded scripted demo;
- a system with citations that are merely source filenames;
- a system with no evaluation harness;
- a system where “agentic” just means one function call;
- a system where every question sends every document to the model.

These shortcuts defeat the purpose of the project.

---

# 34. Scope Boundaries / Out of Scope for the Initial Build

Do not block the core project on:

- real enterprise SSO;
- billing;
- multi-region deployment;
- dozens of live third-party connectors;
- real consulting-client data;
- autonomous execution of business decisions;
- complex slide-generation automation;
- production-grade OCR for every edge case;
- internet-scale crawling;
- perfect data-loss-prevention infrastructure;
- fully general spreadsheet reasoning;
- distributed microservices for components that do not need them.

The system should be architecturally credible without becoming impossible to finish.

---

# 35. Acceptance Criteria

The project is not complete until all of the following are true.

## Product

- A user can create/open a workspace.
- A user can ingest the seeded multi-format Northstar corpus.
- Source ingestion status is visible.
- A user can ask research questions and receive streamed responses.
- Answers contain resolvable evidence handles.
- Clicking a citation shows exact evidence and provenance.
- The system can perform cross-source questions.
- The system can analyze a strategic hypothesis using support and contradiction evidence.
- The system can combine at least one structured dataset with unstructured retrieval.

## Architecture

- PostgreSQL/pgvector or an explicitly justified equivalent is used for persistent retrieval storage.
- Semantic and lexical retrieval both exist.
- Rank fusion exists.
- Reranking exists with fallback.
- Parent/child hierarchical chunking exists.
- The model uses governed tools rather than raw DB access.
- Agent execution is bounded.
- SSE or an explicitly justified streaming mechanism is implemented.
- Redis or an equivalent optional cache is implemented or clearly documented as a deliberate omission with reasoning.

## Trust

- 100% of rendered citations resolve.
- No known cross-workspace leakage exists.
- No-hit queries do not produce unsupported confident answers.
- Retrieved prompt injection cannot override system/tool policy in the test suite.
- Source provenance is preserved for all supported formats.

## Evaluation

- Gold set exists and is versioned.
- Dense-only baseline can be compared with hybrid retrieval.
- Retrieval Recall@K and MRR are reported.
- Citation quality is evaluated.
- Refusal/evidence-insufficient behavior is evaluated.
- At least two retrieval or prompting iterations are documented with before/after metrics.

## Engineering quality

- Core modules have tests.
- CI passes.
- Local setup is documented.
- Seed script is reproducible.
- Architecture docs exist.
- Major decisions have ADRs.
- Failure modes are documented.
- The deployed or local demo is deterministic enough for an interview.

---

# 36. Key System-Design Questions the Implementation Should Make Easy to Answer

While building, continually ensure the architecture gives the engineer concrete answers to questions such as:

- Why did you choose hybrid retrieval instead of vector-only search?
- Why PostgreSQL + pgvector instead of a dedicated vector database?
- How does RRF work and why is it useful here?
- Why use a reranker after retrieval?
- Why use parent/child chunks?
- How did you choose chunk size and overlap?
- How do you keep a large source from dominating retrieval?
- How do citations remain stable and resolvable?
- How do you stop the LLM from inventing citations?
- How do you handle structured data differently from prose?
- Why does the agent need tools rather than a single RAG call?
- Why MCP?
- How do you bound the agent?
- What happens when a tool fails?
- What happens when the embedding model fails?
- What happens when no evidence exists?
- Why SSE instead of WebSockets?
- How do you prevent prompt injection through uploaded documents?
- How do you prevent one client workspace from leaking into another?
- How do you evaluate retrieval independently from generation?
- How do you know a generated answer is grounded?
- What does your gold set look like?
- What did you tune based on evaluation results?
- What is cached and how do you invalidate it?
- What is the slowest part of the request path?
- How do you manage context size and cost?
- What would break first at 10x traffic?
- What would you change at 100x corpus size?
- When would you move from Postgres to a separate search/vector system?
- What is synchronous versus asynchronous?
- How would this change for real confidential client data?

Do not merely prepare verbal answers. Wherever possible, make the code and measurements support those answers.

---

# 37. Final Build Philosophy

MarketSignal should demonstrate a specific engineering thesis:

> **Reliable enterprise AI is not primarily a prompting problem. It is a systems problem involving retrieval quality, source provenance, controlled tool access, context management, observability, evaluation, and explicit failure behavior.**

The system should feel like it was built by someone who has already encountered real RAG and agent failure modes and designed around them.

The project’s strongest story is continuity with prior enterprise research-RAG work:

- During a Visa internship, the author worked on trustworthy, citation-backed research over fragmented legal and compliance sources.
- MarketSignal generalizes those engineering principles to strategy consulting, where teams face an analogous information problem across customer, competitor, market, and client evidence.
- The domain changes, but the hard systems questions remain: how to retrieve the right information, preserve source authority, coordinate tools, control an agent, manage context, evaluate quality, and fail safely.

That continuity is intentional. Build MarketSignal so every major architecture choice can be explained from first principles and connected naturally to the general lessons of that prior work.

---

# 38. Required Pre-Implementation Architecture Plan

This requirement is fulfilled by `docs/ARCHITECTURE_PLAN.md`.

Before implementing code, a concise **Architecture Plan** is required, containing:

1. proposed repository structure;
2. component diagram;
3. concrete technology selections;
4. database schema outline;
5. evidence-handle grammar;
6. ingestion pipeline design;
7. retrieval pipeline with proposed candidate counts and model choices;
8. MCP/tool schemas;
9. agent loop state machine;
10. SSE event contract;
11. evaluation architecture;
12. deployment approach;
13. major risks;
14. assumptions;
15. ADRs that need to be written immediately.

Then implement **Phase 0 → Phase 1 → Phase 2** in order. Do not jump directly to polished frontend work before ingestion, citation resolution, and retrieval correctness are proven.

At the end of each phase:

- run tests;
- document what changed;
- record unresolved issues;
- update architecture docs if implementation diverged;
- add or update evaluation cases;
- ensure the next phase builds on a functioning vertical slice.

---

# 39. Concise Product Pitch for README / Interview

Use the following as the baseline pitch, adjusting wording naturally as the product evolves:

> **MarketSignal is an agentic growth-strategy intelligence platform that helps consultants turn fragmented customer, competitor, market, and internal business evidence into grounded strategic insights. It combines hybrid retrieval, reranking, hierarchical context, controlled MCP tools, exact evidence citations, and a quantitative evaluation framework so every important claim can be traced back to its source.**

A slightly more technical interview version:

> **I built MarketSignal to explore how the trustworthy enterprise-RAG patterns I worked with during my Visa internship generalize to strategy consulting. The system uses PostgreSQL/pgvector, hybrid lexical and semantic retrieval, rank fusion and reranking, parent-child chunks, a bounded MCP-based agent, SSE streaming, immutable evidence handles, caching, and a gold-set evaluation harness. The key design goal is that strategic synthesis is useful, but still auditable back to exact evidence.**

---

# 40. Final Build Guidance

Treat this specification as the product and architecture contract. Preserve the core architecture, but make thoughtful implementation decisions rather than following the document mechanically. When there is a choice between a flashy feature and a defensible engineering subsystem, prioritize the subsystem.

The final result should be something the engineer can:

1. demo reliably;
2. explain end-to-end without hand-waving;
3. defend under deep system-design questioning;
4. compare naturally with the enterprise research-RAG architecture patterns from prior work;
5. continue extending after the interview.
