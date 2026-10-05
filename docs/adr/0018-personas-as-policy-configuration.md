# ADR-0018: Personas as policy configuration, not tool restriction

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 4a/4b (this ADR is updated with measurements when the component is built)
- **Related:** plan §37.1 (also §3, §15, §17, §22, §24, §26); ADR-0006, ADR-0007, ADR-0011, ADR-0015; approved deviation D9

## Context

The product serves consulting roles that ask different kinds of question about the same workspace. A growth strategist cares about market size and attractiveness. A customer-insights analyst cares about prevalence and verbatims. A brand strategist looks for gaps between positioning and perception. The spec (§5) introduces **personas** to capture this and says they influence "tool availability".

The agent's tool surface (ADR-0006) is already constrained:
- every tool is **read-only**;
- the workspace comes from capability-token claims and is never a tool argument;
- confidentiality is capped by `max_conf` and enforced as a SQL predicate;
- no tool reaches the network, the filesystem or anything that writes.

The question is which lever a persona should pull: tool availability, retrieval emphasis, prompting, or orchestration mode.

## Decision

Personas are **configuration only**: YAML files in `agent/personas/`. Each persona sets three things:

| Persona | Priority classes (soft prior) | Default mode | Prompt policy |
|---|---|---|---|
| Growth Strategy | market, internal financial/performance, customer, competitor | research | Where to play; size and attractiveness; separate evidence from thesis |
| Customer Insights | customer (survey, interviews, reviews) | standard | Prevalence and segment differences; quote verbatims; no causal overreach |
| Brand Strategy | internal brand, competitor, customer perception | research | Positioning vs perception gaps; whitespace |
| Marketing Strategy | channel datasets, customer, competitor marketing | research | Channel and message effectiveness, with the metrics behind them |
| Generalist | none | auto | Minimal bias |

1. **Source-class priors (soft).** When a retrieval call has no explicit `source_classes`, balancing (§15) gives each of the persona's priority classes a *guaranteed slot*. The slot is subject to the relative relevance floor: the class's best item must be within the class-local top-k or within Δ of that class's best score. It is **never a hard filter**. Explicit classes from the agent or the user take precedence.
2. **Prompt policy.** A persona-specific instruction block sets analytical emphasis, for example "quote verbatims" or "no causal overreach". It never relaxes the answer contract, citation rules or trust boundaries.
3. **Default mode.** A persona sets the mode used when the request names none. `auto` defers to the deterministic router (ADR-0015). An explicit `mode` from the user always wins.

**All personas share the same read-only tool set.** The capability token still carries `persona` and `tools=[…]`. Step 2 of the governance pipeline (§17) still rejects any tool that is not in `claims.tools` with `POLICY_DENIED`. The allowlist mechanism therefore exists and is tested, but no persona narrows it today.

Persona is part of the run record (`conversations.persona`, `query_runs.persona`), the answer-cache key (§22), the `run_started` event and the gold-item schema.

## Approved spec deviation

- **Spec position:** personas influence "tool availability".
- **Approved change (D9):** all personas share the same read-only tool set. They differ in source-class priors, prompt policy and default mode.
- **Approval requirement:** none was attached beyond the change itself. As part of the approved change, the allowlist mechanism exists and is tested.
- **Rationale recorded with the approval:** restricting read-only tools lowers answer quality and gains no security.
- **Approved 2026-10-05.**

## Alternatives considered

- **Per-persona tool restriction (the spec's position).** For example, Customer Insights without analytics, or Brand Strategy without keyword search. Rejected for these reasons:
  - It removes ways of reaching evidence that a question may legitimately need. A Customer Insights question about survey prevalence needs analytics.
  - It adds no security. Every tool is read-only and workspace-pinned, and the persona is a user-selectable lens, not an authorization principal. The real boundaries are workspace scope (ADR-0009) and `max_conf`.
  - Different tool arrays per persona would also fragment the prompt-cache prefix, because tool definitions sit at the start of the cached prefix.
- **Persona as a hard source-class filter.** Measurable and simple, but it misses cross-class evidence. A brand question often needs customer and market evidence, and contradicting evidence from a non-priority class would be hidden.
- **Persona as prompt-only.** Cheapest, but weak: the model may ignore the emphasis, and the effect cannot be measured in retrieval traces.
- **Persona-specific retrieval pipelines or rankers.** Multiplies configuration and evaluation surface for a demo-scale benefit that has not been demonstrated.

## Tradeoffs accepted

- Balancing has a little more ranking complexity: a reserved slot per priority class, subject to a floor.
- Personas change emphasis, not capability, so two personas can produce similar answers to a narrow question. That is intended.
- The spec's "tool availability" framing is honoured only at the level of mechanism (the tested allowlist), not in shipped behaviour.
- Persona is in the cache key, so the same question under two personas is cached twice.

## Consequences

**Positive**
- Personas cannot hide evidence or block a tool a question needs. Answer quality does not depend on choosing the "right" persona.
- Adding a persona means adding a YAML file: no code change and no new tool surface.
- The tool-definition prefix is byte-identical across personas, which keeps prompt caching effective (§33).
- If a future persona or tenant genuinely needs a narrower tool set, the allowlist is already enforced in the governance pipeline.

**Negative**
- The effect of a persona is subtle, so it must be measured rather than assumed.
- A prompt policy is untested prose until evaluated. A poorly worded policy could bias abstention or over-refusal.

**Follow-ups**
- Validate persona YAML against a Pydantic schema at startup: known classes only, a valid mode, and a bounded prompt length.
- Phase 7: run a small persona ablation (§37.1) and report class coverage and Recall@pack with and without the prior.

**Verification**
- Governance test: a token whose `tools` claim omits a tool gets `POLICY_DENIED` for that tool, and a `tool_runs` audit row is written.
- Parity test: every persona's token yields the same tool array, and the serialized tool definitions are byte-identical.
- Unit: *balancing with relative floors*. A priority class gets a slot only when it is within the floor, and is never forced in below it. Explicit `source_classes` override the persona prior.
- Unit: mode precedence. An explicit `mode` beats the persona default, and `auto` reaches the router.
- Behavioural eval: abstain/qualify recall ≥ 0.90 and over-refusal ≤ 0.10 hold for every persona (§27 gates), reported per persona when n allows.
- Phase 4 exit: the Demo 2 query makes at least 2 tool calls across at least 2 classes and is grounded.
