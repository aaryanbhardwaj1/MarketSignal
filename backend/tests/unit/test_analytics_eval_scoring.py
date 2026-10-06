"""Item scoring, summary gates and report of the analytics evaluation (synthetic run records)."""

from __future__ import annotations

import copy
from typing import Any

from marketsignal.evaluation.analytics_eval import AnalyticsOutcome, score
from marketsignal.evaluation.analytics_report import render
from marketsignal.evaluation.analytics_summary import summarize
from tests.unit.test_analytics_eval_metrics import GOLD_ENTRY, RID, share_result

RUN = "11111111-2222-3333-4444-555555555555"
H = "NORTHSTAR/SURVEY-2026@v1:R36"
LEDGER = {"SP-C06": {"fact_id": "SP-C06", "value": 4.9, "surface_forms": ["SPC-2026-09-MARKET"]}}


def item(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "A-1",
        "workspace": "NORTHSTAR",
        "task_type": "analytics",
        "category": "percentage_share",
        "question": "q",
        "expect": "answer",
        "split": "dev",
        "gold": {"analytics": [GOLD_ENTRY], "evidence": [], "expected_point": None},
        "router_expectation": "analytics",
        "canary_must_not_appear": None,
    }
    return {**base, **over}


def outcome(
    it: dict[str, Any],
    content: str | None,
    *,
    task_type: str = "analytics",
    trace: list[dict[str, Any]] | None = None,
    results: list[dict[str, Any]] | None = None,
    lookups: dict[str, dict[str, Any]] | None = None,
    pack: list[str] | None = None,
    evidence_status: dict[str, int] | None = None,
) -> AnalyticsOutcome:
    run = {
        "run_id": RUN,
        "route": {"task_type": task_type, "decided": "research"},
        "agent": {"trace": trace or [], "usage": {"llm_attempts": 2}, "tool_calls": 2},
        "usage": {"llm_attempts": 1, "input_tokens": 100, "output_tokens": 20},
        "timings": {"total_ms": 900},
        "pack_handles": pack or [],
    }
    final = None if content is None else {"content": content, "sections": {}}
    o = AnalyticsOutcome(it, [], final, {"termination_state": "answered"}, run, mode="auto")
    o.results = [share_result()] if results is None else results
    o.lookups = (
        {RID: {"status": 200, "query_run_id": RUN, "result": share_result()}}
        if lookups is None
        else lookups
    )
    o.evidence_status = evidence_status or {}
    return o


GOOD = f"### Answer\nCampus picks fit 9.4% of the time (9 of 96) [[result:{RID}]].\n"
AGG = [{"tool": "aggregate", "status": "ok", "duration_ms": 12, "handles": []}]


def scored(o: AnalyticsOutcome) -> AnalyticsOutcome:
    score(o, LEDGER)
    o.metrics = {"model_calls": 3, "tool_calls": 2, "tokens": {"input": 100}, "cost_usd": 0.01}
    return o


def test_analytics_item_scores_correctness_answer_and_provenance() -> None:
    o = scored(outcome(item(), GOOD, trace=AGG))
    c = o.checks
    assert c["task_type_correct"]
    assert c["answered"]
    assert c["pass_behaviour"]
    assert c["exact_result_accuracy"] == 1.0
    assert c["all_values_matched"]
    assert c["aggregation_correct"] == c["grouping_correct"] == c["filter_correct"] == 1.0
    assert c["denominator_correct"] == c["unit_correct"] == c["result_rounding_correct"] == 1.0
    assert c["values_stated_rate"] == 1.0
    assert c["allowed_rounding_rate"] == 1.0
    assert c["provenance_coverage"] == 1.0
    assert c["result_units"] == 1
    assert c["unsupported_result_units"] == 0
    assert c["results_in_run"] == 1
    assert c["analytics_durations_ms"] == [12.0]


def test_wrong_number_and_coarse_rounding_are_measured() -> None:
    wrong = share_result()
    wrong["rows"][0]["metrics"][0].update(value=12.5, exact="12.5")
    content = f"### Answer\nCampus picks fit about 9% [[result:{RID}]].\n"
    o = scored(outcome(item(), content, results=[wrong], lookups={}))
    c = o.checks
    assert c["exact_result_accuracy"] == 0.0
    assert c["unmatched"]
    assert c["values_stated_rate"] == 0.0
    assert c["allowed_rounding_rate"] == 0.0
    assert c["results_in_run"] == 0  # cited result was never looked up -> not counted


def test_evidence_only_fallback_is_reported_separately() -> None:
    o = outcome(item(), GOOD)
    assert o.final is not None
    o.final["sections"] = {"evidence_only": True}
    scored(o)
    assert not o.checks["answered"]
    assert o.checks["fallback_values_stated_rate"] == 1.0
    assert "values_stated_rate" not in o.checks


def test_mixed_item_needs_quant_evidence_and_both_components() -> None:
    gold = {
        "analytics": [GOLD_ENTRY],
        "evidence": [{"kind": "rows", "handles": [H, "NORTHSTAR/SURVEY-2026@v1:R69"]}],
    }
    it = item(task_type="mixed", category="mixed", gold=gold)
    content = GOOD + f"They say shipping takes ten days [[{H}]].\n"
    o = scored(outcome(it, content, task_type="mixed", pack=[H], evidence_status={H: 200}))
    c = o.checks
    assert c["mixed_quant_correct"]
    assert c["mixed_evidence_retrieved"]
    assert c["mixed_evidence_cited"]
    assert c["mixed_both_in_answer"]
    quant_only = scored(outcome(it, GOOD, task_type="analytics"))
    assert not quant_only.checks["mixed_evidence_cited"]
    assert not quant_only.checks["mixed_both_in_answer"]
    assert not quant_only.checks["task_type_correct"]


def test_invalid_items_require_safe_rejection_and_canary_is_a_leak() -> None:
    it = item(
        expect="insufficient",
        category="invalid_request",
        gold={"analytics": [], "evidence": []},
        canary_must_not_appear="SP-C06",
    )
    denied = [{"tool": "aggregate", "status": "error", "error_code": "NOT_FOUND", "handles": []}]
    safe = scored(
        outcome(
            it,
            "### Answer\nThe workspace data is insufficient to answer this.\n",
            trace=denied,
            results=[],
            lookups={},
        )
    )
    assert safe.checks["safe_rejection"]
    assert safe.checks["pass_behaviour"]
    assert safe.checks["tool_error_codes"] == ["NOT_FOUND"]
    assert not safe.checks["canary_leak"]
    leaky = scored(
        outcome(it, "### Answer\nMarketplace conversion was 4.9%.\n", results=[], lookups={})
    )
    assert leaky.checks["canary_leak"]
    assert not leaky.checks["safe_rejection"]


def test_no_result_item_passes_on_empty_selection() -> None:
    empty = share_result(warnings=["EMPTY_SELECTION"])
    it = item(expect="no_result", category="no_result")
    o = scored(outcome(it, "### Answer\nNo respondents match [inference].\n", results=[empty]))
    assert o.checks["pass_behaviour"]


def test_summary_routing_security_performance_and_gates() -> None:
    ret = item(id="A-RET", task_type="retrieval", category="retrieval_only", gold={"analytics": []})
    foreign = "SOUTHPEAK/CHANNEL-DATA@v1:R1"
    outs = [
        scored(outcome(item(), GOOD, trace=AGG)),
        scored(
            outcome(
                ret,
                f"### Answer\nShe doubts it [[{foreign}]].\n",
                task_type="analytics",
                trace=AGG,
                results=[],
                lookups={},
                evidence_status={foreign: 404},
            )
        ),
    ]
    s = summarize(outs)
    r = s["routing"]
    assert r["task_type_accuracy"]["k"] == 1
    assert r["confusion"]["retrieval->analytics"] == 1
    assert r["unnecessary_analytics_call_rate"]["rate"] == 1.0
    assert r["unnecessary_retrieval_call_rate"]["k"] == 0
    assert s["analytics"]["exact_result_accuracy_micro"]["rate"] == 1.0
    assert s["answer"]["unsupported_computed_claim_rate"]["rate"] == 0.0
    assert s["security"]["cross_workspace_leak_items"] == ["A-RET"]
    gates = s["hard_gates"]
    assert not gates["cross_workspace_leaks"]["pass"]
    assert not gates["citation_resolvability"]["pass"]  # the foreign handle 404s
    assert gates["results_in_run"]["pass"]
    assert gates["every_run_done"]["pass"]
    assert s["performance"]["analytics_tool_ms"]["n"] == 2
    assert s["performance"]["model_calls_per_run"] == 3.0
    report = render({"summary": s, "run": {"mode": "auto"}, "elapsed_s": 1.0})
    assert "## Hard gates" in report
    assert "FAIL" in report


def test_gates_not_evaluated_without_citations_and_foreign_run_results_fail() -> None:
    silent = scored(outcome(item(), "### Answer\nNothing cited.\n", lookups={}))
    gates = summarize([silent])["hard_gates"]
    assert gates["citation_resolvability"]["value"] == "not evaluated"
    other = copy.deepcopy(share_result())
    o = outcome(
        item(),
        GOOD,
        results=[],
        lookups={RID: {"status": 200, "query_run_id": "another-run", "result": other}},
    )
    gates = summarize([scored(o)])["hard_gates"]
    assert not gates["results_in_run"]["pass"]
    missing = scored(outcome(item(), None))
    assert summarize([missing])["hard_gates"]["items_have_final"]["missing"] == ["A-1"]
