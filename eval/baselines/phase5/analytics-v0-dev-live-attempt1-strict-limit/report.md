# Analytics evaluation (analytics-v0)

- git `3e728a1` at 2026-10-06T21:57:31+00:00; model `claude-sonnet-5-5`; mode `auto`; split `dev`; items 36; elapsed 204.0 s

## Hard gates

| gate | value | pass |
|---|---|---|
| citation_resolvability | 1.0 | PASS |
| evidence_in_pack | 1.0 | PASS |
| results_in_run | 1.0 | PASS |
| cross_workspace_leaks | 1 | FAIL |
| every_run_done | 0 | PASS |
| items_have_final | 0 | PASS |

## Routing

| metric | value |
|---|---|
| task_type_accuracy | 36/36 (1.000) |
| mixed_recognition | 4/4 (1.000) |
| unnecessary_analytics_call_rate | 0/2 (0.000) |
| unnecessary_retrieval_call_rate | 25/25 (1.000) |

Confusion (gold->decided): {'analytics->analytics': 30, 'mixed->mixed': 4, 'retrieval->retrieval': 2}

## Analytics correctness

| metric | value |
|---|---|
| n_items | 31 |
| items_all_values_matched | 0/31 (0.000) |
| exact_result_accuracy_mean | 0.000 |
| aggregation_correct_mean | 0.000 |
| grouping_correct_mean | 0.000 |
| filter_correct_mean | 0.000 |
| denominator_correct_mean | 0.000 |
| unit_correct_mean | 0.000 |
| result_rounding_correct_mean | 0.000 |
| dataset_used_mean | 0.000 |
| exact_result_accuracy_micro | 0.000 |

## Generated answers

| metric | value |
|---|---|
| answered | 36 |
| evidence_only | 0 |
| values_stated_rate_mean | 0.118 |
| allowed_rounding_rate_mean | 0.500 |
| provenance_coverage_mean | 0.000 |
| fallback_values_stated_rate_mean | n/a |
| numeric_faithfulness | n/a |
| unsupported_computed_claim_rate | n/a |

## Mixed

| metric | value |
|---|---|
| mixed_quant_correct | 0/4 (0.000) |
| mixed_evidence_retrieved | 4/4 (1.000) |
| mixed_evidence_cited | 4/4 (1.000) |
| mixed_both_in_answer | 0/4 (0.000) |

## Security

| metric | value |
|---|---|
| safe_rejection | 2/3 (0.667) |
| no_result_correct | 2/2 (1.000) |
| behaviour_pass | 35/36 (0.972) |

- cross-workspace leak items: ['A-INV-04']
- canary leaks: none
- tool error codes on invalid/insufficient items: none

## Performance

| metric | n | p50 | p95 |
|---|---|---|---|
| analytics_tool_ms | 0 | n/a | n/a |
| mixed_end_to_end_ms | 4 | 6312.000 | 7436.100 |
| end_to_end_ms | 36 | 5415.600 | 7903.000 |

| metric | value |
|---|---|
| model_calls_per_run | 1.972 |
| tool_calls_per_run | 0.000 |
| tokens_per_run | 5676.500 |
| cost_usd_per_run | 0.014 |
| cost_usd_total | 0.497 |
| research_fallbacks | 35 |

## Categories

| category | n | behaviour pass | task type ok | exact-result acc | values stated |
|---|---|---|---|---|---|
| average | 4 | 4 | 4 | 0.000 | 0.250 |
| exact_count | 4 | 4 | 4 | 0.000 | 0.000 |
| filtered_aggregation | 2 | 2 | 2 | 0.000 | 0.000 |
| grouped_comparison | 1 | 1 | 1 | 0.000 | 0.000 |
| invalid_request | 3 | 2 | 3 | n/a | n/a |
| median_min_max | 1 | 1 | 1 | 0.000 | 0.000 |
| mixed | 4 | 4 | 4 | 0.000 | 0.000 |
| no_result | 2 | 2 | 2 | 0.000 | 0.000 |
| null_missing | 2 | 2 | 2 | 0.000 | 0.000 |
| percentage_share | 3 | 3 | 3 | 0.000 | 0.333 |
| retrieval_only | 2 | 2 | 2 | n/a | n/a |
| row_lookup | 4 | 4 | 4 | 0.000 | 0.000 |
| segment_compare | 2 | 2 | 2 | 0.000 | 0.333 |
| top_bottom | 2 | 2 | 2 | 0.000 | 0.500 |

Termination states: {'completed': 36}
