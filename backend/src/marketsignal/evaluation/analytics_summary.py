"""Aggregate metrics of the analytics evaluation (pure over scored outcomes).

Rates are ``{"k", "n", "rate", "ci"}`` (Wilson 95%) over the items where the check applies;
means are item-level means of per-item fractions; ``micro`` counts pool every gold value.

* routing.task_type_accuracy - ``route.task_type == item.task_type`` over all items; confusion
  keys ``gold->decided``; mixed_recognition = mixed items routed ``mixed``;
  unnecessary_analytics_call_rate = retrieval items with >= 1 analytics tool call;
  unnecessary_retrieval_call_rate = analytics-only answer items with >= 1 search call (a
  standard gather counts as one).
* analytics - over items with gold analytics and ``expect`` answer/no_result.
* answer - over LLM-answered items (``answered``); evidence-only fallbacks separately.
  numeric_faithfulness = supported / all numbers in result-citing units;
  unsupported_computed_claim_rate = result-citing units with an unsupported number / units.
* security - leaks are counted over every item; safe_rejection over expect insufficient/invalid.
* performance - analytics tool p50/p95 from trace ``duration_ms`` of analytics tools (denied
  calls excluded); mixed end-to-end p50/p95 from ``timings.total_ms``; per-run means of
  ``grounded_stats.run_metrics`` (model calls, tool calls, tokens, cost).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from marketsignal.evaluation.stats import percentile, wilson

if TYPE_CHECKING:
    from marketsignal.evaluation.analytics_eval import AnalyticsOutcome

Outcomes = Sequence["AnalyticsOutcome"]


def rate(outcomes: Outcomes, test: Callable[[AnalyticsOutcome], bool | None]) -> dict[str, Any]:
    flags = [f for f in (test(o) for o in outcomes) if f is not None]
    k, n = sum(1 for f in flags if f), len(flags)
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, 4) if n else None,
        "ci": wilson(k, n).as_dict() if n else None,
    }


def mean(outcomes: Outcomes, key: str) -> float | None:
    values = [float(o.checks[key]) for o in outcomes if o.checks.get(key) is not None]
    return round(sum(values) / len(values), 4) if values else None


def dist(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "p50": None, "p95": None}
    return {
        "n": len(values),
        "p50": round(percentile(values, 0.5), 1),
        "p95": round(percentile(values, 0.95), 1),
    }


def _routing(outcomes: Outcomes) -> dict[str, Any]:
    confusion = Counter(f"{o.item['task_type']}->{o.checks['route_task_type']}" for o in outcomes)
    retrieval = [o for o in outcomes if o.item["task_type"] == "retrieval"]
    analytics_only = [
        o for o in outcomes if o.item["task_type"] == "analytics" and o.item["expect"] == "answer"
    ]
    return {
        "task_type_accuracy": rate(outcomes, lambda o: o.checks["task_type_correct"]),
        "confusion": dict(sorted(confusion.items())),
        "mixed_recognition": rate(
            [o for o in outcomes if o.item["task_type"] == "mixed"],
            lambda o: o.checks["route_task_type"] == "mixed",
        ),
        "unnecessary_analytics_call_rate": rate(
            retrieval, lambda o: o.checks["analytics_calls"] > 0
        ),
        "unnecessary_retrieval_call_rate": rate(
            analytics_only, lambda o: o.checks["search_calls"] > 0
        ),
    }


def _analytics(outcomes: Outcomes) -> dict[str, Any]:
    scored = [o for o in outcomes if o.checks.get("gold_values")]
    gold = sum(int(o.checks["gold_values"]) for o in scored)
    matched = sum(int(o.checks["values_matched"]) for o in scored)
    keys = (
        "exact_result_accuracy",
        "aggregation_correct",
        "grouping_correct",
        "filter_correct",
        "denominator_correct",
        "unit_correct",
        "result_rounding_correct",
        "dataset_used",
    )
    return {
        "n_items": len(scored),
        "exact_result_accuracy_micro": {
            "matched": matched,
            "gold_values": gold,
            "rate": round(matched / gold, 4) if gold else None,
        },
        "items_all_values_matched": rate(scored, lambda o: o.checks["all_values_matched"]),
        **{f"{k}_mean": mean(scored, k) for k in keys},
    }


def _answer(outcomes: Outcomes) -> dict[str, Any]:
    answered = [o for o in outcomes if o.checks.get("answered")]
    units = sum(int(o.checks["result_units"]) for o in outcomes)
    bad_units = sum(int(o.checks["unsupported_result_units"]) for o in outcomes)
    numbers = sum(int(o.checks["result_numbers"]) for o in outcomes)
    good = sum(int(o.checks["supported_result_numbers"]) for o in outcomes)
    return {
        "answered": len(answered),
        "evidence_only": sum(1 for o in outcomes if o.checks.get("evidence_only")),
        "values_stated_rate_mean": mean(outcomes, "values_stated_rate"),
        "allowed_rounding_rate_mean": mean(outcomes, "allowed_rounding_rate"),
        "provenance_coverage_mean": mean(outcomes, "provenance_coverage"),
        "fallback_values_stated_rate_mean": mean(outcomes, "fallback_values_stated_rate"),
        "numeric_faithfulness": {
            "supported": good,
            "numbers": numbers,
            "rate": round(good / numbers, 4) if numbers else None,
        },
        "unsupported_computed_claim_rate": {
            "unsupported_units": bad_units,
            "result_units": units,
            "rate": round(bad_units / units, 4) if units else None,
        },
    }


def _check(key: str) -> Callable[[AnalyticsOutcome], bool | None]:
    def test(o: AnalyticsOutcome) -> bool | None:
        value = o.checks.get(key)
        return None if value is None else bool(value)

    return test


def _mixed(outcomes: Outcomes) -> dict[str, Any]:
    mixed = [o for o in outcomes if o.item["task_type"] == "mixed"]
    keys = (
        "mixed_quant_correct",
        "mixed_evidence_retrieved",
        "mixed_evidence_cited",
        "mixed_both_in_answer",
    )
    return {key: rate(mixed, _check(key)) for key in keys}


def _security(outcomes: Outcomes) -> dict[str, Any]:
    leaks = [
        o.item["id"]
        for o in outcomes
        if o.checks["foreign_citations"]
        or o.checks["foreign_trace_handles"]
        or o.checks["foreign_results"]
        or o.checks["southpeak_marker_leak"]
        or o.checks["canary_leak"]
    ]
    rejecting = [o for o in outcomes if o.item["expect"] in ("insufficient", "invalid")]
    codes: Counter[str] = Counter()
    for o in rejecting:
        codes.update(o.checks["tool_error_codes"])
    return {
        "cross_workspace_leak_items": leaks,
        "canary_leaks": [o.item["id"] for o in outcomes if o.checks["canary_leak"]],
        "unauthorized_results": sorted({r for o in outcomes for r in o.checks["foreign_results"]}),
        "safe_rejection": rate(rejecting, lambda o: o.checks["safe_rejection"]),
        "invalid_item_tool_errors": dict(sorted(codes.items())),
        "no_result_correct": rate(
            [o for o in outcomes if o.item["expect"] == "no_result"],
            lambda o: o.checks["pass_behaviour"],
        ),
        "behaviour_pass": rate(outcomes, lambda o: o.checks.get("pass_behaviour")),
    }


def _per_run(outcomes: Outcomes, key: str) -> float | None:
    values = [float(o.metrics[key]) for o in outcomes if o.metrics.get(key) is not None]
    return round(sum(values) / len(values), 3) if values else None


def _performance(outcomes: Outcomes) -> dict[str, Any]:
    durations = [d for o in outcomes for d in o.checks["analytics_durations_ms"]]
    mixed = [
        float(o.checks["total_ms"])
        for o in outcomes
        if o.item["task_type"] == "mixed" and o.checks.get("total_ms") is not None
    ]
    totals = [float(o.checks["total_ms"]) for o in outcomes if o.checks.get("total_ms")]
    tokens = [sum((o.metrics.get("tokens") or {}).values()) for o in outcomes]
    return {
        "analytics_tool_ms": dist(durations),
        "mixed_end_to_end_ms": dist(mixed),
        "end_to_end_ms": dist(totals),
        "model_calls_per_run": _per_run(outcomes, "model_calls"),
        "tool_calls_per_run": _per_run(outcomes, "tool_calls"),
        "tokens_per_run": round(sum(tokens) / len(tokens), 1) if tokens else None,
        "cost_usd_per_run": _per_run(outcomes, "cost_usd"),
        "cost_usd_total": round(sum(float(o.metrics.get("cost_usd") or 0) for o in outcomes), 6),
        "research_fallbacks": sum(1 for o in outcomes if o.metrics.get("research_fallback")),
    }


def _ratio_gate(k: int, n: int, unevaluated: bool) -> dict[str, Any]:
    return {
        "value": "not evaluated" if unevaluated else (round(k / n, 4) if n else 1.0),
        "pass": not unevaluated and k == n,
    }


def hard_gates(outcomes: Outcomes) -> dict[str, Any]:
    c = {
        key: sum(int(o.checks[key]) for o in outcomes)
        for key in (
            "evidence_citations",
            "evidence_resolvable",
            "evidence_in_pack",
            "result_citations",
            "results_resolvable",
            "results_in_run",
        )
    }
    cited = c["evidence_citations"] + c["result_citations"]
    unevaluated = cited == 0 and any(o.item["expect"] == "answer" for o in outcomes)
    leaks = _security(outcomes)["cross_workspace_leak_items"]
    no_done = [o.item["id"] for o in outcomes if not o.checks["has_done"]]
    no_final = [o.item["id"] for o in outcomes if not o.checks["has_final"]]
    return {
        "citation_resolvability": _ratio_gate(
            c["evidence_resolvable"] + c["results_resolvable"], cited, unevaluated
        ),
        "evidence_in_pack": _ratio_gate(
            c["evidence_in_pack"], c["evidence_citations"], unevaluated
        ),
        "results_in_run": _ratio_gate(c["results_in_run"], c["result_citations"], False),
        "cross_workspace_leaks": {"value": len(leaks), "pass": not leaks, "items": leaks},
        "every_run_done": {"value": len(no_done), "pass": not no_done, "missing": no_done},
        "items_have_final": {"value": len(no_final), "pass": not no_final, "missing": no_final},
    }


def _categories(outcomes: Outcomes) -> dict[str, Any]:
    groups: dict[str, list[AnalyticsOutcome]] = {}
    for o in outcomes:
        groups.setdefault(o.item["category"], []).append(o)
    return {
        name: {
            "n": len(members),
            "behaviour_pass": rate(members, lambda o: o.checks.get("pass_behaviour"))["k"],
            "task_type_correct": sum(1 for o in members if o.checks["task_type_correct"]),
            "exact_result_accuracy_mean": mean(members, "exact_result_accuracy"),
            "values_stated_rate_mean": mean(members, "values_stated_rate"),
        }
        for name, members in sorted(groups.items())
    }


def summarize(outcomes: Outcomes) -> dict[str, Any]:
    return {
        "n": len(outcomes),
        "hard_gates": hard_gates(outcomes),
        "routing": _routing(outcomes),
        "analytics": _analytics(outcomes),
        "answer": _answer(outcomes),
        "mixed": _mixed(outcomes),
        "security": _security(outcomes),
        "performance": _performance(outcomes),
        "categories": _categories(outcomes),
        "termination_states": dict(
            sorted(Counter(str(o.done.get("termination_state")) for o in outcomes).items())
        ),
    }
