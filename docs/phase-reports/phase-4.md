# Phase 4 report: research agent, governed MCP tools, verifier precision

**Status: implemented, measured live, awaiting review before Phase 5.** Phase 4 delivers:
- a bounded research agent reaching workspace data only through governed tools, in-process or over MCP Streamable HTTP;
- a deterministic, user-overridable mode router;
- the former Phase 3.1 verifier precision work, measured on a fresh dev/holdout set.

Research mode was compared with the unchanged Phase 3 standard path on a new evaluation set. Failures are kept below as they occurred.

Design: [RESEARCH_AGENT.md](../RESEARCH_AGENT.md), [GOVERNED_TOOLS_AND_MCP.md](../GOVERNED_TOOLS_AND_MCP.md), [GROUNDED_ANSWERING.md](../GROUNDED_ANSWERING.md) §5.7, [SYSTEM_DESIGN.md](../SYSTEM_DESIGN.md). Decisions: ADR-0006, 0007, 0015 and 0018, each with Phase 4 implementation notes. Deviations are in ARCHITECTURE_PLAN §0.4.

## How the work was organised

The lead (integrator) owned every shared interface before any delegation:
- the frozen tool contract (`tools/contracts.py`);
- migration 0005, plus 0006 after the security review;
- the Phase 4 settings, the router and the executor integration;
- purge, the API and app wiring, and documentation.

Each subagent got an explicit file-ownership list, never committed, and had its diff reviewed and its tests re-run by the lead before any commit.

| Workstream | Responsibility | Outcome |
|---|---|---|
| A: verifier precision | verifier-v1 dataset and harness, fixes A1–A7, per-attempt reports | Committed after an adversarial review found 6 regressions, all fixed |
| B: research agent | state machine, bounds, transcript, tool-use provider step, pool | Committed. 246 tests; every bound and stop reason has a named test |
| C: governed tools + MCP | registry, capability tokens, governance pipeline, in-process and HTTP transports, parity | Committed. In-process/HTTP parity across all cases |
| D: frontend | mode selector, route badge, research timeline | Committed. 147 frontend tests |
| E: research-v0 dataset | 57 new items, grouped dev/test split, leakage checks, DB-verified gold | Committed |
| F: comparison harness | `grounded --mode both`, paired comparison, research metrics, independent numeric re-check | Committed |
| Reviewers | adversarial verifier review (false-negative regressions); four-dimension security review with skeptic verification | 6 verifier regressions and 22 security findings (12 confirmed); all fixed or recorded |
| G / H: security fixes | tools/MCP side and agent/integration side of the security findings | Committed |
| Docs | deep dives, ADR notes, deviations | Committed |

## Tests

| Suite | Result |
|---|---|
| Backend `pytest -q` (unit and integration, real Postgres as `ms_app`) | **1068 passed, 9 skipped** (8 opt-in live tests and 1 superuser-DSN test), run twice |
| Backend unit | 865 passed |
| Live hardening (`MS_LIVE_LLM=1`, real model) | **8 passed** against the Phase 4 verifier |
| Frontend | **147 passed**; lint, typecheck and build clean |
| Repository safety | passed (tracked and staged) |
| CI | green on every pushed head |

## Verifier precision (former Phase 3.1)

The verifier-v1 dataset is fresh: 32 families, 77 cases and 259 labelled units, with family-grouped dev/holdout splits and the holdout hash recorded. live-v0 was not used.

| Metric | dev before | dev after | holdout before | holdout after |
|---|---|---|---|---|
| Supported claims wrongly removed (false positives) | 10.1% | **4.0%** | 13.0% | **5.8%** |
| Supported claims kept | 89.9% | 96.0% | 87.0% | 94.2% |
| Unsupported claims accepted (false negatives) | 35.6% | **24.4%** | 30.4% | **30.4%** |
| Regeneration needed | 0.14 | 0.19 | 0.14 | 0.14 |
| Evidence-only fallback | 0.14 | 0.17 | 0.14 | 0.14 |
| Latency p50 (ms) | 0.32 | 0.54 | 0.29 | 0.51 |

- **What changed:**
  - A1, temporal values: years in cited units must appear in the cited item or its visible metadata.
  - A2, visible metadata: a metadata phrase backs only its own number.
  - A3, clause repair: guarded against negation and condition words. Re-pointing is restricted, and effectively off.
  - A4, citation cap: configurable, and stated in the prompt and the regeneration feedback.
  - A5, gap statements: insufficiency sentences are gaps, not inferences.
  - A6, per-attempt reports: persisted, purge-guarded, and the verifier fails closed.
  - A7, conflicts: an advisory signal only, because it raised 4 false flags on holdout.
- **The first version was unsafe.** An adversarial review found six false-negative regressions:
  - alias reassembly through parenthetical removal, with a crash on out-of-range aliases;
  - month names masking real quantities;
  - cross-item years accepted as quantities and periods;
  - figure-only re-pointing;
  - metadata-phrase smuggling;
  - gap statements carrying claims.

  All are fixed. The 55 review probes are now a regression test asserting the verifier never accepts more than Phase 3 did.
- **Holdout used twice.** It was evaluated once for the changes and once for the review-driven safety fixes, and nothing was tuned on it. Details: `eval/baselines/phase4/verifier/SUMMARY.md`.
- **Remaining false negatives** are beyond a numeric check: invented entity names, causal claims without figures, and a figure from the right item but the wrong period.

## Research agent

The agent is a bounded state machine: INIT → AGENT_STEP → EXECUTE → OBSERVE, looping until DONE. `tool_choice` is always `auto`, and the harness-local `finish_research` tool ends gathering.

**Bounds**, with defaults:

| Bound | Default |
|---|---|
| Agent steps | 4 |
| Tool calls | 10 (excess parallel calls are denied without running) |
| Consecutive tool errors before the circuit opens | 3 |
| Repeated identical call (normalized arguments) | stops on the 2nd repeat |
| Agent output tokens | 12,000 |
| Context | 40,000 (estimate: UTF-8 bytes / 3) |
| Evidence pool | 40 parents |
| Gather deadline | one deadline for the whole run (35 s inside the 60 s run deadline) |

Cancellation propagates.

**Termination is proven by tests** for every one of these:
- finish and end_turn;
- each bound above;
- tool timeout and purged evidence;
- model failure on step 1 and on later steps;
- cancellation;
- 150 random scripts that all end within the step limit.

**Fallbacks:**
- When the first model call fails (planner unavailable), the standard gather runs.
- Any stop with nothing gathered also runs the standard gather, keeping the original bound flag.
- When no gather time remains, the run records a retrieval timeout instead of a run timeout.

**Privacy:**
- Thinking blocks (`between_tools`) are kept verbatim in the append-only transcript and never streamed or stored.
- Progress events are fixed templates built from validated arguments; model text appears only as quoted strings of at most 80 characters, with control characters stripped.
- `query_runs.agent` holds only observable actions (stop reason, flags, counts, state path, sanitized trace, usage).
- Tests inject thinking and prose canaries and assert neither appears anywhere.

**Live tool use works.** A smoke run made 4 steps and 5 tool calls, including parallel searches, then called finish_research. It produced a verified answer citing both customer and competitor evidence.

## Governed tools and MCP

- **Four tools:** `search_evidence` (production hybrid RRF, with the reranker forced off), `search_evidence_keyword`, `get_evidence` and `list_sources`. The analytics and hypothesis tools are deferred.
- **One governance pipeline:**
  1. verify the token;
  2. revoke if the run is no longer running;
  3. check the tool allowlist;
  4. validate strictly against closed models, with bounded strings and control characters rejected;
  5. run under a timeout, with a transaction-local `statement_timeout` in a claims-scoped session;
  6. cap the output;
  7. re-check revocation;
  8. write a purge-safe audit row;
  9. return an escaped, untrusted observation.
- **Workspace identity** comes only from HS256 capability claims (`aud=mcp`, run id required, bounded lifetime, source-class claim). A `workspace_id` argument is a validation error.
- **Forgery tests** cover another workspace, a missing credential, expired, wrong-audience, wrong-key and malformed tokens, plus revoked runs and disallowed tools.
- **Parity:** every logical call through the in-process transport and through MCP Streamable HTTP, against a real loopback server, gives equal results, observations, errors and audit rows. That covers all auth failures, validation cases and the source-class claim.
- **HTTP transport:**
  - `/mcp` is loopback-only and rejects forwarded headers unless public.
  - `tools_transport=http` falls back in-process on genuine transport failures (`TOOLS_TRANSPORT_FALLBACK`).

## Routing

- **Precedence:** explicit standard/research, then explicit auto (cue rules), then the persona default, then the cue rules.
- **Recording:** the decision is stored in `query_runs.route`, `run_started` and the 202 response, and the UI shows it.
- **Personas** are validated ids, never free text.
- **Router agreement with research-v0's expected route** (deterministic, measured without a model):

  | Split | Agreement |
  |---|---|
  | dev | **19/23 (83%)** |
  | test | **21/34 (62%)** |

  On test, 11 items expected to need research were routed to standard: the cue rules miss simply phrased multi-step questions. Not tuned on test; see the Phase 5 plan.

## Standard vs research (research-v0 test split, 34 pairs, live)

| Metric | Standard | Research | Research − standard (95% CI) |
|---|---|---|---|
| Hard gates (resolvable, in pack, leaks, done, final) | all pass | all pass | — |
| Behaviour pass | 34/34 | 33/34 | −0.029 [−0.088, 0] |
| Gold coverage (cited) | 0.822 | 0.937 | **+0.115 [0.023, 0.224]** |
| Gold handle recall (pack) | 0.794 | 0.906 | **+0.111 [0.028, 0.217]** |
| Answer completeness (gold values stated) | 0.736 | 0.747 | +0.012 [0, 0.035] |
| Conflict coverage | 2/2 | 2/2 | — |
| Abstention correct | 4/4 | 4/4 | — |
| Unsupported cited units (independent re-check) | 0/225 | 1/236 | the 1 is a locator label ("Interview 7"), see below |
| Model calls / run | 1 | 3.97 | +2.97 |
| Tool calls / run | 0 | 3.74 | +3.74 |
| Retrieval calls / run | 1 | 2.82 | +1.82 |
| Agent steps / run | 0 | 2.97 | — |
| Tokens / run | 5,212 | 20,390 | +15,180 |
| Cost / run (USD) | 0.0134 | 0.0364 | +0.0229 |
| First token p50 / p95 | 1.58 s / 4.58 s | 1.57 s / 5.33 s | — |
| End to end p50 / p95 | **5.8 s / 9.2 s** | **14.4 s / 20.3 s** | +8.3 s |
| Agent stop reasons | — | finish 24, step limit 8, end_turn 2 | — |
| Termination | completed 34 | completed 34 | — |
| Tool failures, fallbacks, regenerations | 0 | 0 | — |

**By category**, gold coverage standard → research:

| Category | Gold coverage |
|---|---|
| first-pass-insufficient | 0.79 → **1.00** |
| reformulation | 0.50 → **1.00** |
| identifier-then-semantic | 0.50 → 0.62 |
| simple controls | 1.00 → 1.00 (no gain) |
| multi-class | 0.89 → 0.89 (no gain) |
| conflict | 1.00 → 1.00 (no gain) |
| customer+competitor, customer+internal | no gain |

Research costs about 2.7× more and takes 2.4× longer in every category. The plan's research target is about 25 s p50, so 14.4 s is within it.

**Dev split** (23 pairs, a plumbing and sanity check, not used for tuning): the same pattern. Answer completeness rose 0.76 → 0.86 (+0.095 [0.024, 0.175]), cost was $0.042 vs $0.015 per run, and end-to-end p50 was 15.9 vs 6.9 s.

**Conclusion:**
- Research reliably finds and cites more of the gold evidence where the first search misses vocabulary or needs a follow-up. On simple lookups it only adds cost.
- Gains in stated gold values are small. The agent gathers evidence that synthesis does not always state.
- This supports keeping standard as the default and improving the router's research cues.

## Preserved failures

- **R-SC-04 (research, simple control).** The agent found the channel table's description but not the millennial row, and stated insufficiency. Standard answered correctly.
- **Unsupported-unit flags.** The independent re-check flags 1 research unit on test and 2 on dev. All three are locator or title phrases ("Interview 7", "Interview 12", "Brand Strategy 2026") that the verifier's A2 rule accepts as visible metadata. The re-check compares against item text only, so it is deliberately stricter.
- **Over-refusal regression on grounded-v0** (standard mode, new verifier, live; all six hard gates pass): 3/60 against live-v0's 1/60.
  - The per-attempt reports show G-R0-054 and G-A4 failing both attempts on `too_many_citations`. Stating the cap did not stop enumeration answers from over-citing.
  - The third case (G-R0-031) also fell back to evidence only. Its attempt reports were not in the query result (a text-match miss in the diagnostic query), so its cause is not confirmed.
- **G-A4 canary counter.** The evidence-only fallback quotes the planted injection review verbatim as evidence. The model did not obey the injection, but the fallback shows untrusted injection text to the user inside a quote.

## Security findings

**Before integration**, an adversarial review of the verifier found **6 false-negative regressions**, listed in the verifier section. All are fixed and turned into regression tests.

**After integration**, a four-dimension security review with skeptic verification produced 22 findings: 12 confirmed and 10 low. All confirmed findings and most low ones are fixed with tests.

| Finding | Fix |
|---|---|
| Research ignored the run's source-class filter | Class claim in the token, enforced by the tools and the pool |
| A verification report written after a purge survived it | Purge guard on insert |
| Agent tool arguments and trace could outlive a purge | Purge reaches agent-seen runs and redacts arguments and trace; migration 0006 column grant; purge-safe audit and trace writes |
| Unbounded per-item strings and NUL bytes could fail runs | Model-level bounds; control characters rejected |
| The fallback gather got a fresh 35 s budget | One gather deadline |
| Some empty-handed stops skipped the fallback | Every such stop falls back |
| Repeat detection was evadable | Normalized keys |
| A provider construction error failed the run | Becomes planner-unavailable |
| HTTP transport had no fallback | In-process fallback |
| The loopback guard trusted forwarded headers | Rejected unless public |
| Weaker token checks | `jti` required, lifetime cap, post-call revocation re-check |
| `list_sources` and conversation context rendering | Escaped, untrusted elements |
| Free-text persona | Validated ids |

The live smoke also found that the anthropic client's `httpx2` loggers escaped the log pin; that is fixed.

## Live API cost (Phase 4)

| Run | Cost |
|---|---|
| research-v0 test, both modes | $1.69 |
| research-v0 dev, both modes | $1.31 |
| grounded-v0 regression | $1.06 |
| Research smoke | about $0.05 |
| Live hardening | about $0.15 |
| **Total** | **about $4.3** |

Prices: $2 input, $10 output, $2.50 cache write and $0.20 cache read per million tokens (`claude-sonnet-5-5`).

## Unresolved risks and limitations

- Enumeration answers still exceed the citation cap and over-refuse, despite the stated cap.
- The router misses simply phrased multi-step questions (62% agreement on test).
- Research gathers more evidence than synthesis states (completeness +0.01).
- The evidence-only fallback can display injection-carrier text as quoted evidence.
- Verifier false negatives remain for non-numeric hallucinations: entity names and causal claims.
- Analytics and hypothesis tools, persona priors and prompt policies, cross-process cancel, rate limits, the spend ledger and the answer cache are deferred.
- `query_runs.tool_calls` records executed calls. The budget is enforced in the agent runtime, not by an atomic database counter.
- Research p95 is 20.3 s, inside the target but close to the 35 s gather budget under load.

## Commits

```
765202e feat(phase4): foundations: tool contract, migration 0005, agent/tool/MCP settings
945fd32 feat(runs): deterministic, user-overridable mode router (ADR-0015)
117a45d feat(agent): bounded research agent state machine with tool-use provider support
4bb0656 feat(tools,mcp): governed tool registry, capability tokens, in-process and MCP HTTP transports
19c3a15 test(eval): research-v0 dataset for standard-vs-research comparison
644daf0 feat(runs): research mode end to end: router in the API, agent gather, MCP mount
26d5afe feat(frontend): mode selector, route badge and research progress timeline
5f638eb fix(telemetry): pin httpx2/httpcore2 loggers too (anthropic 1.x HTTP client)
6c16dd3 feat(eval): standard-vs-research grounded evaluation with paired comparison
8cc93b5 feat(verifier): precision hardening (former Phase 3.1) and per-attempt verification reports
6262195 fix(purge): reach agent-seen runs; verification reports honour the purge guard
c5f7d58 fix(tools,mcp): security-review hardening of the governed tool boundary
bcc4621 fix(agent,runs): security-review hardening of the research agent and its integration
a6474d5 fix(api): conversation persona must be a known persona; correct stale docstrings
8ae34ac docs: Phase 4 research agent and governed tools deep dives, ADR notes, deviations
5b9f5b5 test(eval): live standard-vs-research comparison on research-v0 (dev and test)
ec94d1c test(eval): live grounded-v0 hard-gate regression with the Phase 4 verifier
```

The commit adding this report follows.
