# Phase 2 final configuration (c3, hybrid + rerank, no balancing, no instruction), dev

- Split: **dev**, items: 44
- Dataset: `retrieval-v0` · corpus `d68f6473052e` · ledger `95e9bb87bae7`
- Run: git=65f8667, at=2026-10-05T23:21:02+00:00, config_hash=41dd3956306c46f9

## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)

| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| dense | 56.8 [42.2, 70.3] | 77.3 [63.0, 87.2] | 84.1 [70.6, 92.1] | 80.3 [68.6, 90.5] | 83.3 [72.3, 93.2] | 66.4 [54.1, 78.3] | 13.14 | 20.01 |
| lexical | 45.5 [31.7, 59.9] | 77.3 [63.0, 87.2] | 81.8 [68.0, 90.5] | 78.4 [66.3, 89.4] | 82.2 [70.8, 92.4] | 57.9 [45.7, 69.8] | 16.16 | 28.52 |
| hybrid | 59.1 [44.4, 72.3] | 79.5 [65.5, 88.8] | 86.4 [73.3, 93.6] | 83.7 [72.7, 93.2] | 87.9 [78.4, 95.8] | 69.3 [57.2, 80.6] | 28.05 | 42.95 |
| dense-rerank | 70.5 [55.8, 81.8] | 84.1 [70.6, 92.1] | 86.4 [73.3, 93.6] | 82.2 [70.8, 92.0] | 83.3 [72.3, 93.2] | 76.9 [65.2, 87.7] | 598.12 | 740.35 |
| hybrid-rerank | 70.5 [55.8, 81.8] | 86.4 [73.3, 93.6] | 88.6 [76.0, 95.0] | 83.3 [73.1, 92.4] | 87.9 [78.4, 95.8] | 77.4 [66.1, 87.9] | 668.67 | 929.49 |

## Latency by stage (ms, p50 / p95)

- **dense**: dense_ms 4.27/9.92, embed_ms 5.94/9.13, fusion_ms 0.3/0.45, total_ms 13.14/20.01, wall_ms 13.62/20.65
- **lexical**: fusion_ms 0.38/1.11, lexical_ms 13.75/24.5, lexical_prep_ms 0.64/1.91, total_ms 16.16/28.52, wall_ms 16.54/29.28
- **hybrid**: dense_ms 3.93/6.39, embed_ms 5.88/9.06, fusion_ms 0.52/0.66, lexical_ms 14.89/24.57, lexical_prep_ms 0.68/1.58, total_ms 28.05/42.95, wall_ms 28.47/43.38
- **dense-rerank**: dense_ms 13.64/23.01, embed_ms 8.2/31.41, fusion_ms 0.3/0.39, hydrate_ms 2.14/2.87, rerank_ms 555.88/691.67, total_ms 598.12/740.35, wall_ms 600.08/742.62
- **hybrid-rerank**: dense_ms 13.31/28.19, embed_ms 8.87/35.33, fusion_ms 0.59/0.69, hydrate_ms 1.34/1.76, lexical_ms 29.91/45.69, lexical_prep_ms 1.6/2.35, rerank_ms 596.81/854.63, total_ms 668.67/929.49, wall_ms 670.73/931.76

## By category (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| category | n | dense | lexical | hybrid | dense-rerank | hybrid-rerank |
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

| source format | n | dense | lexical | hybrid | dense-rerank | hybrid-rerank |
|---|---|---|---|---|---|---|
| csv | 7 | 1/7 · 5/7 · 0.26 | 3/7 · 5/7 · 0.55 | 3/7 · 5/7 · 0.53 | 5/7 · 5/7 · 0.71 | 5/7 · 6/7 · 0.74 |
| docx | 9 | 6/9 · 9/9 · 0.77 | 4/9 · 8/9 · 0.58 | 6/9 · 8/9 · 0.79 | 9/9 · 9/9 · 1.00 | 9/9 · 9/9 · 1.00 |
| markdown | 8 | 5/8 · 7/8 · 0.73 | 3/8 · 7/8 · 0.56 | 4/8 · 7/8 · 0.65 | 5/8 · 7/8 · 0.73 | 5/8 · 7/8 · 0.74 |
| pdf | 8 | 7/8 · 7/8 · 0.89 | 3/8 · 6/8 · 0.50 | 4/8 · 8/8 · 0.63 | 6/8 · 8/8 · 0.83 | 6/8 · 8/8 · 0.83 |
| pptx | 9 | 5/9 · 9/9 · 0.78 | 6/9 · 9/9 · 0.77 | 8/9 · 9/9 · 0.93 | 7/9 · 9/9 · 0.87 | 7/9 · 9/9 · 0.87 |
| text | 3 | 3/3 · 3/3 · 1.00 | 2/3 · 3/3 · 0.71 | 2/3 · 3/3 · 0.83 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 |
| xlsx | 7 | 3/7 · 4/7 · 0.44 | 2/7 · 4/7 · 0.41 | 3/7 · 4/7 · 0.50 | 2/7 · 4/7 · 0.41 | 2/7 · 4/7 · 0.41 |

## By overlap bin (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| overlap bin | n | dense | lexical | hybrid | dense-rerank | hybrid-rerank |
|---|---|---|---|---|---|---|
| high | 2 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 |
| low | 13 | 23.1% · 76.9% · 0.42 | 15.4% · 61.5% · 0.30 | 38.5% · 76.9% · 0.52 | 53.8% · 84.6% · 0.65 | 53.8% · 84.6% · 0.66 |
| mid | 29 | 72.4% · 89.7% · 0.78 | 58.6% · 93.1% · 0.71 | 69.0% · 93.1% · 0.79 | 79.3% · 89.7% · 0.84 | 79.3% · 93.1% · 0.85 |

## Paired comparisons (same items)

| Comparison | hit@1 (only ref / only other, p) | hit@10 (…) | ΔMRR [95% CI] | Δrecall@10 [95% CI] |
|---|---|---|---|---|
| dense->lexical | 10 / 5, p=0.3018 | 2 / 1, p=1.0 | -0.084 [-0.202, +0.033] | -0.019 [-0.091, +0.049] |
| dense->hybrid | 6 / 7, p=1.0 | 1 / 2, p=1.0 | +0.029 [-0.073, +0.130] | +0.034 [-0.023, +0.114] |
| dense->dense-rerank | 3 / 9, p=0.146 | 0 / 1, p=1.0 | +0.105 [+0.016, +0.201] | +0.019 [-0.027, +0.076] |
| dense->hybrid-rerank | 3 / 9, p=0.146 | 0 / 2, p=0.5 | +0.110 [+0.021, +0.207] | +0.030 [-0.034, +0.110] |

## Failure buckets at k=10: dense|lexical

### both_miss (6)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense: {'NS-140': None}; lexical: {'NS-140': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B5']
  - lexical top-3: ['NORTHSTAR/CHANNEL-PERF@v1:T1', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense: {'SP-C06': None}; lexical: {'SP-C06': None}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R211', 'SOUTHPEAK/SURVEY-2026@v1:R167', 'SOUTHPEAK/SURVEY-2026@v1:R5']
  - lexical top-3: ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.T1', 'SOUTHPEAK/PLANNING-NOTES@v1:S1.B5', 'SOUTHPEAK/INTERVIEWS@v1:S1.B1']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; lexical: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B12']
  - lexical top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks dense: {'NS-005': 12}; lexical: {'NS-005': 17}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P4.B1']
  - lexical top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P2.B2']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense: {'NS-102': 24}; lexical: {'NS-102': 28}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/PACE-DECK@v1:SL2', 'NORTHSTAR/Q3-REVIEW@v1:SL15']
  - lexical top-3: ['NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; lexical: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/REVIEWS@v1:R360']
  - lexical top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/KINETIC-AR@v1:P4.B1', 'NORTHSTAR/PRODUCT-PERF@v1:SH2.T1']

### lexical_only (1)

- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense: {'NS-148': None}; lexical: {'NS-148': 2}
  - dense top-3: ['NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/REVIEWS@v1:R401', 'NORTHSTAR/REVIEWS@v1:R683']
  - lexical top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B10', 'NORTHSTAR/REVIEWS@v1:R656', 'NORTHSTAR/WTP-STUDY@v1:P4.B2']

### dense_only (2)

- **R0-042** (semantic_paraphrase, overlap 0.0): What portion of young shoppers put more faith in fellow buyers' opinions and influencer demos than in what companies say in their ads?
  - expected ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1'] · ranks dense: {'NS-040': 1}; lexical: {'NS-040': 82}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1', 'NORTHSTAR/PACE-DECK@v1:SL4.N1', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B7']
  - lexical top-3: ['NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S2.B1', 'NORTHSTAR/GENZ-TRENDS@v2:P3.B2']
- **R0-055** (enumeration, overlap 0.286): Which individual customers (interviewees or survey respondents) want brands to disclose where their shoes are made or how much recycled material goes into them?
  - expected ['NORTHSTAR/INTERVIEWS@v1:S11.Q1', 'NORTHSTAR/SURVEY-2026@v1:R63'] · ranks dense: {'NS-063': 8, 'NS-146': None}; lexical: {'NS-063': 23, 'NS-146': 81}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R478', 'NORTHSTAR/SURVEY-2026@v1:R437', 'NORTHSTAR/SURVEY-2026@v1:R207']
  - lexical top-3: ['NORTHSTAR/SURVEY-2026@v1:R66', 'NORTHSTAR/SURVEY-2026@v1:R437', 'NORTHSTAR/SURVEY-2026@v1:R105']


## Failure buckets at k=10: dense|hybrid

### both_miss (5)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense: {'NS-140': None}; hybrid: {'NS-140': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B5']
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P1.B2']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense: {'SP-C06': None}; hybrid: {'SP-C06': None}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R211', 'SOUTHPEAK/SURVEY-2026@v1:R167', 'SOUTHPEAK/SURVEY-2026@v1:R5']
  - hybrid top-3: ['SOUTHPEAK/SURVEY-2026@v1:R180', 'SOUTHPEAK/SURVEY-2026@v1:R159', 'SOUTHPEAK/SURVEY-2026@v1:R171']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; hybrid: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B12']
  - hybrid top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/PRODUCT-PERF@v1:SH2.T1']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense: {'NS-102': 24}; hybrid: {'NS-102': 16}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/PACE-DECK@v1:SL2', 'NORTHSTAR/Q3-REVIEW@v1:SL15']
  - hybrid top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; hybrid: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/REVIEWS@v1:R360']
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/REVIEWS@v1:R360']

### hybrid_only (2)

- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense: {'NS-148': None}; hybrid: {'NS-148': 8}
  - dense top-3: ['NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/REVIEWS@v1:R401', 'NORTHSTAR/REVIEWS@v1:R683']
  - hybrid top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/REVIEWS@v1:R293', 'NORTHSTAR/REVIEWS@v1:R186']
- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks dense: {'NS-005': 12}; hybrid: {'NS-005': 9}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P4.B1']
  - hybrid top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/GENZ-TRENDS@v2:P3.B3']

### dense_only (1)

- **R0-055** (enumeration, overlap 0.286): Which individual customers (interviewees or survey respondents) want brands to disclose where their shoes are made or how much recycled material goes into them?
  - expected ['NORTHSTAR/INTERVIEWS@v1:S11.Q1', 'NORTHSTAR/SURVEY-2026@v1:R63'] · ranks dense: {'NS-063': 8, 'NS-146': None}; hybrid: {'NS-063': 11, 'NS-146': 119}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R478', 'NORTHSTAR/SURVEY-2026@v1:R437', 'NORTHSTAR/SURVEY-2026@v1:R207']
  - hybrid top-3: ['NORTHSTAR/SURVEY-2026@v1:R437', 'NORTHSTAR/SURVEY-2026@v1:R207', 'NORTHSTAR/SURVEY-2026@v1:R105']


## Failure buckets at k=10: dense|dense-rerank

### both_miss (6)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense: {'NS-140': None}; dense-rerank: {'NS-140': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B5']
  - dense-rerank top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense: {'SP-C06': None}; dense-rerank: {'SP-C06': None}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R211', 'SOUTHPEAK/SURVEY-2026@v1:R167', 'SOUTHPEAK/SURVEY-2026@v1:R5']
  - dense-rerank top-3: ['SOUTHPEAK/SURVEY-2026@v1:R75', 'SOUTHPEAK/SURVEY-2026@v1:R234', 'SOUTHPEAK/SURVEY-2026@v1:R5']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; dense-rerank: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B12']
  - dense-rerank top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense: {'NS-148': None}; dense-rerank: {'NS-148': None}
  - dense top-3: ['NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/REVIEWS@v1:R401', 'NORTHSTAR/REVIEWS@v1:R683']
  - dense-rerank top-3: ['NORTHSTAR/REVIEWS@v1:R426', 'NORTHSTAR/REVIEWS@v1:R293', 'NORTHSTAR/REVIEWS@v1:R482']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense: {'NS-102': 24}; dense-rerank: {'NS-102': 24}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/PACE-DECK@v1:SL2', 'NORTHSTAR/Q3-REVIEW@v1:SL15']
  - dense-rerank top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; dense-rerank: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/REVIEWS@v1:R360']
  - dense-rerank top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']

### dense-rerank_only (1)

- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks dense: {'NS-005': 12}; dense-rerank: {'NS-005': 8}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P4.B1']
  - dense-rerank top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P2.B2']


## Failure buckets at k=10: dense|hybrid-rerank

### both_miss (5)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense: {'NS-140': None}; hybrid-rerank: {'NS-140': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B5']
  - hybrid-rerank top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense: {'SP-C06': None}; hybrid-rerank: {'SP-C06': None}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R211', 'SOUTHPEAK/SURVEY-2026@v1:R167', 'SOUTHPEAK/SURVEY-2026@v1:R5']
  - hybrid-rerank top-3: ['SOUTHPEAK/PLANNING-NOTES@v1:S1.B1', 'SOUTHPEAK/PLANNING-NOTES@v1:S1.B5', 'SOUTHPEAK/SURVEY-2026@v1:R234']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; hybrid-rerank: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B12']
  - hybrid-rerank top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense: {'NS-102': 24}; hybrid-rerank: {'NS-102': 15}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/PACE-DECK@v1:SL2', 'NORTHSTAR/Q3-REVIEW@v1:SL15']
  - hybrid-rerank top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; hybrid-rerank: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/REVIEWS@v1:R360']
  - hybrid-rerank top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']

### hybrid-rerank_only (2)

- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense: {'NS-148': None}; hybrid-rerank: {'NS-148': 5}
  - dense top-3: ['NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/REVIEWS@v1:R401', 'NORTHSTAR/REVIEWS@v1:R683']
  - hybrid-rerank top-3: ['NORTHSTAR/REVIEWS@v1:R426', 'NORTHSTAR/REVIEWS@v1:R186', 'NORTHSTAR/REVIEWS@v1:R293']
- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks dense: {'NS-005': 12}; hybrid-rerank: {'NS-005': 8}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P4.B1']
  - hybrid-rerank top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P2.B2']


## Distractor outranking

- **dense**: distractor above the true parent in 0/6 items with a ledger distractor
- **lexical**: distractor above the true parent in 0/6 items with a ledger distractor
- **hybrid**: distractor above the true parent in 0/6 items with a ledger distractor
- **dense-rerank**: distractor above the true parent in 0/6 items with a ledger distractor
- **hybrid-rerank**: distractor above the true parent in 0/6 items with a ledger distractor
