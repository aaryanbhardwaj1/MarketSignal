# Phase 2 milestone: TEST split, c2 index (untouched baselines A/B and c2 pipeline arms)

- Split: **test**, items: 21
- Dataset: `retrieval-v0` · corpus `d68f6473052e` · ledger `95e9bb87bae7`
- Run: git=6f7486c, at=2026-10-05T23:22:45+00:00, config_hash=5cd88fc3abc551f6, milestone=phase2-final: frozen config c3 hybrid+rerank; this invocation = c2 index (untouched baselines + c2 arms)

## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)

| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| baseline-dense | 28.6 [13.8, 50.0] | 47.6 [28.3, 67.6] | 57.1 [36.5, 75.5] | 51.6 [31.0, 71.4] | 56.3 [35.7, 76.2] | 38.3 [21.3, 56.8] | 13.26 | 23.0 |
| baseline-lexical | 4.8 [0.8, 22.7] | 4.8 [0.8, 22.7] | 4.8 [0.8, 22.7] | 4.8 [0.0, 14.3] | 4.8 [0.0, 14.3] | 4.8 [0.0, 14.3] | 2.33 | 2.43 |
| dense@c2 | 28.6 [13.8, 50.0] | 47.6 [28.3, 67.6] | 57.1 [36.5, 75.5] | 51.6 [31.0, 71.4] | 56.3 [35.7, 76.2] | 38.3 [21.3, 56.8] | 12.27 | 19.24 |
| lexical@c2 | 19.0 [7.7, 40.0] | 38.1 [20.8, 59.1] | 52.4 [32.4, 71.7] | 46.8 [26.2, 67.5] | 54.0 [33.3, 74.6] | 27.9 [13.3, 44.9] | 12.93 | 32.39 |
| hybrid@c2 | 28.6 [13.8, 50.0] | 52.4 [32.4, 71.7] | 61.9 [40.9, 79.2] | 56.3 [35.7, 76.2] | 56.3 [35.7, 76.2] | 39.2 [22.4, 57.4] | 26.3 | 35.42 |
| dense-rerank@c2 | 42.9 [24.5, 63.5] | 52.4 [32.4, 71.7] | 57.1 [36.5, 75.5] | 54.8 [33.3, 76.2] | 56.3 [35.7, 76.2] | 48.5 [29.0, 68.4] | 498.17 | 735.71 |
| hybrid-rerank@c2 | 42.9 [24.5, 63.5] | 52.4 [32.4, 71.7] | 52.4 [32.4, 71.7] | 50.0 [28.6, 71.4] | 56.3 [35.7, 76.2] | 48.2 [28.5, 68.0] | 676.91 | 863.77 |

## Latency by stage (ms, p50 / p95)

- **baseline-dense**: dense_ms 6.17/11.87, embed_ms 7.34/11.11, total_ms 13.26/23.0, wall_ms 13.67/23.54
- **baseline-lexical**: lexical_ms 2.33/2.43, total_ms 2.33/2.43, wall_ms 2.6/2.78
- **dense@c2**: dense_ms 4.13/6.99, embed_ms 6.03/10.05, fusion_ms 0.31/0.66, total_ms 12.27/19.24, wall_ms 12.71/19.95
- **lexical@c2**: fusion_ms 0.3/0.7, lexical_ms 10.34/26.26, lexical_prep_ms 0.64/1.48, total_ms 12.93/32.39, wall_ms 13.46/33.26
- **hybrid@c2**: dense_ms 3.84/4.41, embed_ms 5.28/10.07, fusion_ms 0.55/0.61, lexical_ms 10.58/19.85, lexical_prep_ms 0.74/0.94, total_ms 26.3/35.42, wall_ms 26.75/35.98
- **dense-rerank@c2**: dense_ms 11.94/20.4, embed_ms 7.82/13.14, fusion_ms 0.31/0.41, hydrate_ms 2.09/3.11, rerank_ms 473.98/709.45, total_ms 498.17/735.71, wall_ms 499.43/739.08
- **hybrid-rerank@c2**: dense_ms 13.18/21.5, embed_ms 8.75/29.61, fusion_ms 0.62/0.87, hydrate_ms 1.32/2.05, lexical_ms 25.81/40.4, lexical_prep_ms 1.55/2.19, rerank_ms 613.49/749.31, total_ms 676.91/863.77, wall_ms 681.2/866.63

## By category (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| category | n | baseline-dense | baseline-lexical | dense@c2 | lexical@c2 | hybrid@c2 | dense-rerank@c2 | hybrid-rerank@c2 |
|---|---|---|---|---|---|---|---|---|
| ambiguous_distractor | 1 | 0/1 · 1/1 · 0.50 | 0/1 · 0/1 · 0.00 | 0/1 · 1/1 · 0.50 | 0/1 · 1/1 · 0.50 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 |
| cross_format | 1 | 0/1 · 1/1 · 0.33 | 0/1 · 0/1 · 0.00 | 0/1 · 1/1 · 0.33 | 0/1 · 1/1 · 0.33 | 0/1 · 1/1 · 0.50 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 |
| customer_free_text | 2 | 0/2 · 0/2 · 0.04 | 0/2 · 0/2 · 0.00 | 0/2 · 0/2 · 0.04 | 0/2 · 0/2 · 0.02 | 0/2 · 0/2 · 0.04 | 0/2 · 0/2 · 0.04 | 0/2 · 0/2 · 0.04 |
| enumeration | 1 | 0/1 · 1/1 · 0.17 | 0/1 · 0/1 · 0.00 | 0/1 · 1/1 · 0.17 | 0/1 · 1/1 · 0.17 | 0/1 · 1/1 · 0.25 | 0/1 · 0/1 · 0.09 | 0/1 · 0/1 · 0.07 |
| exact_number | 3 | 1/3 · 1/3 · 0.33 | 0/3 · 0/3 · 0.00 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.33 |
| keyword_sensitive | 3 | 1/3 · 2/3 · 0.38 | 0/3 · 0/3 · 0.00 | 1/3 · 2/3 · 0.38 | 1/3 · 1/3 · 0.34 | 1/3 · 2/3 · 0.37 | 1/3 · 2/3 · 0.45 | 1/3 · 2/3 · 0.45 |
| named_entity | 3 | 0/3 · 1/3 · 0.17 | 0/3 · 0/3 · 0.00 | 0/3 · 1/3 · 0.17 | 0/3 · 1/3 · 0.07 | 0/3 · 1/3 · 0.17 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.33 |
| semantic_paraphrase | 3 | 2/3 · 3/3 · 0.75 | 0/3 · 0/3 · 0.00 | 2/3 · 3/3 · 0.75 | 0/3 · 1/3 · 0.07 | 1/3 · 3/3 · 0.50 | 1/3 · 3/3 · 0.56 | 1/3 · 2/3 · 0.53 |
| single_source_fact | 3 | 1/3 · 1/3 · 0.36 | 1/3 · 1/3 · 0.33 | 1/3 · 1/3 · 0.36 | 1/3 · 3/3 · 0.46 | 1/3 · 2/3 · 0.43 | 2/3 · 2/3 · 0.67 | 2/3 · 2/3 · 0.68 |
| versioning | 1 | 1/1 · 1/1 · 1.00 | 0/1 · 0/1 · 0.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 |

## By source format (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| source format | n | baseline-dense | baseline-lexical | dense@c2 | lexical@c2 | hybrid@c2 | dense-rerank@c2 | hybrid-rerank@c2 |
|---|---|---|---|---|---|---|---|---|
| csv | 7 | 0/7 · 3/7 · 0.10 | 0/7 · 0/7 · 0.00 | 0/7 · 3/7 · 0.10 | 0/7 · 2/7 · 0.08 | 0/7 · 3/7 · 0.13 | 1/7 · 2/7 · 0.22 | 1/7 · 2/7 · 0.21 |
| docx | 2 | 0/2 · 1/2 · 0.13 | 0/2 · 0/2 · 0.00 | 0/2 · 1/2 · 0.13 | 0/2 · 2/2 · 0.17 | 0/2 · 2/2 · 0.25 | 1/2 · 1/2 · 0.55 | 1/2 · 1/2 · 0.54 |
| markdown | 2 | 2/2 · 2/2 · 1.00 | 1/2 · 1/2 · 0.50 | 2/2 · 2/2 · 1.00 | 1/2 · 2/2 · 0.55 | 2/2 · 2/2 · 1.00 | 2/2 · 2/2 · 1.00 | 2/2 · 2/2 · 1.00 |
| pdf | 8 | 3/8 · 7/8 · 0.57 | 0/8 · 0/8 · 0.00 | 3/8 · 7/8 · 0.57 | 2/8 · 6/8 · 0.42 | 3/8 · 7/8 · 0.57 | 5/8 · 7/8 · 0.71 | 5/8 · 6/8 · 0.70 |
| pptx | 1 | 1/1 · 1/1 · 1.00 | 0/1 · 0/1 · 0.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 |
| xlsx | 3 | 0/3 · 0/3 · 0.00 | 0/3 · 0/3 · 0.00 | 0/3 · 0/3 · 0.00 | 0/3 · 0/3 · 0.00 | 0/3 · 0/3 · 0.00 | 0/3 · 0/3 · 0.00 | 0/3 · 0/3 · 0.00 |

## By overlap bin (hit@1 · hit@10 · MRR; cells with n < 10 as k/n)

| overlap bin | n | baseline-dense | baseline-lexical | dense@c2 | lexical@c2 | hybrid@c2 | dense-rerank@c2 | hybrid-rerank@c2 |
|---|---|---|---|---|---|---|---|---|
| high | 1 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 | 1/1 · 1/1 · 1.00 |
| low | 8 | 2/8 · 5/8 · 0.32 | 0/8 · 0/8 · 0.00 | 2/8 · 5/8 · 0.32 | 0/8 · 2/8 · 0.05 | 1/8 · 5/8 · 0.23 | 1/8 · 4/8 · 0.26 | 1/8 · 3/8 · 0.25 |
| mid | 12 | 25.0% · 50.0% · 0.38 | 0.0% · 0.0% · 0.00 | 25.0% · 50.0% · 0.38 | 25.0% · 66.7% · 0.37 | 33.3% · 58.3% · 0.45 | 58.3% · 58.3% · 0.59 | 58.3% · 58.3% · 0.59 |

## Paired comparisons (same items)

| Comparison | hit@1 (only ref / only other, p) | hit@10 (…) | ΔMRR [95% CI] | Δrecall@10 [95% CI] |
|---|---|---|---|---|
| baseline-dense->baseline-lexical | 5 / 0, p=0.0625 | 11 / 0, p=0.001 | -0.335 [-0.513, -0.173] | -0.468 [-0.667, -0.270] |
| baseline-dense->dense@c2 | 0 / 0, p=1.0 | 0 / 0, p=1.0 | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] |
| baseline-dense->lexical@c2 | 2 / 0, p=0.5 | 3 / 2, p=1.0 | -0.104 [-0.235, -0.003] | -0.048 [-0.238, +0.143] |
| baseline-dense->hybrid@c2 | 1 / 1, p=1.0 | 0 / 1, p=1.0 | +0.009 [-0.078, +0.085] | +0.048 [+0.000, +0.143] |
| baseline-dense->dense-rerank@c2 | 1 / 4, p=0.375 | 1 / 1, p=1.0 | +0.102 [-0.019, +0.234] | +0.032 [-0.048, +0.143] |
| baseline-dense->hybrid-rerank@c2 | 1 / 4, p=0.375 | 2 / 1, p=1.0 | +0.099 [-0.024, +0.233] | -0.016 [-0.159, +0.127] |

## Failure buckets at k=10: baseline-dense|baseline-lexical

### both_miss (9)

- **R0-003** (single_source_fact, overlap 0.5): Where and over what dates did Northstar's spring 2026 personalization pilot run, and how many customers did it reach?
  - expected ['NORTHSTAR/PERSO-PILOT@v1:S1.B3'] · ranks baseline-dense: {'NS-053': 11}; baseline-lexical: {'NS-053': None}
  - baseline-dense top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
  - baseline-lexical top-3: []
- **R0-010** (exact_number, overlap 0.4): What was the Gen Z return rate on Northstar's brand site in August 2026?
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R102'] · ranks baseline-dense: {'NS-142': None}; baseline-lexical: {'NS-142': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - baseline-lexical top-3: []
- **R0-015** (exact_number, overlap 0.5): Running Footwear gross margin for August 2026
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH1.R135'] · ranks baseline-dense: {'NS-122': None}; baseline-lexical: {'NS-122': None}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
  - baseline-lexical top-3: []
- **R0-021** (named_entity, overlap 0.222): What is Northstar's best-selling product by units so far in FY26?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R14'] · ranks baseline-dense: {'NS-121': None}; baseline-lexical: {'NS-121': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
  - baseline-lexical top-3: []
- **R0-023** (named_entity, overlap 0.1): Which Northstar product had a big chunk of its Q3 2026 returns blamed on running small?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH3.R35'] · ranks baseline-dense: {'NS-124': None}; baseline-lexical: {'NS-124': None}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/SURVEY-2026@v1:R385', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2']
  - baseline-lexical top-3: []
- **R0-025** (keyword_sensitive, overlap 0.2): What did survey respondent R0147 say about sizing?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks baseline-dense: {'NS-143': 60}; baseline-lexical: {'NS-143': None}
  - baseline-dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R291', 'NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R247']
  - baseline-lexical top-3: []

### baseline-dense_only (11)

- **R0-012** (exact_number, overlap 0.583): In Q3 2026, what was the median first response time for customer contacts arriving via social channels?
  - expected ['NORTHSTAR/SUPPORT-THEMES@v1:P3.B3'] · ranks baseline-dense: {'NS-013': 1}; baseline-lexical: {'NS-013': None}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P3.B3', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/SURVEY-2026@v1:R555']
  - baseline-lexical top-3: []
- **R0-022** (named_entity, overlap 0.444): Which Gen Z customer group is Northstar's biggest and also spends the most per order?
  - expected ['NORTHSTAR/BRAND-STRATEGY@v1:P3.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL7'] · ranks baseline-dense: {'NS-007': 2}; baseline-lexical: {'NS-007': None}
  - baseline-dense top-3: ['NORTHSTAR/GENZ-FOCUS-GROUP@v1:S2.B1', 'NORTHSTAR/BRAND-STRATEGY@v1:P3.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1']
  - baseline-lexical top-3: []
- **R0-028** (keyword_sensitive, overlap 0.25): RV-00412 Knit Runner 2 durability complaint details
  - expected ['NORTHSTAR/REVIEWS@v1:R413'] · ranks baseline-dense: {'NS-147': 9}; baseline-lexical: {'NS-147': None}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2']
  - baseline-lexical top-3: []
- **R0-030** (keyword_sensitive, overlap 0.571): How many stores have Vantage's Fit Lab, and how many scans has it done?
  - expected ['NORTHSTAR/VANTAGE-DECK@v1:SL8.N1'] · ranks baseline-dense: {'NS-091': 1}; baseline-lexical: {'NS-091': None}
  - baseline-dense top-3: ['NORTHSTAR/VANTAGE-DECK@v1:SL8.N1', 'NORTHSTAR/VANTAGE-WEB@v1:S1.B7', 'NORTHSTAR/Q3-REVIEW@v1:SL13']
  - baseline-lexical top-3: []
- **R0-041** (semantic_paraphrase, overlap 0.062): How slowly did the care team typically get back to people who messaged through social apps last quarter, compared with the goal they had set?
  - expected ['NORTHSTAR/SUPPORT-THEMES@v1:P3.B3'] · ranks baseline-dense: {'NS-013': 1}; baseline-lexical: {'NS-013': None}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P3.B3', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B5']
  - baseline-lexical top-3: []
- **R0-043** (semantic_paraphrase, overlap 0.2): What slice of young buyers' sneaker purchases still happens at shops dedicated to runners?
  - expected ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5'] · ranks baseline-dense: {'NS-109': 1}; baseline-lexical: {'NS-109': None}
  - baseline-dense top-3: ['NORTHSTAR/CHANNEL-SHIFT@v1:S1.B5', 'NORTHSTAR/GENZ-TRENDS@v2:P2.B2', 'NORTHSTAR/REVIEWS@v1:R428']
  - baseline-lexical top-3: []


## Failure buckets at k=10: baseline-dense|dense@c2

### both_miss (9)

- **R0-003** (single_source_fact, overlap 0.5): Where and over what dates did Northstar's spring 2026 personalization pilot run, and how many customers did it reach?
  - expected ['NORTHSTAR/PERSO-PILOT@v1:S1.B3'] · ranks baseline-dense: {'NS-053': 11}; dense@c2: {'NS-053': 11}
  - baseline-dense top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
  - dense@c2 top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
- **R0-010** (exact_number, overlap 0.4): What was the Gen Z return rate on Northstar's brand site in August 2026?
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R102'] · ranks baseline-dense: {'NS-142': None}; dense@c2: {'NS-142': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - dense@c2 top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
- **R0-015** (exact_number, overlap 0.5): Running Footwear gross margin for August 2026
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH1.R135'] · ranks baseline-dense: {'NS-122': None}; dense@c2: {'NS-122': None}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
  - dense@c2 top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
- **R0-021** (named_entity, overlap 0.222): What is Northstar's best-selling product by units so far in FY26?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R14'] · ranks baseline-dense: {'NS-121': None}; dense@c2: {'NS-121': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
  - dense@c2 top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
- **R0-023** (named_entity, overlap 0.1): Which Northstar product had a big chunk of its Q3 2026 returns blamed on running small?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH3.R35'] · ranks baseline-dense: {'NS-124': None}; dense@c2: {'NS-124': None}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/SURVEY-2026@v1:R385', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2']
  - dense@c2 top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/SURVEY-2026@v1:R385', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2']
- **R0-025** (keyword_sensitive, overlap 0.2): What did survey respondent R0147 say about sizing?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks baseline-dense: {'NS-143': 60}; dense@c2: {'NS-143': 60}
  - baseline-dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R291', 'NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R247']
  - dense@c2 top-3: ['NORTHSTAR/SURVEY-2026@v1:R291', 'NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R247']


## Failure buckets at k=10: baseline-dense|lexical@c2

### lexical@c2_only (2)

- **R0-003** (single_source_fact, overlap 0.5): Where and over what dates did Northstar's spring 2026 personalization pilot run, and how many customers did it reach?
  - expected ['NORTHSTAR/PERSO-PILOT@v1:S1.B3'] · ranks baseline-dense: {'NS-053': 11}; lexical@c2: {'NS-053': 6}
  - baseline-dense top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
  - lexical@c2 top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B2']
- **R0-031** (single_source_fact, overlap 0.429): What do Southpeak's survey respondents name as their top issue?
  - expected ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3'] · ranks baseline-dense: {'SP-C02': None}; lexical@c2: {'SP-C02': 5}
  - baseline-dense top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R32', 'SOUTHPEAK/SURVEY-2026@v1:R177']
  - lexical@c2 top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P3.B2', 'SOUTHPEAK/BRAND-STRATEGY@v1:P2.B5', 'SOUTHPEAK/BOARD-DECK@v1:SL8']

### both_miss (7)

- **R0-010** (exact_number, overlap 0.4): What was the Gen Z return rate on Northstar's brand site in August 2026?
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R102'] · ranks baseline-dense: {'NS-142': None}; lexical@c2: {'NS-142': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - lexical@c2 top-3: ['NORTHSTAR/CHANNEL-PERF@v1:T1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B2', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-015** (exact_number, overlap 0.5): Running Footwear gross margin for August 2026
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH1.R135'] · ranks baseline-dense: {'NS-122': None}; lexical@c2: {'NS-122': None}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
  - lexical@c2 top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/PRODUCT-PERF@v1:SH1.T1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
- **R0-021** (named_entity, overlap 0.222): What is Northstar's best-selling product by units so far in FY26?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R14'] · ranks baseline-dense: {'NS-121': None}; lexical@c2: {'NS-121': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
  - lexical@c2 top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH1.T1', 'NORTHSTAR/PRODUCT-PERF@v1:SH2.T1', 'NORTHSTAR/VANTAGE-DECK@v1:SL5']
- **R0-023** (named_entity, overlap 0.1): Which Northstar product had a big chunk of its Q3 2026 returns blamed on running small?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH3.R35'] · ranks baseline-dense: {'NS-124': None}; lexical@c2: {'NS-124': None}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/SURVEY-2026@v1:R385', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2']
  - lexical@c2 top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2']
- **R0-025** (keyword_sensitive, overlap 0.2): What did survey respondent R0147 say about sizing?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks baseline-dense: {'NS-143': 60}; lexical@c2: {'NS-143': None}
  - baseline-dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R291', 'NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R247']
  - lexical@c2 top-3: ['NORTHSTAR/SURVEY-2026@v1:T1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/WTP-STUDY@v1:P3.B4']
- **R0-033** (customer_free_text, overlap 0.429): What did survey respondent R0147 say about how they buy leggings and tees?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks baseline-dense: {'NS-143': 39}; lexical@c2: {'NS-143': 55}
  - baseline-dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R33', 'NORTHSTAR/SURVEY-2026@v1:R29', 'NORTHSTAR/SURVEY-2026@v1:R518']
  - lexical@c2 top-3: ['NORTHSTAR/SURVEY-2026@v1:R18', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B3']

### baseline-dense_only (3)

- **R0-028** (keyword_sensitive, overlap 0.25): RV-00412 Knit Runner 2 durability complaint details
  - expected ['NORTHSTAR/REVIEWS@v1:R413'] · ranks baseline-dense: {'NS-147': 9}; lexical@c2: {'NS-147': 28}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/Q3-REVIEW@v1:SL8.N1', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2']
  - lexical@c2 top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL8', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/FY27-MEMO@v1:S1.B4']
- **R0-041** (semantic_paraphrase, overlap 0.062): How slowly did the care team typically get back to people who messaged through social apps last quarter, compared with the goal they had set?
  - expected ['NORTHSTAR/SUPPORT-THEMES@v1:P3.B3'] · ranks baseline-dense: {'NS-013': 1}; lexical@c2: {'NS-013': 13}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P3.B3', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B5']
  - lexical@c2 top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P4.B2', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P7.B2']
- **R0-047** (semantic_paraphrase, overlap 0.077): In the trade-off exercise, how did shoppers weigh getting a shoe shaped to their foot against picking their own colors?
  - expected ['NORTHSTAR/WTP-STUDY@v1:P2.B2', 'NORTHSTAR/WTP-STUDY@v1:P3.B2'] · ranks baseline-dense: {'NS-043': 4}; lexical@c2: {'NS-043': 29}
  - baseline-dense top-3: ['NORTHSTAR/WTP-STUDY@v1:P2.B1', 'NORTHSTAR/WTP-STUDY@v1:P1.B2', 'NORTHSTAR/VANTAGE-DECK@v1:SL9.N1']
  - lexical@c2 top-3: ['NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B6', 'NORTHSTAR/KINETIC-WEB@v1:S1.B7', 'NORTHSTAR/GENZ-TRENDS@v2:P3.B3']


## Failure buckets at k=10: baseline-dense|hybrid@c2

### hybrid@c2_only (1)

- **R0-003** (single_source_fact, overlap 0.5): Where and over what dates did Northstar's spring 2026 personalization pilot run, and how many customers did it reach?
  - expected ['NORTHSTAR/PERSO-PILOT@v1:S1.B3'] · ranks baseline-dense: {'NS-053': 11}; hybrid@c2: {'NS-053': 4}
  - baseline-dense top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
  - hybrid@c2 top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']

### both_miss (8)

- **R0-010** (exact_number, overlap 0.4): What was the Gen Z return rate on Northstar's brand site in August 2026?
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R102'] · ranks baseline-dense: {'NS-142': None}; hybrid@c2: {'NS-142': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - hybrid@c2 top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-015** (exact_number, overlap 0.5): Running Footwear gross margin for August 2026
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH1.R135'] · ranks baseline-dense: {'NS-122': None}; hybrid@c2: {'NS-122': None}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
  - hybrid@c2 top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3', 'NORTHSTAR/KINETIC-AR@v1:P4.B2']
- **R0-021** (named_entity, overlap 0.222): What is Northstar's best-selling product by units so far in FY26?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R14'] · ranks baseline-dense: {'NS-121': None}; hybrid@c2: {'NS-121': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
  - hybrid@c2 top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
- **R0-023** (named_entity, overlap 0.1): Which Northstar product had a big chunk of its Q3 2026 returns blamed on running small?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH3.R35'] · ranks baseline-dense: {'NS-124': None}; hybrid@c2: {'NS-124': None}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/SURVEY-2026@v1:R385', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2']
  - hybrid@c2 top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2']
- **R0-025** (keyword_sensitive, overlap 0.2): What did survey respondent R0147 say about sizing?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks baseline-dense: {'NS-143': 60}; hybrid@c2: {'NS-143': 114}
  - baseline-dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R291', 'NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R247']
  - hybrid@c2 top-3: ['NORTHSTAR/SURVEY-2026@v1:R369', 'NORTHSTAR/SURVEY-2026@v1:R97', 'NORTHSTAR/FY27-MEMO@v1:S1.B4']
- **R0-031** (single_source_fact, overlap 0.429): What do Southpeak's survey respondents name as their top issue?
  - expected ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3'] · ranks baseline-dense: {'SP-C02': None}; hybrid@c2: {'SP-C02': 22}
  - baseline-dense top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R32', 'SOUTHPEAK/SURVEY-2026@v1:R177']
  - hybrid@c2 top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/INTERVIEWS@v1:S2.B1', 'SOUTHPEAK/SURVEY-2026@v1:R210']


## Failure buckets at k=10: baseline-dense|dense-rerank@c2

### dense-rerank@c2_only (1)

- **R0-003** (single_source_fact, overlap 0.5): Where and over what dates did Northstar's spring 2026 personalization pilot run, and how many customers did it reach?
  - expected ['NORTHSTAR/PERSO-PILOT@v1:S1.B3'] · ranks baseline-dense: {'NS-053': 11}; dense-rerank@c2: {'NS-053': 1}
  - baseline-dense top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
  - dense-rerank@c2 top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/SURVEY-2026@v1:R596']

### both_miss (8)

- **R0-010** (exact_number, overlap 0.4): What was the Gen Z return rate on Northstar's brand site in August 2026?
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R102'] · ranks baseline-dense: {'NS-142': None}; dense-rerank@c2: {'NS-142': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - dense-rerank@c2 top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-015** (exact_number, overlap 0.5): Running Footwear gross margin for August 2026
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH1.R135'] · ranks baseline-dense: {'NS-122': None}; dense-rerank@c2: {'NS-122': None}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
  - dense-rerank@c2 top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/KINETIC-AR@v1:P4.B2', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
- **R0-021** (named_entity, overlap 0.222): What is Northstar's best-selling product by units so far in FY26?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R14'] · ranks baseline-dense: {'NS-121': None}; dense-rerank@c2: {'NS-121': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
  - dense-rerank@c2 top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/REVIEWS@v1:R666', 'NORTHSTAR/SURVEY-2026@v1:R161']
- **R0-023** (named_entity, overlap 0.1): Which Northstar product had a big chunk of its Q3 2026 returns blamed on running small?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH3.R35'] · ranks baseline-dense: {'NS-124': None}; dense-rerank@c2: {'NS-124': None}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/SURVEY-2026@v1:R385', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2']
  - dense-rerank@c2 top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/SURVEY-2026@v1:R369']
- **R0-025** (keyword_sensitive, overlap 0.2): What did survey respondent R0147 say about sizing?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks baseline-dense: {'NS-143': 60}; dense-rerank@c2: {'NS-143': 60}
  - baseline-dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R291', 'NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R247']
  - dense-rerank@c2 top-3: ['NORTHSTAR/SURVEY-2026@v1:R171', 'NORTHSTAR/SURVEY-2026@v1:R167', 'NORTHSTAR/SURVEY-2026@v1:R28']
- **R0-031** (single_source_fact, overlap 0.429): What do Southpeak's survey respondents name as their top issue?
  - expected ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3'] · ranks baseline-dense: {'SP-C02': None}; dense-rerank@c2: {'SP-C02': None}
  - baseline-dense top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R32', 'SOUTHPEAK/SURVEY-2026@v1:R177']
  - dense-rerank@c2 top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R117', 'SOUTHPEAK/SURVEY-2026@v1:R159']

### baseline-dense_only (1)

- **R0-054** (enumeration, overlap 0.316): Pull every individual customer voice (interviewees, survey verbatims, product reviews) describing the knit upper on their running shoes fraying, splitting or tearing early.
  - expected ['NORTHSTAR/INTERVIEWS@v1:S7.Q1', 'NORTHSTAR/REVIEWS@v1:R413', 'NORTHSTAR/SURVEY-2026@v1:R522'] · ranks baseline-dense: {'NS-062': 33, 'NS-145': 6, 'NS-147': 25}; dense-rerank@c2: {'NS-062': 33, 'NS-145': 11, 'NS-147': 25}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3']
  - dense-rerank@c2 top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/SURVEY-2026@v1:R43', 'NORTHSTAR/SURVEY-2026@v1:R299']


## Failure buckets at k=10: baseline-dense|hybrid-rerank@c2

### hybrid-rerank@c2_only (1)

- **R0-003** (single_source_fact, overlap 0.5): Where and over what dates did Northstar's spring 2026 personalization pilot run, and how many customers did it reach?
  - expected ['NORTHSTAR/PERSO-PILOT@v1:S1.B3'] · ranks baseline-dense: {'NS-053': 11}; hybrid-rerank@c2: {'NS-053': 1}
  - baseline-dense top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/PERSO-PILOT@v1:S1.B2', 'NORTHSTAR/Q3-REVIEW@v1:SL10']
  - hybrid-rerank@c2 top-3: ['NORTHSTAR/PERSO-PILOT@v1:S1.B3', 'NORTHSTAR/PERSO-PILOT@v1:S1.B1', 'NORTHSTAR/SURVEY-2026@v1:R596']

### both_miss (8)

- **R0-010** (exact_number, overlap 0.4): What was the Gen Z return rate on Northstar's brand site in August 2026?
  - expected ['NORTHSTAR/CHANNEL-PERF@v1:R102'] · ranks baseline-dense: {'NS-142': None}; hybrid-rerank@c2: {'NS-142': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1', 'NORTHSTAR/Q3-REVIEW@v1:SL3']
  - hybrid-rerank@c2 top-3: ['NORTHSTAR/ANALYST-CALL@v1:S1.B1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B1']
- **R0-015** (exact_number, overlap 0.5): Running Footwear gross margin for August 2026
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH1.R135'] · ranks baseline-dense: {'NS-122': None}; hybrid-rerank@c2: {'NS-122': None}
  - baseline-dense top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL4', 'NORTHSTAR/VANTAGE-DECK@v1:SL3']
  - hybrid-rerank@c2 top-3: ['NORTHSTAR/Q3-REVIEW@v1:SL4', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/BRAND-STRATEGY@v1:P5.B3']
- **R0-021** (named_entity, overlap 0.222): What is Northstar's best-selling product by units so far in FY26?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH2.R14'] · ranks baseline-dense: {'NS-121': None}; hybrid-rerank@c2: {'NS-121': None}
  - baseline-dense top-3: ['NORTHSTAR/BRAND-STRATEGY@v1:P1.B3', 'NORTHSTAR/Q3-REVIEW@v1:SL3', 'NORTHSTAR/Q3-REVIEW@v1:SL3.N1']
  - hybrid-rerank@c2 top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH2.T1', 'NORTHSTAR/FIN-SUMMARY-FY26@v1:SH1.T1', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B3']
- **R0-023** (named_entity, overlap 0.1): Which Northstar product had a big chunk of its Q3 2026 returns blamed on running small?
  - expected ['NORTHSTAR/PRODUCT-PERF@v1:SH3.R35'] · ranks baseline-dense: {'NS-124': None}; hybrid-rerank@c2: {'NS-124': None}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P1.B1', 'NORTHSTAR/SURVEY-2026@v1:R385', 'NORTHSTAR/BRAND-STRATEGY@v1:P1.B2']
  - hybrid-rerank@c2 top-3: ['NORTHSTAR/PRODUCT-PERF@v1:SH3.T1', 'NORTHSTAR/REVIEWS@v1:R664', 'NORTHSTAR/SUPPORT-THEMES@v1:P2.B1']
- **R0-025** (keyword_sensitive, overlap 0.2): What did survey respondent R0147 say about sizing?
  - expected ['NORTHSTAR/SURVEY-2026@v1:R148'] · ranks baseline-dense: {'NS-143': 60}; hybrid-rerank@c2: {'NS-143': 114}
  - baseline-dense top-3: ['NORTHSTAR/SURVEY-2026@v1:R291', 'NORTHSTAR/SURVEY-2026@v1:R356', 'NORTHSTAR/SURVEY-2026@v1:R247']
  - hybrid-rerank@c2 top-3: ['NORTHSTAR/SURVEY-2026@v1:R28', 'NORTHSTAR/SURVEY-2026@v1:R247', 'NORTHSTAR/SURVEY-2026@v1:R396']
- **R0-031** (single_source_fact, overlap 0.429): What do Southpeak's survey respondents name as their top issue?
  - expected ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B3'] · ranks baseline-dense: {'SP-C02': None}; hybrid-rerank@c2: {'SP-C02': 22}
  - baseline-dense top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/SURVEY-2026@v1:R32', 'SOUTHPEAK/SURVEY-2026@v1:R177']
  - hybrid-rerank@c2 top-3: ['SOUTHPEAK/BRAND-STRATEGY@v1:P2.B2', 'SOUTHPEAK/BRAND-STRATEGY@v1:P3.B2', 'SOUTHPEAK/BRAND-STRATEGY@v1:P2.B5']

### baseline-dense_only (2)

- **R0-047** (semantic_paraphrase, overlap 0.077): In the trade-off exercise, how did shoppers weigh getting a shoe shaped to their foot against picking their own colors?
  - expected ['NORTHSTAR/WTP-STUDY@v1:P2.B2', 'NORTHSTAR/WTP-STUDY@v1:P3.B2'] · ranks baseline-dense: {'NS-043': 4}; hybrid-rerank@c2: {'NS-043': 12}
  - baseline-dense top-3: ['NORTHSTAR/WTP-STUDY@v1:P2.B1', 'NORTHSTAR/WTP-STUDY@v1:P1.B2', 'NORTHSTAR/VANTAGE-DECK@v1:SL9.N1']
  - hybrid-rerank@c2 top-3: ['NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B6', 'NORTHSTAR/GENZ-TRENDS@v2:P3.B2', 'NORTHSTAR/ANALYST-CALL@v1:S1.B1']
- **R0-054** (enumeration, overlap 0.316): Pull every individual customer voice (interviewees, survey verbatims, product reviews) describing the knit upper on their running shoes fraying, splitting or tearing early.
  - expected ['NORTHSTAR/INTERVIEWS@v1:S7.Q1', 'NORTHSTAR/REVIEWS@v1:R413', 'NORTHSTAR/SURVEY-2026@v1:R522'] · ranks baseline-dense: {'NS-062': 33, 'NS-145': 6, 'NS-147': 25}; hybrid-rerank@c2: {'NS-062': 79, 'NS-145': 14, 'NS-147': 24}
  - baseline-dense top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P6.B3']
  - hybrid-rerank@c2 top-3: ['NORTHSTAR/SUPPORT-THEMES@v1:P2.B2', 'NORTHSTAR/BRAND-STRATEGY@v1:P4.B2', 'NORTHSTAR/SURVEY-2026@v1:R43']


## Distractor outranking

- **baseline-dense**: distractor above the true parent in 0/1 items with a ledger distractor
- **baseline-lexical**: distractor above the true parent in 0/1 items with a ledger distractor
- **dense@c2**: distractor above the true parent in 0/1 items with a ledger distractor
- **lexical@c2**: distractor above the true parent in 0/1 items with a ledger distractor
- **hybrid@c2**: distractor above the true parent in 0/1 items with a ledger distractor
- **dense-rerank@c2**: distractor above the true parent in 0/1 items with a ledger distractor
- **hybrid-rerank@c2**: distractor above the true parent in 0/1 items with a ledger distractor
