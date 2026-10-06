# ADR-0007: Custom bounded agent state machine

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 4a (FakeLLM-tested over the in-process transport; Streamable HTTP in 4b), preceded by a Phase 0 spike on the Anthropic thinking/effort/strict-tool surface (this ADR is updated with measurements when the component is built)
- **Related:** plan §3, §19, §20, §28; ADR-0006 (MCP boundary), ADR-0008 (SSE), ADR-0015 (standard vs research modes); approved deviation D10 (context only; covered by ADR-0015)

## Context

Research mode handles multi-hop, cross-class and analytic questions, where one retrieval pass is not enough. An LLM chooses tools, observes results and decides when it has enough evidence. Unbounded loops are the main operational risk: runaway cost, latency past the spec's target, repeated identical calls, and context growth across steps.

Two API constraints apply to the chosen model (Claude Sonnet 5.5 for agent and synthesis):
- Thinking blocks are bound to the exact request prefix. Editing earlier tool results or dropping thinking blocks invalidates them.
- Forced tool choice returns 400 on Sonnet/Opus 5.5, so the loop cannot force the model to call a "stop" tool.

The interview has to be able to ask "what stops the agent?" and get an answer that is visible in code and covered by tests.

## Decision

A **custom explicit state machine** (about 500 lines) owns the loop. The LLM is only a step function inside it.

```
INIT → AGENT_STEP → EXECUTE (all tool_use blocks; excess beyond budget → POLICY_DENIED) → OBSERVE → (bounds/deadline) → AGENT_STEP …
  exits on: finish_research | end_turn | bound hit | gather deadline
  end_turn with zero successful searches → deterministic fallback search (PLANNER_NO_TOOL_FALLBACK)
BUILD_PACK —empty→ TERMINATE(no_relevant_evidence)
SYNTHESIZE → VERIFY —structural fail ∧ time left→ draft_reset → SYNTHESIZE(feedback) → VERIFY
                   —fail again | LLM down | refusal | max_tokens→ EVIDENCE_ONLY
FINAL → DONE(termination_state)
```

**Bounds (initial configured defaults, not measurements).** On every bound, the run proceeds to BUILD_PACK with the evidence gathered so far rather than discarding it.

| Bound | Default | On hit |
|---|---|---|
| `AGENT_STEP_LIMIT` | 4 | Stop gathering; `AGENT_STEP_BUDGET_EXHAUSTED` |
| `AGENT_MAX_TOOL_CALLS` | 10 | Same; excess parallel calls return `POLICY_DENIED` |
| `AGENT_MAX_CONSECUTIVE_TOOL_ERRORS` | 3 | Circuit opens; `TOOL_CIRCUIT_OPEN` |
| Duplicate (tool, canonical args) | 2nd repeat | `AGENT_REPEAT_CALL_STOPPED` |
| `TOOL_TIMEOUT_S` | 8 (analytics 5) | `TOOL_TIMEOUT`, counted as an error |
| `OBS_MAX_TOKENS` | 1,000 | Observation truncated |
| `AGENT_MAX_CONTEXT_TOKENS` | 40,000 (incl. replayed thinking + tools) | Stop gathering; `AGENT_CONTEXT_LIMIT`; history never edited |
| `EVIDENCE_POOL_MAX` | 40 parents | Stop gathering |
| `PACK_MAX_ITEMS / PACK_MAX_TOKENS` | 12 / 9,000 | Budget fill; `PACK_BUDGET_TRUNCATED` |
| `RUN_DEADLINE_S` | 60 (gather 35) | Gather timeout → BUILD_PACK with the evidence gathered so far; overall → `timeout` |

**Append-only transcript.** Each assistant response's full `content` (thinking blocks, including empty ones, plus text and `tool_use`) is resent unchanged on every step. The context bound stops gathering instead of trimming. If mid-run trimming is ever needed, server-side context editing is used; client-side stubs never are.

**`finish_research` terminal tool.** A harness-local tool (`{sufficient: bool, gaps: list[str]}`), not an MCP data tool, is the expected way to end gathering. Tools use native tool use with strict schemas and `tool_choice=auto`. An `end_turn` with prose is accepted as an exit, but the prose is discarded; the agent's `max_tokens` (4,096, effort `low`) keeps that cheap. Synthesis is a separate call over the deterministic pack (ADR-0004); the agent never writes user-facing prose.

**The agent owns run state.** The run-scoped evidence pool (per item: handle, anchor child id and its `char_start`/`char_end` offsets into the parent, best scores, expansion kinds, classes and provenance, taken from tool `structured_content`; ADR-0003, ADR-0006) and call budgets live here, keeping tools stateless (ADR-0006). The LLM sees compact observations; full evidence text never enters agent context.

**Context management (§20).** Retrieval queries are written from the question plus a compact, deterministically built conversation state: a rolling summary of at most 400 tokens from prior verified answers, the last 2 user questions, and up to 20 previously cited handles. The static system prompt and name-sorted tool definitions are prompt-cached. Per-turn input is O(pack + bounded state), independent of conversation length.

**LLM call envelope.** One wrapper handles every LLM call:
- Timeout = `min(phase budget, remaining deadline)`.
- SDK `max_retries=0`; our own policy retries 429, 529 or 5xx once with jitter, only if budget remains.
- `stop_reason`: `refusal` → `MODEL_REFUSAL` → evidence-only; `max_tokens` → `GENERATION_TRUNCATED` (not a citation failure).
- Spend reservation in the Postgres ledger before the call, reconciled against `usage` after; refusal to reserve → `BUDGET_EXHAUSTED`, evidence-only.
- One cancel scope per run. Tool SQL is bounded by `statement_timeout`, ONNX work by a semaphore; in-flight thread work finishes but its result is discarded.
- Thinking (adaptive) and effort are pinned explicitly, so behaviour does not depend on account defaults.

**Fallbacks.** First LLM call fails → run the `standard` gather path (`PLANNER_UNAVAILABLE_FALLBACK`).

**Privacy of reasoning.** Thinking and agent text are excluded from UI, logs and DB once the run ends. Progress events are built deterministically from tool arguments; model-derived query text appears only as quoted plain text truncated to about 80 characters.

**Termination states** with fixed precedence: `cancelled > timeout > tool_failure > no_relevant_evidence > generation_unavailable > retrieval_degraded > completed_with_limited_evidence > completed`. Flags carry details.

## Alternatives considered

- **LangGraph.** Mature graph runtime, but bounds, transcript handling and fallbacks would be split between framework defaults and our code. Proving the prefix is byte-identical across steps is harder through an abstraction.
- **Anthropic `tool_runner` (beta).** Least code, but beta, and it owns the loop, so per-step bounds, proceeding to the pack on a bound hit, and repeated-call stops are not first-class.
- **PydanticAI.** Typed and pleasant, but same issue: the loop policy we need to defend is not ours to show or test.
- **Forced tool choice for termination.** Returns 400 on the 5.5 models; not available.
- **Client-side history trimming or summarization mid-run.** Invalidates bound thinking blocks; rejected in favour of stop-gathering.
- **Agent for every query.** Covered by ADR-0015 (D10): deterministic routing between standard and research mode.

## Tradeoffs accepted

- We own and maintain about 500 lines of loop code instead of a framework.
- Append-only transcripts make context grow per step; the 40k-token bound stops gathering early rather than compressing.
- Discarding `end_turn` prose wastes a few tokens on occasional runs.
- Fixed effort and `max_tokens` per route favour cache stability over per-query tuning.

## Consequences

**Positive**
- Every bound is explicit config, unit-testable with FakeLLM scripted transcripts, and visible in traces and flags.
- Runs always terminate with a typed state; a bound hit proceeds to BUILD_PACK with the evidence gathered so far instead of failing.
- No model reasoning is persisted.

**Negative**
- Framework features (checkpointing, visual graph tooling) are not available.
- The Phase 0 spike result could force changes to the thinking/effort configuration.

**Follow-ups**
- Phase 7 agent-vs-single-pass ablation (mandatory under D10) supplies the evidence for when the agent is worth its cost; results are added here.
- Record measured steps, tool calls, context tokens and gather time per run from `query_runs`.

**Verification**
- FakeLLM bound tests: step limit, circuit breaker, repeated-call stop, context limit, `end_turn`-without-search fallback, parallel-call budget, refusal, `max_tokens`.
- Byte-identical request-prefix test across agent steps.
- Termination-precedence and degradation-mapping unit tests; every degradation code has a named test.
- Eval item: 30-turn synthetic conversation confirms bounded per-turn input tokens.
- Phase 4 exit criterion: the Demo 2 query makes at least 2 tool calls across at least 2 source classes and is grounded.

## Implementation notes (Phase 3, 2026-10-05)

The agent loop is Phase 4. Phase 3 built the parts of this ADR that standard mode shares (`runs/executor.py`, `runs/synthesis.py`, `runs/finalize.py`, `runs/flags.py`, `runs/state.py`, `generation/*`):

- **Bounds as configured defaults:** `pack_max_items` 12, `pack_max_tokens` 9,000 (`PACK_BUDGET_TRUNCATED`), `run_deadline_s` 60 with `run_gather_budget_s` 35. Added: `pack_item_max_tokens` 900 (anchor-centred window), `pack_candidates` 24, `regeneration_min_remaining_s` 15 and `run_finalize_reserve_s` 3 (each LLM call is clamped to the remaining deadline minus this reserve, so a slow model degrades to evidence-only rather than a run timeout).
- **Pack token unit:** the parents' stored WordPiece `token_count`, a deterministic proxy for model tokens; real usage is recorded from the provider.
- **`stop_reason` handling as decided:** `refusal` → `MODEL_REFUSAL`, `max_tokens` → `GENERATION_TRUNCATED`, both evidence-only without regeneration.
- **Termination precedence** implemented as decided, plus `interrupted` from the reaper (ADR-0008). `PRECEDENCE` and `termination_state` live in `runs/flags.py`. Publishing and `done` run once, outside the deadline scope and shielded from further cancels, and are bounded by `run_finalize_timeout_s` (20 s, validated to be less than `run_reap_margin_s`; on expiry a best-effort `done` and row update, and a run with no `final` ends `timeout`/`failed`).
- **Context management:** rolling summary capped at 1,600 characters (about 400 tokens) from the Answer units of verified answers, `[inference]` units excluded; last 2 questions; up to 20 cited handles (without the one-line labels). Retrieval uses the current question only.
- **Deviation: spend reservation not built.** No ledger reservation happens before the LLM call (`BUDGET_EXHAUSTED` does not exist yet); see ADR-0014.

### Live spike facts for Phase 4 (2026-10-06)

- Claude 5.x rejects `thinking: {"type": "disabled"}`; "no thinking before responding" is `{"type": "between_tools"}`. With tools, the short updates written between tool calls arrive as **thinking blocks**: they must be kept verbatim in the append-only transcript and never streamed or persisted as answer text.
- `tool_choice` `{"type": "tool"}` and `{"type": "any"}` return 400 on `claude-sonnet-5-5`. Only `auto` (and `none`) is available, as this ADR already assumed (`finish_research` as the expected exit). `auto` produces **parallel** tool calls by default.
- `output_config.format` json_schema returns schema-valid JSON, and strict tool schemas are accepted by `count_tokens`. See [spike 0002](../spikes/0002-anthropic-live.md).
