# Phase 2 step 4: BGE query instruction (B arm), dev

- Split: **dev**, items: 44
- Dataset: `retrieval-v0` · corpus `d68f6473052e` · ledger `95e9bb87bae7`
- Run: git=90c3c31, at=2026-10-05T23:05:54+00:00, config_hash=7a99b9858fd900ff

## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)

| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| dense+bge-instruction | 56.8 [42.2, 70.3] | 75.0 [60.6, 85.4] | 75.0 [60.6, 85.4] | 71.2 [58.3, 83.7] | 83.3 [72.3, 93.2] | 66.8 [54.6, 78.8] | 17.08 | 21.12 |
| hybrid-rerank+bge-instruction | 70.5 [55.8, 81.8] | 84.1 [70.6, 92.1] | 86.4 [73.3, 93.6] | 81.1 [70.1, 90.9] | 85.6 [75.4, 94.7] | 77.0 [65.3, 87.8] | 716.0 | 898.06 |

## Latency by stage (ms, p50 / p95)

- **dense+bge-instruction**: dense_ms 7.3/9.3, embed_ms 7.33/10.44, fusion_ms 0.3/0.34, total_ms 17.08/21.12, wall_ms 17.74/21.61
- **hybrid-rerank+bge-instruction**: dense_ms 14.98/25.69, embed_ms 11.52/21.27, fusion_ms 0.61/0.73, hydrate_ms 1.46/3.03, lexical_ms 25.82/43.3, lexical_prep_ms 1.65/2.49, rerank_ms 652.97/822.31, total_ms 716.0/898.06, wall_ms 719.72/900.34

## By category (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| category | n | dense+bge-instruction | hybrid-rerank+bge-instruction |
|---|---|---|---|
| ambiguous_distractor | 4 | 2/4 · 2/4 · 0.51 | 1/4 · 3/4 · 0.46 |
| cross_format | 4 | 4/4 · 4/4 · 1.00 | 4/4 · 4/4 · 1.00 |
| customer_free_text | 5 | 3/5 · 4/5 · 0.72 | 5/5 · 5/5 · 1.00 |
| enumeration | 3 | 0/3 · 3/3 · 0.50 | 1/3 · 3/3 · 0.61 |
| exact_number | 7 | 4/7 · 5/7 · 0.64 | 4/7 · 5/7 · 0.64 |
| keyword_sensitive | 4 | 0/4 · 0/4 · 0.04 | 2/4 · 2/4 · 0.51 |
| named_entity | 3 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 |
| semantic_paraphrase | 5 | 2/5 · 3/5 · 0.52 | 3/5 · 4/5 · 0.64 |
| single_source_fact | 6 | 4/6 · 6/6 · 0.83 | 6/6 · 6/6 · 1.00 |
| versioning | 3 | 3/3 · 3/3 · 1.00 | 2/3 · 3/3 · 0.83 |

## By source format (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| source format | n | dense+bge-instruction | hybrid-rerank+bge-instruction |
|---|---|---|---|
| csv | 7 | 1/7 · 2/7 · 0.25 | 5/7 · 5/7 · 0.72 |
| docx | 9 | 5/9 · 9/9 · 0.78 | 9/9 · 9/9 · 1.00 |
| markdown | 8 | 5/8 · 7/8 · 0.75 | 5/8 · 7/8 · 0.74 |
| pdf | 8 | 7/8 · 7/8 · 0.89 | 6/8 · 8/8 · 0.83 |
| pptx | 9 | 6/9 · 9/9 · 0.83 | 7/9 · 9/9 · 0.87 |
| text | 3 | 3/3 · 3/3 · 1.00 | 3/3 · 3/3 · 1.00 |
| xlsx | 7 | 3/7 · 3/7 · 0.44 | 2/7 · 4/7 · 0.41 |

## By overlap bin (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| overlap bin | n | dense+bge-instruction | hybrid-rerank+bge-instruction |
|---|---|---|---|
| high | 2 | 1/2 · 1/2 · 0.50 | 1/2 · 1/2 · 0.50 |
| low | 13 | 30.8% · 69.2% · 0.51 | 53.8% · 84.6% · 0.66 |
| mid | 29 | 69.0% · 79.3% · 0.75 | 79.3% · 89.7% · 0.84 |

## Paired comparisons (same items)

| Comparison | hit@1 (only ref / only other, p) | hit@10 (…) | ΔMRR [95% CI] | Δrecall@10 [95% CI] |
|---|---|---|---|---|
| dense+bge-instruction->hybrid-rerank+bge-instruction | 3 / 9, p=0.146 | 0 / 5, p=0.0625 | +0.102 [+0.013, +0.198] | +0.098 [+0.000, +0.205] |

## Failure buckets at k=10: dense+bge-instruction|hybrid-rerank+bge-instruction

### both_miss (6)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks dense+bge-instruction: {'NS-140': None}; hybrid-rerank+bge-instruction: {'NS-140': None}
  - dense+bge-instruction top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2']
  - hybrid-rerank+bge-instruction top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B5', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL5']
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks dense+bge-instruction: {'SP-C06': None}; hybrid-rerank+bge-instruction: {'SP-C06': None}
  - dense+bge-instruction top-3: ['SOUTHPEAK/SURVEY-2026@v1:R211', 'SOUTHPEAK/SURVEY-2026@v1:R184', 'SOUTHPEAK/SURVEY-2026@v1:R103']
  - hybrid-rerank+bge-instruction top-3: ['SOUTHPEAK/PLANNING-NOTES@v1:S1.B1', 'SOUTHPEAK/PLANNING-NOTES@v1:S1.B5', 'SOUTHPEAK/SURVEY-2026@v1:R180']
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense+bge-instruction: {'NS-120': None}; hybrid-rerank+bge-instruction: {'NS-120': None}
  - dense+bge-instruction top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - hybrid-rerank+bge-instruction top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/KINETIC-AR@v1:P3.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks dense+bge-instruction: {'NS-148': None}; hybrid-rerank+bge-instruction: {'NS-148': 53}
  - dense+bge-instruction top-3: ['NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/REVIEWS@v1:R683']
  - hybrid-rerank+bge-instruction top-3: ['NORTHSTAR/REVIEWS@v1:R629', 'NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/REVIEWS@v1:R492']
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks dense+bge-instruction: {'NS-102': 37}; hybrid-rerank+bge-instruction: {'NS-102': 15}
  - dense+bge-instruction top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL15', 'NORTHSTAR/KINETIC-AR@v1:P4.B1']
  - hybrid-rerank+bge-instruction top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B9', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2']
- **R0-058** (ambiguous_distractor, overlap 0.25): Return rate for the second-generation Knit Runner, not the original model?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks dense+bge-instruction: {'NS-120': None}; hybrid-rerank+bge-instruction: {'NS-120': None}
  - dense+bge-instruction top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/REVIEWS@v1:R360']
  - hybrid-rerank+bge-instruction top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1']

### hybrid-rerank+bge-instruction_only (5)

- **R0-026** (keyword_sensitive, overlap 0.667): R0388 comment on paying more for made-to-foot shoes
  - expected ['NORTHSTAR/SURVEY-2026@v1:R389'] · ranks dense+bge-instruction: {'NS-144': 11}; hybrid-rerank+bge-instruction: {'NS-144': 1}
  - dense+bge-instruction top-3: ['NORTHSTAR/INTERVIEWS@v1:S9.Q1', 'NORTHSTAR/WTP-STUDY@v1:P1.B2', 'NORTHSTAR/KINETIC-AR@v1:P1.B2']
  - hybrid-rerank+bge-instruction top-3: ['NORTHSTAR/SURVEY-2026@v1:R389', 'NORTHSTAR/INTERVIEWS@v1:S9.Q1', 'NORTHSTAR/WTP-STUDY@v1:P1.B2']
- **R0-029** (keyword_sensitive, overlap 0.429): What does survey respondent R0062 want shown on product pages?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R63'] · ranks dense+bge-instruction: {'NS-146': 19}; hybrid-rerank+bge-instruction: {'NS-146': 1}
  - dense+bge-instruction top-3: ['NORTHSTAR/SURVEY-2026@v1:T1', 'NORTHSTAR/SURVEY-2026@v1:R577', 'NORTHSTAR/SUPPORT-THEMES@v1:P3.B1']
  - hybrid-rerank+bge-instruction top-3: ['NORTHSTAR/SURVEY-2026@v1:R63', 'NORTHSTAR/SURVEY-2026@v1:R77', 'NORTHSTAR/SURVEY-2026@v1:R32']
- **R0-034** (customer_free_text, overlap 0.5): Which survey verbatim asks for recycled content and factory locations to be listed on product pages, and which respondent gave it?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R63'] · ranks dense+bge-instruction: {'NS-146': 12}; hybrid-rerank+bge-instruction: {'NS-146': 1}
  - dense+bge-instruction top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P3.B1', 'NORTHSTAR/SURVEY-2026@v1:R179', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B5']
  - hybrid-rerank+bge-instruction top-3: ['NORTHSTAR/SURVEY-2026@v1:R63', 'NORTHSTAR/SUPPORT-THEMES@v1:P3.B1', 'NORTHSTAR/SURVEY-2026@v1:R32']
- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks dense+bge-instruction: {'NS-005': 13}; hybrid-rerank+bge-instruction: {'NS-005': 8}
  - dense+bge-instruction top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/INTERVIEWS@v1:S5.B1']
  - hybrid-rerank+bge-instruction top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P2.B2']
- **R0-060** (ambiguous_distractor, overlap 0.154): How large is the 2026 US athletic footwear market for Gen Z shoppers specifically, in the category sizing workbook?
  - expected ['NORTHSTAR/CATEGORY-SIZING@v1:SH1.R5'] · ranks dense+bge-instruction: {'NS-129': 19}; hybrid-rerank+bge-instruction: {'NS-129': 3}
  - dense+bge-instruction top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B3', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R19', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R18']
  - hybrid-rerank+bge-instruction top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B3', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R2', 'NORTHSTAR/CATEGORY-SIZING@v1:SH1.R5']


## Distractor outranking

- **dense+bge-instruction**: distractor above the true parent in 0/6 items with a ledger distractor
- **hybrid-rerank+bge-instruction**: distractor above the true parent in 0/6 items with a ledger distractor
