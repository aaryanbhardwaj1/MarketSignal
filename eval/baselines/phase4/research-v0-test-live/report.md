# Grounded evaluation: standard vs research

- Paired items: 34 (unpaired: none) · model `claude-sonnet-5-5` · git 8ae34ac · split test · 210.5 s standard / 494.1 s research
- Deltas are research - standard; 95% CIs are paired bootstrap (10000 resamples); rates also carry an exact McNemar p.

## Hard gates

| Gate | standard | research |
|---|---|---|
| citation_resolvability | 1.0 | 1.0 |
| citation_in_pack | 1.0 | 1.0 |
| every_run_done | 0 | 0 |
| answer_items_have_final | 0 | 0 |
| cross_workspace_leaks | 0 | 0 |
| empty_pack_never_calls_llm | not applicable | not applicable |

## Comparison

| Metric | standard | research | research - standard (95% CI) | n pairs |
|---|---|---|---|---|
| behaviour_pass | 1 | 0.9706 | -0.0294 [-0.0882, 0] · McNemar p=1 | 34 |
| answered | 0.9412 | 0.9412 | 0 [-0.0882, 0.0882] · McNemar p=1 | 34 |
| gold_coverage | 0.8218 | 0.9368 | 0.1149 [0.023, 0.2241] | 29 |
| answer_completeness | 0.7356 | 0.7471 | 0.0115 [0, 0.0345] | 29 |
| gold_handle_recall | 0.7944 | 0.9056 | 0.1111 [0.0278, 0.2167] | 30 |
| unsupported_claim_rate | 0 | 0.0046 | 0.0046 [0, 0.0138] | 31 |
| first_token_ms | 2088 | 2260 | 172.4 [-614.2, 949.2] | 34 |
| total_ms | 6091 | 1.443e+04 | 8339 [7062, 9564] | 34 |
| model_calls | 1 | 3.971 | 2.971 [2.735, 3.206] | 34 |
| tool_calls | 0 | 3.735 | 3.735 [3.147, 4.382] | 34 |
| retrieval_calls | 1 | 2.824 | 1.823 [1.323, 2.412] | 34 |
| tokens_total | 5212 | 2.039e+04 | 1.518e+04 [1.333e+04, 1.708e+04] | 34 |
| cost_usd | 0.0134 | 0.0364 | 0.0229 [0.0195, 0.0264] | 34 |

## Cost, effort and termination

| | standard | research |
|---|---|---|
| model calls (total / mean) | 34 / 1 | 135 / 3.971 |
| tool calls (total / mean) | 0 / 0 | 127 / 3.735 |
| tool failures (total / mean) | 0 / 0 | 0 / 0 |
| retrieval calls (total / mean) | 34 / 1 | 96 / 2.824 |
| agent steps (total / mean) | 0 / 0 | 101 / 2.971 |
| tokens in / out / cache read / cache write | 132679 / 18658 / 25874 / 0 | 393067 / 39814 / 260497 / 0 |
| cost USD (total / per run) | 0.457106 / 0.013444 | 1.236373 / 0.036364 |
| first token ms p50 / p95 | 1584 / 4581 | 1572 / 5332 |
| end-to-end ms p50 / p95 | 5782 / 9247 | 1.44e+04 / 2.028e+04 |
| research fallbacks | 0 | 0 |
| regenerations | 0 | 0 |
| evidence-only fallbacks | 0 | 0 |
| behaviour pass | 34/34 | 33/34 |
| gold coverage (cited, mean) | 0.7944 | 0.9368 |
| answer completeness (mean) | 0.7111 | 0.7471 |
| gold handle recall (pack, mean) | 0.7944 | 0.9056 |
| unsupported cited units | 0/225 (0) | 1/236 (0.0042) |
| conflict coverage | 2/2 | 2/2 |
| abstention correct | 4/4 | 4/4 |
| routes decided | {'standard': 34} | {'research': 34} |
| agent stop reasons | - | {'end_turn': 2, 'finish_research': 24, 'step_limit': 8} |
| termination states | {'completed': 34} | {'completed': 34} |

## By category

### conflict_search (n=2)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 1 | 1 | 0 |
| answer_completeness | 1 | 1 | 0 |
| gold_handle_recall | 1 | 1 | 0 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 863 | 2725 | 1862 |
| total_ms | 6855 | 1.465e+04 | 7791 |
| model_calls | 1 | 3.5 | 2.5 |
| tool_calls | 0 | 3 | 3 |
| retrieval_calls | 1 | 1.5 | 0.5 |
| tokens_total | 6534 | 1.986e+04 | 1.333e+04 |
| cost_usd | 0.018 | 0.0372 | 0.0192 |

### customer_competitor (n=3)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 1 | 1 | 0 |
| answer_completeness | 0.5 | 0.5 | 0 |
| gold_handle_recall | 1 | 1 | 0 |
| unsupported_claim_rate | 0 | 0.0476 | 0.0476 |
| first_token_ms | 1150 | 1350 | 200.7 |
| total_ms | 6111 | 1.407e+04 | 7959 |
| model_calls | 1 | 3.667 | 2.667 |
| tool_calls | 0 | 3.667 | 3.667 |
| retrieval_calls | 1 | 2.667 | 1.667 |
| tokens_total | 5681 | 2.109e+04 | 1.541e+04 |
| cost_usd | 0.0152 | 0.0404 | 0.0251 |

### customer_internal (n=3)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 1 | 1 | 0 |
| answer_completeness | 0.6667 | 0.6667 | 0 |
| gold_handle_recall | 1 | 1 | 0 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 2683 | 2206 | -476.7 |
| total_ms | 6928 | 1.439e+04 | 7460 |
| model_calls | 1 | 3.333 | 2.333 |
| tool_calls | 0 | 2.667 | 2.667 |
| retrieval_calls | 1 | 2 | 1 |
| tokens_total | 5276 | 1.657e+04 | 1.129e+04 |
| cost_usd | 0.0141 | 0.0317 | 0.0176 |

### first_pass_insufficient (n=4)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 0.7917 | 1 | 0.2083 |
| answer_completeness | 0.7917 | 0.875 | 0.0833 |
| gold_handle_recall | 0.7917 | 1 | 0.2083 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 2248 | 2034 | -214 |
| total_ms | 7389 | 1.485e+04 | 7459 |
| model_calls | 1 | 4.25 | 3.25 |
| tool_calls | 0 | 3.25 | 3.25 |
| retrieval_calls | 1 | 2.25 | 1.25 |
| tokens_total | 4856 | 2.11e+04 | 1.625e+04 |
| cost_usd | 0.0144 | 0.0374 | 0.023 |

### identifier_then_semantic (n=4)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 0.5 | 0.625 | 0.125 |
| answer_completeness | 0.25 | 0.25 | 0 |
| gold_handle_recall | 0.5 | 0.625 | 0.125 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 1915 | 2072 | 156.8 |
| total_ms | 6187 | 1.58e+04 | 9610 |
| model_calls | 1 | 4.75 | 3.75 |
| tool_calls | 0 | 5.25 | 5.25 |
| retrieval_calls | 1 | 4 | 3 |
| tokens_total | 4900 | 2.29e+04 | 1.8e+04 |
| cost_usd | 0.0128 | 0.0399 | 0.0271 |

### insufficient_stop (n=4)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 0.5 | 0.75 | 0.25 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 2453 | 3456 | 1004 |
| total_ms | 4777 | 1.629e+04 | 1.151e+04 |
| model_calls | 1 | 4.25 | 3.25 |
| tool_calls | 0 | 4 | 4 |
| retrieval_calls | 1 | 3.5 | 2.5 |
| tokens_total | 4649 | 2.043e+04 | 1.578e+04 |
| cost_usd | 0.0103 | 0.0347 | 0.0244 |

### multi_class (n=3)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 0.8889 | 0.8889 | 0 |
| answer_completeness | 0.8889 | 0.8889 | 0 |
| gold_handle_recall | 0.8889 | 0.8889 | 0 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 2498 | 2645 | 147 |
| total_ms | 7354 | 1.759e+04 | 1.024e+04 |
| model_calls | 1 | 4.667 | 3.667 |
| tool_calls | 0 | 5.333 | 5.333 |
| retrieval_calls | 1 | 3.333 | 2.333 |
| tokens_total | 6459 | 2.866e+04 | 2.22e+04 |
| cost_usd | 0.0171 | 0.0522 | 0.0351 |

### reformulation (n=4)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 0.5 | 1 | 0.5 |
| answer_completeness | 0.75 | 0.75 | 0 |
| gold_handle_recall | 0.5 | 1 | 0.5 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 2204 | 2345 | 140.8 |
| total_ms | 6030 | 1.254e+04 | 6509 |
| model_calls | 1 | 3.75 | 2.75 |
| tool_calls | 0 | 2.75 | 2.75 |
| retrieval_calls | 1 | 1.5 | 0.5 |
| tokens_total | 5198 | 1.804e+04 | 1.285e+04 |
| cost_usd | 0.0134 | 0.0306 | 0.0172 |

### simple_control (n=7)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 0.8571 | -0.1429 |
| answered | 1 | 0.8571 | -0.1429 |
| gold_coverage | 1 | 1 | 0 |
| answer_completeness | 1 | 1 | 0 |
| gold_handle_recall | 0.8571 | 0.8571 | 0 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 2141 | 1880 | -260.8 |
| total_ms | 4954 | 1.218e+04 | 7228 |
| model_calls | 1 | 3.571 | 2.571 |
| tool_calls | 0 | 3.571 | 3.571 |
| retrieval_calls | 1 | 3.429 | 2.429 |
| tokens_total | 4784 | 1.783e+04 | 1.304e+04 |
| cost_usd | 0.0111 | 0.0313 | 0.0201 |

## Per-item failures

### standard

#### R-RF-06 (reformulation) - completed · stop None · flags []

**Q:** What was Northstar's company-wide promoter score across all age groups in Q2?

failures: contract ['uncited answer sentence: The evidence does not establish a company-wide Q2 promoter s']

```markdown
### Answer

The evidence does not establish a company-wide Q2 promoter score across all age groups. The only Q2 NPS figure is for Gen Z, and the 31 overall figure comes from the May survey, which is not identified as a Q2 measure [inference].

### Key findings

- Gen Z NPS fell to 22 in Q2 from 28 in Q1 [[NORTHSTAR/Q3-REVIEW@v1:SL3]].
- The May survey gave Gen Z an NPS of 22, customers aged 28 and older 49, and 31 overall [[NORTHSTAR/BRAND-STRATEGY@v1:P2.B2]].
- The survey covered 600 respondents: 400 Gen Z and 200 aged 28 and older [[NORTHSTAR/BRAND-STRATEGY@v1:P4.B1]].
- The survey's Gen Z result was 160 promoters, 168 passives and 72 detractors, and the older group's was 116 promoters, 66 passives and 18 detractors [[NORTHSTAR/BRAND-STRATEGY@v1:P4.B3]].

### Interpretation

The 31 overall figure in [[NORTHSTAR/BRAND-STRATEGY@v1:P2.B2]] may roughly correspond to Q2 timing, since the survey ran in May, but no item links it to Q2 reporting [inference]. The matching Gen Z value of 22 in both the survey [[NORTHSTAR/BRAND-STRATEGY@v1:P2.B2]] and the Q2 results [[NORTHSTAR/Q3-REVIEW@v1:SL3]] suggests the Q2 Gen Z figure may be drawn from the May survey, but this is not stated [inference].

### Gaps & unknowns

No item reports a company-wide NPS explicitly labelled as Q2. A Q2 NPS table or dashboard covering all age groups, or confirmation that the May survey result is the Q2 company-wide measure, would close the gap. The Q1 company-wide score is also not provided, so no quarter-over-quarter comparison is possible.
```
#### R-IS-04 (insufficient_stop) - completed · stop None · flags []

**Q:** How much debt does Northstar carry on its balance sheet?

failures: contract ['uncited answer sentence: The evidence does not state how much debt Northstar carries ']

```markdown
### Answer

The evidence does not state how much debt Northstar carries on its balance sheet. The provided Northstar items cover revenue, margin, survey responses and a personalization pilot, but none reports debt, borrowings or other balance-sheet liabilities [inference].

### Gaps & unknowns

No balance-sheet, debt, credit facility or leverage data for Northstar appears in the evidence [inference]. The Northstar financial excerpts address only net revenue, gross margin and Gen Z revenue share [inference]. A source that would close the gap: Northstar's audited financial statements or the balance sheet and debt footnotes in an annual report or lender disclosure.
```
#### R-IS-05 (insufficient_stop) - completed · stop None · flags []

**Q:** What royalty does Southpeak pay to license the waterproof membrane in its shell jackets?

failures: contract ['uncited answer sentence: The evidence does not state any royalty, licensing fee or li']

```markdown
### Answer

The evidence does not state any royalty, licensing fee or licensing arrangement for a waterproof membrane in Southpeak's shell jackets.

### Gaps & unknowns

None of the items mention a membrane licensor, a licensing agreement or royalty terms. The material covers brand strategy, board slides and customer survey responses, none of which address this. The survey responses that mention waterproofing concern rain pants, not shell jackets, and say nothing about the membrane or its sourcing [inference]. A supplier or licensing contract, a cost-of-goods breakdown, or finance or procurement documents on technology licences would close this gap.
```

### research

#### R-CC-01 (customer_competitor) - completed · stop end_turn · flags []

**Q:** An interviewee put a number on how much extra they would pay for a shoe built from a scan of their foot. How does that compare with what Kinetic Lab charges for its custom runner?

failures: unsupported numbers ['7']

```markdown
### Answer

The interviewee said she would pay "maybe ten or fifteen dollars more" for a shoe built around her foot scan, but not fifty [[NORTHSTAR/INTERVIEWS@v1:S9.Q1]]. Kinetic Lab charges $210 for its custom runner [[NORTHSTAR/KINETIC-WEB@v1:S1.B6]]. The two figures measure different things: hers is an extra premium over a standard shoe, while $210 is Kinetic Lab's full price, so the evidence gives no direct like-for-like comparison [inference].

### Key findings

- Interview 7 (Maya R.) would pay "maybe ten or fifteen dollars more" for a shoe built from her foot scan, "but not fifty"; at fifty she would "just buy two pairs on sale" [[NORTHSTAR/INTERVIEWS@v1:S9.Q1]].
- Kinetic Lab prices its custom runner at $210 [[NORTHSTAR/KINETIC-WEB@v1:S1.B6]]; other sources give the same price [[NORTHSTAR/Q3-REVIEW@v1:SL13]][[NORTHSTAR/BRAND-STRATEGY@v1:P5.B3]].
- Kinetic Lab also charges $35 for a rescan fitting, though one rescan is included in the first 30 days of its fit guarantee [[NORTHSTAR/KINETIC-WEB@v1:S1.B6]].
- Kinetic Lab's trainer starts at a lower price than its custom runner [[NORTHSTAR/KINETIC-WEB@v1:S1.B6]].
- A survey respondent separately said she would pay "maybe 15% more" for shoes made to her foot, conditional on normal delivery speed [[NORTHSTAR/SURVEY-2026@v1:R389]].

### Interpretation

Because the interviewee's willingness to pay is stated only as an increment, it can be compared with $210 only if a baseline price for a standard shoe is assumed, and the evidence does not supply one [inference]. Her stated ceiling of fifty dollars extra suggests she would be sensitive to a large custom premium, but the evidence does not show how large Kinetic Lab's premium over its own or others' standard shoes is [inference].

### Gaps & unknowns

The evidence does not give the standard-shoe price the interviewee had in mind, nor Kinetic Lab's non-custom price points beyond noting that its trainer is cheaper. A competitor price list for comparable non-custom runners, or a survey that asks willingness to pay against a stated baseline price, would allow a like-for-like comparison [inference]. This is also a single interview, so it cannot be treated as representative [inference].
```
#### R-IS-04 (insufficient_stop) - completed · stop finish_research · flags []

**Q:** How much debt does Northstar carry on its balance sheet?

failures: contract ['uncited answer sentence: The evidence does not state how much debt Northstar carries.', 'uncited answer sentence: None of the provided items includes balance sheet, borrowing']

```markdown
### Answer

The evidence does not state how much debt Northstar carries. None of the provided items includes balance sheet, borrowing or liabilities data for Northstar.

### Key findings

- The Northstar survey rows contain customer attributes and feedback, not financial position data [[NORTHSTAR/SURVEY-2026@v1:R495]][[NORTHSTAR/SURVEY-2026@v1:R318]].
- The one balance sheet reference is for a different company, Kinetic Lab, which mentions a stronger balance sheet after a funding round [[NORTHSTAR/KINETIC-AR@v1:P2.B2]]. It gives no debt figure and says nothing about Northstar.

### Gaps & unknowns

Northstar's debt level is not established [inference]. The other sheets of the FY26 Financial Summary workbook may contain this, but only the Segment_Revenue sheet was provided [inference]. The evidence also does not say whether any debt figure would be net or gross, or how it is defined [inference].
```
#### R-IS-05 (insufficient_stop) - completed · stop finish_research · flags []

**Q:** What royalty does Southpeak pay to license the waterproof membrane in its shell jackets?

failures: contract ['uncited answer sentence: The evidence does not state any royalty that Southpeak pays ']

```markdown
### Answer

The evidence does not state any royalty that Southpeak pays to license a waterproof membrane for its shell jackets. None of the provided items mention a membrane, a licensing agreement or royalty terms [inference].

### Gaps & unknowns

The evidence does not establish whether Southpeak licenses a waterproof membrane at all, who the licensor is, or what royalty rate or fee applies. A supplier or licensing contract, a cost-of-goods breakdown for the Ridgeline shell jacket, or finance disclosures on royalty expenses would close this gap.
```
#### R-SC-04 (simple_control) - completed · stop step_limit · flags ['AGENT_STEP_BUDGET_EXHAUSTED']

**Q:** What conversion rate did millennial shoppers have on the Social Shop in September 2026?

failures: behaviour

```markdown
### Answer

The evidence does not state the millennial conversion rate on the Social Shop for September 2026 [inference]. The only relevant item is a table description that lists the relevant columns (channel, segment, month, conversion_rate_pct) but contains none of the actual values [inference].

### Gaps & unknowns

Other items discuss Social Shop growth and Gen Z conversion in qualitative terms, but give no millennial conversion figure for any month [inference]. Closing the gap requires the underlying Northstar Channel Performance table rows, filtered to channel, segment and month, or a report quoting that specific value.
```
