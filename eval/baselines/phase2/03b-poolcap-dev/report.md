# Phase 2 step 3b: rerank-pool source cap only (final cap off), dev

- Split: **dev**, items: 44
- Dataset: `retrieval-v0` · corpus `d68f6473052e` · ledger `95e9bb87bae7`
- Run: git=90c3c31, at=2026-10-05T23:05:19+00:00, config_hash=fcde3e92cee57059

## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)

| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| hybrid-rerank-balance-poolcap-only | 70.5 [55.8, 81.8] | 81.8 [68.0, 90.5] | 84.1 [70.6, 92.1] | 78.8 [67.0, 89.0] | 83.3 [72.3, 93.2] | 76.3 [64.4, 87.4] | 679.04 | 922.21 |

## Latency by stage (ms, p50 / p95)

- **hybrid-rerank-balance-poolcap-only**: balance_ms 0.04/0.12, dense_ms 13.01/18.98, embed_ms 8.29/24.77, fusion_ms 0.57/0.7, hydrate_ms 1.33/2.84, lexical_ms 25.12/40.63, lexical_prep_ms 1.48/2.52, rerank_ms 621.24/825.29, total_ms 679.04/922.21, wall_ms 683.07/923.87

## By category (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| category | n | hybrid-rerank-balance-poolcap-only |
|---|---|---|
| ambiguous_distractor | 4 | 1/4 · 2/4 · 0.39 |
| cross_format | 4 | 4/4 · 4/4 · 1.00 |
| customer_free_text | 5 | 5/5 · 5/5 · 1.00 |
| enumeration | 3 | 1/3 · 3/3 · 0.61 |
| exact_number | 7 | 4/7 · 5/7 · 0.64 |
| keyword_sensitive | 4 | 2/4 · 2/4 · 0.51 |
| named_entity | 3 | 3/3 · 3/3 · 1.00 |
| semantic_paraphrase | 5 | 3/5 · 4/5 · 0.64 |
| single_source_fact | 6 | 6/6 · 6/6 · 1.00 |
| versioning | 3 | 2/3 · 3/3 · 0.83 |

## By source format (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| source format | n | hybrid-rerank-balance-poolcap-only |
|---|---|---|
| csv | 7 | 5/7 · 5/7 · 0.72 |
| docx | 9 | 9/9 · 9/9 · 1.00 |
| markdown | 8 | 5/8 · 7/8 · 0.74 |
| pdf | 8 | 6/8 · 8/8 · 0.83 |
| pptx | 9 | 7/9 · 9/9 · 0.87 |
| text | 3 | 3/3 · 3/3 · 1.00 |
| xlsx | 7 | 2/7 · 3/7 · 0.36 |

## By overlap bin (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| overlap bin | n | hybrid-rerank-balance-poolcap-only |
|---|---|---|
| high | 2 | 1/2 · 1/2 · 0.50 |
| low | 13 | 53.8% · 76.9% · 0.63 |
| mid | 29 | 79.3% · 89.7% · 0.84 |

## Distractor outranking

- **hybrid-rerank-balance-poolcap-only**: distractor above the true parent in 0/6 items with a ledger distractor
