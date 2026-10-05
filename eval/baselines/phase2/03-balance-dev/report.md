# Phase 2 step 3: source/class balancing (dev)

- Split: **dev**, items: 44
- Dataset: `retrieval-v0` · corpus `d68f6473052e` · ledger `95e9bb87bae7`
- Run: git=90c3c31, at=2026-10-05T23:04:45+00:00, config_hash=ef072cbc6bfdd965

## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)

| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| hybrid-rerank | 70.5 [55.8, 81.8] | 84.1 [70.6, 92.1] | 86.4 [73.3, 93.6] | 81.1 [70.1, 90.9] | 85.6 [75.4, 94.7] | 77.0 [65.3, 87.8] | 664.9 | 976.43 |
| hybrid-rerank-balance | 70.5 [55.8, 81.8] | 81.8 [68.0, 90.5] | 84.1 [70.6, 92.1] | 79.2 [67.8, 89.4] | 80.3 [68.6, 90.5] | 76.2 [64.2, 87.2] | 729.03 | 935.12 |

## Latency by stage (ms, p50 / p95)

- **hybrid-rerank**: dense_ms 14.0/29.4, embed_ms 8.36/30.39, fusion_ms 0.58/0.67, hydrate_ms 1.37/2.14, lexical_ms 24.49/40.32, lexical_prep_ms 1.51/2.77, rerank_ms 604.75/851.96, total_ms 664.9/976.43, wall_ms 669.23/980.45
- **hybrid-rerank-balance**: balance_ms 0.04/0.25, dense_ms 14.62/26.22, embed_ms 9.13/30.79, fusion_ms 0.6/0.72, hydrate_ms 1.38/2.33, lexical_ms 24.46/39.82, lexical_prep_ms 1.52/2.41, rerank_ms 673.87/852.24, total_ms 729.03/935.12, wall_ms 735.62/939.24

## By category (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| category | n | hybrid-rerank | hybrid-rerank-balance |
|---|---|---|---|
| ambiguous_distractor | 4 | 1/4 · 3/4 · 0.46 | 1/4 · 2/4 · 0.38 |
| cross_format | 4 | 4/4 · 4/4 · 1.00 | 4/4 · 4/4 · 1.00 |
| customer_free_text | 5 | 5/5 · 5/5 · 1.00 | 5/5 · 5/5 · 1.00 |
| enumeration | 3 | 1/3 · 3/3 · 0.61 | 1/3 · 3/3 · 0.61 |
| exact_number | 7 | 4/7 · 5/7 · 0.64 | 4/7 · 5/7 · 0.64 |
| keyword_sensitive | 4 | 2/4 · 2/4 · 0.51 | 2/4 · 2/4 · 0.50 |
| named_entity | 3 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 |
| semantic_paraphrase | 5 | 3/5 · 4/5 · 0.64 | 3/5 · 4/5 · 0.63 |
| single_source_fact | 6 | 6/6 · 6/6 · 1.00 | 6/6 · 6/6 · 1.00 |
| versioning | 3 | 2/3 · 3/3 · 0.83 | 2/3 · 3/3 · 0.83 |

## By source format (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| source format | n | hybrid-rerank | hybrid-rerank-balance |
|---|---|---|---|
| csv | 7 | 5/7 · 5/7 · 0.72 | 5/7 · 5/7 · 0.72 |
| docx | 9 | 9/9 · 9/9 · 1.00 | 9/9 · 9/9 · 1.00 |
| markdown | 8 | 5/8 · 7/8 · 0.74 | 5/8 · 7/8 · 0.73 |
| pdf | 8 | 6/8 · 8/8 · 0.83 | 6/8 · 8/8 · 0.83 |
| pptx | 9 | 7/9 · 9/9 · 0.87 | 7/9 · 9/9 · 0.87 |
| text | 3 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 |
| xlsx | 7 | 2/7 · 4/7 · 0.41 | 2/7 · 3/7 · 0.36 |

## By overlap bin (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| overlap bin | n | hybrid-rerank | hybrid-rerank-balance |
|---|---|---|---|
| high | 2 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 |
| low | 13 | 53.8% · 84.6% · 0.66 | 53.8% · 76.9% · 0.63 |
| mid | 29 | 79.3% · 89.7% · 0.84 | 79.3% · 89.7% · 0.84 |

## Paired comparisons (same items)

| Comparison | hit@1 (only ref / only other, p) | hit@10 (…) | ΔMRR [95% CI] | Δrecall@10 [95% CI] |
|---|---|---|---|---|
| hybrid-rerank->hybrid-rerank-balance | 0 / 0, p=1.0 | 1 / 0, p=1.0 | -0.008 [-0.023, +0.000] | -0.019 [-0.076, +0.023] |

## Failure buckets at k=10: hybrid-rerank|hybrid-rerank-balance

### both_miss (6)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks hybrid-rerank: {'NS-140': None}; hybrid-rerank-balance: {'NS-140': None}
  - hybrid-rerank top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
  - hybrid-rerank-balance top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks hybrid-rerank: {'SP-C06': None}; hybrid-rerank-balance: {'SP-C06': None}
  - hybrid-rerank top-3: ['SOUTHPEAK/PLANNING-NOTES@v1:S1.B1', 'SOUTHPEAK/PLANNING-NOTES@v1:S1.B5', 'SOUTHPEAK/SURVEY-2026@v1:R180']
  - hybrid-rerank-balance top-3: ['SOUTHPEAK/PLANNING-NOTES@v1:S1.B1', 'SOUTHPEAK/PLANNING-NOTES@v1:S1.B5', 'SOUTHPEAK/SURVEY-2026@v1:R180']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks hybrid-rerank: {'NS-120': None}; hybrid-rerank-balance: {'NS-120': None}
  - hybrid-rerank top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
  - hybrid-rerank-balance top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks hybrid-rerank: {'NS-148': 52}; hybrid-rerank-balance: {'NS-148': 64}
  - hybrid-rerank top-3: ['NORTHSTAR/REVIEWS@v1:R401', 'NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/REVIEWS@v1:R683']
  - hybrid-rerank-balance top-3: ['NORTHSTAR/REVIEWS@v1:R401', 'NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/REVIEWS@v1:R683']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks hybrid-rerank: {'NS-102': 15}; hybrid-rerank-balance: {'NS-102': 50}
  - hybrid-rerank top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
  - hybrid-rerank-balance top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks hybrid-rerank: {'NS-120': None}; hybrid-rerank-balance: {'NS-120': None}
  - hybrid-rerank top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']
  - hybrid-rerank-balance top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']

### hybrid-rerank_only (1)

- **R0-060** (ambiguous_distractor, overlap 0.154): How large is the 2026 US athletic footwear market for Gen Z shoppers specifically, in the category sizing workbook?
  - expected ['NORTHSTAR/CATEGORY-SIZING@v1:SH1.R5'] · ranks hybrid-rerank: {'NS-129': 3}; hybrid-rerank-balance: {'NS-129': 36}
  - hybrid-rerank top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B3', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R2', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R5']
  - hybrid-rerank-balance top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B3', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R18', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R16']


## Distractor outranking

- **hybrid-rerank**: distractor above the true parent in 0/6 items with a ledger distractor
- **hybrid-rerank-balance**: distractor above the true parent in 0/6 items with a ledger distractor
