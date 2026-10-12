# MarketSignal demo guide

A 3 to 5 minute walkthrough of MarketSignal, run fully offline against saved runs. No model is called during the demo: the API runs with `MS_LLM_ENABLED=false`, so new questions are refused before any provider call and the UI says **Live model unavailable**. Everything shown comes from persisted runs, the deterministic analytics engine, or committed evaluation artifacts.

All URLs assume the frontend on `http://localhost:3000` and the Northstar workspace. Shorthand: `W = http://localhost:3000/w/NORTHSTAR`.

## Pre-demo checklist

Do this 10 minutes before.

1. `make up`: Postgres and Redis are healthy.
2. `make api-demo`: API on `:8000` with the live model off and test workspaces hidden. Check that `curl -s localhost:8000/readyz` reports `"status":"ready"`.
3. `pnpm --dir frontend dev`: frontend on `:3000`.
4. **Fresh database only:** `make worker`, `make seed` and `make demo-seed`. An existing local database already holds the corpus and the saved runs.
5. Optional: `make demo-verify` re-verifies every curated insight number and citation against the corpus.
6. **Warm the caches.** The dev server compiles each route on first visit, so open every URL in the table below once, in order.
7. Check the sidebar footer: it says **Live model unavailable**. That is by design, not a fault. Say so if anyone asks.
8. Browser at 1440 px or wider, zoom 100%, one tab per step if you want instant switching.

| Step | URL |
|---|---|
| 1. Overview | `W/overview` |
| 2. Ask MarketSignal | `W/ask/0ec3ca8c-5a3d-41c4-aca2-6f0967dacb51` |
| 2b. Same question, standard mode | `W/ask/7c8c6da4-1551-4a53-bbcd-9018de5957ba` |
| 2c. Same question, research mode | `W/ask/97c28be3-392b-46b3-aa5d-4cf86bcc45da` |
| 3. Evidence drawer | `W/evidence?ev=NORTHSTAR%2FBRAND-STRATEGY%40v1%3AP4.B2` |
| 4. Analytics | `W/analytics/genz-top-pain-points` |
| 5. Growth Opportunities | `W/opportunities/O2` |
| 6. Telemetry run trace | `W/dev/telemetry/runs/6f18725e-3095-4aab-a90f-ae8505d7dc55` |
| 6b. Evidence-only fallback | `W/dev/telemetry/runs/288b6e18-8682-4d67-b35d-2a62edd76bb5` |
| 7. RAG Evaluation | `W/dev/evaluation?tab=retrieval`, then `?tab=grounded` and `?tab=research` |
| 8. Evidence Library | `W/evidence` |

## Opening line (10 s)

> "MarketSignal helps a strategy team turn scattered customer, competitor, market and internal evidence into growth insights they can defend. Every claim points to an exact passage or a computed figure, and a deterministic verifier checks it. It's decision support: it lays out the evidence for and against, and the strategist decides."

## Walkthrough

### 1. Overview (30 s)

**Go to** `W/overview` (or click **Overview** in the sidebar).

**You will see** the Northstar Athletics header and a workspace summary: evidence sources, structured datasets, customer evidence, research runs and saved results. Below that are **Key signals** from the curated analyst brief, each with figures, numbered evidence chips and a **Verified against current evidence** status, plus a line saying when the brief was re-verified.

**Say:**
- "Northstar is a fictional apparel company. Everything here is synthetic."
- "The first signal is fit inconsistency: 27.0% of 400 Gen Z respondents name it as their top frustration, against 19.0% of the 200 respondents aged 28 and over."
- "These signals are curated, not generated. On every page load the figures are recomputed from the survey dataset and each citation is re-resolved. Anything that stops verifying is hidden."

### 2. Ask MarketSignal (75 s)

**Go to** `W/ask/0ec3ca8c-5a3d-41c4-aca2-6f0967dacb51`, or click **Ask MarketSignal** and pick the first **Featured** conversation: *"How many survey respondents call knit upper durability their biggest problem, and what kinds of wear do they report?"*

**You will see**
- The answer in fixed sections: **Answer**, **Interpretation** (labelled *Inference*), **Key findings**, then **Supporting evidence** grouped by source.
- The headline count (68 of the 600 survey rows) carries a **Computed** chip, separate from the numbered evidence citations.
- Numbered citations on every finding. The supporting evidence shows the survey rows quoted verbatim, plus a support-themes page and the brand strategy document.
- Further down: the computed result panel (a count on the customer survey dataset, version 1) and **Research details** for the run.
- At the bottom, the question box is disabled with the **Live model unavailable** notice.

**Say:**
- "This is a mixed question: one part needs a number, the other needs customer language. The router saw the numeric cue and sent it to research mode."
- "The agent didn't do the arithmetic. It asked a governed analytics tool to count rows, and code computed 68. That result is cited as a computed figure, not as evidence."
- "The wear descriptions are cited to exact survey rows. Inference is labelled as inference."
- "The verifier made corrections before accepting it: it removed numbers that had slipped into the gaps section."

**Then show the mode tradeoff** (optional, 20 s). In the conversation list, open the two featured entries that ask *"How much do young shoppers care about fast delivery…"*. The standard one is marked *Same question as above, answered for comparison*.
- Standard (`7c8c6da4`): one model call, no tool calls, about 9.4 s.
- Research (`97c28be3`): four model calls and four tool calls, about 16.4 s.
- "Same question; both answers cite five passages. Research mode is slower and costs more. I'll show the measured tradeoff in the evaluation page."

These run figures come from the Telemetry pages for runs `a17ab246` and `f63a469f`.

### 3. Evidence drawer (20 s)

**Click** citation **1** in the answer, or any **Open passage** link. For the canonical example, open `W/evidence?ev=NORTHSTAR%2FBRAND-STRATEGY%40v1%3AP4.B2`.

**You will see** the **Evidence passage** drawer: source title, class and format, the page and section path, the full passage, the text **Before this passage** and **After this passage**, the passage parts, and a **Technical details** disclosure.

**Say:**
- "Every citation in the product opens this drawer at the exact passage in the exact source version. This one is page 4 of the brand strategy: it says fit is named by 27% of Gen Z respondents, the same figure the Overview recomputed from the raw survey."
- Open **Technical details**: "Underneath is an immutable handle, `NORTHSTAR/BRAND-STRATEGY@v1:P4.B2`: workspace, source, version, locator. A new upload creates a new version, so old citations still resolve."

### 4. Analytics (25 s)

**Go to** **Analytics** in the sidebar and open **Top pain points among Gen Z respondents** (`W/analytics/genz-top-pain-points`).

**You will see** **What was measured** (question, filters, grouped by, base of 400 Gen Z respondents), a **Result** bar list headed *Computed from structured data* (fit inconsistency 108, price vs value 72, sizing across categories 56, knit upper durability 48, and so on), **Provenance** (dataset, version 1, table, 400 rows matched, recomputed time) and **Caveats**.

**Say:**
- "These analyses run on the same deterministic engine the agent uses. No model is involved and nothing is cached: the numbers are recomputed from the versioned dataset on each load."
- "108 of 400 is the 27.0% on the Overview."

### 5. Growth Opportunities (40 s)

**Go to** **Growth Opportunities** and open **Personalization as a premium tier** (`W/opportunities/O2`).

**You will see** a **Mixed evidence** status, the thesis and the status rationale, then **Supporting evidence (6)** and **Contradicting evidence (7)** side by side, with analyst notes on some passages. Further down: quantitative signals recomputed from the datasets, gaps, the next step and caveats.

**Say:**
- "This is the strongest strategy story. Stated demand: 38% of Gen Z respondents say they'd pay a 15% premium for personalized fit."
- "Revealed behaviour disagrees: only 9% of pilot shoppers picked the 15% premium tier, pilot buyers repurchased at 18% against 24% for the control group, and the average lead time was 12 days."
- "So the status is Mixed evidence, not a score. The gaps are explicit: no cohort dataset for the pilot, no unit economics. The next step is to test personalization at standard lead time while the national rollout stays paused."
- "There are no opportunity scores anywhere. Status is qualitative, and every quoted number is re-verified against its passage."

### 6. Telemetry (35 s)

**Go to** **Telemetry** (`W/dev/telemetry`), then open the knit-durability run (`W/dev/telemetry/runs/6f18725e-3095-4aab-a90f-ae8505d7dc55`). This is the same run as the Ask demo.

**On the summary page, you will see** runs by mode, latency p50/p95 by mode and by stage, mean tokens, model and tool calls per run, **Estimated cost (list prices)**, regeneration and fallback rates, and an audited table of research tool calls. The **Include test-harness runs** checkbox is off, and the count of excluded runs is shown under it.

**On the run page, you will see**
- **Outcome**: completed, 17.8 s. Calls: 5 model / 5 tool.
- Tokens: 21,725. Estimated cost about $0.06 at list prices, not billed.
- Passages cited: 12, of 13 in the pack, including 1 computed. **Verification**: verified after corrections.
- **Route decision**: requested Automatic, decided Research, because *the question needed computed figures* (cues: numeric, analytics).
- **Research steps**: 4 steps, 5 tool calls, stopped by `finish_research`, 22 passages in the evidence pool.
- **Stage timing**: research steps 9.31 s, evidence pack 8 ms, synthesis 8.24 s, verification 26 ms.
- **Timeline**: each tool call (describe_dataset, search_evidence, the count on the survey dataset, get_evidence) with its status and duration.
- A notice: *Model reasoning is not recorded*.

**Say:**
- "This is all persisted run data: route decision, stage timings, every governed tool call with its duration, and the verification attempt. Verification costs tens of milliseconds; the time goes into the agent and synthesis."
- "We record observable actions, not model reasoning. Cost is an estimate from stored token counts at list prices."

**Optional (15 s):** open `W/dev/telemetry/runs/288b6e18-8682-4d67-b35d-2a62edd76bb5`. It shows **Evidence only (live model unavailable)**, a **Degraded run** callout (*Research planning unavailable*, *Live model unavailable*), 0 tokens, and 8 passages still cited. "When the model was unavailable, the run fell back to retrieved evidence and said so. It never fabricated an answer."

### 7. RAG Evaluation (45 s)

**Go to** **RAG Evaluation** (`W/dev/evaluation?tab=retrieval`).

**Retrieval tab, you will see** two callouts: hybrid recovered more expected evidence than vector-only on the held-out split (ΔRecall@10 +0.324, 95% CI +0.118 to +0.529, n = 17), and a **Negative finding**: the reranker lowered held-out recall (ΔRecall@10 −0.167, CI −0.343 to −0.020). Below are dense, lexical, hybrid and hybrid + reranker compared with intervals and latency, paired comparisons, and **Decisions**.

**Say:**
- "Held-out Recall@10: dense 0.549, lexical 0.814, hybrid 0.873. Hybrid is the production default."
- "The reranker is my favourite result. On dev it improved MRR, so it looked like a win. On the held-out split it lost recall, and its p50 latency is 670 ms against 27 ms for hybrid, so we rejected it." Toggle **Split** to *Dev* to show the dev numbers, then back.
- "Two other ideas, a BGE query prefix and source balancing, also lost on dev and weren't adopted. Each **Source** link points to the committed artifact."

**Grounded answers tab** (`?tab=grounded`): **Safety gates** all pass: 256/256 citations resolve, 256/256 sit in the evidence pack, 76/76 runs with no cross-workspace leak. "The weakest category is called out: conflict questions."

**Standard vs Research tab** (`?tab=research`, *Held-out test*): research retrieves more gold evidence (0.794 to 0.906) and cites more (0.822 to 0.937), but states gold values no better (not distinguishable). It uses about 5,212 against 20,393 tokens per run, and p50 latency goes from 5.78 s to 14.4 s. "Research isn't better on every measure; it's a cost and latency trade. That's why a deterministic router picks the mode."

### 8. Evidence Library (15 s)

**Go to** **Evidence Library** (`W/evidence`).

**You will see** the source count, how many are ready and the number of evidence passages; a passage search box; filters for type, category and status; an *Include superseded versions* toggle; and the sources table.

**Say:** "Seven formats come in through one ingestion pipeline: PDF, Word, PowerPoint, Excel, CSV, Markdown and plain text. Each becomes versioned parent and child passages with exact character spans. That's what makes the citations exact."

### Close (10 s)

> "In short: hybrid retrieval, deterministic analytics, a bounded agent behind governed tools, and a verifier, all measured, including the things that didn't work."

## Architecture talking points

Use these for follow-up questions.

- **Two modes, one tail.** Standard mode retrieves once and synthesises; research mode runs a bounded agent. Both feed the same evidence pack, synthesis and deterministic verifier. A deterministic router picks the mode from cues, and the user can override it. ([ADR-0015](adr/0015-standard-vs-research-modes.md))
- **Parent-level RRF.** Children are embedded for recall; fusion and citation happen on the parent passage. ([ADR-0002](adr/0002-hybrid-retrieval-parent-level-rrf.md), [ADR-0003](adr/0003-parent-child-chunks-parent-citation-unit.md))
- **Aliases, not handles, in the prompt.** The model cites run-local aliases that map deterministically to canonical handles, and a streaming gate holds back text until its citations are known. ([ADR-0004](adr/0004-evidence-handle-grammar-and-alias-citations.md))
- **Governed tools.** Eight read-only tools (four evidence, four analytics), each call carrying a run-scoped capability token. The workspace comes from trusted context, never from the model. The same tools are served in-process and over MCP Streamable HTTP, with a parity test. ([ADR-0006](adr/0006-governed-mcp-tool-boundary.md), [governed tools and MCP](GOVERNED_TOOLS_AND_MCP.md))
- **Bounded agent.** An explicit state machine with a fixed order of bound checks (time, tool errors, pool size, steps, tool calls, tokens, context), each with its own stop reason. ([ADR-0007](adr/0007-bounded-agent-state-machine.md), [research agent](RESEARCH_AGENT.md))
- **The model chooses, code computes.** Analytics tools accept only closed enums and bounded values: no SQL and no code execution. ([ADR-0020](adr/0020-deterministic-structured-analytics.md))
- **Isolation.** The API connects as a non-privileged role, and Postgres RLS guards every tenant table. ([ADR-0009](adr/0009-workspace-isolation.md))
- **Honest limits.** Analytics routing held up on dev (36/36) but not on holdout (31/54). The verifier still misses non-numeric hallucinations. The research-summary hand-off was not measured live. ([Phase 5 report](phase-reports/phase-5.md))

## Fallback plan

| Problem | What to do |
|---|---|
| The frontend shows an API error or empty pages | Check `curl -s localhost:8000/readyz`. Restart with `make api-demo`. If Postgres is down, run `make up`. |
| A page is slow on first open | That's dev-mode compilation. Keep talking; next time warm the caches. |
| A citation click doesn't open the drawer | Use the direct URL from step 3, or **Open passage** on a supporting-evidence card. |
| Featured conversations are missing | The database wasn't seeded with the demo snapshot. Run `make demo-seed` (it needs `make seed` on a fresh database). Meanwhile, demo Overview, Opportunities, Analytics and Evaluation, which don't depend on saved runs. |
| A curated signal or opportunity is hidden | It failed re-verification against the corpus. Run `make demo-verify` to see why, and use a different signal. |
| Someone asks you to ask a new question | "Live generation is turned off for this offline demo; it needs an API key. Here is a saved run of the same kind." Open backup conversation `42719cd8-909b-4997-a25e-2b08508a029e` (Gen Z cart abandonment over size charts, plus competitor gait scanning; research run `1d6c6de2`) or `75577600-577c-4ae7-aaa2-964175d647f6` (a clean standard run accepted with no repairs; run `fbffdd6b`, which has retrieval traces in Telemetry). |
| Nothing works | Walk through the measured results in the README and this guide's talking points, and pivot to the architecture discussion. |

## Short and long versions

**3-minute version.** Keep steps 1, 2 (skip the mode pair), 5, 6 (run trace only) and 7 (Retrieval tab only, with the reranker finding). Skip 3 (mention the drawer in step 2 with one citation click), 4 and 8.

| Step | 3 min | 5 min |
|---|---|---|
| Opening | 10 s | 10 s |
| 1. Overview | 20 s | 30 s |
| 2. Ask MarketSignal | 50 s (one citation click) | 75 s (with the mode pair) |
| 3. Evidence drawer | merged into step 2 | 20 s |
| 4. Analytics | skip | 25 s |
| 5. Growth Opportunities | 35 s | 40 s |
| 6. Telemetry | 25 s (run trace) | 35 s (summary, trace, fallback) |
| 7. RAG Evaluation | 30 s (Retrieval tab) | 45 s (three tabs) |
| 8. Evidence Library | skip | 15 s |
| Close | 10 s | 10 s |

**If time runs short mid-demo,** drop in this order: Evidence Library, the evidence-only fallback run, the Standard vs Research tab, Analytics, the mode pair. Always keep the O2 opportunity and the reranker negative finding: they carry the product story and the engineering story.
