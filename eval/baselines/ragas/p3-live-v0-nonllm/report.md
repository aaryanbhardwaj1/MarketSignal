# RAGAS evaluation report

- ragas version: 0.4.3
- mode: offline
- created: 2026-10-14T17:07:28+00:00
- git sha: 3b5ed593b39dc1c3e971f0634f398ee355b4af93
- ragas usage tracking disabled: True
- inputs: `eval/reports/ragas-inputs/p3-live-v0.samples.json` (p3-live-v0)

## What was measured

### p3-live-v0 / standard

59 scored samples, 17 excluded by the exporter.

| Metric | Mean | Median | P25 | P75 | n | Undefined |
|---|---:|---:|---:|---:|---:|---:|
| Context recall (IDs, evidence pack) | 0.894 | 1.000 | 1.000 | 1.000 | 59 | 0 |
| Context precision (IDs, evidence pack) | 0.097 | 0.083 | 0.083 | 0.083 | 59 | 0 |
| Context recall (IDs, cited passages) | 0.886 | 1.000 | 1.000 | 1.000 | 59 | 0 |
| Context precision (IDs, cited passages) | 0.463 | 0.333 | 0.250 | 0.500 | 59 | 0 |
| Context recall (text similarity, evidence pack) | 0.903 | 1.000 | 1.000 | 1.000 | 59 | 0 |
| Context precision (text similarity, evidence pack) | 0.713 | 0.941 | 0.484 | 1.000 | 59 | 0 |

## Definitions

- **Context recall (IDs, evidence pack)** (`id_context_recall_pack`, ragas `IDBasedContextRecall`): Share of distinct gold passage handles that appear in the evidence pack.
- **Context precision (IDs, evidence pack)** (`id_context_precision_pack`, ragas `IDBasedContextPrecision`): Share of distinct evidence-pack handles that are gold handles. Undefined for an empty pack.
- **Context recall (IDs, cited passages)** (`id_context_recall_cited`, ragas `IDBasedContextRecall`): Share of distinct gold passage handles that the answer actually cites.
- **Context precision (IDs, cited passages)** (`id_context_precision_cited`, ragas `IDBasedContextPrecision`): Share of distinct cited handles that are gold handles. Undefined when the answer cites nothing.
- **Context recall (text similarity, evidence pack)** (`nonllm_context_recall_pack`, ragas `NonLLMContextRecall`): Share of gold passages whose best normalised string similarity to any pack passage exceeds 0.5. A lexical heuristic, not a judgement of meaning.
- **Context precision (text similarity, evidence pack)** (`nonllm_context_precision_pack`, ragas `NonLLMContextPrecisionWithReference`): Rank-weighted average precision of pack passages, where a pack passage counts as relevant when its best string similarity to a gold passage is at least 0.5.

## Not measured

- **Faithfulness (model-judged)** (`faithfulness`): not run, needs a judge model; it is wired but was not run (no model calls were made).
- **Answer relevancy (model-judged)** (`answer_relevancy`): not run, needs a judge model; it is wired but was not run (no model calls were made).
- **Context precision vs reference (model-judged)** (`llm_context_precision_with_reference`): not run, needs authored reference answers; the gold sets hold short gold facts and handles, not reference answers.
- **Context recall vs reference (model-judged)** (`llm_context_recall`): not run, needs authored reference answers; the gold sets hold short gold facts and handles, not reference answers.
- **Factual correctness vs reference (model-judged)** (`factual_correctness`): not run, needs authored reference answers; the gold sets hold short gold facts and handles, not reference answers.

## Caveat

No model was called for this run: every score here is a model-free heuristic. RAGAS scores are proxies computed by the ragas library, not objective truth. ID-based scores depend on the gold handles being complete; text-similarity scores are lexical and can miss paraphrases or reward surface overlap.

## Reconciliation with historical metrics

The historical grounded-answer run (`eval/baselines/phase3/live-v0/results.json`) has no
evidence-pack recall metric to reconcile against: its `gold_coverage` measures gold facts the
answer cites, per fact, which is a different definition from these RAGAS scores. RAGAS
`IDBasedContextRecall` counts every distinct gold handle, alternates included, so it is not
directly comparable with any per-fact figure. No historical number is restated here.

## Provenance note

This run recorded git sha `3b5ed59` while the working tree held uncommitted changes (the
exporter and this runner were being added), so the sha identifies the base commit, not the exact
code. The scored inputs are the persisted live outputs and gold dataset listed above, which were
not changed; no model was called and nothing was tuned on these scores. The intermediate samples
file under `eval/reports/ragas-inputs/` is local scratch and is not committed; it can be
regenerated with `python -m marketsignal.evaluation ragas-export`.
