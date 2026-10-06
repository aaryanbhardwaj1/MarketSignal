# Phase 5 report: structured analytics, Phase 4 regressions

**Status: implemented and measured live on dev and holdout. The A3 live comparison is incomplete: API credits ran out. Awaiting review before Phase 6.**

Phase 5 delivers deterministic structured analytics. The model chooses *what* to compute, code computes it, and answers cite computed results the verifier checks exactly. It also closes the three Phase 4 regressions (A1–A3).

All failures are kept below, including live findings that changed the design.

Design: [ADR-0020](../adr/0020-deterministic-structured-analytics.md), [GOVERNED_TOOLS_AND_MCP.md](../GOVERNED_TOOLS_AND_MCP.md) §1.1, [GROUNDED_ANSWERING.md](../GROUNDED_ANSWERING.md) §5.8–5.9, [RESEARCH_AGENT.md](../RESEARCH_AGENT.md) §8.1, [SYSTEM_DESIGN.md](../SYSTEM_DESIGN.md). Phase 5 notes are in ADR-0006 and ADR-0015, and deviations in ARCHITECTURE_PLAN §0.4. The live API finding is in [spike 0002](../spikes/0002-anthropic-live.md) (Phase 5 addendum).

## Exit criteria

| Criterion | Result |
|---|---|
| A1 citation overflow | **Fixed.** `fit_citations` (deterministic citation budget) is unit-tested. Live: 6/6 enumeration dev answers completed, with no `too_many_citations` and no fallback; the budget never needed to act (5–18 citations against a cap of 20) |
| A2 injection-safe fallback | **Fixed.** Instruction-like evidence text is withheld from the evidence-only answer (`safe_text.py`, `WITHHELD_MARKER`) and down-ranked. Covered by unit tests |
| A3 research synthesis completeness | **Implemented, not measured live.** A bounded `ResearchSummary` is handed to synthesis (setting `research_summary`, default on). The off/on comparison stopped when API credits ran out (below) |
| Dataset model and governed analytics tools | **Done.** Four tools behind the Phase 4 governed boundary; no SQL, expressions or code; allowlisted columns; configurable limits; workspace from the token |
| Adversarial tests | **Done.** Two security reviews, plus three adversarial rounds on the live-driven verifier fix (below) |
| Computed-result provenance | **Done.** `analytics_results` (forced RLS, append-only), `[R#]` → `[[result:<id>]]`, result cards, `GET /results/{id}`, purge coverage |
| Numeric faithfulness for results | **Done.** Exact value, or the exact value rounded half-even to the stated decimals, with unit, scale, sign and direction. Live: 1.000 on dev, 0.990 on holdout |
| retrieval/analytics/mixed routing with a trace | **Done, with weak generalisation.** Dev 36/36; holdout 31/54 (below) |
| Previously analytics-only retrieval-v0 items answerable | **Done.** analytics-v0 includes them (`converted_from`) and answers them with computed results |
| Fresh dataset, leakage-resistant splits, deterministic golds | **Done.** analytics-v0: 90 items, 36 dev and 54 holdout. Golds are computed independently of the product engine (77/77 agreement) |
| Minimal frontend only | **Done.** Result chips and a result card; no redesign |
| No Phase 6 work pulled forward | **Kept** |

## How the work was organised

The lead integrated and owned every shared interface before any delegation:
- the frozen analytics contract (`tools/analytics_contracts.py`);
- migration 0007, the `analytics_*` settings and the router;
- the executor, purge, the results API and the evaluation CLI;
- documentation.

Workstreams ran with explicit file ownership, at most three concurrently, and never committed. The lead reviewed every diff and re-ran its tests before each commit. All development used fake or scripted models.

| Workstream | Responsibility | Outcome |
|---|---|---|
| W1 Phase 4 regressions | A1 citation budget, A2 safe fallback, A3 research summary | Committed (`e1b3e7c`, `ac25a6e`) |
| W2 engine and tools | `analytics/` engine, four governed tools, observations, MCP parity | Committed (`06fc6e4`) |
| W3 dataset | analytics-v0 (90 items), independent golds, leakage checks, A1 and A3 dev sets | Committed (`10a9886`) |
| W4a results in answers | `[R#]` aliases, `<computed_results>`, gate, verifier result rules, cards, fallback result lines | Committed (`7ca9c5d`) |
| W4b agent hand-off | `AgentOutcome.results`, scale, analytics prompt and progress templates | Committed (`68e7996`) |
| W5 evaluation | analytics runner and metrics (routing, exactness, answers, mixed, security, cost) | Committed (`75d4e8d`) |
| W6 frontend | result chip, result card, citation and stream changes | Committed (`dd236cd`). 201 frontend tests |
| Security review | multi-dimension review with skeptic verification | Confirmed findings all fixed (below) |
| Verifier-fix reviewer | three adversarial rounds on the live-driven verifier change | 16 + 5 + 2 false negatives in drafts, all fixed before commit |
| Docs | deep dives, ADR-0020, ADR notes, deviations | Committed (`73bd5a5`) |

## Analytics architecture and tool contracts

- **Tools.**
  - `describe_dataset`: lists datasets, or one dataset's schema.
  - `aggregate`: ≤ 4 metrics (`count`, `count_distinct`, `sum`, `mean`, `median`, `min`, `max`, `share`), ≤ 5 filters, ≤ 2 group-by columns, order and limit (≤ 50).
  - `group_compare`: A vs B with the difference; its denominator is denA + denB.
  - `filter_rows`: ≤ 20 rows of ≤ 8 columns; the row handles are real evidence handles.
  - Filter ops: `eq`, `ne`, `in`, `not_in`, `gt`, `gte`, `lt`, `lte`, `between`, `is_null`, `not_null`.
- **Boundary.** Every call runs through the Phase 4 governor (token, revocation, allowlist, strict validation, timeout, caps, audit, escaped observation).
  - Column names are matched against the stored profile and never reach SQL.
  - The only data SQL is one parameterised, RLS-scoped row fetch.
  - The workspace, confidentiality and class scope come from the capability token.
- **Determinism.** Pure-Python `Decimal` arithmetic with `ROUND_HALF_EVEN`:
  - percent 1 dp, currency 2 dp, ratio 3 dp, other means and medians 2 dp;
  - counts, integer sums, min and max exact;
  - every value carries `exact`, `unit`, an inferred `scale`, `numerator` and `denominator`;
  - a zero denominator gives null plus `ZERO_DENOMINATOR`;
  - also `EMPTY_SELECTION`, `NULLS_EXCLUDED`, `GROUPS_TRUNCATED`; NaN and Infinity are rejected.
- **Provenance.**
  - Every computing call persists an `AnalyticsResult` in `analytics_results` (migration 0007): forced RLS, `UPDATE` revoked, source version and table cascade.
  - The insert takes `FOR SHARE` on the source and rechecks its version, so purge ordering is safe.
  - Answers cite results as `[R#]`, stored as `[[result:<uuid>]]`, separate from evidence handles. Result cards carry `kind: "result"`.
  - Result source versions are frozen into `pack_handles`, so every purge guard covers them, and purge redacts answers citing a purged source's results.
- **Routing.** `task_type` is retrieval, analytics or mixed, from deterministic cues. Analytics and mixed go to research mode unless the user picked a mode, and the decision is recorded in `query_runs.route`.
- **Live API deviation.** The analytics tools are offered `strict: false`.
  - The live API caps a strict tool array at 16 union-typed and 24 optional parameters; Phase 5 had 36 and 38.
  - The first live dev run failed on every agent step because of this.
  - Server-side strict Pydantic validation remains the boundary. A guard test counts the limits.

## Results: analytics-v0 (live, `claude-sonnet-5-5`, effort low)

The dev split was used to find bugs. The holdout ran **once**, after the system was frozen at `1775244`, and nothing was tuned on it.

| Metric | Dev (36, `fb31765`) | **Holdout (54, `1775244`)** |
|---|---|---|
| Hard gates (citations resolvable and in pack, results in run, no cross-workspace leak, every run done) | all pass | **all pass** |
| Task-type accuracy | 36/36 | **31/54 (0.574)** |
| Mixed recognition | 4/4 | **2/6** |
| Unnecessary analytics / retrieval calls | 0/2, 3/25 | 0/4, 13/38 |
| Items with all gold values matched | 29/31 | **33/46 (0.717)** |
| Exact-result accuracy (mean / micro) | 0.935 / 0.900 | **0.746 / 0.761** |
| Aggregation / grouping / filter correct | 0.885 / 0.846 / 0.774 | 0.683 / 0.658 / 0.522 |
| Denominator / unit / rounding correct | 0.935 / 0.880 / 0.935 | 0.725 / 0.496 / 0.746 |
| Answered (evidence-only fallback) | 35 (1) | 51 (1) |
| Values stated (mean) | 0.956 | 0.726 |
| **Numeric faithfulness** | **1.000** | **0.990** |
| **Unsupported computed-claim rate** | **0.000** | **0.007** |
| Provenance coverage | 0.931 | 0.969 |
| Allowed rounding | 1.000 | 0.970 |
| Mixed: quantitative correct / evidence retrieved / evidence cited / both in answer | 3/4, 4/4, 4/4, 4/4 | 4/6, 5/6, 5/6, 4/6 |
| Safe rejection (invalid requests) / no-result correct | 3/3, 2/2 | 4/4, 2/2 |
| Behaviour pass | 35/36 | 52/54 |
| Canary or cross-workspace leaks | none | **none** |
| Analytics tool latency p50 / p95 | 21 / 61 ms | **21 / 50 ms** |
| End-to-end p50 / p95 | 11.6 / 16.2 s | **11.7 / 17.4 s** |
| Mixed end-to-end p50 / p95 | 15.6 / 17.3 s | **17.1 / 17.8 s** |
| Model calls / tool calls / tokens per run | 4.86 / 3.42 / 35.7k | 3.83 / 2.65 / 28.3k |
| Cost per run / total | $0.032 / $1.14 | $0.027 / $1.49 |

**Reading the holdout.** The computation and grounding layers held: no leaks, numeric faithfulness 0.990, and the analytics tools are fast and exact. The weak point is the **deterministic task-type router**. It was tuned on dev phrasing only and reached 36/36 there, but on holdout 23 of 54 questions got a different task type.
- **12 questions went to standard mode** (10 analytics, 2 mixed), where the analytics tools are not offered. They phrase computations with verbs and constructions the cues lack: "tally", "sum", "combined", "weakest/best month", "which three SKUs generated the most", "look up", "sell-through", "net sales … in Q4".
- The other 11 still ran in research mode, so the agent had the analytics tools. 6 were analytics/mixed label swaps; 5 were labelled retrieval but sent to research by other cues.
- Most of the holdout's lower exactness and values-stated figures follow from the 12 standard-mode routes.
- `unit_correct` (0.496) and `filter_correct` (0.522) are strict structural comparisons with the gold spec. An equivalent filter (for example `month >= 2026-08-01` instead of `month = 2026-09`) counts as wrong even when the value is right.

## Live findings that changed the system (dev only)

1. **Strict-mode grammar limits** (attempt 1, preserved in `analytics-v0-dev-live-attempt1-strict-limit`). Every agent step returned 400, and all 35 research runs fell back to standard (the 36th item was routed to standard). **Fix:** non-strict analytics tools (`b138beb`).
2. **Verifier false positives on computed results** (attempt 2, preserved in `analytics-v0-dev-live-attempt2-verifier-fp`). 7 of 36 correct answers fell back to evidence only. Correct values were rejected because:
   - a label held a change word ("Trail Starters");
   - the metric's own column named a change ("mean YoY growth is 6.7%");
   - "versus" juxtaposed two levels;
   - a parenthesis cut off a gap word;
   - digits sat inside names ("NS-KR2", "Crew Sock 3 Pack");
   - filter_rows percent cells had no unit;
   - the scanned-row count and single-year titles supported nothing;
   - "fall into" read as a change.

   **Fix** (`7e75df3`, `9a1525e`):
   - each relaxation is scoped;
   - three adversarial review rounds found **23 false negatives** in drafts of the fix (for example, a column named `price_change_pct` hiding "change", "Over 65" exempting 65, "600 of the Trail Starters"), all closed and kept as regression tests;
   - range labels ("18-21", "45+") were the last dev fallback, re-verified offline against the stored result.
3. **Scorer bugs** (fixed in the evaluator, not the product).
   - The cross-workspace leak check flagged a question echoing "Southpeak Outdoor".
   - The independent result re-check counted filter operands and row counts as unsupported claims.

## Phase 4 hardening outcomes

| Item | Outcome |
|---|---|
| A1: enumeration answers over-cite and fall back | Budget implemented. Live enumeration dev (6 items, standard, $0.10): 6/6 completed, 0 fallbacks, 0 over-refusals, all hard gates pass. Answer completeness varies (0–1.0); two answers state that the evidence lacks the figures, a retrieval limit rather than a citation failure. The frozen grounded-v0 regressions were not re-run |
| A2: fallback shows injection carrier text | Withheld and down-ranked, unit-tested. Not re-run live |
| A3: research synthesis less complete than its gather | Summary hand-off implemented and tested with fakes. Live: the summary-off arm completed 10/12 (completeness 1.0 on 7 items, 0.5–0.67 on 3); the last 2 items and the whole summary-on arm were rejected with *"credit balance is too low"*. **No live before/after comparison exists**; the summary-on output was discarded as uninformative |

## Security findings

The **Phase 5 security review**'s confirmed findings are all fixed with tests (`fa144f9`, `3e728a1`, `5d5d282`, `d9fedfc`). Grouped by area:
- **Run results.** Results of a source purged between the gather and the freeze could reach synthesis.
- **Analytics engine and tools.**
  - filter spec shape;
  - boolean levels;
  - date periods;
  - huge numbers;
  - NaN and Infinity;
  - analytics handles recorded for purge;
  - purge-safe ordering of the result insert;
  - `group_by` merge.
- **Result verification.**
  - Unicode format characters gluing figures together (high);
  - non-USD currency suffixes;
  - difference direction and subject;
  - years taken only from labels;
  - over-precise numbers;
  - essential `[R#]` kept by the citation budget;
  - the zero rule;
  - fallback labels;
  - result markers in digests.
- **Router.** Ambiguous quantitative words need metric context.

**Verifier-fix review:** 23 false negatives in drafts, none committed.

**Live security metrics:** no cross-workspace leaks, no canary leaks, and safe rejection of invalid requests 4/4 on holdout.

**Known semantic limits** (accepted, documented): a difference stated like a level ("App 0.03 versus Marketplace"), a level stated with "beat", "advantage over" or "margin over", and a denominator stated in a different role.

## Tests and CI

| Suite | Result |
|---|---|
| Backend `pytest -q` (unit and integration, real Postgres as `ms_app`) | **1571 passed, 9 skipped** (8 opt-in live tests, 1 superuser-DSN test) |
| Backend unit | 1345 passed |
| Frontend | **201 passed**; lint, typecheck and build clean |
| ruff, mypy strict | clean (152 source files) |
| Repository safety | passed on every commit |
| CI | green on every pushed head |

## Live API cost (Phase 5)

| Run | Cost |
|---|---|
| analytics-v0 dev, attempt 1 (strict-limit failure) | $0.50 |
| analytics-v0 dev, attempt 2 (verifier false positives) | $1.21 |
| analytics-v0 dev, final | $1.14 |
| analytics-v0 holdout (once) | $1.49 |
| A1 enumeration dev | $0.10 |
| A3 summary-off arm (10 of 12 items, agent and synthesis) | $0.46 |
| Strict-limit probes | under $0.05 |
| **Total** | **about $4.9** |

No single batch exceeded the $5 threshold. API credits are now exhausted; no further live run is possible until credits are added.

## Preserved failures

- **Router generalisation** (holdout, above): 12 questions needing analytics (10 analytics, 2 mixed) routed to standard mode.
- **A-LKP-07** (holdout): long-format P&L table. The unit is a separate `unit` column, so the value cell is typed "number" and "47.2 percent" was rejected, ending in the evidence-only fallback.
- **A-FLT-03** (holdout): the model doubted that the Southpeak dataset belongs to Southpeak (nothing names the owner), and its answer dropped the value.
- **A-CMP-07** (dev): answered from a slide that states both return rates, without computing the gap.
- **A-MIX-07** (dev): reported "9 of 300" instead of the requested fraction.
- **Fallback re-check artefact:** the independent re-check counts the row numbers in deterministic fallback lines ("row 2: …") as unsupported (holdout 0.007).

## Unresolved risks and limitations

- **Task-type routing does not generalise** (holdout 57%). Analytics questions phrased outside the cue list get standard mode and no analytics tools.
- **A3 is unmeasured live.**
- **Long-format tables** with a per-row unit column are not unit-aware.
- **Semantic verifier limits:** the gaps listed under Security findings.
- **Units are inferred from column names**, so a badly named column gets a wrong unit or scale.
- No period-over-period operation, joins or custom formulas.
- Analytics runs only in research mode, which costs research latency.
- Phase 4 limits (enumeration completeness, non-numeric hallucination, deferred rate limits and spend ledger) stand.

## Frontend debt for Phase 6

- The result card is a basic portal modal with no focus trap, and it is not routable or shareable.
- Chip, badge and tone styles are duplicated across `citation-chip.tsx`, `result-chip.tsx`, `badge.tsx` and the answer view.
- Gap styling is a label plus a background, not a distinct block.
- The Sources list has no computed-results list.
- There are no charts for grouped or compared results.
- Tables have no sorting or pagination, and `filter_rows` columns are not typed or aligned.
- `instruction_like_withheld` has no UI.
- Warning codes get `humanize()` only, with no friendly copy.
- `Intl` formatting is hard-coded to `en-US`.
- The research timeline has no per-step detail (which metrics were computed).
- `task_type` is not shown in the route badge.
- More broadly, the current UI is functional but not the final product structure.

## Proposed Phase 6 plan (for review; not started)

1. **Carry-overs first, measured on fresh dev data.**
   - Routing that generalises: keep the deterministic cues as a fast path, and add a constrained classifier step that sends any quantitative-looking question to research. Measure on a fresh routing set, never on the analytics-v0 holdout.
   - Long-format table units.
   - The A3 live comparison (about $1, needs credits).
2. **Growth Opportunity Workspace:** the planned product surface for opportunities, with the hypothesis lifecycle (draft, evidence for and against, computed support, status). It is built on the existing evidence and result provenance, so every claim stays cited.
3. **Frontend redesign** (the debt above):
   - an information architecture for workspace, opportunities, research runs and sources;
   - a shared design system for chips, cards and badges;
   - accessible, routable result views with simple charts for grouped and compared results.
4. **Evaluation:** a fresh dev/holdout set for the workspace flows, with the same discipline (one frozen holdout run, cost projection before any batch over $5).

## Commits

```
14655b2 feat(phase5): analytics foundations: frozen analytics contract, migration 0007, limits
962c53c feat(runs): deterministic retrieval/analytics/mixed task routing
ceb09d4 fix(purge): computed analytics results never outlive their source
e1b3e7c fix(generation): evidence-only fallback never surfaces instruction-like source text
ac25a6e fix(generation): deterministic citation budget; structured research summary handoff
06fc6e4 feat(analytics): deterministic analytics engine and governed analytics tools
10a9886 test(eval): analytics-v0 dataset and Phase 5 fresh dev sets
25bc58e feat(api): computed-result endpoint GET /results/{id}
87ba5f3 feat(runs): broaden task-type cues (tuned on analytics-v0 dev only)
75d4e8d feat(eval): analytics evaluation runner (routing, exact results, answers, mixed, security, cost)
68e7996 feat(agent,analytics): computed results handed to synthesis; scale; analytics prompts and progress
7ca9c5d feat(generation): computed analytics results in grounded answers with numeric verification
dd236cd feat(frontend): computed-result chips and result card (minimal Phase 5 UI)
5d5d282 fix(runs): results of a source purged before the freeze never reach synthesis
d9fedfc fix(runs): ambiguous quantitative words need metric context to route as analytics
fa144f9 fix(analytics): security-review hardening of the analytics engine and tools
3e728a1 fix(generation): security-review hardening of computed-result verification
b138beb fix(tools): analytics tools are offered non-strict (live API grammar limits)
59f5a2e test(eval): echoed workspace names are not leaks; preserve the failed first dev run
2caf3b8 test(tools): analytics tools are expected non-strict; record the strict-array limits
73bd5a5 docs: Phase 5 structured analytics: tools, results in answers, routing, ADR-0020
7e75df3 fix(verifier): computed-result support false positives found on live dev
fb31765 fix(eval): result re-check accepts filter operands and row counts; keep dev attempt 2
9a1525e fix(verifier): range-label endpoints back plain numbers ('18-21', '45+')
1775244 test(eval): live analytics-v0 dev run after the verifier fixes
7028a6c test(eval): live analytics-v0 holdout run (once, system frozen at 1775244)
```

The commits adding the A1/A3 dev outputs and this report follow.
