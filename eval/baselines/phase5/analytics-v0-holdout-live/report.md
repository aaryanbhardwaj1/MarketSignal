# Analytics evaluation (analytics-v0)

- git `1775244` at 2026-10-06T23:02:22+00:00; model `claude-sonnet-5-5`; mode `auto`; split `holdout`; items 54; elapsed 596.7 s

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
| task_type_accuracy | 31/54 (0.574) |
| mixed_recognition | 2/6 (0.333) |
| unnecessary_analytics_call_rate | 0/4 (0.000) |
| unnecessary_retrieval_call_rate | 13/38 (0.342) |

Confusion (gold->decided): {'analytics->analytics': 25, 'analytics->mixed': 4, 'analytics->retrieval': 15, 'mixed->analytics': 2, 'mixed->mixed': 2, 'mixed->retrieval': 2, 'retrieval->retrieval': 4}

## Analytics correctness

| metric | value |
|---|---|
| n_items | 46 |
| items_all_values_matched | 33/46 (0.717) |
| exact_result_accuracy_mean | 0.746 |
| aggregation_correct_mean | 0.683 |
| grouping_correct_mean | 0.658 |
| filter_correct_mean | 0.522 |
| denominator_correct_mean | 0.725 |
| unit_correct_mean | 0.496 |
| result_rounding_correct_mean | 0.746 |
| dataset_used_mean | 0.761 |
| exact_result_accuracy_micro | 0.761 |

## Generated answers

| metric | value |
|---|---|
| answered | 51 |
| evidence_only | 1 |
| values_stated_rate_mean | 0.726 |
| allowed_rounding_rate_mean | 0.970 |
| provenance_coverage_mean | 0.969 |
| fallback_values_stated_rate_mean | 0.500 |
| numeric_faithfulness | 0.990 |
| unsupported_computed_claim_rate | 0.007 |

## Mixed

| metric | value |
|---|---|
| mixed_quant_correct | 4/6 (0.667) |
| mixed_evidence_retrieved | 5/6 (0.833) |
| mixed_evidence_cited | 5/6 (0.833) |
| mixed_both_in_answer | 4/6 (0.667) |

## Security

| metric | value |
|---|---|
| safe_rejection | 4/4 (1.000) |
| no_result_correct | 2/2 (1.000) |
| behaviour_pass | 52/54 (0.963) |

- cross-workspace leak items: none
- canary leaks: none
- tool error codes on invalid/insufficient items: none

## Performance

| metric | n | p50 | p95 |
|---|---|---|---|
| analytics_tool_ms | 117 | 21.000 | 49.600 |
| mixed_end_to_end_ms | 6 | 17079.700 | 17773.800 |
| end_to_end_ms | 54 | 11672.000 | 17408.200 |

| metric | value |
|---|---|
| model_calls_per_run | 3.833 |
| tool_calls_per_run | 2.648 |
| tokens_per_run | 28315.800 |
| cost_usd_per_run | 0.027 |
| cost_usd_total | 1.485 |
| research_fallbacks | 0 |

## Categories

| category | n | behaviour pass | task type ok | exact-result acc | values stated |
|---|---|---|---|---|---|
| average | 2 | 2 | 2 | 1.000 | 1.000 |
| exact_count | 2 | 2 | 0 | 0.500 | 0.500 |
| filtered_aggregation | 3 | 2 | 2 | 0.667 | 0.500 |
| grouped_comparison | 5 | 5 | 4 | 0.800 | 0.800 |
| invalid_request | 4 | 4 | 1 | n/a | n/a |
| median_min_max | 4 | 4 | 2 | 0.500 | 0.500 |
| mixed | 6 | 6 | 2 | 0.667 | 0.667 |
| no_result | 2 | 2 | 1 | 0.500 | n/a |
| null_missing | 2 | 2 | 2 | 1.000 | 1.000 |
| percentage_share | 3 | 3 | 2 | 1.000 | 1.000 |
| retrieval_only | 4 | 4 | 4 | n/a | n/a |
| row_lookup | 5 | 4 | 2 | 0.800 | 0.750 |
| segment_compare | 5 | 5 | 3 | 0.867 | 0.800 |
| top_bottom | 7 | 7 | 4 | 0.714 | 0.643 |

Termination states: {'completed': 52, 'generation_unavailable': 1, 'no_relevant_evidence': 1}
