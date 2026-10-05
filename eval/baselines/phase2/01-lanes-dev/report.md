# Phase 2 step 1: production lanes and parent-level RRF (dev)

- Split: **dev**, items: 44
- Dataset: `retrieval-v0` · corpus `d68f6473052e` · ledger `95e9bb87bae7`
- Run: git=dca59f5, at=2026-10-05T22:58:40+00:00, config_hash=93e4b80e2839e563

## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)

| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| dense | 56.8 [42.2, 70.3] | 75.0 [60.6, 85.4] | 81.8 [68.0, 90.5] | 78.0 [65.9, 89.0] | 83.3 [72.3, 93.2] | 66.2 [53.9, 78.1] | 17.42 | 25.49 |
| lexical | 40.9 [27.7, 55.6] | 72.7 [58.2, 83.7] | 77.3 [63.0, 87.2] | 73.9 [61.0, 86.0] | 77.7 [65.2, 89.0] | 53.5 [41.2, 65.7] | 14.51 | 26.83 |
| hybrid | 54.5 [40.1, 68.3] | 75.0 [60.6, 85.4] | 84.1 [70.6, 92.1] | 80.3 [68.6, 90.5] | 85.6 [75.4, 94.7] | 64.7 [52.4, 76.7] | 27.21 | 58.29 |

## Latency by stage (ms, p50 / p95)

- **dense**: dense_ms 8.42/10.37, embed_ms 6.46/12.41, fusion_ms 0.3/0.76, total_ms 17.42/25.49, wall_ms 18.17/26.25
- **lexical**: fusion_ms 0.34/1.26, lexical_ms 12.05/23.94, lexical_prep_ms 0.67/0.98, total_ms 14.51/26.83, wall_ms 15.23/27.44
- **hybrid**: dense_ms 4.04/9.07, embed_ms 6.29/9.6, fusion_ms 0.53/0.65, lexical_ms 12.27/23.6, lexical_prep_ms 0.84/1.93, total_ms 27.21/58.29, wall_ms 27.68/59.04

## By category (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| category | n | dense | lexical | hybrid |
|---|---|---|---|---|
| ambiguous_distractor | 4 | 2/4 · 2/4 · 0.52 | 0/4 · 3/4 · 0.31 | 2/4 · 3/4 · 0.53 |
| cross_format | 4 | 4/4 · 4/4 · 1.00 | 2/4 · 4/4 · 0.68 | 3/4 · 4/4 · 0.88 |
| customer_free_text | 5 | 3/5 · 5/5 · 0.72 | 3/5 · 5/5 · 0.73 | 3/5 · 5/5 · 0.77 |
| enumeration | 3 | 0/3 · 3/3 · 0.39 | 0/3 · 2/3 · 0.26 | 0/3 · 3/3 · 0.26 |
| exact_number | 7 | 5/7 · 5/7 · 0.71 | 5/7 · 5/7 · 0.71 | 5/7 · 5/7 · 0.71 |
| keyword_sensitive | 4 | 0/4 · 2/4 · 0.08 | 0/4 · 1/4 · 0.15 | 0/4 · 2/4 · 0.17 |
| named_entity | 3 | 2/3 · 3/3 · 0.83 | 2/3 · 3/3 · 0.83 | 3/3 · 3/3 · 1.00 |
| semantic_paraphrase | 5 | 2/5 · 3/5 · 0.49 | 0/5 · 2/5 · 0.08 | 1/5 · 3/5 · 0.35 |
| single_source_fact | 6 | 4/6 · 6/6 · 0.83 | 5/6 · 6/6 · 0.87 | 6/6 · 6/6 · 1.00 |
| versioning | 3 | 3/3 · 3/3 · 1.00 | 1/3 · 3/3 · 0.48 | 1/3 · 3/3 · 0.61 |

## By source format (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| source format | n | dense | lexical | hybrid |
|---|---|---|---|---|
| csv | 7 | 1/7 · 5/7 · 0.25 | 1/7 · 3/7 · 0.28 | 1/7 · 5/7 · 0.30 |
| docx | 9 | 6/9 · 9/9 · 0.80 | 4/9 · 8/9 · 0.58 | 6/9 · 9/9 · 0.79 |
| markdown | 8 | 5/8 · 7/8 · 0.73 | 3/8 · 7/8 · 0.56 | 4/8 · 7/8 · 0.65 |
| pdf | 8 | 7/8 · 7/8 · 0.89 | 3/8 · 6/8 · 0.50 | 4/8 · 7/8 · 0.63 |
| pptx | 9 | 5/9 · 9/9 · 0.78 | 6/9 · 9/9 · 0.77 | 8/9 · 9/9 · 0.93 |
| text | 3 | 3/3 · 3/3 · 1.00 | 2/3 · 3/3 · 0.72 | 2/3 · 3/3 · 0.83 |
| xlsx | 7 | 3/7 · 3/7 · 0.44 | 2/7 · 4/7 · 0.39 | 3/7 · 4/7 · 0.44 |

## By overlap bin (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| overlap bin | n | dense | lexical | hybrid |
|---|---|---|---|---|
| high | 2 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 |
| low | 13 | 23.1% · 69.2% · 0.44 | 15.4% · 61.5% · 0.30 | 38.5% · 76.9% · 0.48 |
| mid | 29 | 72.4% · 89.7% · 0.77 | 51.7% · 86.2% · 0.64 | 62.1% · 89.7% · 0.73 |

## Paired comparisons (same items)

| Comparison | hit@1 (only ref / only other, p) | hit@10 (…) | ΔMRR [95% CI] | Δrecall@10 [95% CI] |
|---|---|---|---|---|
| dense->lexical | 10 / 3, p=0.0923 | 3 / 1, p=0.625 | -0.127 [-0.234, -0.024] | -0.042 [-0.125, +0.038] |
| dense->hybrid | 6 / 5, p=1.0 | 1 / 2, p=1.0 | -0.015 [-0.104, +0.074] | +0.023 [-0.045, +0.091] |

## Failure buckets at k=10: dense|lexical

### both_miss (7)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense: {'NS-140': None}; lexical: {'NS-140': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B5']
  - lexical top-3: ['NORTHSTAR/CHANNEL-PERF@v1:T1', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense: {'SP-C06': None}; lexical: {'SP-C06': None}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R211', 'SOUTHPEAK/SURVEY-2026@v1:R184', 'SOUTHPEAK/SURVEY-2026@v1:R103']
  - lexical top-3: ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.T1', 'SOUTHPEAK/PLANNING-NOTES@v1:S1.B5', 'SOUTHPEAK/INTERVIEWS@v1:S1.B1']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; lexical: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B12']
  - lexical top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense: {'NS-148': None}; lexical: {'NS-148': 26}
  - dense top-3: ['NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/REVIEWS@v1:R683']
  - lexical top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B10', 'NORTHSTAR/WTP-STUDY@v1:P4.B2', 'NORTHSTAR/VANTAGE-DECK@v1:SL4.N1']
- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks dense: {'NS-005': 12}; lexical: {'NS-005': 17}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P4.B1']
  - lexical top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P2.B2']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense: {'NS-102': 24}; lexical: {'NS-102': 28}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/PACE-DECK@v1:SL2', 'NORTHSTAR/Q3-REVIEW@v1:SL15']
  - lexical top-3: ['NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9']

### dense_only (3)

- **R0-029** (keyword_sensitive, overlap 0.429): What does survey respondent R0062 want shown on product pages?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R63'] · ranks dense: {'NS-146': 7}; lexical: {'NS-146': 21}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:T1', 'NORTHSTAR/SURVEY-2026@v1:R478', 'NORTHSTAR/SURVEY-2026@v1:R577']
  - lexical top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P4.B2', 'NORTHSTAR/SURVEY-2026@v1:R77', 'NORTHSTAR/SURVEY-2026@v1:R478']
- **R0-042** (semantic_paraphrase, overlap 0.0): What portion of young shoppers put more faith in fellow buyers' opinions and influencer demos than in what companies say in their ads?
  - expected ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1'] · ranks dense: {'NS-040': 1}; lexical: {'NS-040': 82}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1', 'NORTHSTAR/PACE-DECK@v1:SL4.N1', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B7']
  - lexical top-3: ['NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S2.B1', 'NORTHSTAR/GENZ-TRENDS@v2:P3.B2']
- **R0-055** (enumeration, overlap 0.286): Which individual customers (interviewees or survey respondents) want brands to disclose where their shoes are made or how much recycled material goes into them?
  - expected ['NORTHSTAR/INTERVIEWS@v1:S11.Q1', 'NORTHSTAR/SURVEY-2026@v1:R63'] · ranks dense: {'NS-063': 3, 'NS-146': None}; lexical: {'NS-063': 25, 'NS-146': None}
  - dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R478', 'NORTHSTAR/SURVEY-2026@v1:R207', 'NORTHSTAR/INTERVIEWS@v1:S11.Q1']
  - lexical top-3: ['NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B4', 'NORTHSTAR/SURVEY-2026@v1:R66', 'NORTHSTAR/SURVEY-2026@v1:R437']

### lexical_only (1)

- **R0-060** (ambiguous_distractor, overlap 0.154): How large is the 2026 US athletic footwear market for Gen Z shoppers specifically, in the category sizing workbook?
  - expected ['NORTHSTAR/CATEGORY-SIZING@v1:SH1.R5'] · ranks dense: {'NS-129': 14}; lexical: {'NS-129': 4}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B3', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R19', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R18']
  - lexical top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P2.B2', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R3']


## Failure buckets at k=10: dense|hybrid

### both_miss (6)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense: {'NS-140': None}; hybrid: {'NS-140': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B5']
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P1.B2']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense: {'SP-C06': None}; hybrid: {'SP-C06': None}
  - dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R211', 'SOUTHPEAK/SURVEY-2026@v1:R184', 'SOUTHPEAK/SURVEY-2026@v1:R103']
  - hybrid top-3: ['SOUTHPEAK/SURVEY-2026@v1:R171', 'SOUTHPEAK/SURVEY-2026@v1:R159', 'SOUTHPEAK/SURVEY-2026@v1:R180']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; hybrid: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B12']
  - hybrid top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/PRODUCT-PERF@v1:SH2.T1']
- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense: {'NS-148': None}; hybrid: {'NS-148': 52}
  - dense top-3: ['NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/REVIEWS@v1:R683']
  - hybrid top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/SUPPORT-THEMES@v1:P4.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL6.N1']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense: {'NS-102': 24}; hybrid: {'NS-102': 16}
  - dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/PACE-DECK@v1:SL2', 'NORTHSTAR/Q3-REVIEW@v1:SL15']
  - hybrid top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense: {'NS-120': None}; hybrid: {'NS-120': None}
  - dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2']
  - hybrid top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3']

### hybrid_only (2)

- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks dense: {'NS-005': 12}; hybrid: {'NS-005': 10}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P4.B1']
  - hybrid top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/GENZ-TRENDS@v2:P3.B3']
- **R0-060** (ambiguous_distractor, overlap 0.154): How large is the 2026 US athletic footwear market for Gen Z shoppers specifically, in the category sizing workbook?
  - expected ['NORTHSTAR/CATEGORY-SIZING@v1:SH1.R5'] · ranks dense: {'NS-129': 14}; hybrid: {'NS-129': 9}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B3', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R19', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R18']
  - hybrid top-3: ['NORTHSTAR/CATEGORY-SIZING@v1:SH1.R7', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R19', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R17']

### dense_only (1)

- **R0-042** (semantic_paraphrase, overlap 0.0): What portion of young shoppers put more faith in fellow buyers' opinions and influencer demos than in what companies say in their ads?
  - expected ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1'] · ranks dense: {'NS-040': 1}; hybrid: {'NS-040': 13}
  - dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P4.B1', 'NORTHSTAR/PACE-DECK@v1:SL4.N1', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B7']
  - hybrid top-3: ['NORTHSTAR/INTERVIEWS@v1:S9.Q4', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B4']


## Distractor outranking

- **dense**: distractor above the true parent in 0/6 items with a ledger distractor
- **lexical**: distractor above the true parent in 0/6 items with a ledger distractor
- **hybrid**: distractor above the true parent in 0/6 items with a ledger distractor
