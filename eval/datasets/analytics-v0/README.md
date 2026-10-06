# analytics-v0

Phase 5 structured-analytics evaluation set: retrieval-only, analytics-only and mixed (quantitative + qualitative) questions over the fixed synthetic seed corpus. Built by `scripts/build_analytics_v0.py` (deterministic; `--check` diffs a rebuild against these files; `--verify-db` validates specs, the DB column profile, golds recomputed from `dataset_rows` and every evidence handle). Do not edit `items.json` by hand.

All data is fictional. Questions and ids are new; the ten retrieval-v0 items that task-types.json classifies `analytics`/`multi_tool` (unreachable for retrieval) are converted here with new wording (`converted_from`, provenance `converted:retrieval-v0:<id>`).

## How golds are computed

- Directly from the seed files in `seed_data/generated/{northstar,southpeak}` by an **independent reference implementation inside the builder**: stdlib `csv` (`utf-8-sig`), XLSX via `zipfile` + `ElementTree` (no openpyxl, no pandas), `decimal.Decimal` arithmetic (28 digits) and `ROUND_HALF_EVEN`. The product analytics engine is never imported, and no LLM is involved.
- XLSX numeric cells are IEEE doubles; they are read at Excel's 15-significant-digit display precision (`9.199999999999999` -> `9.2`), which is also what ingestion stores (checked by `--verify-db`).
- Golds are computed twice from two fresh loads and must be identical (build fails otherwise). `--verify-db` recomputes every gold a third time from the ingested `dataset_rows` values and requires identical values, exacts, denominators and warnings.
- Ledger cross-check: where `seed_data/fact_ledger.json` states the value (row anchors, plus the survey shares NS-004 and SP-C02 restated in documents), `ledger_crosscheck` records ledger vs computed value; any mismatch fails the build. 18 checks across 17 items, all matching.

### Semantics and rounding (brief rules; interpretation recorded per value)

`half_even; share/percent 1dp; currency_usd 2dp; mean/median non-currency 2dp; ratio 3dp; counts, integer sums, min/max exact`.

- `share` = 100 x rows satisfying the condition / filtered rows with a non-null value in the condition column (`numerator`, `denominator`), 1 dp.
- `count` counts filtered rows; `count_distinct` counts distinct non-null values; numeric metrics exclude empty cells (`NULLS_EXCLUDED`, reflected in `denominator`).
- `mean`/`median` of a `_pct` column are treated as percent (1 dp); of currency (`_usd`, `_usd_m`, `_usd_bn`, `price_usd`) 2 dp; otherwise (nps, rating, price_sensitivity) 2 dp. **Interpretation choice:** if the engine rounds means of percent columns to 2 dp, compare on `exact`. Affected items: `A-AVG-05`, `A-GRP-06`, `A-CMP-02`, `A-NUL-01`, `A-NUL-03`, `A-NUL-04`.
- `sum` of integer values and `min`/`max` are exact; median over an even base = mean of the two middle values.
- `group_compare` difference = A - B computed on the exact values, then rounded with the metric's rule.
- Empty selection: `count` = 0, other metrics null; `EMPTY_SELECTION` always, plus `ZERO_DENOMINATOR` for share/mean/median.
- `filter_rows` lookups return the raw cell (`exact`) and the row handle.

## Schema

`id, workspace, task_type (retrieval|analytics|mixed), category, question, expect (answer|insufficient|no_result|invalid), gold{analytics[], evidence[], expected_point}, router_expectation, family, group, split, notes, provenance, converted_from, invalid_reason, canary_must_not_appear, max_conf, ledger_crosscheck, leakage`.

- `gold.analytics[]`: `tool` (aggregate|group_compare|filter_rows), `dataset` (`<SOURCE_CODE>:<sheet_ordinal>`, scoped by `workspace`), `spec` (a valid `AggregateIn`/`GroupCompareIn`/`FilterRowsIn` dict - one acceptable spec, not the only one), `answer_kind` (scalar|top_n|breakdown|compare|lookup), `values[]` (`group`, `metric`, `value` rounded, `exact`, `unit`, `rounding`, `denominator`, `numerator` for shares, `handle` for lookups), `difference` (compare), `rows_matched`, `rows_scanned`, `warnings`.
- `gold.evidence[]`: `kind: rows` (survey/review row parents selected by filters and optional keywords - any-of handles, `row_keys` gives respondent/review ids) or `kind: document` (ledger fact with research-v0 / retrieval-v0 reviewed handles, any-of). Every listed evidence entry is required; `expected_point` is the qualitative claim the answer should make.
- `max_conf`: highest source confidentiality among the item's datasets vs the workspace's `llm_max_confidentiality` (DB: NORTHSTAR = `confidential`, SOUTHPEAK = `confidential`). Confidential FIN-SUMMARY-FY26 items therefore expect an answer; if a workspace is lowered below `confidential`, those items must flip to `insufficient`.

## Counts

| category | task_type | dev | holdout | total |
|---|---|---|---|---|
| average | analytics | 4 | 2 | 6 |
| exact_count | analytics | 4 | 2 | 6 |
| filtered_aggregation | analytics | 2 | 3 | 5 |
| grouped_comparison | analytics | 1 | 5 | 6 |
| invalid_request | analytics | 3 | 4 | 7 |
| median_min_max | analytics | 1 | 4 | 5 |
| mixed | mixed | 4 | 6 | 10 |
| no_result | analytics | 2 | 2 | 4 |
| null_missing | analytics | 2 | 2 | 4 |
| percentage_share | analytics | 3 | 3 | 6 |
| retrieval_only | retrieval | 2 | 4 | 6 |
| row_lookup | analytics | 4 | 5 | 9 |
| segment_compare | analytics | 2 | 5 | 7 |
| top_bottom | analytics | 2 | 7 | 9 |
| **all** | | 36 | 54 | 90 |

| task_type | dev | holdout |
|---|---|---|
| analytics | 30 | 44 |
| mixed | 4 | 6 |
| retrieval | 2 | 4 |

Workspaces: {'NORTHSTAR': 72, 'SOUTHPEAK': 18}. Expect: {'answer': 79, 'insufficient': 4, 'invalid': 3, 'no_result': 4}. Router expectation: {'analytics': 74, 'mixed': 10, 'retrieval': 6}.

## Data notes

- Columns with empty cells (checked over every seed table): `CATEGORY-SIZING:1.yoy_growth_pct` (9 of 54, base years) and `FIN-SUMMARY-FY26:1.yoy_change_pct` (3 of 10, percent lines; confidential). No other seed column has empties, so `null_missing` items use these two.
- `CATEGORY-SIZING:1.category` is profiled as `text` (free_text, 3 distinct values); items filtering on it (`A-NUL-01`, `A-LKP-06`) need eq on text columns.
- `no_result` items use valid levels/ranges whose intersection is empty (so the expected outcome is `EMPTY_SELECTION`, not a validation error).
- `invalid_request`: `unknown_column` and `dataset_not_in_workspace` expect `insufficient`; `unsupported_computation` (correlation, forecast, standard deviation) expects `invalid` (a safe refusal; the model must not compute it itself). `A-INV-04` asks NORTHSTAR for Southpeak's channel data: the SOUTHPEAK canary SP-C06 must not appear.

## Converted retrieval-v0 items

| retrieval-v0 | type | analytics-v0 | gold |
|---|---|---|---|
| R0-009 | analytics | A-LKP-01 | 3.4 |
| R0-010 | analytics | A-LKP-02 | 21.3 |
| R0-015 | analytics | A-LKP-03 | 44.5 |
| R0-017 | analytics | A-LKP-04 | 4.9 |
| R0-021 | analytics | A-TOP-07 | Studio Contour Legging: 212400 |
| R0-023 | analytics | A-TOP-08 | Switchback Trail: 41 |
| R0-024 | analytics | A-LKP-05 | 16.8 |
| R0-048 | multi_tool | A-MIX-09 | 2960 |
| R0-050 | multi_tool | A-MIX-10 | 3.4 |
| R0-058 | analytics | A-CMP-07 | 16.8 vs 13.1 (diff 3.7) |

## Split

69 groups. Items are union-found when they share a question family (dataset + family label), a ledger fact or an evidence handle; whole groups go to dev (~40%) or holdout by a greedy pass (largest first, ties by sha256(`analytics-v0`:group)) followed by deterministic single-group flips that reduce the squared deviation per category, per task_type and overall.

Holdout hash (sha256 of the canonical JSON of the holdout items, sorted by id): `5e471b90fb62c55411db976866a9551336e7d7fcac2723f98d40a282974b1d71`.

## Leakage

Each question is compared with every retrieval-v0 (frozen, dev and test), grounded-v0 and research-v0 question by normalized-token Jaccard (all tokens, and content tokens without stopwords); the build fails above 0.6. Exact copies and duplicate questions also fail.

| item | split | answer | max J (all) | nearest | max J (content) | nearest |
|---|---|---|---|---|---|---|
| A-CNT-01 | dev | 76 | 0.161 | R-FP-04 (research-v0) | 0.130 | R-FP-04 (research-v0) |
| A-CNT-02 | dev | 2 | 0.167 | R-IT-02 (research-v0) | 0.176 | R-IT-02 (research-v0) |
| A-CNT-03 | holdout | 20 | 0.200 | G-A4 (grounded-v0) | 0.133 | R0-033 (retrieval-v0 test) |
| A-CNT-04 | holdout | 59 | 0.158 | G-E2 (grounded-v0) | 0.154 | R0-025 (retrieval-v0 test) |
| A-CNT-05 | dev | 8 | 0.161 | R-IT-02 (research-v0) | 0.111 | R-IT-02 (research-v0) |
| A-CNT-06 | dev | 2 | 0.136 | R-SC-09 (research-v0) | 0.154 | R0-027 (retrieval-v0 dev) |
| A-SHR-01 | holdout | 27.0 (108/400) | 0.276 | R-SC-07 (research-v0) | 0.300 | R-SC-07 (research-v0) |
| A-SHR-02 | holdout | 26.0 (52/200) | 0.250 | R-SC-07 (research-v0) | 0.211 | R-SC-07 (research-v0) |
| A-SHR-03 | dev | 33.0 (99/300) | 0.438 | R0-031 (retrieval-v0 test) | 0.364 | R0-031 (retrieval-v0 test) |
| A-SHR-04 | holdout | 38.5 (5/13) | 0.200 | R-SC-05 (research-v0) | 0.231 | R0-028 (retrieval-v0 test) |
| A-SHR-05 | dev | 35.6 (37/104) | 0.147 | R-IT-04 (research-v0) | 0.105 | R-SC-03 (research-v0) |
| A-SHR-06 | dev | 25.0 (18/72) | 0.179 | R0-065 (retrieval-v0 test) | 0.143 | R0-031 (retrieval-v0 test) |
| A-AVG-01 | holdout | 7.9 | 0.111 | R0-009 (retrieval-v0 dev) | 0.118 | R-SC-07 (research-v0) |
| A-AVG-02 | dev | 3.9 | 0.179 | R0-040 (retrieval-v0 dev) | 0.167 | R-SC-07 (research-v0) |
| A-AVG-03 | holdout | 3.78 | 0.182 | R0-037 (retrieval-v0 dev) | 0.154 | R0-015 (retrieval-v0 test) |
| A-AVG-04 | dev | 92.85 | 0.242 | R-IT-04 (research-v0) | 0.250 | R-IT-04 (research-v0) |
| A-AVG-05 | dev | 6.5 | 0.222 | R0-017 (retrieval-v0 dev) | 0.231 | R0-017 (retrieval-v0 dev) |
| A-AVG-06 | dev | 7.02 | 0.190 | R0-021 (retrieval-v0 test) | 0.154 | R0-031 (retrieval-v0 test) |
| A-MMM-01 | dev | 76.0 | 0.200 | R0-021 (retrieval-v0 test) | 0.125 | R-RF-06 (research-v0) |
| A-MMM-02 | holdout | 5.5 | 0.278 | R-SC-05 (research-v0) | 0.250 | R0-024 (retrieval-v0 dev) |
| A-MMM-03 | holdout | 39.5 | 0.267 | R0-015 (retrieval-v0 test) | 0.273 | R0-015 (retrieval-v0 test) |
| A-MMM-04 | holdout | 4569331 | 0.190 | G-I7 (grounded-v0) | 0.083 | G-I1 (grounded-v0) |
| A-MMM-05 | holdout | 8.0 | 0.188 | G-I5 (grounded-v0) | 0.125 | R-SC-07 (research-v0) |
| A-GRP-01 | holdout | 5 groups | 0.150 | R0-009 (retrieval-v0 dev) | 0.176 | R0-009 (retrieval-v0 dev) |
| A-GRP-02 | holdout | 5 groups | 0.261 | R0-012 (retrieval-v0 test) | 0.167 | R0-012 (retrieval-v0 test) |
| A-GRP-03 | dev | 5 groups | 0.212 | R0-052 (retrieval-v0 test) | 0.125 | R0-007 (retrieval-v0 test) |
| A-GRP-04 | holdout | 7 groups | 0.136 | R0-010 (retrieval-v0 test) | 0.125 | R0-010 (retrieval-v0 test) |
| A-GRP-05 | holdout | 7 groups | 0.111 | R0-017 (retrieval-v0 dev) | 0.176 | R-IT-02 (research-v0) |
| A-GRP-06 | holdout | 10 groups | 0.261 | R0-009 (retrieval-v0 dev) | 0.294 | R0-009 (retrieval-v0 dev) |
| A-FLT-01 | holdout | 28284 | 0.350 | R0-009 (retrieval-v0 dev) | 0.400 | R0-009 (retrieval-v0 dev) |
| A-FLT-02 | holdout | 63902415 | 0.250 | R0-015 (retrieval-v0 test) | 0.273 | R0-015 (retrieval-v0 test) |
| A-FLT-03 | holdout | 900299 | 0.167 | R0-003 (retrieval-v0 test) | 0.118 | R0-003 (retrieval-v0 test) |
| A-FLT-04 | dev | 4.03 | 0.167 | R0-010 (retrieval-v0 test) | 0.176 | R0-010 (retrieval-v0 test) |
| A-FLT-05 | dev | 3.38 | 0.167 | R-SC-04 (research-v0) | 0.062 | R0-059 (retrieval-v0 dev) |
| A-CMP-01 | holdout | 7.9 vs 7.88 (diff 0.02) | 0.103 | R-FP-04 (research-v0) | 0.100 | R-IT-04 (research-v0) |
| A-CMP-02 | holdout | 2.9 vs 1.9 (diff 1.0) | 0.300 | R0-009 (retrieval-v0 dev) | 0.357 | R-SC-04 (research-v0) |
| A-CMP-03 | holdout | 11.8 vs 12.5 (diff -0.7) | 0.143 | R0-028 (retrieval-v0 test) | 0.188 | R0-028 (retrieval-v0 test) |
| A-CMP-04 | holdout | 15.8 vs 13.9 (diff 1.9) | 0.194 | G-A2 (grounded-v0) | 0.083 | G-A2 (grounded-v0) |
| A-CMP-05 | dev | 4.22 vs 4.18 (diff 0.03) | 0.158 | G-I8 (grounded-v0) | 0.091 | G-I8 (grounded-v0) |
| A-CMP-06 | holdout | 143.09 vs 117.8 (diff 25.29) | 0.286 | R-IT-04 (research-v0) | 0.235 | R-IT-04 (research-v0) |
| A-CMP-07 | dev | 16.8 vs 13.1 (diff 3.7) | 0.316 | R-SC-05 (research-v0) | 0.308 | R0-058 (retrieval-v0 dev) |
| A-TOP-01 | holdout | Studio Contour Legging: 12020317 | 0.182 | R-IS-03 (research-v0) | 0.167 | R0-008 (retrieval-v0 dev) |
| A-TOP-02 | holdout | Knit Runner 2: 3.4 | 0.167 | R-FP-06 (research-v0) | 0.105 | R-IT-03 (research-v0) |
| A-TOP-03 | holdout | Outerwear and Hoodies: 73.2 | 0.200 | R-SC-04 (research-v0) | 0.200 | R0-017 (retrieval-v0 dev) |
| A-TOP-04 | dev | Crew Sock 3 Pack: 209 | 0.158 | G-A4 (grounded-v0) | 0.100 | R0-021 (retrieval-v0 test) |
| A-TOP-05 | holdout | Mountain West: 41.2 | 0.111 | R0-044 (retrieval-v0 dev) | 0.154 | R0-031 (retrieval-v0 test) |
| A-TOP-06 | holdout | Studio Contour Legging: 6783 | 0.286 | R0-023 (retrieval-v0 test) | 0.308 | R0-023 (retrieval-v0 test) |
| A-TOP-07 | holdout | Studio Contour Legging: 212400 | 0.161 | R-IT-02 (research-v0) | 0.125 | R-IT-02 (research-v0) |
| A-TOP-08 | holdout | Switchback Trail: 41 | 0.346 | R0-023 (retrieval-v0 test) | 0.312 | R0-023 (retrieval-v0 test) |
| A-TOP-09 | dev | Gen Z (18-27): 13.8 | 0.167 | R-RF-02 (research-v0) | 0.125 | R-RF-02 (research-v0) |
| A-NUL-01 | dev | 23.2 | 0.346 | R0-060 (retrieval-v0 dev) | 0.316 | R0-060 (retrieval-v0 dev) |
| A-NUL-02 | holdout | 9 | 0.217 | R-SC-09 (research-v0) | 0.188 | R-SC-03 (research-v0) |
| A-NUL-03 | holdout | 9.0 | 0.160 | R0-021 (retrieval-v0 test) | 0.095 | R-SC-01 (research-v0) |
| A-NUL-04 | dev | 6.7 | 0.182 | R0-032 (retrieval-v0 dev) | 0.100 | R-RF-06 (research-v0) |
| A-NOR-01 | dev | 0 | 0.176 | R0-056 (retrieval-v0 dev) | 0.100 | G-I2 (grounded-v0) |
| A-NOR-02 | holdout | null | 0.158 | R0-008 (retrieval-v0 dev) | 0.062 | G-A4 (grounded-v0) |
| A-NOR-03 | holdout | null | 0.263 | R-SC-02 (research-v0) | 0.154 | R0-017 (retrieval-v0 dev) |
| A-NOR-04 | dev | 0 | 0.167 | R0-031 (retrieval-v0 test) | 0.154 | R0-031 (retrieval-v0 test) |
| A-INV-01 | dev | insufficient | 0.208 | R0-012 (retrieval-v0 test) | 0.105 | R-IT-03 (research-v0) |
| A-INV-02 | dev | invalid | 0.133 | R-FP-04 (research-v0) | 0.143 | R0-031 (retrieval-v0 test) |
| A-INV-03 | holdout | invalid | 0.250 | R0-015 (retrieval-v0 test) | 0.231 | R0-015 (retrieval-v0 test) |
| A-INV-04 | dev | insufficient | 0.200 | R0-009 (retrieval-v0 dev) | 0.231 | R0-017 (retrieval-v0 dev) |
| A-INV-05 | holdout | insufficient | 0.231 | R0-015 (retrieval-v0 test) | 0.182 | R0-015 (retrieval-v0 test) |
| A-INV-06 | holdout | insufficient | 0.143 | R0-025 (retrieval-v0 test) | 0.182 | R0-025 (retrieval-v0 test) |
| A-INV-07 | holdout | invalid | 0.167 | R0-053 (retrieval-v0 dev) | 0.118 | R-IT-02 (research-v0) |
| A-RET-01 | holdout | answer | 0.118 | R0-005 (retrieval-v0 dev) | 0.111 | R0-065 (retrieval-v0 test) |
| A-RET-02 | holdout | answer | 0.227 | R0-016 (retrieval-v0 dev) | 0.200 | R0-016 (retrieval-v0 dev) |
| A-RET-03 | dev | answer | 0.250 | R-RF-03 (research-v0) | 0.267 | R-SC-08 (research-v0) |
| A-RET-04 | dev | answer | 0.258 | R0-064 (retrieval-v0 dev) | 0.160 | R0-064 (retrieval-v0 dev) |
| A-RET-05 | holdout | answer | 0.190 | R0-007 (retrieval-v0 test) | 0.231 | R0-007 (retrieval-v0 test) |
| A-RET-06 | holdout | answer | 0.267 | R0-039 (retrieval-v0 test) | 0.182 | R0-039 (retrieval-v0 test) |
| A-MIX-01 | holdout | Campus Competitors: 9.4 (9/96) | 0.185 | R0-031 (retrieval-v0 test) | 0.143 | R0-057 (retrieval-v0 test) |
| A-MIX-02 | holdout | 68 | 0.208 | R0-031 (retrieval-v0 test) | 0.174 | R0-038 (retrieval-v0 dev) |
| A-MIX-03 | holdout | 3.0 | 0.226 | R-IT-03 (research-v0) | 0.174 | R-IT-01 (research-v0) |
| A-MIX-04 | holdout | Urban Outdoor: 13.9 (10/72) | 0.162 | R-FP-06 (research-v0) | 0.120 | R0-052 (retrieval-v0 test) |
| A-MIX-05 | dev | 10.5 (13/124) | 0.227 | R0-031 (retrieval-v0 test) | 0.133 | R0-031 (retrieval-v0 test) |
| A-MIX-06 | dev | 6.2 (6/96) | 0.237 | R0-052 (retrieval-v0 test) | 0.107 | R0-052 (retrieval-v0 test) |
| A-MIX-07 | dev | 3.0 (9/300) | 0.273 | R0-031 (retrieval-v0 test) | 0.231 | R0-031 (retrieval-v0 test) |
| A-MIX-08 | holdout | 4.67 | 0.240 | R0-033 (retrieval-v0 test) | 0.176 | G-A4 (grounded-v0) |
| A-MIX-09 | holdout | 2960 | 0.324 | R0-048 (retrieval-v0 dev) | 0.333 | R0-048 (retrieval-v0 dev) |
| A-MIX-10 | dev | 3.4 | 0.360 | R0-009 (retrieval-v0 dev) | 0.381 | R0-009 (retrieval-v0 dev) |
| A-LKP-01 | dev | 3.4 | 0.476 | R-SC-04 (research-v0) | 0.400 | R0-009 (retrieval-v0 dev) |
| A-LKP-02 | holdout | 21.3 | 0.429 | R0-010 (retrieval-v0 test) | 0.467 | R0-010 (retrieval-v0 test) |
| A-LKP-03 | holdout | 44.5 | 0.250 | R0-015 (retrieval-v0 test) | 0.231 | R0-015 (retrieval-v0 test) |
| A-LKP-04 | dev | 4.9 | 0.294 | R0-017 (retrieval-v0 dev) | 0.273 | R0-017 (retrieval-v0 dev) |
| A-LKP-05 | dev | 16.8 | 0.190 | R-SC-05 (research-v0) | 0.105 | R-IT-06 (research-v0) |
| A-LKP-06 | holdout | 18.6 | 0.379 | R0-060 (retrieval-v0 dev) | 0.300 | R0-060 (retrieval-v0 dev) |
| A-LKP-07 | holdout | 47.2 | 0.211 | R0-008 (retrieval-v0 dev) | 0.231 | R0-008 (retrieval-v0 dev) |
| A-LKP-08 | dev | 96.0 | 0.304 | R0-010 (retrieval-v0 test) | 0.263 | R-IT-04 (research-v0) |
| A-LKP-09 | holdout | 19.4 | 0.421 | G-C3 (grounded-v0) | 0.462 | G-C3 (grounded-v0) |

Highest similarity: A-LKP-01 (0.476).

## Caveats

- A gold `spec` is one valid way to compute the answer; graders should compare values (and `exact` within rounding), not spec equality. Lookups are expressed with `filter_rows`; an `aggregate` max/min over the same filters is equally valid.
- Mixed items' row evidence is any-of over all matching rows; `expected_point` paraphrases the recurring verbatim themes and was written by reading those rows.
- `router_expectation` is judged from the question text alone.
- Single author; no second reviewer for questions or expected points.
