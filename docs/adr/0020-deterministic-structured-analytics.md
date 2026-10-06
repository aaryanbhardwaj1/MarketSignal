# ADR-0020: Deterministic structured analytics: the model chooses what to compute, code computes it

- **Status:** Accepted
- **Date:** 2026-10-06
- **Implementation:** Built in Phase 5. Contract `tools/analytics_contracts.py`; tools `tools/impl/analytics.py`; engine `analytics/` (`schema.py`, `validate.py`, `engine.py`, `rounding.py`, `store.py`); results in answers `generation/results.py`, `generation/result_claims.py`; persistence migration `0007_analytics_results.py`; endpoint `api/routers/results.py`. Deep dives: [`GOVERNED_TOOLS_AND_MCP.md` §1.1](../GOVERNED_TOOLS_AND_MCP.md), [`GROUNDED_ANSWERING.md` §5.8](../GROUNDED_ANSWERING.md).
- **Related:** plan §18 (analytics tool schema), §19; ADR-0004 (handles and aliases), ADR-0006 (governed tool boundary), ADR-0007 (bounded agent), ADR-0009 (workspace isolation), ADR-0015 (router, task type), ADR-0016 (purge)

## Context

Many consulting questions are quantitative over tabular sources: shares, averages, rankings, segment comparisons. Before Phase 5 the system could only retrieve rows and passages and let the synthesis model read numbers from them. That fails on anything that needs a computation over more rows than fit in a pack, and invites the model to do arithmetic, which the verifier cannot check (derived arithmetic is never accepted).

Requirements:

1. Computed numbers must be **exact and reproducible**: the same request over the same dataset version gives the same value, with a stated rounding rule and denominator.
2. The model must not gain a new way to reach data: no SQL, no code, no widening of the workspace, class or confidentiality scope (ADR-0006, ADR-0009).
3. Every number in an answer must still be verifiable against something the server produced, and must not outlive a purge of its source (ADR-0016).
4. The tools must work with the live API's tool grammar.

## Decision

**The LLM chooses what to compute; code computes it.** Four governed tools (`describe_dataset`, `aggregate`, `group_compare`, `filter_rows`) take only closed enums and bounded values: metric functions `count`, `count_distinct`, `sum`, `mean`, `median`, `min`, `max`, `share`; filter ops `eq`, `ne`, `in`, `not_in`, `gt`, `gte`, `lt`, `lte`, `between`, `is_null`, `not_null`; at most 4 metrics, 5 filters, 2 group-by columns, 50 groups and 20 listed rows (configurable `analytics_*` settings).

- **No SQL, expressions or code.** Column names are matched exactly against the stored `dataset_tables.columns` profile and are never interpolated into SQL. The only data SQL is one parameterized, RLS-scoped row fetch by table id. Computation is pure Python over `Decimal`.
- **Scope from the token.** Datasets (`"<SOURCE_CODE>:<sheet_ordinal>"`) are the active versions visible under the token's workspace, `max_conf` and class claims. The tools run through the same governor, audit and transports as the evidence tools.
- **Fixed rounding.** `ROUND_HALF_EVEN`: percent and `share` 1 dp, `currency_usd` 2 dp, other means and medians 2 dp, ratio 3 dp; counts, integer sums, `min` and `max` exact. Each value carries its unrounded `exact` string, unit, inferred scale, numerator and denominator. Zero denominators give a null value (`ZERO_DENOMINATOR`), never a guess.
- **Provenance.** Every computing call persists its result in `analytics_results` (forced RLS, no `UPDATE` for the runtime role) before returning it, under a `result_id`, with the dataset table, source version and normalized spec.
- **A separate citation kind.** Answers cite results with run-local `[R#]` aliases, stored as `[[result:<id>]]` and shown as result cards. A result is not text evidence and never becomes an evidence handle. The verifier accepts a number citing `[R#]` only if it equals the result's rounded value, its exact value rounded half-even to the stated decimals, or a numerator, denominator or label, with unit, scale and sign agreeing.
- **Non-strict tool schemas, strict server validation.** The analytics tools are offered with `strict: false` because the strict array limits (≤ 16 union-typed, ≤ 24 optional parameters across all tools) are exceeded. Server-side strict Pydantic validation remains the boundary.

## Alternatives considered

- **Text-to-SQL.** Most expressive. The model would write the query, so column and table names, joins and predicates would reach the database from model output. Even under RLS and a read-only role, it opens injection, resource-exhaustion and scope-widening paths that the governed boundary exists to close, and results would not be reproducible across phrasings. Rejected.
- **Code interpreter (model-written Python or pandas).** Flexible and familiar. It needs a sandbox, gives the model arbitrary computation over tenant data, and makes outputs hard to verify or bound. Rejected.
- **LLM arithmetic over retrieved rows.** No new component. Results depend on which rows fit in the pack, arithmetic errors are common, and the verifier cannot check derived numbers. Rejected.
- **One flattened `query_structured_metrics` tool (the plan's §18 schema).** Fewer tools. A single schema with per-operation optional fields is harder for the model to fill correctly and leaves most fields irrelevant per call. Replaced by four focused tools with the same governance.

## Tradeoffs accepted

- **Limited expressiveness.** No joins across datasets, no period-over-period change operation, no custom formulas. Questions outside the vocabulary are answered from retrieved evidence, or not at all.
- **Units inferred from column names** (`value_usd_bn` → `currency_usd`, `billion`). A badly named column gets the wrong unit or scale.
- **Non-strict schemas** let the model produce malformed calls that strict mode would have prevented; they fail as `VALIDATION_ERROR` and count toward the agent's error streak.
- **Analytics only in research mode.** Quantitative questions are routed to the agent (ADR-0015 Phase 5 note), which costs research-mode latency.

## Consequences

**Positive**
- Every computed figure is exact, reproducible from a stored spec and source version, and retrievable through `GET /api/workspaces/{ws}/results/{result_id}`.
- The model gains no data-access capability beyond closed, bounded operations through the existing boundary.
- The verifier can check computed figures as strictly as quoted ones, so analytics answers keep the grounding guarantee.

**Negative**
- A second citation kind across the gate, verifier, citation budget, fallback, purge and UI.
- Another table that purge must capture and delete.

**Follow-ups**
- New operations (for example period change) are added as closed enums, never as expressions.

**Verification**
- Unit and integration tests for validation, rounding, scale, non-finite rejection, SQL-like payloads, visibility, limits and purge ordering (`tests/unit/test_analytics_*.py`, `tests/integration/test_analytics_tools.py`, `tests/integration/test_results_api.py`).
- Verifier tests for the `[R#]` numeric rule and the citation budget (`test_results_in_answers.py`, `test_verifier_citation_budget.py`).
- analytics-v0 (90 items, dev/holdout; golds computed independently by `scripts/build_analytics_v0.py`), run with `python -m marketsignal.evaluation analytics --split dev|holdout --out DIR [--fake]`. Results: the Phase 5 report (`docs/phase-reports/phase-5.md`).
