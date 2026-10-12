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
2. **Information architecture.** A persistent sidebar with two groups.
   - **Workspace:** Overview, Ask MarketSignal, Growth Opportunities, Analytics, Evidence Library.
   - **Developer Tools:** Telemetry, RAG Evaluation.
   - Old routes redirect to the new ones. Workspace creation, uploads and deletes leave the UI; the backend endpoints stay.
3. **Business surfaces.**
   - **Overview** and **Growth Opportunities** come from a versioned **curated analyst brief**. Its evidence is re-resolved and its figures recomputed deterministically on every request, and anything that no longer verifies is hidden. Statuses are qualitative, with no scores.
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

## Not built

- New retrieval, agent or verifier logic.
- Auth, deployment, billing.
- AI-generated opportunities, opportunity scores, a charting library, dark mode, animation.
- Any live model call.
