# Phase 3 report: grounded answering

**Status: core path implemented and tested offline. Live Anthropic validation pending.** The live compatibility spike, the live grounded evaluation and the real-model latency and token measurements have not run. No Anthropic API key could be loaded in the development environment (`Settings.anthropic_api_key` is unset). Until those runs are done and recorded below, Phase 3 does not meet its exit criteria.

Design references: [SYSTEM_DESIGN.md](../SYSTEM_DESIGN.md) and [GROUNDED_ANSWERING.md](../GROUNDED_ANSWERING.md). Decisions live in ADR-0004, 0007, 0008, 0011, 0015 and 0016, each with a Phase 3 implementation-notes section, and the deviations are in ARCHITECTURE_PLAN §0.4.

## What was built

- **Pipeline.** A question goes through production hybrid retrieval, then into a bounded, deterministic evidence pack (12 items, 9,000 tokens, 900 tokens per item, parents resolved from Postgres within the workspace). One synthesis pass cites run-local `[E#]` aliases. A streaming alias gate removes unknown aliases before display. The deterministic verifier then repairs the draft, regenerates once, or falls back to evidence only. The answer is persisted with canonical handles, and `final` and `done` are sent over SSE.
- **Abstention.** An empty pack never calls the model and returns a deterministic insufficiency message. Score-based weak-evidence abstention is deferred, with data: the top dense cosine on insufficient-evidence questions (0.684–0.822) sits inside the answerable range (0.649–0.907). See `eval/baselines/phase3/abstention-signals.json` and `scripts/phase3_abstention_signals.py`.
- **Runs.** Migration 0004 adds conversations, query_runs, messages and run_events, all under forced RLS. SSE supports replay by `Last-Event-ID`, a 15 s heartbeat, and stream tokens bound to the run and workspace. `done` is written exactly once, `final` is the source of truth, and `draft_reset` withdraws unverified drafts. There is a periodic reaper, and finalization is time-bounded.
- **Purge.** Purge now covers answers, conversation summaries and run events, including runs in flight; the locking argument is in `runs/store.py`.
- **Frontend.** `/w/[ws]/chat` adds a streaming draft, the verified final, citation chips, Evidence/Inference/Unknown sections, and evidence-only and abstention banners.
- **Grounded evaluation.** `grounded-v0` has 76 items: 42 answerable, 6 exact-number, 7 cross-source, 5 conflict, 8 insufficient, 2 empty-pack and 6 citation-adversarial. There are six hard gates and deterministic metrics only, with no LLM judge.

## Tests

| Suite | Result |
|---|---|
| Backend (`pytest -q`, unit + integration, real Postgres) | **555 passed, 1 skipped** (the skip needs a superuser DSN), run three times in a row after the final fixes |
| Frontend (`pnpm test`) | **111 passed**; lint, typecheck and build clean |
| CI | Green through `2fcb5e6`. Later commits are pending the push check. |

New Phase 3 suites cover the alias gate (including a Hypothesis split-invariance property), the verifier and its hardening cases, the LLM providers, the runs API (SSE, replay, cancel, deadline, reaper), purge during a run, and the event writer. The adversarial citation cases required by the plan are covered: invented, malformed, split across deltas, outside the pack, foreign-workspace, purged during generation, duplicate, and placed inside punctuation or Markdown.

## Measurements available now (offline, FakeLLM)

Grounded evaluation with the scripted fake model at `647d2e7`, retrieval config `35fc5c5a734a67e9`, 76 items:

| Gate | Value | Pass |
|---|---|---|
| citation_resolvability | 1.0 | yes |
| citation_in_pack | 1.0 | yes |
| every_run_done (items missing done) | 0 | yes |
| answer_items_have_final (missing) | 0 | yes |
| cross_workspace_leaks | 0 | yes |
| empty_pack_never_calls_llm | 1.0 | yes |

These gates test the pipeline's guarantees, not model quality. The fake model does not read the evidence, so its behaviour metrics (for example, insufficient 0/8) say nothing about answer quality and are not reported as results.

Latency of the non-LLM path, per run (ms):

| Stage | p50 | p95 | max |
|---|---|---|---|
| Retrieval (hybrid, warm) | 32.5 | 58.0 | 575.6 (first query, model load) |
| Pack build | 1.5 | 2.0 | 42.8 |
| Verification | 2.4 | 3.6 | 16.0 |
| End to end with FakeLLM | 78.8 | 138.2 | 655.7 |

**Pending live evaluation:** real first-token and end-to-end p50/p95, input and output tokens per answer, cache-read tokens, citation and abstention behaviour on a real model, and the example grounded answers.

## Adversarial review: failures found and fixed

A four-reviewer adversarial review of the Phase 3 path, with skeptic verification, produced 37 findings: 22 confirmed, 14 low-severity (not separately verified), 1 refuted. A second review of the fixes found 5 more. All confirmed findings, and every low-severity one except cross-process cancel, were fixed with tests that failed before the fix. They are kept here because they are the most informative part of this phase.

| Area | Failure (confirmed reproduction) | Fix |
|---|---|---|
| Citation forgery | `[[[](u)OTHERWS/SECRET@v[](u)1:P1]]`: removing a link reassembled a foreign-workspace `[[HANDLE]]` that reached stored content with `ok=True` | Leak stripping runs to a fixpoint, and the render drops any `[[…]]` that is not a cited pack item |
| Alias gate | With an empty pack, `[E1[E1]]` displayed `[E1]` after the inner alias was removed (found by Hypothesis) | A separator is added when a removal follows an alias prefix |
| Numeric faithfulness | `612.0 billion` was supported by `612.0 million`; `2,960%` by `2,960 respondents`; `340bps` and `9.9pp` were never checked | Scale, percent and currency must agree; glued units and spelled magnitudes are extracted |
| Fix regression | The first numeric fix rejected correct percents from `col: value` dataset rows | Count labels are limited to count nouns and count-type columns |
| Interpretation / Gaps | Citations not checked against their own item; untagged factual claims in Gaps | Cited check applied; non-gap units tagged `[inference]` |
| Purge | Purged text survived in `rolling_summary`, in uncited-but-used answers, and in events written after the purge; a re-upload re-enabled a run's purged text; ingesting a re-upload un-purged the old version (a Phase 1 bug) | Run-side writes lock the run row and check the purge state of the exact version; purge locks affected runs; conversation state is reset; citation cards become tombstones; supersede skips purged versions |
| Lifecycle | A double cancel could prevent `done`; a late deadline could terminate twice; the reaper could add a second `done`; runs could stay `running` forever; LLM budgets were not clamped | Exactly-once shielded termination, idempotent periodic reaper, DB refusal of events after `done`, bounded finalization, clamped budgets that lead to evidence-only |
| Evaluation | Hard gates passed vacuously when no run produced a final; insufficiency was credited from any Gaps line | New completeness gates; citation gates fail when nothing was evaluated; insufficiency judged on the Answer section only |
| Logs | SSE stream tokens in uvicorn access logs; bound parameters (evidence text) in DB error strings | Access-log scrub filter; `hide_parameters=True` |

## Example repaired generations (verifier, real outputs)

- Input Answer sentence `Price led for 27% of buyers [E1] [[[](u)OTHERWS/SECRET@v[](u)1:P1]].` Stored as `Price led for 27% of buyers [[NORTHSTAR/SURVEY-2026@v1:R185]].` The forged marker is removed and only the cited pack item stays.
- Input `Price led for 27% of buyers [E1[E99]].` with E99 not in the pack. The unknown alias is removed (`unknown_aliases=['E99']`), the remnant `[E1 ]` is inert, and the uncited sentence is tagged `[inference]`.
- Input `Revenue was 612.0 million [E1].` in Interpretation, where 612.0 appears only in E2. Before the fix it was stored with E1's chip. Now it fails the cited check and is repaired.

Example live grounded answers: **pending live evaluation.**

## Unresolved failure modes and limits

- **Live model behaviour is unmeasured.** That includes over-refusal, conflict reporting and numeric errors from a real model.
- **Cross-process cancel.** Cancel reaches only runs owned by the receiving process. With several API processes the run continues. (Known; ADR-0008 notes.)
- **No rate limiting or concurrent-run cap per workspace.** The review finding was refuted as a correctness bug, but the gap is real. It is deferred to the deployment hardening phase.
- **Numeric checks have limits.** An unlabelled bare table cell can back a percent claim. Spelled numbers without a magnitude word, and fractions ("a third"), are not checked.
- **Text already sent to the model before a purge cannot be recalled.** The guarantee is that nothing is *stored* or replayable after the purge.
- **Partial answers are not persisted as `incomplete`.** Cancel and timeout withdraw the draft instead (deviation recorded in §0.4).
- **Reload mid-run:** the UI cannot reattach to a running stream because the stream token is not stored. It shows a refresh prompt.

## Commits

```
76fd87a feat(llm): provider interface, scripted FakeLLM and the Anthropic adapter
fb3488f feat(generation): evidence pack, prompts, streaming alias gate, answer verifier
7c2c1e1 feat(runs): conversations, runs and the SSE event log (migration 0004)
ed7e9f6 feat(runs): standard-mode grounded answering over SSE
dab5f35 feat(eval): grounded-answer evaluation (grounded-v0) and the abstention-signal analysis
712c8ef chore(spike): live Anthropic compatibility spike script
79c57a4 feat(frontend): grounded chat UI with SSE run stream and citation chips
b73265c fix(eval,telemetry): strict grounded-eval gates; scrub stream tokens and bound params from logs
da7c1c2 fix(generation): close citation-forgery and numeric-faithfulness gaps in the verifier
4123b66 fix(generation): alias gate removal can no longer assemble a new alias
2fcb5e6 fix(runs): purge-safe runs and an uninterruptible, exactly-once termination
c729259 chore(eval): reproducible abstention-signal generator with provenance
6b7d4cc fix(generation): accept percent claims backed by dataset rows; read spelled decimals
5aeec1b fix(runs): per-run purge guard on version state; bounded finalize; no events after done
647d2e7 refactor(runs): split the executor into synthesis, finalize, flags and state modules
```

## Remaining to close Phase 3

1. Configure the key locally, then run `uv --directory backend run python ../scripts/spike_anthropic.py`. Record the non-secret results in `docs/spikes/0002-anthropic-live.md` and update the ADRs if the API differs.
2. Run `uv --directory backend run python -m marketsignal.evaluation grounded --out ../eval/baselines/phase3/live-v0` once. Record the gates, behaviour by category, p50/p95 latency, tokens, example answers and every failure here, unedited.
