# RAGAS evaluation report

- ragas version: 0.4.3
- mode: offline
- created: 2026-10-14T17:07:29+00:00
- git sha: 3b5ed593b39dc1c3e971f0634f398ee355b4af93
- ragas usage tracking disabled: True
- inputs: `eval/reports/ragas-inputs/p4-research-test.samples.json` (p4-research-test)

## What was measured

### p4-research-test / standard

30 scored samples, 4 excluded by the exporter.

| Metric | Mean | Median | P25 | P75 | n | Undefined |
|---|---:|---:|---:|---:|---:|---:|
| Context recall (IDs, evidence pack) | 0.736 | 1.000 | 0.500 | 1.000 | 30 | 0 |
| Context precision (IDs, evidence pack) | 0.158 | 0.167 | 0.083 | 0.167 | 30 | 0 |
| Context recall (IDs, cited passages) | 0.724 | 0.917 | 0.500 | 1.000 | 30 | 0 |
| Context precision (IDs, cited passages) | 0.478 | 0.500 | 0.333 | 0.667 | 30 | 0 |
| Context recall (text similarity, evidence pack) | 0.753 | 1.000 | 0.500 | 1.000 | 30 | 0 |
| Context precision (text similarity, evidence pack) | 0.676 | 0.739 | 0.497 | 1.000 | 30 | 0 |

### p4-research-test / research

30 scored samples, 4 excluded by the exporter.

| Metric | Mean | Median | P25 | P75 | n | Undefined |
|---|---:|---:|---:|---:|---:|---:|
| Context recall (IDs, evidence pack) | 0.864 | 1.000 | 0.750 | 1.000 | 30 | 0 |
| Context precision (IDs, evidence pack) | 0.191 | 0.167 | 0.103 | 0.250 | 30 | 0 |
| Context recall (IDs, cited passages) | 0.843 | 1.000 | 0.750 | 1.000 | 30 | 0 |
| Context precision (IDs, cited passages) | 0.495 | 0.400 | 0.286 | 0.667 | 29 | 1 |
| Context recall (text similarity, evidence pack) | 0.881 | 1.000 | 0.812 | 1.000 | 30 | 0 |
| Context precision (text similarity, evidence pack) | 0.745 | 0.833 | 0.566 | 1.000 | 30 | 0 |

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

The historical Standard vs Research comparison for this split
(`eval/baselines/phase4/research-v0-test-live/compare.json`, `/metrics/gold_handle_recall`)
reports 0.7944 (standard) and 0.9056 (research) over the same 30 scored items. The RAGAS
`IDBasedContextRecall` pack scores above are lower (0.736 and 0.864) because the two use
different definitions, not because of different data:

- the historical metric counts a gold fact as found when **any** of its accepted handles is in
  the evidence pack (per-fact recall, averaged per item);
- RAGAS counts **every distinct gold handle**, alternates included, so a fact with two accepted
  handles of which only one was retrieved scores 0.5 rather than 1.

Recomputing the per-fact rule over the same pack handles and gold facts reproduces 0.7944 and
0.9056 exactly; the evaluation catalog builder repeats that check every time it runs.

## Provenance note

Both RAGAS runs recorded git sha `3b5ed59` while the working tree held uncommitted changes (the
exporter and this runner were being added), so the sha identifies the base commit, not the exact
code. The scored inputs are the persisted live outputs and gold datasets listed above, which were
not changed; no model was called and nothing was tuned on these scores. The intermediate samples
file under `eval/reports/ragas-inputs/` is local scratch and is not committed; it can be
regenerated with `python -m marketsignal.evaluation ragas-export`.
