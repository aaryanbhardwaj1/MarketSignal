# MarketSignal demo guide

A 5 to 8 minute interview walkthrough of MarketSignal, run fully offline. The business story comes first (Chat, Evidence, Analytics, Insights, Growth Opportunities, a presentation), then the trust story (Telemetry and RAG Evaluation).

No model is called during the demo. The API runs with `MS_LLM_ENABLED=false`, so new questions are refused before any provider call and the UI says **Live model unavailable**. That is by design, not a fault. Everything shown comes from persisted runs, the curated brief re-verified on each request, the deterministic analytics engine, or committed evaluation artifacts.

All URLs assume the frontend on `http://localhost:3000` and the Northstar workspace. Shorthand: `W = http://localhost:3000/w/NORTHSTAR`.

## Pre-demo checklist

Do this 10 minutes before.

1. `make up`: Postgres and Redis are healthy.
2. `make api-demo`: API on `:8000` with the live model off and test workspaces hidden. Check that `curl -s localhost:8000/readyz` reports `"status":"ready"`.
3. Frontend on `:3000`. **Recommended for the interview:** a production build,
   `pnpm --dir frontend build && pnpm --dir frontend start`. It has no compile pauses and no
   development badge. `pnpm --dir frontend dev` also works.
4. **Fresh database only:** `make worker`, `make seed` and `make demo-seed`. An existing local database already holds the corpus and the saved runs; do not re-seed it.
5. Optional: `make demo-verify` re-verifies every curated insight number and citation against the corpus.
6. **Warm the pages.** Open every URL in the table below once, in order. This matters most with the dev server, which compiles each route on first visit. It also fills the server log you show in step 7.
7. Check the notice in Chat: it says **Live model unavailable**. Say so if anyone asks.
8. Browser at 1440 px or wider, zoom 100%, one tab per step if you want instant switching.

| Step | URL |
|---|---|
| 1. Chat | `W/ask`, then `W/ask/0ec3ca8c-5a3d-41c4-aca2-6f0967dacb51` |
| 2. Evidence | `W/evidence?ev=NORTHSTAR%2FBRAND-STRATEGY%40v1%3AP4.B2` |
| 3. Analytics | `W/analytics/genz-top-pain-points` |
| 4. Insights | `W/insights` |
| 5. Growth Opportunities | `W/opportunities/O2` |
| 6. Create presentation | `W/insights/deck?s=premium-ceiling,personalization-lead-time,personalization-status-signal,personalization-niche-outlook,kinetic-return-claim&o=O2&a=pain-points-by-cohort,fit-and-personalization-by-segment,price-sensitivity-by-cohort` |
| 7. Telemetry | `W/dev/telemetry`, `W/dev/telemetry/runs/6f18725e-3095-4aab-a90f-ae8505d7dc55`, `W/dev/telemetry/runs/288b6e18-8682-4d67-b35d-2a62edd76bb5`, `W/dev/telemetry?tab=logs` |
| 8. RAG Evaluation | `W/dev/evaluation?tab=overview`, then `retrieval`, `grounded`, `research`, `ragas`, `failures` |

The step 6 URL is exactly what the **Create presentation** button on O2 opens: the opportunity plus its related insights and analyses.

## Opening line (10 s)

> "MarketSignal helps a strategy team turn scattered customer, competitor, market and internal evidence into growth insights they can defend. Every claim points to an exact passage or a computed figure, and a deterministic verifier checks it. It's decision support: it lays out the evidence for and against, and the strategist decides."

## Walkthrough

### 1. Chat (75 s)

**Go to** `W/ask`, then open the first entry under **Saved research** in the sidebar: *"How many survey respondents call knit upper durability their biggest problem, and what kinds of wear do they report?"* (`W/ask/0ec3ca8c-5a3d-41c4-aca2-6f0967dacb51`).

**You will see**
- A clean start page, with saved research listed first and the question box showing the **Live model unavailable** notice.
- The answer laid out as a short research report: an executive answer with an interpretation tagged **Inference**, key findings, computed figures, supporting evidence grouped by source, and evidence gaps.
- The headline count (68 of the 600 survey rows) carries a **Computed** chip, separate from the numbered evidence citations.
- **Research steps** for the run, with a replay that plays the saved stages back at their recorded timings.

**Say:**
- "Northstar is a fictional apparel company. Everything here is synthetic."
- "This question needs a number and customer language. The router saw the numeric cue and sent it to research mode. The agent asked a governed analytics tool to count rows, and code computed 68. That figure is cited as a computed result, not as evidence."
- "The wear descriptions are cited to exact survey rows, and the verifier corrected the draft before accepting it."

### 2. Evidence (30 s)

**Click** citation **1** in the answer. For the canonical example, open `W/evidence?ev=NORTHSTAR%2FBRAND-STRATEGY%40v1%3AP4.B2`.

**You will see** the evidence panel: source title, class and format, the page and section path, the full passage with the text before and after it, and a **Technical details** disclosure.

**Say:**
- "Every citation opens the exact passage in the exact source version. This is page 4 of the brand strategy: fit inconsistency is named by 27% of Gen Z survey respondents as their top frustration."
- Open **Technical details**: "Underneath is an immutable handle, `NORTHSTAR/BRAND-STRATEGY@v1:P4.B2`: workspace, source, version, locator. A new upload creates a new version, so old citations still resolve."

### 3. Analytics (30 s)

**Go to** **Analytics** and open **Top pain points among Gen Z respondents** (`W/analytics/genz-top-pain-points`).

**You will see** the question, the filter (age groups 18-21, 22-24 and 25-27), a base of 400 Gen Z respondents, and a bar chart: fit inconsistency 108, price vs value 72, sizing across categories 56, knit upper durability 48, sustainability transparency 36, delivery speed 32, lack of personalization 28, community and social proof 20. Below are the provenance (Northstar Customer Survey 2026, version 1, 400 rows matched), an interpretation labelled **Inference**, caveats, and **used by** links to the insights and the opportunity that rely on it.

**Say:**
- "No model here. The deterministic engine recomputes this from the versioned dataset on every load; nothing is cached."
- "108 of 400 is the same 27% the brand strategy states. The **used by** links show which insights depend on this number."

### 4. Insights (50 s)

**Go to** **Insights** (`W/insights`).

**You will see** the curated brief in six categories: Strategic Opportunities, Emerging Signals, Risks / Blockers, Competitor Findings, Optimization Opportunities and Future Outlook. Each item has a status, a claim type, evidence counts for and against, and a verification indicator.

Point at three items:
- **Observed:** *Fit inconsistency is the top Gen Z frustration*: 27.0% of Gen Z respondents against 19.0% of respondents aged 28+, recomputed.
- **Forecast:** under Future Outlook, *Personalization expected to stay niche through 2028*. It is labelled **Projection stated by Northstar Consumer Panel Analyst Call Notes**, and its implication is tagged as Inference.
- **Contradiction indicator:** *Stated premium tolerance tops out around 15%* shows mixed evidence, with three supporting passages and one contradicting.

**Say:**
- "Every statement has a claim type: Observed, Derived, Inference, Hypothesis or Forecast. The schema rejects a claim without the support its type needs. A forecast must be stated by a cited source; we never forecast on our own."
- "This brief is written by an analyst, not generated. On every request each passage is re-resolved and each figure recomputed, and the page shows the result."

### 5. Growth Opportunities (50 s)

**Go to** **Growth Opportunities** and open **Personalization as a premium tier** (`W/opportunities/O2`).

**You will see** a **Mixed evidence** status, the thesis (tagged Inference), why it matters, then **Supporting evidence (6)** and **Contradicting evidence (7)** side by side. Further down: risks with their evidence, recomputed figures, gaps, the next step and the next question to investigate.

**Say:**
- "This is the strongest strategy story. Stated demand: 38% of Gen Z respondents say they would pay a 15% premium for personalized fit."
- "What shoppers actually did disagrees: only 9% of pilot shoppers chose the 15% premium tier, pilot buyers repurchased at 18% against 24% for the matched control group, and lead time averaged 12 days."
- "So the status is Mixed evidence, not a score. The gaps are explicit: the pilot exists only as prose with no cohort dataset, and there are no unit economics. The next question: does personalization at standard lead time change repeat purchase against a matched control?"

### 6. Create presentation (50 s)

**Click** **Create presentation** on O2. It opens the deck builder with the opportunity, its five related insights and three related analyses preselected (step 6 URL).

**You will see**
- The selection and a live outline in fixed sections: title, executive summary, key customer findings, quantitative evidence, competitor and market findings, growth opportunities, risks and blockers, next steps. Empty sections are left out.
- On generate, the stages *Structuring findings*, *Selecting supporting evidence*, *Creating narrative*, *Building slides* and *Finalizing presentation*.
- A slide preview in the browser (arrow keys move between slides), each slide with its numbered sources, and a `.pptx` download.
- An excluded list for any selected item that failed re-verification, each with a plain reason. With the seeded corpus every item verifies, so this list stays empty; say what it is for.

**Say:**
- "The deck is built on the server from the same re-verified brief, with no model. Slide text is copied from the verified findings; only section titles, status labels and counts are fixed text. Inference, Hypothesis and Forecast claims keep their tags."
- "It fails closed: an item whose main claim lost its support is excluded and reported, never padded. The same input renders the same file."

### 7. Telemetry (50 s)

**Go to** the **Telemetry** icon in the top bar (`W/dev/telemetry`).

**On Overview, you will see** charts titled *How did runs end?*, *How long does a run take?*, *Where does the time go?*, *How many model calls per run?* and *Which research tools run?*, plus estimated cost at list prices. **Include test-harness runs** is off by default.

**Open the run trace** for the Chat demo (`W/dev/telemetry/runs/6f18725e-3095-4aab-a90f-ae8505d7dc55`):
- Completed in 17.8 s, 5 model calls and 5 tool calls, 21,725 tokens, an estimated $0.06 at list prices.
- 12 of 13 passages in the pack cited; verified after corrections.
- Route: requested Automatic, decided Research (cues: numeric, analytics).
- Research: 4 steps, stopped by `finish_research`, 22 passages in the pool.
- Stage timing: research steps 9.31 s, evidence pack 8 ms, synthesis 8.24 s, verification 26 ms.
- *Model reasoning is not recorded.*

**Optional:** the evidence-only fallback (`W/dev/telemetry/runs/288b6e18-8682-4d67-b35d-2a62edd76bb5`): research planning and synthesis were unavailable, 0 tokens, and 8 passages still cited. "When the model was unavailable, the run fell back to retrieved evidence and said so. It never made up an answer."

**Then open Server logs** (`W/dev/telemetry?tab=logs`): the API's own requests from this demo, each with method, route, status, duration and request id. Health checks are hidden unless you switch them on.

**Say:**
- "This is persisted run data: route decision, stage timings, every governed tool call, and the verification attempt. Verification costs tens of milliseconds; the time goes into the agent and synthesis."
- "The server log is sanitized at capture. It keeps ids, statuses and durations and drops questions, answers, bodies, headers and query strings. It lives in memory in this API process and is mounted only in development."

### 8. RAG Evaluation (60 s)

**Go to** the **RAG Evaluation** icon (`W/dev/evaluation?tab=overview`).

**Overview** shows four story cards: *Hybrid beats dense on held-out recall*, *Reranker rejected*, *Every citation resolves and stays in the evidence pack*, and *Standard vs Research trade-off*. Each links to its tab.

**Retrieval** (`?tab=retrieval`): held-out Recall@10 is dense 0.549, lexical 0.814, hybrid 0.873 (n = 17). Hybrid vs dense ΔRecall@10 +0.324 (95% CI +0.118 to +0.529). **Negative finding:** the reranker improved MRR on dev but lowered held-out Recall@10 by 0.167 (CI −0.343 to −0.020), with a p50 latency of 670 ms against 27 ms for hybrid.
- "The reranker is my favourite result. On dev it looked like a win; on held-out it lost recall and cost latency, so we rejected it."

**Grounding & safety** (`?tab=grounded`): the safety gates pass: 256/256 citations resolve, 256/256 sit in the evidence pack, 76/76 runs with no cross-workspace leak.

**Standard vs Research** (`?tab=research`): research retrieves more gold evidence (0.794 to 0.906) and cites more (0.822 to 0.937), but states gold values no better. It uses 20,393 tokens per run against 5,212, and p50 latency rises from 5.78 s to 14.40 s.
- "Research isn't better on every measure; it's a cost and latency trade. That's why a deterministic router picks the mode."

**RAGAS** (`?tab=ragas`): metrics computed offline on persisted outputs, with no model calls. ID-based context recall over the evidence pack: 0.894 on Phase 3 grounded answers (n = 59), and 0.736 standard vs 0.864 research on the Phase 4 test split (n = 30 each). Model-judged metrics are listed as not run.
- "RAGAS runs in an isolated runner with its own lockfile. Its recall reads lower than our historical figure (0.736 vs 0.794 for standard) because it counts every alternate gold handle; recomputing our per-fact rule on the same items reproduces the historical numbers exactly."
- "Faithfulness and answer relevancy are wired but not run: no model credits. I'd rather show 'not run' than a number I didn't measure."

**Failure analysis** (`?tab=failures`): *Failed cases are preserved, not discarded*, with failure buckets by run.

### Close (10 s)

> "In short: hybrid retrieval, deterministic analytics, a bounded agent behind governed tools, a verifier, and curated insights and decks that are re-verified on every request. All measured, including what didn't work."

## Architecture talking points

Use these for follow-up questions.

- **Two modes, one tail.** Standard mode retrieves once and synthesises; research mode runs a bounded agent. Both feed the same evidence pack, synthesis and deterministic verifier. A deterministic router picks the mode from cues, and the user can override it. ([ADR-0015](adr/0015-standard-vs-research-modes.md))
- **Parent-level RRF.** Children are embedded for recall; fusion and citation happen on the parent passage. ([ADR-0002](adr/0002-hybrid-retrieval-parent-level-rrf.md), [ADR-0003](adr/0003-parent-child-chunks-parent-citation-unit.md))
- **Aliases, not handles, in the prompt.** The model cites run-local aliases that map deterministically to canonical handles, and a streaming gate holds back text until its citations are known. ([ADR-0004](adr/0004-evidence-handle-grammar-and-alias-citations.md))
- **Governed tools.** Eight read-only tools (four evidence, four analytics), each call carrying a run-scoped capability token. The workspace comes from trusted context, never from the model. The same tools are served in-process and over MCP Streamable HTTP, with a parity test. ([ADR-0006](adr/0006-governed-mcp-tool-boundary.md), [governed tools and MCP](GOVERNED_TOOLS_AND_MCP.md))
- **Bounded agent.** An explicit state machine with a fixed order of bound checks, each with its own stop reason. ([ADR-0007](adr/0007-bounded-agent-state-machine.md), [research agent](RESEARCH_AGENT.md))
- **The model chooses, code computes.** Analytics tools accept only closed enums and bounded values: no SQL and no code execution. ([ADR-0020](adr/0020-deterministic-structured-analytics.md))
- **Claim types.** Observed, Derived, Inference, Hypothesis and Forecast, each with a support rule the brief's schema enforces; a forecast needs a cited passage that states the projection.
- **RAGAS in isolation.** The runner has its own lockfile, never imports the backend, switches off RAGAS usage tracking and scores exported persisted outputs. ([ADR-0021](adr/0021-ragas-isolated-runner.md))
- **Grounded decks.** Composed on the server from the re-verified brief, fail-closed per item, rendered with python-pptx to identical bytes for the same input. ([ADR-0022](adr/0022-grounded-deck-generation.md))
- **Server log.** A sanitized, bounded ring buffer in the API process; nothing written to disk or the database; mounted only outside production. ([ADR-0023](adr/0023-developer-server-log.md))
- **Isolation.** The API connects as a non-privileged role, and Postgres RLS guards every tenant table. ([ADR-0009](adr/0009-workspace-isolation.md))
- **Honest limits.** Analytics routing held up on dev (36/36) but not on holdout (31/54). The verifier still misses non-numeric hallucinations. RAGAS model-judged metrics were not run. The developer tools have no role checks yet. ([Phase 5 report](phase-reports/phase-5.md))

## Fallback plan

| Problem | What to do |
|---|---|
| The frontend shows an API error or empty pages | Check `curl -s localhost:8000/readyz`. Restart with `make api-demo`. If Postgres is down, run `make up`. |
| A page is slow on first open | That's dev-mode compilation. Keep talking; next time use the production build and warm the pages. |
| A citation click doesn't open the evidence panel | Use the step 2 URL: `W/evidence?ev=NORTHSTAR%2FBRAND-STRATEGY%40v1%3AP4.B2`. |
| Saved research is missing from the sidebar | The database wasn't seeded with the demo snapshot. Run `make demo-seed` (it needs `make seed` on a fresh database). Meanwhile, demo Insights, Growth Opportunities, Analytics, the deck and RAG Evaluation, which don't depend on saved runs. |
| An insight or opportunity shows as stale or withdrawn | It failed re-verification against the corpus. Run `make demo-verify` to see why, and use a different item. |
| The deck download fails | Show the in-browser preview; it comes from the same composed deck. Restart the API if the error repeats. |
| Server logs are empty | The log is in memory in the API process, so it starts empty after an API restart. It fills as pages load: open two or three pages and come back. |
| Someone asks you to ask a new question | "Live generation is turned off for this offline demo; it needs an API key. Here is a saved run of the same kind." Open backup conversation `W/ask/42719cd8-909b-4997-a25e-2b08508a029e` (Gen Z cart abandonment over size charts, plus competitor gait scanning) or `W/ask/75577600-577c-4ae7-aaa2-964175d647f6` (a clean standard run accepted with no repairs). |
| Someone attaches a file | It uploads through the real source API but is processed only while `make worker` runs. Attachments join the workspace evidence; they don't scope a single answer. |
| Nothing works | Walk through the measured results in the README and this guide's talking points, and pivot to the architecture discussion. |

## Short and long versions

**5-minute version.** Keep steps 1, 4 (one claim-type example), 5, 6 (preview only), 7 (run trace only) and 8 (Overview and Retrieval, with the reranker finding). Merge step 2 into step 1 with one citation click and skip step 3.

| Step | 5 min | 8 min |
|---|---|---|
| Opening | 10 s | 10 s |
| 1. Chat | 50 s (one citation click) | 75 s |
| 2. Evidence | merged into step 1 | 30 s |
| 3. Analytics | skip | 30 s |
| 4. Insights | 35 s | 50 s |
| 5. Growth Opportunities | 45 s | 50 s |
| 6. Create presentation | 35 s (preview) | 50 s (stages, preview, download) |
| 7. Telemetry | 35 s (run trace) | 50 s (overview, trace, fallback, server logs) |
| 8. RAG Evaluation | 50 s (Overview, Retrieval) | 60 s (all listed tabs) |
| Close | 10 s | 10 s |

**If time runs short mid-demo,** drop in this order: the evidence-only fallback run, Failure analysis, Server logs, Standard vs Research, Analytics, the deck download. Always keep the O2 opportunity and the reranker negative finding: they carry the product story and the engineering story.
