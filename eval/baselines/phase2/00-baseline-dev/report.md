# Phase 2 baseline (untouched Phase 1 lanes), dev split

- Split: **dev**, items: 44
- Dataset: `retrieval-v0` · corpus `d68f6473052e` · ledger `95e9bb87bae7`
- Run: git=1c38c66, at=2026-10-05T20:56:47+00:00, config_hash=e88b58608b22af3a

## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)

| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| baseline-dense | 56.8 [42.2, 70.3] | 75.0 [60.6, 85.4] | 81.8 [68.0, 90.5] | 78.0 [65.9, 89.0] | 83.3 [72.3, 93.2] | 66.2 [53.9, 78.1] | 10.76 | 13.88 |
| baseline-lexical | 4.5 [1.3, 15.1] | 4.5 [1.3, 15.1] | 4.5 [1.3, 15.1] | 4.5 [0.0, 11.4] | 4.5 [0.0, 11.4] | 4.5 [0.0, 11.4] | 2.16 | 2.65 |

## Latency by stage (ms, p50 / p95)

- **baseline-dense**: dense_ms 4.87/7.29, embed_ms 5.71/8.07, total_ms 10.76/13.88, wall_ms 11.17/14.25
- **baseline-lexical**: lexical_ms 2.16/2.65, total_ms 2.16/2.65, wall_ms 2.43/2.93

## By category (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| category | n | baseline-dense | baseline-lexical |
|---|---|---|---|
| ambiguous_distractor | 4 | 2/4 · 2/4 · 0.52 | 0/4 · 0/4 · 0.00 |
| cross_format | 4 | 4/4 · 4/4 · 1.00 | 0/4 · 0/4 · 0.00 |
| customer_free_text | 5 | 3/5 · 5/5 · 0.72 | 0/5 · 0/5 · 0.00 |
| enumeration | 3 | 0/3 · 3/3 · 0.39 | 0/3 · 0/3 · 0.00 |
| exact_number | 7 | 5/7 · 5/7 · 0.71 | 2/7 · 2/7 · 0.29 |
| keyword_sensitive | 4 | 0/4 · 2/4 · 0.08 | 0/4 · 0/4 · 0.00 |
| named_entity | 3 | 2/3 · 3/3 · 0.83 | 0/3 · 0/3 · 0.00 |
| semantic_paraphrase | 5 | 2/5 · 3/5 · 0.49 | 0/5 · 0/5 · 0.00 |
| single_source_fact | 6 | 4/6 · 6/6 · 0.83 | 0/6 · 0/6 · 0.00 |
| versioning | 3 | 3/3 · 3/3 · 1.00 | 0/3 · 0/3 · 0.00 |

## By source format (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| source format | n | baseline-dense | baseline-lexical |
|---|---|---|---|
| csv | 7 | 1/7 · 5/7 · 0.25 | 0/7 · 0/7 · 0.00 |
| docx | 9 | 6/9 · 9/9 · 0.80 | 0/9 · 0/9 · 0.00 |
| markdown | 8 | 5/8 · 7/8 · 0.73 | 1/8 · 1/8 · 0.12 |
| pdf | 8 | 7/8 · 7/8 · 0.89 | 0/8 · 0/8 · 0.00 |
| pptx | 9 | 5/9 · 9/9 · 0.78 | 0/9 · 0/9 · 0.00 |
| text | 3 | 3/3 · 3/3 · 1.00 | 0/3 · 0/3 · 0.00 |
| xlsx | 7 | 3/7 · 3/7 · 0.44 | 1/7 · 1/7 · 0.14 |

## By overlap bin (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| overlap bin | n | baseline-dense | baseline-lexical |
|---|---|---|---|
| high | 2 | 1/2 · 1/2 · 0.50 | 0/2 · 0/2 · 0.00 |
| low | 13 | 23.1% · 69.2% · 0.44 | 0.0% · 0.0% · 0.00 |
| mid | 29 | 72.4% · 89.7% · 0.77 | 6.9% · 6.9% · 0.07 |

## Paired comparisons (same items)

| Comparison | hit@1 (only ref / only other, p) | hit@10 (…) | ΔMRR [95% CI] | Δrecall@10 [95% CI] |
|---|---|---|---|---|
| baseline-dense->baseline-lexical | 23 / 0, p=0.0 | 34 / 0, p=0.0 | -0.616 [-0.741, -0.490] | -0.735 [-0.852, -0.610] |

## Failure buckets at k=10: baseline-dense|baseline-lexical

### baseline-dense_only (34)

- **R0-001** (single_source_fact, overlap 0.444): What did Northstar leadership decide about a national rollout of personalization at the Q3 strategy review?
  - expected ['NORTHSTAR/Q3-REVIEW@v1:SL14.N1'] · ranks baseline-dense: {'NS-083': 1}; baseline-lexical: {'NS-083': None}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL14.N1', 'NORTHSTAR/Q3-REVIEW@v1:SL1', 'NORTHSTAR/Q3-REVIEW@v1:SL2']
  - baseline-lexical top-3: []
- **R0-002** (single_source_fact, overlap 0.667): When does the FY27 planning memo propose introducing the cross-category Fit Promise free exchange guarantee?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks baseline-dense: {'NS-101': 1}; baseline-lexical: {'NS-101': None}
  - baseline-dense top-3: ['NORTHSTAR/FY27-MEMO@v1:S1.B6', 'NORTHSTAR/FY27-MEMO@v1:S1.B8', 'NORTHSTAR/FY27-MEMO@v1:S1.B9']
  - baseline-lexical top-3: []
- **R0-004** (single_source_fact, overlap 0.5): What ceiling does the consumer panel analyst expect personalized shoes to stay under, as a share of US athletic footwear units, through 2028?
  - expected ['NORTHSTAR/ANALYST-CALL@v1:S1.B2'] · ranks baseline-dense: {'NS-112': 1}; baseline-lexical: {'NS-112': None}
  - baseline-dense top-3: ['NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/GENZ-TRENDS@v2:P5.B2', 'NORTHSTAR/WTP-STUDY@v1:P1.B2']
  - baseline-lexical top-3: []
- **R0-005** (single_source_fact, overlap 0.0): Why does Pace & Co. stay away from offering customized products?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P5.B4', 'NORTHSTAR/PACE-DECK@v1:SL9.N1'] · ranks baseline-dense: {'NS-094': 2}; baseline-lexical: {'NS-094': None}
  - baseline-dense top-3: ['NORTHSTAR/PACE-DECK@v1:SL9', 'NORTHSTAR/PACE-DECK@v1:SL9.N1', 'NORTHSTAR/BRAND-STRATEGY@v1:P5.B4']
  - baseline-lexical top-3: []
- **R0-006** (single_source_fact, overlap 0.375): Who took part in the Northstar Gen Z focus group, and where and when was it held?
  - expected ['NORTHSTAR/GENZ-FOCUS-GROUP@v1:S2.B1'] · ranks baseline-dense: {'NS-073': 1}; baseline-lexical: {'NS-073': None}
  - baseline-dense top-3: ['NORTHSTAR/GENZ-FOCUS-GROUP@v1:S2.B1', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S1.B1', 'NORTHSTAR/INTERVIEWS@v1:S1.B1']
  - baseline-lexical top-3: []
- **R0-011** (exact_number, overlap 0.4): How much net revenue did Northstar book in Q2 FY26 according to the Q3 strategy review?
  - expected ['NORTHSTAR/Q3-REVIEW@v1:SL3'] · ranks baseline-dense: {'NS-080': 1}; baseline-lexical: {'NS-080': None}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL2']
  - baseline-lexical top-3: []

### both_miss (8)

- **R0-009** (exact_number, overlap 0.444): Gen Z conversion rate on the Social Shop channel, September 2026
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R116'] · ranks baseline-dense: {'NS-140': None}; baseline-lexical: {'NS-140': None}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL5', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B5']
  - baseline-lexical top-3: []
- **R0-017** (exact_number, overlap 0.429): What was Southpeak's marketplace conversion rate in September 2026?
  - expected ['SOUTHPEAK/CHANNEL-DATA@v1:SH1.R59'] · ranks baseline-dense: {'SP-C06': None}; baseline-lexical: {'SP-C06': None}
  - baseline-dense top-3: ['SOUTHPEAK/SURVEY-2026@v1:R211', 'SOUTHPEAK/SURVEY-2026@v1:R184', 'SOUTHPEAK/SURVEY-2026@v1:R103']
  - baseline-lexical top-3: []
- **R0-024** (keyword_sensitive, overlap 1.0): NS-KR2 return rate
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R2'] · ranks baseline-dense: {'NS-120': None}; baseline-lexical: {'NS-120': None}
  - baseline-dense top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B12']
  - baseline-lexical top-3: []
- **R0-027** (keyword_sensitive, overlap 0.5): Pull up review RV-00655 — what was the customer's experience?
  - expected ['NORTHSTAR/REVIEWS@v1:R656'] · ranks baseline-dense: {'NS-148': None}; baseline-lexical: {'NS-148': None}
  - baseline-dense top-3: ['NORTHSTAR/REVIEWS@v1:R574', 'NORTHSTAR/PERSO-PILOT@v1:S1.B8', 'NORTHSTAR/REVIEWS@v1:R683']
  - baseline-lexical top-3: []
- **R0-040** (semantic_paraphrase, overlap 0.091): Rather than fighting for the pro-athlete crowd, what reputation is the company trying to own with younger shoppers?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2'] · ranks baseline-dense: {'NS-005': 12}; baseline-lexical: {'NS-005': None}
  - baseline-dense top-3: ['NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P4.B1']
  - baseline-lexical top-3: []
- **R0-045** (semantic_paraphrase, overlap 0.0): Under what condition does the strategy team's next-year plan say bespoke products should move beyond a small trial?
  - expected ['NORTHSTAR/FY27-MEMO@v1:S1.B6'] · ranks baseline-dense: {'NS-102': 24}; baseline-lexical: {'NS-102': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/PACE-DECK@v1:SL2', 'NORTHSTAR/Q3-REVIEW@v1:SL15']
  - baseline-lexical top-3: []


## Distractor outranking

- **baseline-dense**: distractor above the true parent in 0/6 items with a ledger distractor
- **baseline-lexical**: distractor above the true parent in 0/6 items with a ledger distractor
