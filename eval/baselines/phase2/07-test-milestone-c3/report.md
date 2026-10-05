# Phase 2 milestone: TEST split, c3 index (final configuration = hybrid-rerank)

- Split: **test**, items: 21
- Dataset: `retrieval-v0` · corpus `d68f6473052e` · ledger `95e9bb87bae7`
- Run: git=6f7486c, at=2026-10-05T23:23:15+00:00, config_hash=41dd3956306c46f9, milestone=phase2-final: frozen config c3 hybrid+rerank; this invocation = c3 index (final)

## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)

| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| dense | 28.6 [13.8, 50.0] | 47.6 [28.3, 67.6] | 47.6 [28.3, 67.6] | 44.4 [23.8, 66.7] | 68.3 [49.2, 85.7] | 37.3 [20.1, 56.0] | 14.67 | 18.95 |
| lexical | 38.1 [20.8, 59.1] | 52.4 [32.4, 71.7] | 71.4 [50.0, 86.2] | 65.9 [46.0, 84.9] | 70.6 [51.6, 88.1] | 45.7 [27.6, 64.6] | 13.91 | 30.4 |
| hybrid | 38.1 [20.8, 59.1] | 66.7 [45.4, 82.8] | 76.2 [54.9, 89.4] | 70.6 [51.6, 88.1] | 70.6 [51.6, 88.1] | 49.0 [31.3, 67.1] | 26.96 | 41.07 |
| dense-rerank | 42.9 [24.5, 63.5] | 52.4 [32.4, 71.7] | 61.9 [40.9, 79.2] | 59.5 [38.1, 78.6] | 68.3 [49.2, 85.7] | 49.4 [30.3, 69.0] | 538.29 | 801.04 |
| hybrid-rerank | 42.9 [24.5, 63.5] | 52.4 [32.4, 71.7] | 57.1 [36.5, 75.5] | 57.1 [38.1, 76.2] | 70.6 [51.6, 88.1] | 48.8 [29.4, 68.6] | 670.44 | 921.15 |

## Latency by stage (ms, p50 / p95)

- **dense**: dense_ms 7.06/8.38, embed_ms 6.05/8.7, fusion_ms 0.31/0.49, total_ms 14.67/18.95, wall_ms 15.16/19.4
- **lexical**: fusion_ms 0.29/0.45, lexical_ms 11.06/28.22, lexical_prep_ms 0.59/0.82, total_ms 13.91/30.4, wall_ms 14.43/30.97
- **hybrid**: dense_ms 3.91/7.89, embed_ms 6.12/9.44, fusion_ms 0.54/0.78, lexical_ms 12.11/22.77, lexical_prep_ms 0.67/1.37, total_ms 26.96/41.07, wall_ms 27.45/41.67
- **dense-rerank**: dense_ms 12.71/22.12, embed_ms 8.52/39.57, fusion_ms 0.32/0.36, hydrate_ms 2.1/7.7, rerank_ms 508.0/771.68, total_ms 538.29/801.04, wall_ms 540.06/803.79
- **hybrid-rerank**: dense_ms 13.23/23.08, embed_ms 8.33/31.92, fusion_ms 0.62/0.79, hydrate_ms 1.37/2.05, lexical_ms 27.34/61.23, lexical_prep_ms 1.56/2.05, rerank_ms 620.3/823.37, total_ms 670.44/921.15, wall_ms 671.73/926.08

## By category (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| category | n | dense | lexical | hybrid | dense-rerank | hybrid-rerank |
|---|---|---|---|---|---|---|
| ambiguous_distractor | 1 | 0/1 · 1/1 · 0.50 | 0/1 · 1/1 · 0.50 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 |
| cross_format | 1 | 0/1 · 0/1 · 0.06 | 1/1 · 1/1 · 1.00 | 0/1 · 1/1 · 0.33 | 1/1 · 1/1 · 1.00 | 0/1 · 0/1 · 0.05 |
| customer_free_text | 2 | 0/2 · 0/2 · 0.05 | 2/2 · 2/2 · 1.00 | 1/2 · 2/2 · 0.58 | 0/2 · 1/2 · 0.10 | 1/2 · 2/2 · 0.58 |
| enumeration | 1 | 0/1 · 1/1 · 0.20 | 0/1 · 1/1 · 0.17 | 0/1 · 1/1 · 0.25 | 0/1 · 0/1 · 0.08 | 0/1 · 0/1 · 0.07 |
| exact_number | 3 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.33 |
| keyword_sensitive | 3 | 1/3 · 1/3 · 0.38 | 2/3 · 3/3 · 0.75 | 2/3 · 3/3 · 0.75 | 1/3 · 2/3 · 0.47 | 1/3 · 2/3 · 0.44 |
| named_entity | 3 | 0/3 · 1/3 · 0.17 | 0/3 · 1/3 · 0.07 | 0/3 · 1/3 · 0.17 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.33 |
| semantic_paraphrase | 3 | 2/3 · 3/3 · 0.75 | 0/3 · 1/3 · 0.07 | 1/3 · 3/3 · 0.50 | 1/3 · 3/3 · 0.56 | 1/3 · 2/3 · 0.53 |
| single_source_fact | 3 | 1/3 · 1/3 · 0.36 | 1/3 · 3/3 · 0.43 | 1/3 · 2/3 · 0.43 | 2/3 · 2/3 · 0.67 | 2/3 · 2/3 · 0.68 |
| versioning | 1 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 |

## By source format (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| source format | n | dense | lexical | hybrid | dense-rerank | hybrid-rerank |
|---|---|---|---|---|---|---|
| csv | 7 | 0/7 · 1/7 · 0.07 | 4/7 · 6/7 · 0.63 | 2/7 · 6/7 · 0.43 | 1/7 · 3/7 · 0.24 | 1/7 · 3/7 · 0.23 |
| docx | 2 | 0/2 · 1/2 · 0.14 | 0/2 · 2/2 · 0.17 | 0/2 · 2/2 · 0.25 | 1/2 · 1/2 · 0.54 | 1/2 · 1/2 · 0.54 |
| markdown | 2 | 2/2 · 2/2 · 1.00 | 1/2 · 2/2 · 0.55 | 2/2 · 2/2 · 1.00 | 2/2 · 2/2 · 1.00 | 2/2 · 2/2 · 1.00 |
| pdf | 8 | 3/8 · 6/8 · 0.54 | 3/8 · 6/8 · 0.49 | 3/8 · 7/8 · 0.55 | 5/8 · 7/8 · 0.71 | 4/8 · 5/8 · 0.58 |
| pptx | 1 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 |
| xlsx | 3 | 0/3 · 0/3 · 0.00 | 0/3 · 0/3 · 0.00 | 0/3 · 0/3 · 0.00 | 0/3 · 0/3 · 0.00 | 0/3 · 0/3 · 0.00 |

## By overlap bin (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| overlap bin | n | dense | lexical | hybrid | dense-rerank | hybrid-rerank |
|---|---|---|---|---|---|---|
| high | 1 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 |
| low | 8 | 2/8 · 4/8 · 0.32 | 1/8 · 4/8 · 0.20 | 2/8 · 6/8 · 0.38 | 1/8 · 4/8 · 0.27 | 1/8 · 3/8 · 0.25 |
| mid | 12 | 25.0% · 41.7% · 0.35 | 50.0% · 83.3% · 0.58 | 41.7% · 75.0% · 0.52 | 58.3% · 66.7% · 0.60 | 58.3% · 66.7% · 0.60 |

## Paired comparisons (same items)

| Comparison | hit@1 (only ref / only other, p) | hit@10 (…) | ΔMRR [95% CI] | Δrecall@10 [95% CI] |
|---|---|---|---|---|
| dense->lexical | 2 / 4, p=0.6875 | 2 / 7, p=0.1797 | +0.084 [-0.126, +0.296] | +0.214 [-0.048, +0.452] |
| dense->hybrid | 1 / 3, p=0.625 | 0 / 6, p=0.0312 | +0.117 [-0.019, +0.269] | +0.262 [+0.095, +0.452] |
| dense->dense-rerank | 1 / 4, p=0.375 | 1 / 4, p=0.375 | +0.120 [-0.012, +0.268] | +0.151 [+0.008, +0.317] |
| dense->hybrid-rerank | 1 / 4, p=0.375 | 2 / 4, p=0.6875 | +0.115 [-0.016, +0.266] | +0.127 [-0.079, +0.333] |

## Failure buckets at k=10: dense|lexical

### lexical_only (7)

- **R0-003** (single_source_fact, overlap 0.5): Where and over what dates did Northstar's spring 2026 personalization pilot run, and how many customers did it reach?
  - expected ['NORTHSTAR/PERSO-PILOT@v1:S1.B3'] · ranks dense: {'NS-053': 12}; lexical: {'NS-053': 6}
  - dense top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
  - lexical top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B2']
- **R0-025** (keyword_sensitive, overlap 0.2): What did survey respondent R0147 say about sizing?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks dense: {'NS-143': 15}; lexical: {'NS-143': 1}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R28', 'NORTHSTAR/SURVEY-2026@v1:R498']
  - lexical top-3: ['NORTHSTAR/SURVEY-2026@v1:R148', 'NORTHSTAR/SURVEY-2026@v1:R163', 'NORTHSTAR/SURVEY-2026@v1:R407']
- **R0-028** (keyword_sensitive, overlap 0.25): RV-00412 Knit Runner 2 durability complaint details
  - expected ['NORTHSTAR/REVIEWS@v1:R413'] · ranks dense: {'NS-147': 14}; lexical: {'NS-147': 4}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2']
  - lexical top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B4']
- **R0-031** (single_source_fact, overlap 0.429): What do Southpeak's survey respondents name as their top issue?
  - expected ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3'] · ranks dense: {'SP-C02': None}; lexical: {'SP-C02': 9}
  - dense top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R177', 'SOUTHPEAK/SURVEY-2026@v1:R159']
  - lexical top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P3.B2', 'SOUTHPEAK/BRAND-STRATEGY@v1:P2.B5', 'SOUTHPEAK/BOARD-DECK@v1:SL8']
- **R0-033** (customer_free_text, overlap 0.429): What did survey respondent R0147 say about how they buy leggings and tees?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks dense: {'NS-143': 16}; lexical: {'NS-143': 1}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R518', 'NORTHSTAR/SURVEY-2026@v1:R29', 'NORTHSTAR/SURVEY-2026@v1:R33']
  - lexical top-3: ['NORTHSTAR/SURVEY-2026@v1:R148', 'NORTHSTAR/SURVEY-2026@v1:R18', 'NORTHSTAR/SURVEY-2026@v1:R29']
- **R0-039** (customer_free_text, overlap 0.571): What did Southpeak respondent SP-R0207 say about boot sizing?
  - expected ['SOUTHPEAK/SURVEY-2026@v1:R208'] · ranks dense: {'SP-C05': 25}; lexical: {'SP-C05': 1}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R213', 'SOUTHPEAK/SURVEY-2026@v1:R258', 'SOUTHPEAK/SURVEY-2026@v1:R195']
  - lexical top-3: ['SOUTHPEAK/SURVEY-2026@v1:R208', 'SOUTHPEAK/BRAND-STRATEGY@v1:P2.B5', 'SOUTHPEAK/PLANNING-NOTES@v1:S1.B5']

### both_miss (4)

- **R0-010** (exact_number, overlap 0.4): What was the Gen Z return rate on Northstar's brand site in August 2026?
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R102'] · ranks dense: {'NS-142': None}; lexical: {'NS-142': None}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - lexical top-3: ['NORTHSTAR/CHANNEL-PERF@v1:T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-015** (exact_number, overlap 0.5): Running Footwear gross margin for August 2026
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH1.R135'] · ranks dense: {'NS-122': None}; lexical: {'NS-122': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
  - lexical top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/PRODUCT-PERF@v1:SH1.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
- **R0-021** (named_entity, overlap 0.222): What is Northstar's best-selling product by units so far in FY26?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R14'] · ranks dense: {'NS-121': None}; lexical: {'NS-121': None}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
  - lexical top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH1.T1', 'NORTHSTAR/PRODUCT-PERF@v1:SH2.T1', 'NORTHSTAR/VANTAGE-DECK@v1:SL5']
- **R0-023** (named_entity, overlap 0.1): Which Northstar product had a big chunk of its Q3 2026 returns blamed on running small?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH3.R35'] · ranks dense: {'NS-124': None}; lexical: {'NS-124': None}
  - dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/REVIEWS@v1:R664']
  - lexical top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2']

### dense_only (2)

- **R0-041** (semantic_paraphrase, overlap 0.062): How slowly did the care team typically get back to people who messaged through social apps last quarter, compared with the goal they had set?
  - expected ['NORTHSTAR/SUPPORT-THEMES@v1:P3.B3'] · ranks dense: {'NS-013': 1}; lexical: {'NS-013': 13}
  - dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P3.B3', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B5']
  - lexical top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P4.B2', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2']
- **R0-047** (semantic_paraphrase, overlap 0.077): In the trade-off exercise, how did shoppers weigh getting a shoe shaped to their foot against picking their own colors?
  - expected ['NORTHSTAR/WTP-STUDY@v1:P2.B2', 'NORTHSTAR/WTP-STUDY@v1:P3.B2'] · ranks dense: {'NS-043': 4}; lexical: {'NS-043': 29}
  - dense top-3: ['NORTHSTAR/WTP-STUDY@v1:P2.B1', 'NORTHSTAR/WTP-STUDY@v1:P1.B2', 'NORTHSTAR/VANTAGE-DECK@v1:SL9.N1']
  - lexical top-3: ['NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B6', 'NORTHSTAR/KINETIC-WEB@v1:S1.B7', 'NORTHSTAR/GENZ-TRENDS@v2:P3.B3']


## Failure buckets at k=10: dense|hybrid

### hybrid_only (6)

- **R0-003** (single_source_fact, overlap 0.5): Where and over what dates did Northstar's spring 2026 personalization pilot run, and how many customers did it reach?
  - expected ['NORTHSTAR/PERSO-PILOT@v1:S1.B3'] · ranks dense: {'NS-053': 12}; hybrid: {'NS-053': 4}
  - dense top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
  - hybrid top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
- **R0-025** (keyword_sensitive, overlap 0.2): What did survey respondent R0147 say about sizing?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks dense: {'NS-143': 15}; hybrid: {'NS-143': 1}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R28', 'NORTHSTAR/SURVEY-2026@v1:R498']
  - hybrid top-3: ['NORTHSTAR/SURVEY-2026@v1:R148', 'NORTHSTAR/SURVEY-2026@v1:R369', 'NORTHSTAR/SURVEY-2026@v1:R304']
- **R0-028** (keyword_sensitive, overlap 0.25): RV-00412 Knit Runner 2 durability complaint details
  - expected ['NORTHSTAR/REVIEWS@v1:R413'] · ranks dense: {'NS-147': 14}; hybrid: {'NS-147': 4}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2']
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']
- **R0-033** (customer_free_text, overlap 0.429): What did survey respondent R0147 say about how they buy leggings and tees?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks dense: {'NS-143': 16}; hybrid: {'NS-143': 6}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R518', 'NORTHSTAR/SURVEY-2026@v1:R29', 'NORTHSTAR/SURVEY-2026@v1:R33']
  - hybrid top-3: ['NORTHSTAR/SURVEY-2026@v1:R29', 'NORTHSTAR/SURVEY-2026@v1:R18', 'NORTHSTAR/SURVEY-2026@v1:R379']
- **R0-039** (customer_free_text, overlap 0.571): What did Southpeak respondent SP-R0207 say about boot sizing?
  - expected ['SOUTHPEAK/SURVEY-2026@v1:R208'] · ranks dense: {'SP-C05': 25}; hybrid: {'SP-C05': 1}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R213', 'SOUTHPEAK/SURVEY-2026@v1:R258', 'SOUTHPEAK/SURVEY-2026@v1:R195']
  - hybrid top-3: ['SOUTHPEAK/SURVEY-2026@v1:R208', 'SOUTHPEAK/SURVEY-2026@v1:R269', 'SOUTHPEAK/SURVEY-2026@v1:R81']
- **R0-052** (cross_format, overlap 0.6): For Southpeak, what share of survey respondents say inconsistent fit between boots and trail runners is their top issue, and what did respondent SP-R0207 say about boot sizing?
  - expected ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3', 'SOUTHPEAK/SURVEY-2026@v1:R208'] · ranks dense: {'SP-C02': 16, 'SP-C05': 20}; hybrid: {'SP-C02': 26, 'SP-C05': 3}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R269', 'SOUTHPEAK/SURVEY-2026@v1:R52', 'SOUTHPEAK/SURVEY-2026@v1:R59']
  - hybrid top-3: ['SOUTHPEAK/BOARD-DECK@v1:SL8', 'SOUTHPEAK/SURVEY-2026@v1:R218', 'SOUTHPEAK/SURVEY-2026@v1:R208']

### both_miss (5)

- **R0-010** (exact_number, overlap 0.4): What was the Gen Z return rate on Northstar's brand site in August 2026?
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R102'] · ranks dense: {'NS-142': None}; hybrid: {'NS-142': None}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - hybrid top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2']
- **R0-015** (exact_number, overlap 0.5): Running Footwear gross margin for August 2026
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH1.R135'] · ranks dense: {'NS-122': None}; hybrid: {'NS-122': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3', 'NORTHSTAR/KINETIC-AR@v1:P4.B2']
- **R0-021** (named_entity, overlap 0.222): What is Northstar's best-selling product by units so far in FY26?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R14'] · ranks dense: {'NS-121': None}; hybrid: {'NS-121': None}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
  - hybrid top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
- **R0-023** (named_entity, overlap 0.1): Which Northstar product had a big chunk of its Q3 2026 returns blamed on running small?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH3.R35'] · ranks dense: {'NS-124': None}; hybrid: {'NS-124': None}
  - dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/REVIEWS@v1:R664']
  - hybrid top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B1']
- **R0-031** (single_source_fact, overlap 0.429): What do Southpeak's survey respondents name as their top issue?
  - expected ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3'] · ranks dense: {'SP-C02': None}; hybrid: {'SP-C02': 28}
  - dense top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R177', 'SOUTHPEAK/SURVEY-2026@v1:R159']
  - hybrid top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R159', 'SOUTHPEAK/SURVEY-2026@v1:R180']


## Failure buckets at k=10: dense|dense-rerank

### dense-rerank_only (4)

- **R0-003** (single_source_fact, overlap 0.5): Where and over what dates did Northstar's spring 2026 personalization pilot run, and how many customers did it reach?
  - expected ['NORTHSTAR/PERSO-PILOT@v1:S1.B3'] · ranks dense: {'NS-053': 12}; dense-rerank: {'NS-053': 1}
  - dense top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
  - dense-rerank top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/SURVEY-2026@v1:R596']
- **R0-028** (keyword_sensitive, overlap 0.25): RV-00412 Knit Runner 2 durability complaint details
  - expected ['NORTHSTAR/REVIEWS@v1:R413'] · ranks dense: {'NS-147': 14}; dense-rerank: {'NS-147': 3}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2']
  - dense-rerank top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/REVIEWS@v1:R413']
- **R0-033** (customer_free_text, overlap 0.429): What did survey respondent R0147 say about how they buy leggings and tees?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks dense: {'NS-143': 16}; dense-rerank: {'NS-143': 6}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R518', 'NORTHSTAR/SURVEY-2026@v1:R29', 'NORTHSTAR/SURVEY-2026@v1:R33']
  - dense-rerank top-3: ['NORTHSTAR/SURVEY-2026@v1:R18', 'NORTHSTAR/SURVEY-2026@v1:R134', 'NORTHSTAR/SURVEY-2026@v1:R182']
- **R0-052** (cross_format, overlap 0.6): For Southpeak, what share of survey respondents say inconsistent fit between boots and trail runners is their top issue, and what did respondent SP-R0207 say about boot sizing?
  - expected ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3', 'SOUTHPEAK/SURVEY-2026@v1:R208'] · ranks dense: {'SP-C02': 16, 'SP-C05': 20}; dense-rerank: {'SP-C02': 1, 'SP-C05': 18}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R269', 'SOUTHPEAK/SURVEY-2026@v1:R52', 'SOUTHPEAK/SURVEY-2026@v1:R59']
  - dense-rerank top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3', 'SOUTHPEAK/BOARD-DECK@v1:SL8', 'SOUTHPEAK/SURVEY-2026@v1:R59']

### both_miss (7)

- **R0-010** (exact_number, overlap 0.4): What was the Gen Z return rate on Northstar's brand site in August 2026?
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R102'] · ranks dense: {'NS-142': None}; dense-rerank: {'NS-142': None}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - dense-rerank top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-015** (exact_number, overlap 0.5): Running Footwear gross margin for August 2026
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH1.R135'] · ranks dense: {'NS-122': None}; dense-rerank: {'NS-122': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
  - dense-rerank top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/KINETIC-AR@v1:P4.B2', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
- **R0-021** (named_entity, overlap 0.222): What is Northstar's best-selling product by units so far in FY26?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R14'] · ranks dense: {'NS-121': None}; dense-rerank: {'NS-121': None}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
  - dense-rerank top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/REVIEWS@v1:R666', 'NORTHSTAR/REVIEWS@v1:R677']
- **R0-023** (named_entity, overlap 0.1): Which Northstar product had a big chunk of its Q3 2026 returns blamed on running small?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH3.R35'] · ranks dense: {'NS-124': None}; dense-rerank: {'NS-124': None}
  - dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/REVIEWS@v1:R664']
  - dense-rerank top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/REVIEWS@v1:R664', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2']
- **R0-025** (keyword_sensitive, overlap 0.2): What did survey respondent R0147 say about sizing?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks dense: {'NS-143': 15}; dense-rerank: {'NS-143': 13}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R28', 'NORTHSTAR/SURVEY-2026@v1:R498']
  - dense-rerank top-3: ['NORTHSTAR/SURVEY-2026@v1:R171', 'NORTHSTAR/SURVEY-2026@v1:R167', 'NORTHSTAR/SURVEY-2026@v1:R28']
- **R0-031** (single_source_fact, overlap 0.429): What do Southpeak's survey respondents name as their top issue?
  - expected ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3'] · ranks dense: {'SP-C02': None}; dense-rerank: {'SP-C02': None}
  - dense top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R177', 'SOUTHPEAK/SURVEY-2026@v1:R159']
  - dense-rerank top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R171', 'SOUTHPEAK/SURVEY-2026@v1:R159']

### dense_only (1)

- **R0-054** (enumeration, overlap 0.316): Pull every individual customer voice (interviewees, survey verbatims, product reviews) describing the knit upper on their running shoes fraying, splitting or tearing early.
  - expected ['NORTHSTAR/INTERVIEWS@v1:S7.Q1', 'NORTHSTAR/REVIEWS@v1:R413', 'NORTHSTAR/SURVEY-2026@v1:R522'] · ranks dense: {'NS-062': 41, 'NS-145': 5, 'NS-147': 28}; dense-rerank: {'NS-062': 41, 'NS-145': 12, 'NS-147': 28}
  - dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3']
  - dense-rerank top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/SURVEY-2026@v1:R43', 'NORTHSTAR/SURVEY-2026@v1:R299']


## Failure buckets at k=10: dense|hybrid-rerank

### hybrid-rerank_only (4)

- **R0-003** (single_source_fact, overlap 0.5): Where and over what dates did Northstar's spring 2026 personalization pilot run, and how many customers did it reach?
  - expected ['NORTHSTAR/PERSO-PILOT@v1:S1.B3'] · ranks dense: {'NS-053': 12}; hybrid-rerank: {'NS-053': 1}
  - dense top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
  - hybrid-rerank top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/SURVEY-2026@v1:R596']
- **R0-028** (keyword_sensitive, overlap 0.25): RV-00412 Knit Runner 2 durability complaint details
  - expected ['NORTHSTAR/REVIEWS@v1:R413'] · ranks dense: {'NS-147': 14}; hybrid-rerank: {'NS-147': 4}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2']
  - hybrid-rerank top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/REVIEWS@v1:R583']
- **R0-033** (customer_free_text, overlap 0.429): What did survey respondent R0147 say about how they buy leggings and tees?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks dense: {'NS-143': 16}; hybrid-rerank: {'NS-143': 6}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R518', 'NORTHSTAR/SURVEY-2026@v1:R29', 'NORTHSTAR/SURVEY-2026@v1:R33']
  - hybrid-rerank top-3: ['NORTHSTAR/SURVEY-2026@v1:R18', 'NORTHSTAR/SURVEY-2026@v1:R134', 'NORTHSTAR/SURVEY-2026@v1:R182']
- **R0-039** (customer_free_text, overlap 0.571): What did Southpeak respondent SP-R0207 say about boot sizing?
  - expected ['SOUTHPEAK/SURVEY-2026@v1:R208'] · ranks dense: {'SP-C05': 25}; hybrid-rerank: {'SP-C05': 1}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R213', 'SOUTHPEAK/SURVEY-2026@v1:R258', 'SOUTHPEAK/SURVEY-2026@v1:R195']
  - hybrid-rerank top-3: ['SOUTHPEAK/SURVEY-2026@v1:R208', 'SOUTHPEAK/SURVEY-2026@v1:R209', 'SOUTHPEAK/SURVEY-2026@v1:R258']

### both_miss (7)

- **R0-010** (exact_number, overlap 0.4): What was the Gen Z return rate on Northstar's brand site in August 2026?
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R102'] · ranks dense: {'NS-142': None}; hybrid-rerank: {'NS-142': None}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - hybrid-rerank top-3: ['NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1']
- **R0-015** (exact_number, overlap 0.5): Running Footwear gross margin for August 2026
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH1.R135'] · ranks dense: {'NS-122': None}; hybrid-rerank: {'NS-122': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
  - hybrid-rerank top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/KINETIC-AR@v1:P4.B2']
- **R0-021** (named_entity, overlap 0.222): What is Northstar's best-selling product by units so far in FY26?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R14'] · ranks dense: {'NS-121': None}; hybrid-rerank: {'NS-121': None}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
  - hybrid-rerank top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH2.T1', 'NORTHSTAR/FIN-SUMMARY-FY26@v1:SH1.T1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B3']
- **R0-023** (named_entity, overlap 0.1): Which Northstar product had a big chunk of its Q3 2026 returns blamed on running small?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH3.R35'] · ranks dense: {'NS-124': None}; hybrid-rerank: {'NS-124': None}
  - dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/REVIEWS@v1:R664']
  - hybrid-rerank top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/REVIEWS@v1:R664', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B1']
- **R0-025** (keyword_sensitive, overlap 0.2): What did survey respondent R0147 say about sizing?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks dense: {'NS-143': 15}; hybrid-rerank: {'NS-143': 12}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R28', 'NORTHSTAR/SURVEY-2026@v1:R498']
  - hybrid-rerank top-3: ['NORTHSTAR/SURVEY-2026@v1:R171', 'NORTHSTAR/SURVEY-2026@v1:R167', 'NORTHSTAR/SURVEY-2026@v1:R156']
- **R0-031** (single_source_fact, overlap 0.429): What do Southpeak's survey respondents name as their top issue?
  - expected ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3'] · ranks dense: {'SP-C02': None}; hybrid-rerank: {'SP-C02': 28}
  - dense top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R177', 'SOUTHPEAK/SURVEY-2026@v1:R159']
  - hybrid-rerank top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/BRAND-STRATEGY@v1:P3.B2', 'SOUTHPEAK/BRAND-STRATEGY@v1:P2.B5']

### dense_only (2)

- **R0-047** (semantic_paraphrase, overlap 0.077): In the trade-off exercise, how did shoppers weigh getting a shoe shaped to their foot against picking their own colors?
  - expected ['NORTHSTAR/WTP-STUDY@v1:P2.B2', 'NORTHSTAR/WTP-STUDY@v1:P3.B2'] · ranks dense: {'NS-043': 4}; hybrid-rerank: {'NS-043': 11}
  - dense top-3: ['NORTHSTAR/WTP-STUDY@v1:P2.B1', 'NORTHSTAR/WTP-STUDY@v1:P1.B2', 'NORTHSTAR/VANTAGE-DECK@v1:SL9.N1']
  - hybrid-rerank top-3: ['NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B6', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/GENZ-TRENDS@v2:P3.B3']
- **R0-054** (enumeration, overlap 0.316): Pull every individual customer voice (interviewees, survey verbatims, product reviews) describing the knit upper on their running shoes fraying, splitting or tearing early.
  - expected ['NORTHSTAR/INTERVIEWS@v1:S7.Q1', 'NORTHSTAR/REVIEWS@v1:R413', 'NORTHSTAR/SURVEY-2026@v1:R522'] · ranks dense: {'NS-062': 41, 'NS-145': 5, 'NS-147': 28}; hybrid-rerank: {'NS-062': 83, 'NS-145': 14, 'NS-147': 28}
  - dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3']
  - hybrid-rerank top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B2', 'NORTHSTAR/SURVEY-2026@v1:R43']


## Distractor outranking

- **dense**: distractor above the true parent in 0/1 items with a ledger distractor
- **lexical**: distractor above the true parent in 0/1 items with a ledger distractor
- **hybrid**: distractor above the true parent in 0/1 items with a ledger distractor
- **dense-rerank**: distractor above the true parent in 0/1 items with a ledger distractor
- **hybrid-rerank**: distractor above the true parent in 0/1 items with a ledger distractor
