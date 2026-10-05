# Phase 2 step 2: cross-encoder reranking (dev)

- Split: **dev**, items: 44
- Dataset: `retrieval-v0` · corpus `d68f6473052e` · ledger `95e9bb87bae7`
- Run: git=dca59f5, at=2026-10-05T22:59:44+00:00, config_hash=4a216acbda29d503

## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)

| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| dense | 56.8 [42.2, 70.3] | 75.0 [60.6, 85.4] | 81.8 [68.0, 90.5] | 78.0 [65.9, 89.0] | 83.3 [72.3, 93.2] | 66.2 [53.9, 78.1] | 16.37 | 21.13 |
| hybrid | 54.5 [40.1, 68.3] | 75.0 [60.6, 85.4] | 84.1 [70.6, 92.1] | 80.3 [68.6, 90.5] | 85.6 [75.4, 94.7] | 64.7 [52.4, 76.7] | 25.27 | 43.49 |
| dense-rerank | 70.5 [55.8, 81.8] | 84.1 [70.6, 92.1] | 86.4 [73.3, 93.6] | 82.2 [70.8, 92.0] | 83.3 [72.3, 93.2] | 76.9 [65.2, 87.7] | 601.57 | 833.92 |
| hybrid-rerank | 70.5 [55.8, 81.8] | 84.1 [70.6, 92.1] | 86.4 [73.3, 93.6] | 81.1 [70.1, 90.9] | 85.6 [75.4, 94.7] | 77.0 [65.3, 87.8] | 705.07 | 987.57 |

## Latency by stage (ms, p50 / p95)

- **dense**: dense_ms 7.12/9.54, embed_ms 6.34/10.51, fusion_ms 0.3/0.81, total_ms 16.37/21.13, wall_ms 16.87/21.93
- **hybrid**: dense_ms 3.92/5.56, embed_ms 5.71/8.92, fusion_ms 0.54/0.63, lexical_ms 12.09/28.06, lexical_prep_ms 0.77/1.65, total_ms 25.27/43.49, wall_ms 25.71/44.02
- **dense-rerank**: dense_ms 13.75/23.25, embed_ms 8.32/29.69, fusion_ms 0.3/0.34, hydrate_ms 2.19/3.33, rerank_ms 565.83/800.8, total_ms 601.57/833.92, wall_ms 603.95/844.45
- **hybrid-rerank**: dense_ms 14.29/26.37, embed_ms 9.79/33.98, fusion_ms 0.59/0.7, hydrate_ms 1.34/2.48, lexical_ms 27.46/39.69, lexical_prep_ms 1.65/2.85, rerank_ms 642.0/890.46, total_ms 705.07/987.57, wall_ms 706.69/993.76

## By category (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| category | n | dense | hybrid | dense-rerank | hybrid-rerank |
|---|---|---|---|---|---|
| ambiguous_distractor | 4 | 2/4 · 2/4 · 0.52 | 2/4 · 3/4 · 0.53 | 1/4 · 3/4 · 0.46 | 1/4 · 3/4 · 0.46 |
| cross_format | 4 | 4/4 · 4/4 · 1.00 | 3/4 · 4/4 · 0.88 | 4/4 · 4/4 · 1.00 | 4/4 · 4/4 · 1.00 |
| customer_free_text | 5 | 3/5 · 5/5 · 0.72 | 3/5 · 5/5 · 0.77 | 5/5 · 5/5 · 1.00 | 5/5 · 5/5 · 1.00 |
| enumeration | 3 | 0/3 · 3/3 · 0.39 | 0/3 · 3/3 · 0.26 | 1/3 · 3/3 · 0.61 | 1/3 · 3/3 · 0.61 |
| exact_number | 7 | 5/7 · 5/7 · 0.71 | 5/7 · 5/7 · 0.71 | 4/7 · 5/7 · 0.64 | 4/7 · 5/7 · 0.64 |
| keyword_sensitive | 4 | 0/4 · 2/4 · 0.08 | 0/4 · 2/4 · 0.17 | 2/4 · 2/4 · 0.50 | 2/4 · 2/4 · 0.51 |
| named_entity | 3 | 2/3 · 3/3 · 0.83 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 |
| semantic_paraphrase | 5 | 2/5 · 3/5 · 0.49 | 1/5 · 3/5 · 0.35 | 3/5 · 4/5 · 0.63 | 3/5 · 4/5 · 0.64 |
| single_source_fact | 6 | 4/6 · 6/6 · 0.83 | 6/6 · 6/6 · 1.00 | 6/6 · 6/6 · 1.00 | 6/6 · 6/6 · 1.00 |
| versioning | 3 | 3/3 · 3/3 · 1.00 | 1/3 · 3/3 · 0.61 | 2/3 · 3/3 · 0.83 | 2/3 · 3/3 · 0.83 |

## By source format (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| source format | n | dense | hybrid | dense-rerank | hybrid-rerank |
|---|---|---|---|---|---|
| csv | 7 | 1/7 · 5/7 · 0.25 | 1/7 · 5/7 · 0.30 | 5/7 · 5/7 · 0.71 | 5/7 · 5/7 · 0.72 |
| docx | 9 | 6/9 · 9/9 · 0.80 | 6/9 · 9/9 · 0.79 | 9/9 · 9/9 · 1.00 | 9/9 · 9/9 · 1.00 |
| markdown | 8 | 5/8 · 7/8 · 0.73 | 4/8 · 7/8 · 0.65 | 5/8 · 7/8 · 0.73 | 5/8 · 7/8 · 0.74 |
| pdf | 8 | 7/8 · 7/8 · 0.89 | 4/8 · 7/8 · 0.63 | 6/8 · 8/8 · 0.83 | 6/8 · 8/8 · 0.83 |
| pptx | 9 | 5/9 · 9/9 · 0.78 | 8/9 · 9/9 · 0.93 | 7/9 · 9/9 · 0.87 | 7/9 · 9/9 · 0.87 |
| text | 3 | 3/3 · 3/3 · 1.00 | 2/3 · 3/3 · 0.83 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 |
| xlsx | 7 | 3/7 · 3/7 · 0.44 | 3/7 · 4/7 · 0.44 | 2/7 · 4/7 · 0.41 | 2/7 · 4/7 · 0.41 |

## By overlap bin (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| overlap bin | n | dense | hybrid | dense-rerank | hybrid-rerank |
|---|---|---|---|---|---|
| high | 2 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 |
| low | 13 | 23.1% · 69.2% · 0.44 | 38.5% · 76.9% · 0.48 | 53.8% · 84.6% · 0.65 | 53.8% · 84.6% · 0.66 |
| mid | 29 | 72.4% · 89.7% · 0.77 | 62.1% · 89.7% · 0.73 | 79.3% · 89.7% · 0.84 | 79.3% · 89.7% · 0.84 |

## Paired comparisons (same items)

| Comparison | hit@1 (only ref / only other, p) | hit@10 (…) | ΔMRR [95% CI] | Δrecall@10 [95% CI] |
|---|---|---|---|---|
| hybrid->dense | 5 / 6, p=1.0 | 2 / 1, p=1.0 | +0.015 [-0.074, +0.104] | -0.023 [-0.091, +0.045] |
| hybrid->dense-rerank | 2 / 9, p=0.0654 | 0 / 1, p=1.0 | +0.122 [+0.038, +0.214] | +0.019 [-0.027, +0.076] |
| hybrid->hybrid-rerank | 2 / 9, p=0.0654 | 0 / 1, p=1.0 | +0.123 [+0.038, +0.215] | +0.008 [-0.045, +0.068] |

## Failure buckets at k=10: hybrid|dense

### both_miss (6)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks hybrid: {'NS-140': None}; dense: {'NS-140': None}
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P1.B2']
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B5']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks hybrid: {'SP-C06': None}; dense: {'SP-C06': None}
  - hybrid top-3: ['SOUTHPEAK/SURVEY-2026@v1:R171', 'SOUTHPEAK/SURVEY-2026@v1:R159', 'SOUTHPEAK/SURVEY-2026@v1:R180']
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R211', 'SOUTHPEAK/SURVEY-2026@v1:R184', 'SOUTHPEAK/SURVEY-2026@v1:R103']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks hybrid: {'NS-120': None}; dense: {'NS-120': None}
  - hybrid top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/PRODUCT-PERF@v1:SH2.T1']
  - dense top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B12']
- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks hybrid: {'NS-148': 52}; dense: {'NS-148': None}
  - hybrid top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/SUPPORT-THEMES@v1:P4.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL6.N1']
  - dense top-3: ['NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/REVIEWS@v1:R683']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks hybrid: {'NS-102': 16}; dense: {'NS-102': 24}
  - hybrid top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2']
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/PACE-DECK@v1:SL2', 'NORTHSTAR/Q3-REVIEW@v1:SL15']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks hybrid: {'NS-120': None}; dense: {'NS-120': None}
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3']
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2']

### hybrid_only (2)

- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks hybrid: {'NS-005': 10}; dense: {'NS-005': 12}
  - hybrid top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/GENZ-TRENDS@v2:P3.B3']
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P4.B1']
- **R0-060** (ambiguous_distractor, overlap 0.154): How large is the 2026 US athletic footwear market for Gen Z shoppers specifically, in the category sizing workbook?
  - expected ['NORTHSTAR/CATEGORY-SIZING@v1:SH1.R5'] · ranks hybrid: {'NS-129': 9}; dense: {'NS-129': 14}
  - hybrid top-3: ['NORTHSTAR/CATEGORY-SIZING@v1:SH1.R7', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R19', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R17']
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B3', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R19', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R18']

### dense_only (1)

- **R0-042** (semantic_paraphrase, overlap 0.0): What portion of young shoppers put more faith in fellow buyers' opinions and influencer demos than in what companies say in their ads?
  - expected ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1'] · ranks hybrid: {'NS-040': 13}; dense: {'NS-040': 1}
  - hybrid top-3: ['NORTHSTAR/INTERVIEWS@v1:S9.Q4', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B4']
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1', 'NORTHSTAR/PACE-DECK@v1:SL4.N1', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B7']


## Failure buckets at k=10: hybrid|dense-rerank

### both_miss (6)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks hybrid: {'NS-140': None}; dense-rerank: {'NS-140': None}
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P1.B2']
  - dense-rerank top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks hybrid: {'SP-C06': None}; dense-rerank: {'SP-C06': None}
  - hybrid top-3: ['SOUTHPEAK/SURVEY-2026@v1:R171', 'SOUTHPEAK/SURVEY-2026@v1:R159', 'SOUTHPEAK/SURVEY-2026@v1:R180']
  - dense-rerank top-3: ['SOUTHPEAK/SURVEY-2026@v1:R264', 'SOUTHPEAK/SURVEY-2026@v1:R234', 'SOUTHPEAK/SURVEY-2026@v1:R5']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks hybrid: {'NS-120': None}; dense-rerank: {'NS-120': None}
  - hybrid top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/PRODUCT-PERF@v1:SH2.T1']
  - dense-rerank top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks hybrid: {'NS-148': 52}; dense-rerank: {'NS-148': None}
  - hybrid top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/SUPPORT-THEMES@v1:P4.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL6.N1']
  - dense-rerank top-3: ['NORTHSTAR/REVIEWS@v1:R401', 'NORTHSTAR/REVIEWS@v1:R629', 'NORTHSTAR/REVIEWS@v1:R574']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks hybrid: {'NS-102': 16}; dense-rerank: {'NS-102': 24}
  - hybrid top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2']
  - dense-rerank top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks hybrid: {'NS-120': None}; dense-rerank: {'NS-120': None}
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3']
  - dense-rerank top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']

### dense-rerank_only (1)

- **R0-042** (semantic_paraphrase, overlap 0.0): What portion of young shoppers put more faith in fellow buyers' opinions and influencer demos than in what companies say in their ads?
  - expected ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1'] · ranks hybrid: {'NS-040': 13}; dense-rerank: {'NS-040': 1}
  - hybrid top-3: ['NORTHSTAR/INTERVIEWS@v1:S9.Q4', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B4']
  - dense-rerank top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2']


## Failure buckets at k=10: hybrid|hybrid-rerank

### both_miss (6)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks hybrid: {'NS-140': None}; hybrid-rerank: {'NS-140': None}
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P1.B2']
  - hybrid-rerank top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks hybrid: {'SP-C06': None}; hybrid-rerank: {'SP-C06': None}
  - hybrid top-3: ['SOUTHPEAK/SURVEY-2026@v1:R171', 'SOUTHPEAK/SURVEY-2026@v1:R159', 'SOUTHPEAK/SURVEY-2026@v1:R180']
  - hybrid-rerank top-3: ['SOUTHPEAK/PLANNING-NOTES@v1:S1.B1', 'SOUTHPEAK/PLANNING-NOTES@v1:S1.B5', 'SOUTHPEAK/SURVEY-2026@v1:R180']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks hybrid: {'NS-120': None}; hybrid-rerank: {'NS-120': None}
  - hybrid top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/PRODUCT-PERF@v1:SH2.T1']
  - hybrid-rerank top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks hybrid: {'NS-148': 52}; hybrid-rerank: {'NS-148': 52}
  - hybrid top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/SUPPORT-THEMES@v1:P4.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL6.N1']
  - hybrid-rerank top-3: ['NORTHSTAR/REVIEWS@v1:R401', 'NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/REVIEWS@v1:R683']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks hybrid: {'NS-102': 16}; hybrid-rerank: {'NS-102': 15}
  - hybrid top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2']
  - hybrid-rerank top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks hybrid: {'NS-120': None}; hybrid-rerank: {'NS-120': None}
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3']
  - hybrid-rerank top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']

### hybrid-rerank_only (1)

- **R0-042** (semantic_paraphrase, overlap 0.0): What portion of young shoppers put more faith in fellow buyers' opinions and influencer demos than in what companies say in their ads?
  - expected ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1'] · ranks hybrid: {'NS-040': 13}; hybrid-rerank: {'NS-040': 1}
  - hybrid top-3: ['NORTHSTAR/INTERVIEWS@v1:S9.Q4', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B4']
  - hybrid-rerank top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2']


## Distractor outranking

- **dense**: distractor above the true parent in 0/6 items with a ledger distractor
- **hybrid**: distractor above the true parent in 0/6 items with a ledger distractor
- **dense-rerank**: distractor above the true parent in 0/6 items with a ledger distractor
- **hybrid-rerank**: distractor above the true parent in 0/6 items with a ledger distractor
