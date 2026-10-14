# ADR-0021: RAGAS as an isolated runner over persisted outputs

- **Status:** Accepted
- **Date:** 2026-10-14
- **Implementation:** Built in the final phase. Exporter `backend/src/marketsignal/evaluation/ragas_export.py` (CLI `python -m marketsignal.evaluation ragas-export`); runner `eval/ragas_runner/` (own `pyproject.toml` and `uv.lock`, [README](../../eval/ragas_runner/README.md)); artifacts `eval/baselines/ragas/*/` (`results.json`, `report.md`); catalog section `scripts/eval_catalog_builder/ragas.py`; CI job `ragas-runner`.
- **Related:** ADR-0013 (evaluation methodology, and its 2026-10-14 addendum), ADR-0009 (workspace isolation)

## Context

ADR-0013 chose in-house metric definitions over a framework dependency so every number is explainable and versioned. Reviewers still expect to see standard RAG metrics, and RAGAS is the common reference. Constraints in this phase:

1. **No live model calls.** API credits are exhausted, so only metrics that need no LLM can be computed.
2. **No change to the serving runtime.** RAGAS pulls in a large langchain/openai/datasets dependency tree.
3. **No change to recorded evaluation artifacts.** RAGAS must score what the system already produced, not a fresh run.
4. **No cross-workspace reads.** Passage texts must be resolved in the scope of each item's own workspace.

## Decision

**Three stages joined by files, with RAGAS confined to its own project.**

- **Export (backend, no RAGAS, no model).** `ragas-export` reads a committed run's results and its gold dataset read-only, resolves every pack, cited and gold handle through the evidence resolver in the RLS scope of the item's workspace, and writes a `marketsignal.ragas-samples` (format_version 1) JSON. Items with nothing to ground are excluded with a stated reason (`abstention_expected`, `no_gold_handles`, `foreign_handle`, `unresolvable_handle`); a foreign handle is never resolved. Citation markup is stripped from answers, and `reference` is null because the gold sets hold short facts, not authored reference answers.
- **Score (isolated uv project).** `eval/ragas_runner` pins ragas exactly with its own lockfile (resolution cut-off `exclude-newer = 2026-09-30`), never imports `marketsignal`, and disables RAGAS usage tracking before RAGAS is first imported. `ragas-eval offline` computes the non-LLM metrics: ID-based context precision and recall over the evidence pack and over the cited passages, and text-similarity context precision and recall over the pack. A score RAGAS cannot define is `null` and counted in `n_nan`, never replaced. The output directory must not exist, so recorded artifacts are never overwritten.
- **Publish (catalog).** `results.json` records input paths and sha256s, the RAGAS version and the git sha. The catalog builder reads it read-only: every number carries a JSON pointer to its source, exclusions are recomputed from the gold datasets and must equal the recorded `n_excluded`, and caveats are always attached. Items are served through the closed run ids `ragas-p3-live-v0` and `ragas-p4-research-test` (`GET /api/dev/eval/runs/{run_id}/items`).
- **Model-judged metrics wired, not run.** Faithfulness, answer relevancy and the reference-based LLM metrics are implemented behind `ragas-eval llm`, which needs a confirmation flag, `MS_LIVE_LLM=1` and a key, and without `--confirm-cost` only prints a cost estimate. Offline results list them as not run.

## Alternatives considered

- **RAGAS as an optional extra of the backend package.** One project, one command. Resolving it in the backend lockfile downgraded runtime dependencies the server uses (`fsspec`, `docstring-parser`), so an evaluation tool would have changed production behaviour. Rejected.
- **Re-implement the RAGAS metrics in-house.** No dependency at all, but the point of RAGAS here is an external, recognisable definition; a re-implementation would be one more in-house number. Rejected.
- **Run RAGAS against a fresh evaluation run.** Would need live model calls and would produce numbers not comparable to the committed baselines. Rejected.
- **Run the model-judged metrics now.** Not possible without credits, and a judge needs calibration (ADR-0013) before its numbers mean anything. Deferred behind the opt-in.

## Tradeoffs accepted

- **Heuristic metrics only.** ID and string-similarity context metrics say whether the right passages were retrieved and cited; they say nothing about whether the answer is faithful. The catalog states this as a caveat.
- **Two Python projects and two lockfiles** to maintain, plus a CI job for the runner.
- **ID recall definition.** RAGAS ID recall counts every alternate gold handle, so it differs from the in-house per-fact gold-handle recall; the report reconciles the two and the per-fact rule reproduces the historical figures exactly.

## Consequences

**Positive**
- Standard metric names next to the in-house gates, with no change to the serving lockfile or the recorded artifacts.
- Every RAGAS number traces to an input file by sha256 and to a summary block by pointer.

**Negative**
- The samples file is local scratch (`eval/reports/ragas-inputs/`), so reproducing a score needs a seeded database to re-export.

**Verification**
- Backend: `tests/unit/test_ragas_export.py`, `tests/integration/test_ragas_export_db.py`, `tests/unit/test_eval_catalog_ragas.py` (including that every pre-existing catalog section and item file is unchanged).
- Runner: `eval/ragas_runner/tests/` (offline, run with no API key set).
