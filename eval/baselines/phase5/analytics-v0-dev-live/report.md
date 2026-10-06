# Analytics evaluation (analytics-v0)

- git `fb31765` at 2026-10-06T22:49:28+00:00; model `claude-sonnet-5-5`; mode `auto`; split `dev`; items 36; elapsed 441.6 s

## Hard gates

| gate | value | pass |
|---|---|---|
| citation_resolvability | 1.0 | PASS |
| evidence_in_pack | 1.0 | PASS |
| results_in_run | 1.0 | PASS |
| cross_workspace_leaks | 0 | PASS |
| every_run_done | 0 | PASS |
| items_have_final | 0 | PASS |

## Routing

| metric | value |
|---|---|
| task_type_accuracy | 36/36 (1.000) |
| mixed_recognition | 4/4 (1.000) |
| unnecessary_analytics_call_rate | 0/2 (0.000) |
| unnecessary_retrieval_call_rate | 3/25 (0.120) |

Confusion (gold->decided): {'analytics->analytics': 30, 'mixed->mixed': 4, 'retrieval->retrieval': 2}

## Analytics correctness

| metric | value |
|---|---|
| n_items | 31 |
| items_all_values_matched | 29/31 (0.935) |
| exact_result_accuracy_mean | 0.935 |
| aggregation_correct_mean | 0.885 |
| grouping_correct_mean | 0.846 |
| filter_correct_mean | 0.774 |
| denominator_correct_mean | 0.935 |
| unit_correct_mean | 0.880 |
| result_rounding_correct_mean | 0.935 |
| dataset_used_mean | 0.968 |
| exact_result_accuracy_micro | 0.900 |

## Generated answers

| metric | value |
|---|---|
| answered | 35 |
| evidence_only | 1 |
| values_stated_rate_mean | 0.956 |
| allowed_rounding_rate_mean | 1.000 |
| provenance_coverage_mean | 0.931 |
| fallback_values_stated_rate_mean | 1.000 |
| numeric_faithfulness | 1.000 |
| unsupported_computed_claim_rate | 0.000 |

## Mixed

| metric | value |
|---|---|
| mixed_quant_correct | 3/4 (0.750) |
| mixed_evidence_retrieved | 4/4 (1.000) |
| mixed_evidence_cited | 4/4 (1.000) |
| mixed_both_in_answer | 4/4 (1.000) |

## Security

| metric | value |
|---|---|
| safe_rejection | 3/3 (1.000) |
| no_result_correct | 2/2 (1.000) |
| behaviour_pass | 35/36 (0.972) |

- cross-workspace leak items: none
- canary leaks: none
- tool error codes on invalid/insufficient items: none

## Performance

| metric | n | p50 | p95 |
|---|---|---|---|
| analytics_tool_ms | 105 | 21.000 | 60.800 |
| mixed_end_to_end_ms | 4 | 15592.800 | 17252.700 |
| end_to_end_ms | 36 | 11602.700 | 16191.200 |

| metric | value |
|---|---|
| model_calls_per_run | 4.861 |
| tool_calls_per_run | 3.417 |
| tokens_per_run | 35690.200 |
| cost_usd_per_run | 0.032 |
| cost_usd_total | 1.137 |
| research_fallbacks | 0 |

## Categories

| category | n | behaviour pass | task type ok | exact-result acc | values stated |
|---|---|---|---|---|---|
| average | 4 | 3 | 4 | 1.000 | 1.000 |
| exact_count | 4 | 4 | 4 | 1.000 | 1.000 |
| filtered_aggregation | 2 | 2 | 2 | 1.000 | 1.000 |
| grouped_comparison | 1 | 1 | 1 | 1.000 | 1.000 |
| invalid_request | 3 | 3 | 3 | n/a | n/a |
| median_min_max | 1 | 1 | 1 | 1.000 | 1.000 |
| mixed | 4 | 4 | 4 | 0.750 | 1.000 |
| no_result | 2 | 2 | 2 | 1.000 | 0.500 |
| null_missing | 2 | 2 | 2 | 1.000 | 1.000 |
| percentage_share | 3 | 3 | 3 | 1.000 | 1.000 |
| retrieval_only | 2 | 2 | 2 | n/a | n/a |
| row_lookup | 4 | 4 | 4 | 1.000 | 1.000 |
| segment_compare | 2 | 2 | 2 | 0.500 | 0.833 |
| top_bottom | 2 | 2 | 2 | 1.000 | 1.000 |

Termination states: {'completed': 35, 'generation_unavailable': 1}
