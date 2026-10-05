# ADR-0015: Standard (single-pass) and research (agentic) modes, chosen by a deterministic, user-overridable router

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 4 (router and research mode; standard mode lands end to end in Phase 3; the mandatory agent-vs-single-pass ablation runs in Phase 7) (this ADR is updated with measurements when the component is built)
- **Related:** plan §0.1, §0.3 (D10), §2, §3 (steps 4–5), §3.2, §19, §20, §26, §28, §33, §37.1, §38; ADR-0006 (MCP governed boundary), ADR-0007 (bounded agent state machine), ADR-0011 (answer cache keys on mode), ADR-0013 (evaluation methodology), ADR-0018 (personas); approved deviation D10

## Context

The spec implies that every query goes through the agent. Agentic gathering pays off on multi-hop, cross-class and analytic questions, where one retrieval pass misses evidence. Elsewhere it costs latency and tokens: it adds at least one planning LLM call before retrieval, plus one per step, up to the configured bounds.

The latency targets are about 4 s to first token and < 15 s end-to-end p50 for standard, against about 8 s and about 25 s for research. The spec's end-to-end target is under 15 s. Many questions ("what did the Q3 review say about channel mix?") are single-source lookups that one hybrid search answers.

Mode selection must not itself call an LLM: that would add a call, cost and a non-deterministic failure point to every request. Without an LLM, though, the router can misroute. The project also has to answer "why an agent?" with measurements rather than assertion.

## Decision

**Two modes, one pipeline.** The modes differ only in the **Gather** step. Pack, synthesis, alias gate, verification, fallback, persistence and SSE are shared.

- **standard:** normalize the query, run `search_evidence` (the full hybrid pipeline), and run `search_evidence_keyword` for any quoted or capitalized entities. All calls go through the same tool registry as the agent, so governance, tracing and caps are identical.
- **research:** the bounded agent state machine (ADR-0007, §19), reaching data only through the governed MCP tools. Bounds: 4 steps, 10 tool calls, 3 consecutive tool errors, a repeated-call stop, a 40-parent evidence pool, and a 35 s gather budget inside a 60 s run deadline.

**Deterministic router** (§3 step 4):
1. An explicit request `mode` (`standard` | `research`) always wins. The UI exposes the override.
2. Personas configure a default mode (§37.1): Customer Insights → standard; Growth, Brand and Marketing Strategy → research; Generalist → `auto`. A persona default applies only when the request does not set a mode. `auto` defers to the cue rules.

   Full precedence, highest first: request `standard` | `research` > request `auto` (cue rules; this overrides the persona default) > persona default `standard` | `research` > persona default `auto` (cue rules). With no request mode and no persona, the cue rules apply.
3. In `auto`, deterministic cues select `research`:
   - hypothesis or "evaluate" wording;
   - comparison wording ("vs", "compared", "which competitors");
   - numeric or analytic cues ("how many", "%", "trend", "by segment");
   - two or more source-class cues;
   - a follow-up that needs earlier conversation context.
4. Everything else goes to `standard`.

The chosen mode is recorded in `query_runs` and the `run_started` event, and is part of the answer-cache key (ADR-0011). The router **must not call the LLM** (component contract, §2).

**Fallbacks:**
- If the first planning LLM call fails, research falls back to the standard gather path (`PLANNER_UNAVAILABLE_FALLBACK`).
- If the agent ends without a successful search, a deterministic fallback search runs (`PLANNER_NO_TOOL_FALLBACK`).

## Approved spec deviation

- **Spec position (D10):** every query goes through the agent (implied).
- **Approved change:** a `standard` single-pass mode plus an agentic `research` mode, chosen by a deterministic router that the user can override.
- **Approval requirement:**
  - the router stays deterministic (no LLM) and user-overridable;
  - the **Phase 7 agent-vs-single-pass ablation is mandatory** and is the evidence for when agentic orchestration is worth its cost.
- **Approved 2026-10-05.**

## Alternatives considered

- **Agent always (the spec's implied position).** Simplest mental model. It pays planning latency and tokens on every simple lookup and makes the < 15 s target hard to meet for questions that need one search.
- **LLM router (a classifier call before routing).** Better recall on unusual phrasings. It adds another LLM call, cost and a failure mode to every request, and is non-deterministic, so routing could not be unit-tested exactly. It also violates the D10 approval requirement.
- **Single-pass only.** Fastest and cheapest. It cannot do iterative cross-class gathering, analytics follow-ups or the hypothesis workflow, and gives up the agentic design the project exists to demonstrate.
- **Learned router (a classifier trained on eval outcomes).** Possible once the Phase 7 ablation produces labelled outcomes. Today there is no training data, and it would trade explainability for a small gain.

## Tradeoffs accepted

- **Rule-based routing misroutes.** A complex question phrased simply goes to standard, and a simple question containing "vs" goes to research. Mitigations: the user override, persona defaults, the cheap research → standard fallback, and Phase 7 measurement.
- **Two gather paths to maintain.** This is contained because they share the tool registry and everything after Gather.
- **Keyword-cue rules are English-specific** (A8).
- **Research mode's latency target (about 25 s p50) exceeds the spec's < 15 s.** That is accepted for the question types that need it, and justified only if the ablation shows a benefit.

## Consequences

**Positive**
- Simple questions get the fast path by default. Agentic cost is spent where cues indicate multi-hop need.
- Routing is explainable, reproducible and unit-testable. Any routing decision can be reproduced from the question, persona and request.
- The ablation turns "why an agent?" into a measured answer.

**Negative**
- Cue lists need maintenance as question types grow.
- Mode becomes another dimension in evaluation and caching.

**Follow-ups**
- Phase 4: router decision-table unit tests (explicit-mode precedence, explicit `auto` under a persona whose default is `research` resolving through the cue rules, persona default, each cue, and the no-cue → standard case).
- Phase 7: the mandatory agent-vs-single-pass ablation on cross-source and hypothesis items, run through the e2e runner (§26).
- If the ablation shows no distinguishable benefit for a question category, route that category to standard by default and record the change here.

**Verification**
- **Phase 7 agent-vs-single-pass ablation** (mandatory). Measures: source-class coverage, agent evidence recall (from traces, no judge), answer correctness (ledger facts), latency and tokens. Configs are compared with paired tests on the same items (exact McNemar for binary outcomes, paired bootstrap for continuous ones). Deltas below the stated minimum detectable difference (about 15 points at n ≈ 100) are reported as "not distinguishable".
- Phase 4 exit: the Demo 2 query makes ≥ 2 tool calls across ≥ 2 classes and is grounded. Agent bounds tests run with FakeLLM scripted transcripts.
- Latency: per-stage p50/p95 per mode from `query_runs.timings` and the load test, compared against the §3.2 targets.
- Degradation tests for `PLANNER_UNAVAILABLE_FALLBACK` and `PLANNER_NO_TOOL_FALLBACK`.
