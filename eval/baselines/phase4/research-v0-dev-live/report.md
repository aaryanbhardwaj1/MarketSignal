# Grounded evaluation: standard vs research

- Paired items: 23 (unpaired: none) · model `claude-sonnet-5-5` · git bcc4621 · split dev · 162.5 s standard / 383.6 s research
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
| behaviour_pass | 1 | 1 | 0 [0, 0] · McNemar p=1 | 23 |
| answered | 0.913 | 0.9565 | 0.0435 [0, 0.1304] · McNemar p=1 | 23 |
| gold_coverage | 0.8095 | 0.8571 | 0.0476 [-0.0952, 0.1587] | 21 |
| answer_completeness | 0.7619 | 0.8571 | 0.0952 [0.0238, 0.1746] | 21 |
| gold_handle_recall | 0.8095 | 0.8571 | 0.0476 [-0.0952, 0.1587] | 21 |
| unsupported_claim_rate | 0 | 0.0139 | 0.0139 [0, 0.0372] | 21 |
| first_token_ms | 2286 | 1726 | -560.2 [-1293, 155.1] | 23 |
| total_ms | 6960 | 1.656e+04 | 9603 [7104, 1.25e+04] | 23 |
| model_calls | 1 | 4.261 | 3.261 [2.913, 3.609] | 23 |
| tool_calls | 0 | 4.043 | 4.043 [3.391, 4.783] | 23 |
| retrieval_calls | 1 | 2.87 | 1.87 [1.348, 2.435] | 23 |
| tokens_total | 5909 | 2.264e+04 | 1.673e+04 [1.414e+04, 1.936e+04] | 23 |
| cost_usd | 0.0154 | 0.0417 | 0.0264 [0.0216, 0.0314] | 23 |

## Cost, effort and termination

| | standard | research |
|---|---|---|
| model calls (total / mean) | 23 / 1 | 98 / 4.261 |
| tool calls (total / mean) | 0 / 0 | 93 / 4.043 |
| tool failures (total / mean) | 0 / 0 | 0 / 0 |
| retrieval calls (total / mean) | 23 / 1 | 66 / 2.87 |
| agent steps (total / mean) | 0 / 0 | 74 / 3.217 |
| tokens in / out / cache read / cache write | 104459 / 13940 / 16742 / 761 | 298696 / 31920 / 187843 / 2323 |
| cost USD (total / per run) | 0.353565 / 0.015372 | 0.959969 / 0.041738 |
| first token ms p50 / p95 | 1898 / 4497 | 1406 / 3404 |
| end-to-end ms p50 / p95 | 6917 / 1.067e+04 | 1.594e+04 / 2.36e+04 |
| research fallbacks | 0 | 0 |
| regenerations | 0 | 1 |
| evidence-only fallbacks | 0 | 0 |
| behaviour pass | 23/23 | 23/23 |
| gold coverage (cited, mean) | 0.8095 | 0.8571 |
| answer completeness (mean) | 0.7619 | 0.8571 |
| gold handle recall (pack, mean) | 0.8095 | 0.8571 |
| unsupported cited units | 0/169 (0) | 2/174 (0.0115) |
| conflict coverage | 1/3 | 2/3 |
| abstention correct | 2/2 | 2/2 |
| routes decided | {'standard': 23} | {'research': 23} |
| agent stop reasons | - | {'end_turn': 1, 'finish_research': 18, 'step_limit': 4} |
| termination states | {'completed': 23} | {'completed': 23} |

## By category

### conflict_search (n=3)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 0.7222 | 0.8333 | 0.1111 |
| answer_completeness | 0.5556 | 0.6667 | 0.1111 |
| gold_handle_recall | 0.7222 | 0.8333 | 0.1111 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 3241 | 1504 | -1738 |
| total_ms | 9001 | 1.842e+04 | 9422 |
| model_calls | 1 | 4.333 | 3.333 |
| tool_calls | 0 | 5 | 5 |
| retrieval_calls | 1 | 3.333 | 2.333 |
| tokens_total | 6530 | 2.764e+04 | 2.111e+04 |
| cost_usd | 0.0182 | 0.0555 | 0.0373 |

### customer_competitor (n=2)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 1 | 1 | 0 |
| answer_completeness | 0.75 | 1 | 0.25 |
| gold_handle_recall | 1 | 1 | 0 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 1609 | 1219 | -390.1 |
| total_ms | 6445 | 1.293e+04 | 6487 |
| model_calls | 1 | 3.5 | 2.5 |
| tool_calls | 0 | 4 | 4 |
| retrieval_calls | 1 | 2.5 | 1.5 |
| tokens_total | 5638 | 1.935e+04 | 1.371e+04 |
| cost_usd | 0.0151 | 0.0371 | 0.0219 |

### customer_internal (n=2)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 0.75 | 1 | 0.25 |
| answer_completeness | 0.5 | 0.75 | 0.25 |
| gold_handle_recall | 0.75 | 1 | 0.25 |
| unsupported_claim_rate | 0 | 0.0455 | 0.0455 |
| first_token_ms | 1653 | 2926 | 1273 |
| total_ms | 5591 | 1.306e+04 | 7469 |
| model_calls | 1 | 3 | 2 |
| tool_calls | 0 | 2 | 2 |
| retrieval_calls | 1 | 2 | 1 |
| tokens_total | 6516 | 1.366e+04 | 7139 |
| cost_usd | 0.0163 | 0.0264 | 0.0101 |

### first_pass_insufficient (n=2)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 1 | 1 | 0 |
| answer_completeness | 1 | 1 | 0 |
| gold_handle_recall | 1 | 1 | 0 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 2742 | 1005 | -1737 |
| total_ms | 7335 | 1.473e+04 | 7400 |
| model_calls | 1 | 4.5 | 3.5 |
| tool_calls | 0 | 4 | 4 |
| retrieval_calls | 1 | 2.5 | 1.5 |
| tokens_total | 6534 | 2.376e+04 | 1.722e+04 |
| cost_usd | 0.0172 | 0.0423 | 0.0251 |

### identifier_then_semantic (n=2)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 0.5 | 0.75 | 0.25 |
| answer_completeness | 0.75 | 0.75 | 0 |
| gold_handle_recall | 0.5 | 0.75 | 0.25 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 1387 | 1684 | 297.1 |
| total_ms | 5678 | 1.641e+04 | 1.073e+04 |
| model_calls | 1 | 4.5 | 3.5 |
| tool_calls | 0 | 5.5 | 5.5 |
| retrieval_calls | 1 | 3.5 | 2.5 |
| tokens_total | 5878 | 2.33e+04 | 1.742e+04 |
| cost_usd | 0.0151 | 0.0432 | 0.028 |

### insufficient_stop (n=2)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 0 | 0.5 | 0.5 |
| first_token_ms | 1767 | 1485 | -281.8 |
| total_ms | 4226 | 1.325e+04 | 9025 |
| model_calls | 1 | 4 | 3 |
| tool_calls | 0 | 3 | 3 |
| retrieval_calls | 1 | 2.5 | 1.5 |
| tokens_total | 5225 | 1.83e+04 | 1.307e+04 |
| cost_usd | 0.0107 | 0.0292 | 0.0185 |

### multi_class (n=3)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 0.7778 | 1 | 0.2222 |
| answer_completeness | 0.7778 | 1 | 0.2222 |
| gold_handle_recall | 0.7778 | 1 | 0.2222 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 1604 | 957.6 | -646.8 |
| total_ms | 7686 | 2.64e+04 | 1.871e+04 |
| model_calls | 1 | 5 | 4 |
| tool_calls | 0 | 5.667 | 5.667 |
| retrieval_calls | 1 | 4.333 | 3.333 |
| tokens_total | 6137 | 3.207e+04 | 2.593e+04 |
| cost_usd | 0.0186 | 0.0623 | 0.0437 |

### reformulation (n=2)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 1 | 1 | 0 |
| answer_completeness | 0.5 | 0.5 | 0 |
| gold_handle_recall | 1 | 1 | 0 |
| unsupported_claim_rate | 0 | 0 | 0 |
| first_token_ms | 1295 | 1925 | 630.3 |
| total_ms | 3811 | 1.57e+04 | 1.189e+04 |
| model_calls | 1 | 4 | 3 |
| tool_calls | 0 | 3.5 | 3.5 |
| retrieval_calls | 1 | 2.5 | 1.5 |
| tokens_total | 6282 | 2.051e+04 | 1.423e+04 |
| cost_usd | 0.0143 | 0.0378 | 0.0235 |

### simple_control (n=5)

| Metric | standard | research | Δ |
|---|---|---|---|
| behaviour_pass | 1 | 1 | 0 |
| answered | 1 | 1 | 0 |
| gold_coverage | 0.8 | 0.6 | -0.2 |
| answer_completeness | 1 | 1 | 0 |
| gold_handle_recall | 0.8 | 0.6 | -0.2 |
| unsupported_claim_rate | 0 | 0.04 | 0.04 |
| first_token_ms | 3426 | 2363 | -1063 |
| total_ms | 8770 | 1.486e+04 | 6091 |
| model_calls | 1 | 4.6 | 3.6 |
| tool_calls | 0 | 3.4 | 3.4 |
| retrieval_calls | 1 | 2.4 | 1.4 |
| tokens_total | 5150 | 2.078e+04 | 1.563e+04 |
| cost_usd | 0.0132 | 0.035 | 0.0218 |

## Per-item failures

### standard

#### R-MC-01 (multi_class) - completed · stop None · flags []

**Q:** How far behind its rivals is Northstar with Gen Z? Give Northstar's aided awareness among Gen Z, Vantage Athletic's FY2025 revenue scale, and the share of Pace & Co.'s active customers who are Gen Z.

failures: contract ["uncited answer sentence: The evidence does not state what share of Pace & Co.'s activ"]

```markdown
### Answer

Northstar's aided awareness among Gen Z is 46%, against 71% for Vantage Athletic [[NORTHSTAR/BRAND-STRATEGY@v1:P1.B2]][[NORTHSTAR/VANTAGE-DECK@v1:SL10]]. Vantage's FY2025 net revenue is about $4.2 billion [[NORTHSTAR/BRAND-STRATEGY@v1:P5.B2]]. The evidence does not state what share of Pace & Co.'s active customers are Gen Z.

### Key findings

- Northstar's aided brand awareness among Gen Z consumers stands at 46%, well behind the 71% recorded for Vantage Athletic [[NORTHSTAR/BRAND-STRATEGY@v1:P1.B2]].
- Vantage itself states that its aided awareness among Gen Z stands at 71% [[NORTHSTAR/VANTAGE-DECK@v1:SL10]].
- Vantage Athletic had FY2025 net revenue of about $4.2 billion, with footwear making up 63% of sales [[NORTHSTAR/BRAND-STRATEGY@v1:P5.B2]].
- Northstar's net revenue is on track to grow from $571.0 million in FY25 to a latest estimate of $612.0 million in FY26 [[NORTHSTAR/BRAND-STRATEGY@v1:P1.B2]].
- Gen Z shoppers generated 21% of Northstar net revenue in FY25, up from 17% two years earlier, with a board target of 30% by the end of FY28 [[NORTHSTAR/BRAND-STRATEGY@v1:P1.B2]].
- Gen Z NPS for Northstar is 22, against 49 among customers aged 28 and older [[NORTHSTAR/BRAND-STRATEGY@v1:P2.B2]].
- Pace & Co. is described as winning on price and cadence, and Value Seekers (26% of Northstar's Gen Z base) trade freely between Northstar and Pace & Co. [[NORTHSTAR/Q3-REVIEW@v1:SL13.N1]][[NORTHSTAR/BRAND-STRATEGY@v1:P3.B5]].

### Conflicting evidence

- The Q3 review states that aided awareness trails Vantage Athletic by 25 points [[NORTHSTAR/Q3-REVIEW@v1:SL6]]. The brand strategy gives 46% against 71% [[NORTHSTAR/BRAND-STRATEGY@v1:P1.B2]], and the stated gap is consistent with those two figures. However, E2 notes that figures were restated or superseded, so the current value should be confirmed.
- Gen Z survey sample size differs: the strategy document cites 600 respondents in total [[NORTHSTAR/BRAND-STRATEGY@v1:P1.B2]], while the Q3 review and NPS breakdown cite 400 Gen Z respondents [[NORTHSTAR/Q3-REVIEW@v1:SL6]][[NORTHSTAR/BRAND-STRATEGY@v1:P4.B3]]. These may be different subsets (all respondents versus Gen Z only), but this is not stated explicitly.

### Interpretation

Northstar is substantially smaller than Vantage in both revenue and awareness, so the Gen Z gap is a reach problem more than a reputation problem, consistent with the document's own diagnosis [[NORTHSTAR/BRAND-STRATEGY@v1:P2.B2]] [inference].

### Gaps & unknowns

The evidence contains no figure for the share of Pace & Co.'s active customers who are Gen Z, and no Pace & Co. revenue or awareness data [inference]. A Pace & Co. investor or public disclosure, or a third-party customer panel covering that brand, would close this gap. The evidence also does not clarify which Gen Z definition underlies the awareness figures, since teams use differing definitions [inference].
```
#### R-CF-05 (conflict_search) - completed · stop None · flags []

**Q:** Should Northstar lead its Gen Z messaging with personalization? Check what framing excited the focus group most, and where personalization landed when participants allocated a fixed budget of points across benefits.

failures: contract ['uncited answer sentence: No, the evidence does not support leading Gen Z messaging wi']

```markdown
### Answer

No, the evidence does not support leading Gen Z messaging with personalization. It drew the strongest reaction in the focus group when framed as a status signal friends would notice [[NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B6]], but in the points allocation exercise participants ranked fit guarantee, faster delivery and honest materials information ahead of it. The focus group summary itself recommends positioning personalization as a gifting, team and status feature rather than the lead reason to buy [[NORTHSTAR/GENZ-FOCUS-GROUP@v1:S4.B1]].

### Key findings

- The framing that excited the group most was personalization as a status signal, such as initials on a heel tab or a team colorway; several participants said they would post a personalized pair before a standard one [[NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B6]].
- In the hypothetical 100-point allocation, personalization did not lead; fit guarantee, faster delivery and honest materials information ranked ahead [[NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B6]].
- Participants described a well-fitting, quickly delivered shoe as something they need and a personalized shoe as something they would enjoy [[NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B6]].
- The focus group implications recommend testing personalization in small steps instead of leading with it [[NORTHSTAR/GENZ-FOCUS-GROUP@v1:S4.B1]].
- The pilot readout states that the hypothesis that young customers will pay a premium for made-for-them products is not supported in the form tested, and that long delivery waits were the main reason people did not return [[NORTHSTAR/PERSO-PILOT@v1:S1.B2]].
- The May survey found personalization was named by a small share of respondents as their top frustration, while fit inconsistency led [[NORTHSTAR/FY27-MEMO@v1:S1.B4]].
- The planning memo recommends keeping personalization a limited test in FY27 [[NORTHSTAR/FY27-MEMO@v1:S1.B6]], and the Q3 review asks to hold it at a limited test [[NORTHSTAR/Q3-REVIEW@v1:SL14]].

### Conflicting evidence

- An early July read of the pilot suggested a more favorable picture, but it was based on week six data and a very small sample and is described as superseded by the final results [[NORTHSTAR/PERSO-PILOT@v1:S1.B2]].
- Stated willingness to pay was real in the March study (roughly two in five would pay about 15% more) [[NORTHSTAR/PERSO-PILOT@v1:S1.B9]], but revealed uptake of the paid tier was less than a quarter of the stated share; the pilot readout advises using revealed behavior for revenue assumptions.

### Interpretation

Personalization is better suited to a secondary role in messaging, such as gifting, team and status content, than to the headline benefit [inference]. Leading with it would promise something customers rank below fit and delivery speed, and the pilot's slow lead time could undercut the promise [inference].

### Gaps & unknowns

The focus group had only ten participants and its allocation exercise was hypothetical, so the ranking is directional, not statistical [inference]. The evidence does not include message testing of personalization-led versus fit-led copy with a larger Gen Z sample, and it does not show how personalization-led messaging would affect acquisition. A/B message tests or a quantitative survey with a larger sample would close these gaps.
```
#### R-IS-01 (insufficient_stop) - completed · stop None · flags []

**Q:** How many patents does Kinetic Lab hold on its phone foot-scanning technology?

failures: contract ['uncited answer sentence: The evidence does not state how many patents Kinetic Lab hol', 'uncited answer sentence: None of the provided items mention patents, patent filings o']

```markdown
### Answer

The evidence does not state how many patents Kinetic Lab holds on its phone foot-scanning technology. None of the provided items mention patents, patent filings or intellectual property holdings.

### Gaps & unknowns

The evidence describes the scan process, the fit system and the micro factory, but never addresses patent ownership or counts [inference]. A patent registry search (for example national or international patent office databases, filtered by assignee), or an IP or risk-factors section of a company filing, would close this gap. The annual report excerpts provided are partial, so a full annual report or investor materials might disclose intellectual property holdings [inference].
```
#### R-IS-06 (insufficient_stop) - completed · stop None · flags []

**Q:** How did Northstar's share price react after the Q3 strategy review?

failures: contract ["uncited answer sentence: The evidence does not say how Northstar's share price reacte", 'uncited answer sentence: None of the provided items contains share price, stock marke']

```markdown
### Answer

The evidence does not say how Northstar's share price reacted after the Q3 strategy review. None of the provided items contains share price, stock market or investor reaction data.

### Gaps & unknowns

No item reports any share price, trading volume or market reaction following the review. The review is only described through a title slide and a next-steps slide, and neither covers external market response [inference]. A market data source (exchange price history around the review date), analyst or investor commentary, or an investor relations release would close this gap. It is also unclear from the evidence whether Northstar is publicly listed, which would need to be confirmed from a corporate filing or company profile.
```

### research

#### R-CI-02 (customer_internal) - completed · stop finish_research · flags []

**Q:** What made a shopper who loved the custom colorway tool give up on ordering, and what did Northstar leadership decide about personalization at the Q3 strategy review?

failures: unsupported numbers ['12']

```markdown
### Answer

A shopper who loved the custom colorway tool gave up on ordering because of the twelve day wait [[NORTHSTAR/INTERVIEWS@v1:S14.Q1]]. At the Q3 strategy review, leadership agreed to pause any national rollout of personalization until the full pilot readout in October, and the decision requested was to hold it at a limited test [[NORTHSTAR/Q3-REVIEW@v1:SL14.N1]][[NORTHSTAR/Q3-REVIEW@v1:SL14]].

### Key findings

- Interview 12 (Sam K.) said he "loved" the custom colorway tool, but "the twelve day wait killed it for me" [[NORTHSTAR/INTERVIEWS@v1:S14.Q1]].
- Sam K. said that if the order had come in a few days, he "would have bought two pairs" [[NORTHSTAR/INTERVIEWS@v1:S14.Q1]].
- Other pilot-related feedback also points to waiting time as a barrier: one interviewee loved the online colorway tool but abandoned the order after seeing the wait [[NORTHSTAR/PERSO-PILOT@v1:S1.B8]].
- Leadership agreed to pause any national rollout of personalization until the full pilot readout in October [[NORTHSTAR/Q3-REVIEW@v1:SL14.N1]].
- The stated reasoning was that the early signal came from a tiny sample and the operational constraints are significant [[NORTHSTAR/Q3-REVIEW@v1:SL14.N1]].
- The Q3 review's first decision requested was to "Hold personalization at a limited test and defer any national rollout decision" [[NORTHSTAR/Q3-REVIEW@v1:SL14]].

### Conflicting evidence

- The Q3 review's reasoning cites an early signal from a tiny sample [[NORTHSTAR/Q3-REVIEW@v1:SL14.N1]]. The pilot final readout says an early read circulated in July suggested a more favorable picture, but it was based on week six data and a very small sample and "should be treated as superseded" [[NORTHSTAR/PERSO-PILOT@v1:S1.B2]].
- The final readout states the evidence does not support the hypothesis that young customers will pay a premium for made-for-them products, in the form tested [[NORTHSTAR/PERSO-PILOT@v1:S1.B2]]. It recommends keeping personalization as a limited test.

### Interpretation

The pause and limited-test decision rests on the earlier, smaller read, while the later final readout reaches a more negative conclusion on the premium hypothesis yet recommends the same limited-test posture [inference]. The shopper's reason for abandoning (delivery wait) is consistent with the wait being the main reason given by pilot customers for not returning [[NORTHSTAR/PERSO-PILOT@v1:S1.B2]] [inference].

### Gaps & unknowns

The evidence does not show whether leadership formally confirmed each requested decision at the meeting, only that the pause was agreed and the hold was requested. It also does not say whether the October full readout has changed the decision [inference]. A post-October leadership record or decision log would close this gap.
```
#### R-IS-01 (insufficient_stop) - completed · stop finish_research · flags []

**Q:** How many patents does Kinetic Lab hold on its phone foot-scanning technology?

failures: contract ['uncited answer sentence: The evidence does not state how many patents, if any, Kineti']

```markdown
### Answer

The evidence does not state how many patents, if any, Kinetic Lab holds on its phone foot-scanning technology.

### Gaps & unknowns

None of the provided items mention patents, patent applications, or intellectual property ownership. They describe the scan process, the product range, and financial performance, but not legal protection of the technology. A patent database search (for example USPTO, EPO or WIPO records filed under Kinetic Lab or its founders) or the company's intellectual property disclosures in a regulatory filing or investor materials would close this gap. Whether the scanning software is proprietary, licensed, or built on third-party technology is also not established [inference].
```
#### R-SC-05 (simple_control) - completed · stop finish_research · flags []

**Q:** What is the FY26 return rate of the original Knit Runner, SKU NS-KR1?

failures: unsupported numbers ['2026']

```markdown
### Answer

The evidence gives a return rate of 13.1% for the original Knit Runner, as quoted in two strategy documents [[NORTHSTAR/Q3-REVIEW@v1:SL8]][[NORTHSTAR/BRAND-STRATEGY@v1:P6.B3]]. It does not give a figure explicitly labelled FY26 or tied to SKU NS-KR1 [inference]. The SKU-level return_rate_pct data exists only as a table schema without values [[NORTHSTAR/PRODUCT-PERF@v1:SH2.T1]].

### Key findings

- The Q3 Strategy Review states the return rate is 16.8% on the Knit Runner 2, against 13.1% for the original Knit Runner [[NORTHSTAR/Q3-REVIEW@v1:SL8]].
- The Brand Strategy 2026 document repeats the same comparison, 16.8% against 13.1% [[NORTHSTAR/BRAND-STRATEGY@v1:P6.B3]].

### Conflicting evidence

- No source states a different return rate for the original Knit Runner. The two sources citing 13.1% are consistent with each other [[NORTHSTAR/Q3-REVIEW@v1:SL8]][[NORTHSTAR/BRAND-STRATEGY@v1:P6.B3]].

### Gaps & unknowns

Neither document ties the figure to SKU NS-KR1 by identifier, and the SKU-level values are not shown [inference]. The row for NS-KR1 in the SKU_Performance table (return_rate_pct) would settle both points, as would a note in the strategy documents defining the period and basis of the return rate [inference].
```
