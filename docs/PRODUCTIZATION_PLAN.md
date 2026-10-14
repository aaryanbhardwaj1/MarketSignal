# Productization plan (final phase)

Internal plan, written after a read-only audit of the frontend, the persisted run telemetry, the evaluation artifacts, the demo data and the backend API. The goal is a coherent, credible strategy product for a local interview demo, with **no new AI scope and no live model calls**.

## What the audit found

- **The navigation is organised around implementation, not business tasks.** It is a top nav plus tabs (Dashboard, Sources, Evidence, Search, Chat). There is no conversation history, and there are no Opportunities, Analytics, Telemetry or Evaluation surfaces.
- **Developer internals leak into business screens.**
  - canonical handles, UUIDs and error codes;
  - RRF scores;
  - labels such as "Parents/Children", "Corpus version" and "Smoke search".
- **There is no visual system.**
  - Six unrelated accent palettes, mixed radii and ad hoc 10–11px text.
  - Answers render about 150 characters wide.
  - The sources table has 13 columns.
- **Citations and states are weak.**
  - Citations open the evidence viewer in a new tab, and verification results are never shown.
  - Loading is a single spinner line, and there is no honest offline state.
- **Data hygiene.** Test-harness runs and test workspaces show up in product views.

## Decisions

1. **Design system.** Semantic CSS tokens in Tailwind 4 `@theme`: one restrained accent, neutral surfaces, 1px borders, three radii and one type scale.
   - Shared primitives cover the shell, page header, card, metric card, table, badge, status indicator, form controls, tabs, filter bar, citation chip, evidence card, result panel, bar list, callout, states, drawer and disclosure.
   - A design-rules test rejects banned classes (gradients, blur, ad hoc sizes, raw palettes).
   - No UI framework and no new runtime dependencies.
2. **Information architecture.** A persistent sidebar with two groups (superseded by the chat-first layout in [Final redesign](#final-redesign)).
   - **Workspace:** Overview, Ask MarketSignal, Growth Opportunities, Analytics, Evidence Library.
   - **Developer Tools:** Telemetry, RAG Evaluation.
   - Old routes redirect to the new ones. Workspace creation, uploads and deletes leave the UI; the backend endpoints stay.
3. **Business surfaces.**
   - **Overview** and **Growth Opportunities** come from a versioned **curated analyst brief**. Its evidence is re-resolved and its figures recomputed deterministically on every request. An item that no longer verifies stays visible, marked "Could not be re-verified", with its figures withheld; decks exclude it. (Corrected 2026-10-14: an earlier version of this plan said such items are hidden.) Statuses are qualitative, with no scores.
   - **Analytics** shows named business analyses recomputed by the existing deterministic engine. These are never persisted and never touch an LLM.
4. **Ask MarketSignal.**
   - Saved conversations, with honest Standard/Research/Auto copy.
   - Answer sections in a fixed order, with empty ones hidden.
   - Consolidated, numbered citations that open an evidence drawer showing the exact highlighted passage.
   - Computed results shown distinctly from evidence.
   - Technical identifiers only inside "Technical details".
5. **Developer Tools.**
   - **Telemetry** reads persisted runs only: summary, filterable runs table, and a run detail with the stage timeline, tool calls, verification attempts and retrieval lanes. It never shows model reasoning, which is not recorded. Cost is shown only as an estimate from persisted token usage at list prices.
   - **RAG Evaluation** reads a catalog precomputed from the committed artifacts. Every number carries a JSON pointer to its source file, and the artifacts are never modified. Negative findings and caveats are always shown.
6. **Offline demo.**
   - `MS_LLM_ENABLED=false` refuses new runs with `503 PROVIDER_UNAVAILABLE` before any provider call, and the UI shows "Live model unavailable".
   - A non-retryable provider rejection latches the same state.
   - Featured saved conversations come from a committed demo snapshot that imports after seeding, with integrity guards.
   - Test-harness runs are excluded from product views by default.

## Final redesign

Decisions taken in the last round of work, after the plan above was built.

1. **Chat-first information architecture.**
   - The landing page is Chat, with a conversation sidebar (saved and featured conversations).
   - A top bar carries the business navigation: **Chat · Insights · Growth Opportunities · Analytics**. Overview became Insights.
   - Developer tools (Telemetry, RAG Evaluation) are icon buttons on the right of the top bar. The Evidence library has no nav entry; it is reached from the workspace control and provenance links.
   - Old routes (`/overview`, `/chat`, `/sources`, `/search`) answer with real redirects.
   - Files can be attached in chat; they are uploaded through the same sources endpoint.
2. **Claim-type contract.** Every brief claim is typed **Observed**, **Derived**, **Inference**, **Hypothesis** or **Forecast**. The curated brief (schema v2) enforces the grounding each type needs when it loads, and re-checks it on every request:
   - Observed needs a supporting quote; Derived needs a computed metric; Inference and Hypothesis need a quote or a metric.
   - A Forecast needs a cited passage that states the projection. If that passage stops verifying, the item becomes unverified and its figures are withheld.
   - An analysis summary or interpretation is shown only when every number in it equals a computed figure.
   - Opportunity risks are re-verified like any other claim.
   - Inference, Hypothesis and Forecast are tagged visibly; Observed and Derived are not.
3. **Insights, Growth Opportunities and Analytics are distinct.**
   - **Insights:** what the evidence shows now. Typed signals (emerging signals, risks and blockers, competitor findings, optimizations, future outlook) with an evidence balance and qualitative statuses.
   - **Growth Opportunities:** what to act on. Curated opportunities with supporting and contradicting evidence, risks, and links to the signals and analyses behind them.
   - **Analytics:** the numbers. Named analyses grouped by business area, each recomputed by the deterministic engine with one real visual.
4. **Motion and charts are now allowed** under the design rules. Charts are hand-rolled SVG components (no charting library) and show only computed or persisted values. Motion is short and functional, and `prefers-reduced-motion` is respected.
5. **RAGAS.** Standard RAG metrics through an isolated runner over the persisted evaluation outputs. Only the non-LLM metrics were computed; the model-judged ones are wired behind an opt-in and were not run ([ADR-0021](adr/0021-ragas-isolated-runner.md)).
6. **Decks.** Selected Insights, opportunities and analyses become a PowerPoint deck, composed on the server from the re-verified brief with no model call. Items that do not re-verify are excluded and listed ([ADR-0022](adr/0022-grounded-deck-generation.md)).
7. **Server log.** Telemetry gains a live view of the API process's log: sanitized, in memory, developer-only ([ADR-0023](adr/0023-developer-server-log.md)).

The as-built behaviour is in [`SYSTEM_DESIGN.md` §10](SYSTEM_DESIGN.md#10-product-and-developer-surfaces-final-phase).

## Not built

- New retrieval, agent or verifier logic.
- Auth, deployment, billing.
- AI-generated opportunities, opportunity scores, dark mode.
- Any live model call, including the model-judged RAGAS metrics.
