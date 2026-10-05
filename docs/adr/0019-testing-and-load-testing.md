# ADR-0019: Testing strategy and load testing

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 0 (harness, role setup and CI skeleton), extended every phase; load test in Phase 8 (this ADR is updated with measurements when the component is built)
- **Related:** plan §29 (also §6, §23, §28, §30, §3.2); ADR-0006, ADR-0007, ADR-0009, ADR-0013; approved deviation D11

## Context

The system's guarantees are mostly negative properties:
- no cross-workspace leak;
- no unresolvable citation;
- no silent degradation;
- no unbounded agent loop;
- no request prefix that changes between agent steps and breaks prompt caching.

Properties like these are only credible if tests exercise the real enforcement path. Two things make that hard:

1. **LLM non-determinism and cost.** The agent loop, synthesis, the alias gate and verification all sit behind an LLM. Tests that call the real provider are slow, cost money and flake.
2. **Isolation that can be bypassed by the test setup.** Workspace isolation relies on Postgres RLS (ENABLE + FORCE) under a non-owner role (ADR-0009). A superuser or `BYPASSRLS` role skips RLS silently, so tests that connect as one pass even when the policies are wrong. That is false confidence (§35).

The spec also asks for a load test (spec §26.4) and names Locust or k6.

## Decision

**Test layers (§29).**
- **Unit (no I/O).** Handle grammar (Hypothesis round-trip and fuzz); resolver ordering including tombstones; scope enforcement; parsers using fixtures built at runtime by factories (bomb, encrypted, macro and truncated files, so no binaries are committed); parent and child builders and locators; lexical query builder (adversarial inputs, determinism); parent-level RRF; MaxP rerank and its fallback; balancing with relative floors; cache keys and conditional writes; alias gate with randomized delta splits; verifier; degradation mapping and termination precedence; analytics DSL; strength rules; SSE event order.
- **Agent bounds with `FakeLLM`.** `FakeLLM` implements the same `LLMProvider` interface as the Anthropic adapter and replays scripted transcripts. Scripts cover the step limit, the circuit breaker, the repeated-call stop, the context limit, `end_turn` without a search, the parallel-call budget, refusal and `max_tokens`. A test asserts the **request prefix is byte-identical** across agent steps.
- **Integration** (Postgres + pgvector + Redis, **connected as `ms_app`**):
  - upload → ready → retrieve → resolve;
  - standard and research runs with FakeLLM through **real Streamable HTTP MCP and token auth**;
  - no-hit; embedder down → lexical-only; reranker down; Redis down;
  - RLS negative tests;
  - the purge contract; revert, retry-after-fail and concurrent uploads; transactional-enqueue rollback;
  - SSE resume with `last_event_id`;
  - iterative-scan settings active inside the retrieval transaction; a filtered query returns exactly LIMIT rows; an EXPLAIN check for HNSW use.
- **Contract.** OpenAPI snapshot, SSE JSON schemas, MCP tool-schema snapshot, a route-scoping test, and an optional keyed strict-schema `count_tokens` check.
- **Eval regression.** The retrieval runner on the dev split in CI, with exact search and floors (ADR-0013).
- **Frontend.** vitest (chip parsing, SSE reducer, SafeMarkdown stripping `img`, `a` and HTML); a Playwright smoke (ask → stream → open citation) against a FakeLLM backend; a manual Safari and incognito check on the deployed URL.
- **Coverage target:** 80% on the backend core packages.

**Non-superuser test role.** `db/init/01_roles.sql` creates `ms_owner` (owns the schema, runs migrations) and `ms_app` (`LOGIN NOSUPERUSER NOBYPASSRLS`, DML grants only). Compose initdb and the CI setup step both run it. Integration tests, the API and the worker all connect as `ms_app`. Startup and `/readyz` fail if the current role has `rolsuper OR rolbypassrls`, so a misconfigured test environment fails loudly instead of passing.

**Load test.** 20 concurrent runs plus concurrent ingestion, reporting p50 and p95 for each stage from `query_runs.timings`. Implemented as a **Locust script, or a documented asyncio script if Locust adds friction**, in `scripts/loadtest`. The results are compared with the §3.2 latency **targets** (for example, end-to-end p50 under 15 s for standard and about 25 s for research), and the measured numbers are published in the engineering report.

## Approved spec deviation

- **Spec position:** load test with Locust/k6.
- **Approved change (D11):** a Locust script, or a documented asyncio script if Locust adds friction.
- **Rationale recorded with the approval:** either one serves spec §26.4.
- **Approval requirement:** none beyond the change itself. If the asyncio route is taken, it must be documented (method, concurrency model, and how per-stage timings are collected).
- **Approved 2026-10-05.**

## Alternatives considered

- **Tests against the real LLM provider.** This gives realistic behaviour, but it is non-deterministic, costs money, needs a secret in CI and cannot force rare paths such as refusal, `max_tokens` or loops on demand. It is kept for the manual `eval-full.yml` workflow only.
- **Mocking at the HTTP layer instead of a `FakeLLM` provider.** This couples tests to SDK wire details that churn (§35), and it cannot easily script multi-step tool-use transcripts.
- **Running tests as the database owner or a superuser.** Simpler setup, but RLS is bypassed and isolation tests become meaningless.
- **SQLite or an in-memory store for integration tests.** Faster, but there is no pgvector, no RLS, no FTS parity and no Procrastinate, so the properties that matter go untested.
- **In-process tool calls only.** Faster, but it would miss token verification, the loopback guard and transport behaviour. Integration runs use real Streamable HTTP. The in-process transport exists as a runtime fallback, covered by a parity test.
- **k6 for load.** Capable, but it needs a separate JavaScript runtime and toolchain. Python tooling keeps one language and can reuse the API's schemas.
- **Locust only.** Its HTTP user model is request/response. Consuming SSE streams per run needs custom client code, which is the "friction" that justifies the asyncio fallback.

## Tradeoffs accepted

- FakeLLM tests prove the harness, bounds and contracts, not model quality. Quality is measured separately by evaluation (ADR-0013), and the LLM-judged parts are not CI-gated.
- Integration tests need Docker service containers, which makes CI slower. The CI budget is under 15 minutes with a warm cache.
- The load test at 20 concurrent runs characterizes one api and one worker instance. It does not demonstrate horizontal scale (§34).
- If the asyncio script is chosen, the project gives up Locust's UI and built-in reporting and owns the percentile computation itself.

## Consequences

**Positive**
- Isolation and governance claims are backed by tests that would fail if RLS, the role topology or token checks were wrong.
- Every degradation code in §28 has a named test, so nothing degrades silently.
- CI needs no LLM key. It is deterministic and free to run on every PR.

**Negative**
- FakeLLM transcripts must be kept in sync with real provider behaviour. Drift is caught only by the manual e2e workflow and the keyed contract check.
- Runtime fixture factories are code to maintain, but they avoid committed binaries in a public repository.

**Follow-ups**
- Decide, and record in the load-test report, whether a run uses FakeLLM (isolates platform latency) or the real provider (end-to-end latency, metered by the spend ledger). Report the two separately if both are run.
- Record the load-test tool chosen (Locust or asyncio) and its method in the Phase 8 report.

**Verification**
- CI (§30): unit, integration as `ms_app`, contract, eval smoke and gold-integrity jobs pass on every PR.
- `/readyz` is red when connected as a superuser or BYPASSRLS role, which is a negative test of the guard itself.
- The coverage report shows at least 80% on the backend core packages.
- Phase 8: the load-test report gives p50 and p95 per stage at 20 concurrent runs with concurrent ingestion, set against the §3.2 targets and labelled as measured.
