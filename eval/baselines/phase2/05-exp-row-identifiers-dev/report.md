# Phase 2 experiment: row identifiers in row children (c3-exp, separate DB), dev

- Split: **dev**, items: 44
- Dataset: `retrieval-v0` · corpus `d68f6473052e` · ledger `95e9bb87bae7`
- Run: git=a67004a, at=2026-10-05T23:13:04+00:00, config_hash=8d2cc05d34d9db03

## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)

| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| dense@c3-ids | 56.8 [42.2, 70.3] | 77.3 [63.0, 87.2] | 84.1 [70.6, 92.1] | 80.3 [68.6, 90.5] | 83.3 [72.3, 93.2] | 66.4 [54.1, 78.3] | 14.3 | 21.69 |
| lexical@c3-ids | 45.5 [31.7, 59.9] | 77.3 [63.0, 87.2] | 81.8 [68.0, 90.5] | 78.4 [66.3, 89.4] | 82.2 [70.8, 92.4] | 57.9 [45.7, 69.8] | 16.3 | 27.05 |
| hybrid@c3-ids | 59.1 [44.4, 72.3] | 79.5 [65.5, 88.8] | 86.4 [73.3, 93.6] | 83.7 [72.7, 93.2] | 87.9 [78.4, 95.8] | 69.3 [57.2, 80.6] | 28.81 | 43.98 |
| dense-rerank@c3-ids | 70.5 [55.8, 81.8] | 84.1 [70.6, 92.1] | 86.4 [73.3, 93.6] | 82.2 [70.8, 92.0] | 83.3 [72.3, 93.2] | 76.9 [65.2, 87.7] | 580.38 | 848.76 |
| hybrid-rerank@c3-ids | 70.5 [55.8, 81.8] | 86.4 [73.3, 93.6] | 88.6 [76.0, 95.0] | 83.3 [73.1, 92.4] | 87.9 [78.4, 95.8] | 77.4 [66.1, 87.9] | 676.57 | 978.37 |

## Latency by stage (ms, p50 / p95)

- **dense@c3-ids**: dense_ms 5.54/11.48, embed_ms 6.43/10.89, fusion_ms 0.3/0.82, total_ms 14.3/21.69, wall_ms 14.79/22.22
- **lexical@c3-ids**: fusion_ms 0.33/1.0, lexical_ms 13.14/23.41, lexical_prep_ms 0.64/0.97, total_ms 16.3/27.05, wall_ms 16.76/27.73
- **hybrid@c3-ids**: dense_ms 5.19/7.33, embed_ms 5.66/9.8, fusion_ms 0.53/0.62, lexical_ms 14.59/23.14, lexical_prep_ms 0.78/1.66, total_ms 28.81/43.98, wall_ms 29.32/44.43
- **dense-rerank@c3-ids**: dense_ms 17.33/26.66, embed_ms 8.14/29.52, fusion_ms 0.31/0.38, hydrate_ms 1.93/4.42, rerank_ms 539.39/799.85, total_ms 580.38/848.76, wall_ms 583.5/852.88
- **hybrid-rerank@c3-ids**: dense_ms 14.08/24.13, embed_ms 8.8/35.6, fusion_ms 0.58/0.73, hydrate_ms 1.4/2.96, lexical_ms 27.92/40.42, lexical_prep_ms 1.6/3.83, rerank_ms 610.29/901.98, total_ms 676.57/978.37, wall_ms 678.54/981.14

## By category (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| category | n | dense@c3-ids | lexical@c3-ids | hybrid@c3-ids | dense-rerank@c3-ids | hybrid-rerank@c3-ids |
|---|---|---|---|---|---|---|
| ambiguous_distractor | 4 | 2/4 · 3/4 · 0.53 | 0/4 · 3/4 · 0.33 | 2/4 · 3/4 · 0.62 | 1/4 · 3/4 · 0.46 | 1/4 · 3/4 · 0.46 |
| cross_format | 4 | 4/4 · 4/4 · 1.00 | 2/4 · 4/4 · 0.68 | 3/4 · 4/4 · 0.88 | 4/4 · 4/4 · 1.00 | 4/4 · 4/4 · 1.00 |
| customer_free_text | 5 | 3/5 · 5/5 · 0.73 | 3/5 · 5/5 · 0.73 | 3/5 · 5/5 · 0.80 | 5/5 · 5/5 · 1.00 | 5/5 · 5/5 · 1.00 |
| enumeration | 3 | 0/3 · 3/3 · 0.32 | 0/3 · 2/3 · 0.26 | 0/3 · 2/3 · 0.25 | 1/3 · 3/3 · 0.61 | 1/3 · 3/3 · 0.61 |
| exact_number | 7 | 5/7 · 5/7 · 0.71 | 5/7 · 5/7 · 0.71 | 5/7 · 5/7 · 0.71 | 4/7 · 5/7 · 0.64 | 4/7 · 5/7 · 0.64 |
| keyword_sensitive | 4 | 0/4 · 2/4 · 0.13 | 2/4 · 3/4 · 0.62 | 2/4 · 3/4 · 0.53 | 2/4 · 2/4 · 0.50 | 2/4 · 3/4 · 0.55 |
| named_entity | 3 | 2/3 · 3/3 · 0.83 | 2/3 · 3/3 · 0.83 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 |
| semantic_paraphrase | 5 | 2/5 · 3/5 · 0.49 | 0/5 · 2/5 · 0.07 | 1/5 · 4/5 · 0.35 | 3/5 · 4/5 · 0.63 | 3/5 · 4/5 · 0.64 |
| single_source_fact | 6 | 4/6 · 6/6 · 0.83 | 5/6 · 6/6 · 0.87 | 6/6 · 6/6 · 1.00 | 6/6 · 6/6 · 1.00 | 6/6 · 6/6 · 1.00 |
| versioning | 3 | 3/3 · 3/3 · 1.00 | 1/3 · 3/3 · 0.48 | 1/3 · 3/3 · 0.61 | 2/3 · 3/3 · 0.83 | 2/3 · 3/3 · 0.83 |

## By source format (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| source format | n | dense@c3-ids | lexical@c3-ids | hybrid@c3-ids | dense-rerank@c3-ids | hybrid-rerank@c3-ids |
|---|---|---|---|---|---|---|
| csv | 7 | 1/7 · 5/7 · 0.26 | 3/7 · 5/7 · 0.55 | 3/7 · 5/7 · 0.53 | 5/7 · 5/7 · 0.71 | 5/7 · 6/7 · 0.74 |
| docx | 9 | 6/9 · 9/9 · 0.77 | 4/9 · 8/9 · 0.58 | 6/9 · 8/9 · 0.79 | 9/9 · 9/9 · 1.00 | 9/9 · 9/9 · 1.00 |
| markdown | 8 | 5/8 · 7/8 · 0.73 | 3/8 · 7/8 · 0.56 | 4/8 · 7/8 · 0.65 | 5/8 · 7/8 · 0.73 | 5/8 · 7/8 · 0.74 |
| pdf | 8 | 7/8 · 7/8 · 0.89 | 3/8 · 6/8 · 0.50 | 4/8 · 8/8 · 0.63 | 6/8 · 8/8 · 0.83 | 6/8 · 8/8 · 0.83 |
| pptx | 9 | 5/9 · 9/9 · 0.78 | 6/9 · 9/9 · 0.77 | 8/9 · 9/9 · 0.93 | 7/9 · 9/9 · 0.87 | 7/9 · 9/9 · 0.87 |
| text | 3 | 3/3 · 3/3 · 1.00 | 2/3 · 3/3 · 0.71 | 2/3 · 3/3 · 0.83 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 |
| xlsx | 7 | 3/7 · 4/7 · 0.44 | 2/7 · 4/7 · 0.41 | 3/7 · 4/7 · 0.50 | 2/7 · 4/7 · 0.41 | 2/7 · 4/7 · 0.41 |

## By overlap bin (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| overlap bin | n | dense@c3-ids | lexical@c3-ids | hybrid@c3-ids | dense-rerank@c3-ids | hybrid-rerank@c3-ids |
|---|---|---|---|---|---|---|
| high | 2 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 |
| low | 13 | 23.1% · 76.9% · 0.42 | 15.4% · 61.5% · 0.30 | 38.5% · 76.9% · 0.52 | 53.8% · 84.6% · 0.65 | 53.8% · 84.6% · 0.66 |
| mid | 29 | 72.4% · 89.7% · 0.78 | 58.6% · 93.1% · 0.71 | 69.0% · 93.1% · 0.79 | 79.3% · 89.7% · 0.84 | 79.3% · 93.1% · 0.85 |

## Paired comparisons (same items)

| Comparison | hit@1 (only ref / only other, p) | hit@10 (…) | ΔMRR [95% CI] | Δrecall@10 [95% CI] |
|---|---|---|---|---|
| dense-rerank@c3-ids->dense@c3-ids | 9 / 3, p=0.146 | 1 / 0, p=1.0 | -0.105 [-0.201, -0.016] | -0.019 [-0.076, +0.027] |
| dense-rerank@c3-ids->lexical@c3-ids | 12 / 1, p=0.0034 | 3 / 1, p=0.625 | -0.190 [-0.302, -0.085] | -0.038 [-0.129, +0.045] |
| dense-rerank@c3-ids->hybrid@c3-ids | 7 / 2, p=0.1797 | 1 / 1, p=1.0 | -0.076 [-0.159, -0.001] | +0.015 [-0.034, +0.080] |
| dense-rerank@c3-ids->hybrid-rerank@c3-ids | 0 / 0, p=1.0 | 0 / 1, p=1.0 | +0.005 [+0.000, +0.015] | +0.011 [-0.034, +0.068] |

## Failure buckets at k=10: dense-rerank@c3-ids|dense@c3-ids

### both_miss (6)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense-rerank@c3-ids: {'NS-140': None}; dense@c3-ids: {'NS-140': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
  - dense@c3-ids top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B5']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense-rerank@c3-ids: {'SP-C06': None}; dense@c3-ids: {'SP-C06': None}
  - dense-rerank@c3-ids top-3: ['SOUTHPEAK/SURVEY-2026@v1:R75', 'SOUTHPEAK/SURVEY-2026@v1:R234', 'SOUTHPEAK/SURVEY-2026@v1:R5']
  - dense@c3-ids top-3: ['SOUTHPEAK/SURVEY-2026@v1:R211', 'SOUTHPEAK/SURVEY-2026@v1:R167', 'SOUTHPEAK/SURVEY-2026@v1:R5']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense-rerank@c3-ids: {'NS-120': None}; dense@c3-ids: {'NS-120': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
  - dense@c3-ids top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B12']
- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense-rerank@c3-ids: {'NS-148': None}; dense@c3-ids: {'NS-148': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/REVIEWS@v1:R426', 'NORTHSTAR/REVIEWS@v1:R293', 'NORTHSTAR/REVIEWS@v1:R482']
  - dense@c3-ids top-3: ['NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/REVIEWS@v1:R401', 'NORTHSTAR/REVIEWS@v1:R683']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense-rerank@c3-ids: {'NS-102': 24}; dense@c3-ids: {'NS-102': 24}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
  - dense@c3-ids top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/PACE-DECK@v1:SL2', 'NORTHSTAR/Q3-REVIEW@v1:SL15']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense-rerank@c3-ids: {'NS-120': None}; dense@c3-ids: {'NS-120': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']
  - dense@c3-ids top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/REVIEWS@v1:R360']

### dense-rerank@c3-ids_only (1)

- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks dense-rerank@c3-ids: {'NS-005': 8}; dense@c3-ids: {'NS-005': 12}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P2.B2']
  - dense@c3-ids top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P4.B1']


## Failure buckets at k=10: dense-rerank@c3-ids|lexical@c3-ids

### both_miss (5)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense-rerank@c3-ids: {'NS-140': None}; lexical@c3-ids: {'NS-140': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
  - lexical@c3-ids top-3: ['NORTHSTAR/CHANNEL-PERF@v1:T1', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense-rerank@c3-ids: {'SP-C06': None}; lexical@c3-ids: {'SP-C06': None}
  - dense-rerank@c3-ids top-3: ['SOUTHPEAK/SURVEY-2026@v1:R75', 'SOUTHPEAK/SURVEY-2026@v1:R234', 'SOUTHPEAK/SURVEY-2026@v1:R5']
  - lexical@c3-ids top-3: ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.T1', 'SOUTHPEAK/PLANNING-NOTES@v1:S1.B5', 'SOUTHPEAK/INTERVIEWS@v1:S1.B1']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense-rerank@c3-ids: {'NS-120': None}; lexical@c3-ids: {'NS-120': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
  - lexical@c3-ids top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense-rerank@c3-ids: {'NS-102': 24}; lexical@c3-ids: {'NS-102': 28}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
  - lexical@c3-ids top-3: ['NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense-rerank@c3-ids: {'NS-120': None}; lexical@c3-ids: {'NS-120': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']
  - lexical@c3-ids top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/KINETIC-AR@v1:P4.B1', 'NORTHSTAR/PRODUCT-PERF@v1:SH2.T1']

### lexical@c3-ids_only (1)

- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense-rerank@c3-ids: {'NS-148': None}; lexical@c3-ids: {'NS-148': 2}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/REVIEWS@v1:R426', 'NORTHSTAR/REVIEWS@v1:R293', 'NORTHSTAR/REVIEWS@v1:R482']
  - lexical@c3-ids top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B10', 'NORTHSTAR/REVIEWS@v1:R656', 'NORTHSTAR/WTP-STUDY@v1:P4.B2']

### dense-rerank@c3-ids_only (3)

- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks dense-rerank@c3-ids: {'NS-005': 8}; lexical@c3-ids: {'NS-005': 17}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P2.B2']
  - lexical@c3-ids top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P2.B2']
- **R0-042** (semantic_paraphrase, overlap 0.0): What portion of young shoppers put more faith in fellow buyers' opinions and influencer demos than in what companies say in their ads?
  - expected ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1'] · ranks dense-rerank@c3-ids: {'NS-040': 1}; lexical@c3-ids: {'NS-040': 82}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/PACE-DECK@v1:SL4.N1']
  - lexical@c3-ids top-3: ['NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S2.B1', 'NORTHSTAR/GENZ-TRENDS@v2:P3.B2']
- **R0-055** (enumeration, overlap 0.286): Which individual customers (interviewees or survey respondents) want brands to disclose where their shoes are made or how much recycled material goes into them?
  - expected ['NORTHSTAR/INTERVIEWS@v1:S11.Q1', 'NORTHSTAR/SURVEY-2026@v1:R63'] · ranks dense-rerank@c3-ids: {'NS-063': 1, 'NS-146': None}; lexical@c3-ids: {'NS-063': 23, 'NS-146': 82}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/INTERVIEWS@v1:S11.Q1', 'NORTHSTAR/SURVEY-2026@v1:R437', 'NORTHSTAR/SURVEY-2026@v1:R66']
  - lexical@c3-ids top-3: ['NORTHSTAR/SURVEY-2026@v1:R66', 'NORTHSTAR/SURVEY-2026@v1:R437', 'NORTHSTAR/SURVEY-2026@v1:R105']


## Failure buckets at k=10: dense-rerank@c3-ids|hybrid@c3-ids

### both_miss (5)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense-rerank@c3-ids: {'NS-140': None}; hybrid@c3-ids: {'NS-140': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
  - hybrid@c3-ids top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P1.B2']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense-rerank@c3-ids: {'SP-C06': None}; hybrid@c3-ids: {'SP-C06': None}
  - dense-rerank@c3-ids top-3: ['SOUTHPEAK/SURVEY-2026@v1:R75', 'SOUTHPEAK/SURVEY-2026@v1:R234', 'SOUTHPEAK/SURVEY-2026@v1:R5']
  - hybrid@c3-ids top-3: ['SOUTHPEAK/SURVEY-2026@v1:R300', 'SOUTHPEAK/SURVEY-2026@v1:R171', 'SOUTHPEAK/SURVEY-2026@v1:R236']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense-rerank@c3-ids: {'NS-120': None}; hybrid@c3-ids: {'NS-120': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
  - hybrid@c3-ids top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/PRODUCT-PERF@v1:SH2.T1']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense-rerank@c3-ids: {'NS-102': 24}; hybrid@c3-ids: {'NS-102': 16}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
  - hybrid@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense-rerank@c3-ids: {'NS-120': None}; hybrid@c3-ids: {'NS-120': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']
  - hybrid@c3-ids top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/REVIEWS@v1:R360']

### hybrid@c3-ids_only (1)

- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense-rerank@c3-ids: {'NS-148': None}; hybrid@c3-ids: {'NS-148': 8}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/REVIEWS@v1:R426', 'NORTHSTAR/REVIEWS@v1:R293', 'NORTHSTAR/REVIEWS@v1:R482']
  - hybrid@c3-ids top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/REVIEWS@v1:R293', 'NORTHSTAR/REVIEWS@v1:R607']

### dense-rerank@c3-ids_only (1)

- **R0-055** (enumeration, overlap 0.286): Which individual customers (interviewees or survey respondents) want brands to disclose where their shoes are made or how much recycled material goes into them?
  - expected ['NORTHSTAR/INTERVIEWS@v1:S11.Q1', 'NORTHSTAR/SURVEY-2026@v1:R63'] · ranks dense-rerank@c3-ids: {'NS-063': 1, 'NS-146': None}; hybrid@c3-ids: {'NS-063': 11, 'NS-146': 121}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/INTERVIEWS@v1:S11.Q1', 'NORTHSTAR/SURVEY-2026@v1:R437', 'NORTHSTAR/SURVEY-2026@v1:R66']
  - hybrid@c3-ids top-3: ['NORTHSTAR/SURVEY-2026@v1:R437', 'NORTHSTAR/SURVEY-2026@v1:R207', 'NORTHSTAR/SURVEY-2026@v1:R105']


## Failure buckets at k=10: dense-rerank@c3-ids|hybrid-rerank@c3-ids

### both_miss (5)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense-rerank@c3-ids: {'NS-140': None}; hybrid-rerank@c3-ids: {'NS-140': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
  - hybrid-rerank@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense-rerank@c3-ids: {'SP-C06': None}; hybrid-rerank@c3-ids: {'SP-C06': None}
  - dense-rerank@c3-ids top-3: ['SOUTHPEAK/SURVEY-2026@v1:R75', 'SOUTHPEAK/SURVEY-2026@v1:R234', 'SOUTHPEAK/SURVEY-2026@v1:R5']
  - hybrid-rerank@c3-ids top-3: ['SOUTHPEAK/PLANNING-NOTES@v1:S1.B1', 'SOUTHPEAK/PLANNING-NOTES@v1:S1.B5', 'SOUTHPEAK/SURVEY-2026@v1:R234']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense-rerank@c3-ids: {'NS-120': None}; hybrid-rerank@c3-ids: {'NS-120': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
  - hybrid-rerank@c3-ids top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense-rerank@c3-ids: {'NS-102': 24}; hybrid-rerank@c3-ids: {'NS-102': 15}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
  - hybrid-rerank@c3-ids top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense-rerank@c3-ids: {'NS-120': None}; hybrid-rerank@c3-ids: {'NS-120': None}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']
  - hybrid-rerank@c3-ids top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']

### hybrid-rerank@c3-ids_only (1)

- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense-rerank@c3-ids: {'NS-148': None}; hybrid-rerank@c3-ids: {'NS-148': 5}
  - dense-rerank@c3-ids top-3: ['NORTHSTAR/REVIEWS@v1:R426', 'NORTHSTAR/REVIEWS@v1:R293', 'NORTHSTAR/REVIEWS@v1:R482']
  - hybrid-rerank@c3-ids top-3: ['NORTHSTAR/REVIEWS@v1:R426', 'NORTHSTAR/REVIEWS@v1:R186', 'NORTHSTAR/REVIEWS@v1:R293']


## Distractor outranking

- **dense@c3-ids**: distractor above the true parent in 0/6 items with a ledger distractor
- **lexical@c3-ids**: distractor above the true parent in 0/6 items with a ledger distractor
- **hybrid@c3-ids**: distractor above the true parent in 0/6 items with a ledger distractor
- **dense-rerank@c3-ids**: distractor above the true parent in 0/6 items with a ledger distractor
- **hybrid-rerank@c3-ids**: distractor above the true parent in 0/6 items with a ledger distractor
