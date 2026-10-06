"""Standard-vs-research grounded evaluation: per-run metrics, per-mode summaries, paired
comparison, the numeric re-check and the report (synthetic outcomes; no app, no model)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from marketsignal.evaluation.grounded import (
    ItemOutcome,
    run_item,
    score,
    select_items,
    summarize,
)
from marketsignal.evaluation.grounded_compare import compare
from marketsignal.evaluation.grounded_report import render, render_comparison
from marketsignal.evaluation.grounded_stats import Prices, mode_summary, run_metrics
from marketsignal.evaluation.numeric_recheck import recheck_content

A = "NORTHSTAR/MEMO@v1:S1.B1"
B = "NORTHSTAR/DECK@v1:SL3"
C = "NORTHSTAR/SURVEY@v1:Q2"
TEXTS = {A: "Fit is the top issue for 27 percent of buyers.", B: "Revenue was $4.2 billion."}
PRICES = Prices(input=2.0, output=10.0, cache_write=2.5, cache_read=0.2)


class _Client:
    """Evidence API stand-in: known handles resolve with their text, others 404."""

    async def get(self, url: str) -> Any:
        handle = url.split("/evidence/", 1)[1]
        if handle in TEXTS:
            return SimpleNamespace(status_code=200, json=lambda: {"text": TEXTS[handle]})
        return SimpleNamespace(status_code=404, json=dict)


def _item(expect: str = "answer", **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "R-1",
        "category": "multi_class",
        "question": "q?",
        "workspace": "NORTHSTAR",
        "expect": expect,
        "gold_facts": [],
    }
    base.update(extra)
    return base


def _agent(trace: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "stop_reason": "finish_research",
        "flags": [],
        "steps": 2,
        "tool_calls": len(trace),
        "tool_errors": sum(1 for t in trace if t["status"] != "ok"),
        "usage": {"input_tokens": 1000, "output_tokens": 100, "llm_attempts": 2},
        "trace": trace,
    }
    base.update(extra)
    return base


def _outcome(
    item: dict[str, Any],
    content: str | None,
    *,
    mode: str | None = "standard",
    usage: dict[str, int] | None = None,
    agent: dict[str, Any] | None = None,
    timings: dict[str, Any] | None = None,
    pack: list[str] | None = None,
    done: dict[str, Any] | None = None,
    route: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> ItemOutcome:
    final = None if content is None else {"content": content, "sections": {}}
    run: dict[str, Any] = {
        "mode": "research" if agent is not None else "standard",
        "route": route or {"requested": mode, "decided": "standard", "reason": "requested"},
        "agent": agent,
        "pack_handles": [A, B] if pack is None else pack,
        "usage": usage if usage is not None else {"input_tokens": 500, "output_tokens": 50},
        "timings": timings or {"retrieval_ms": 20, "first_token_ms": 300, "total_ms": 900},
    }
    return ItemOutcome(
        item,
        events or [],
        final,
        {"termination_state": "completed", "flags": []} if done is None else done,
        run,
        mode=mode,
    )


def _scored(out: ItemOutcome) -> ItemOutcome:
    asyncio.run(score(_Client(), out))  # type: ignore[arg-type]
    out.metrics = run_metrics(out, PRICES)
    return out


def _search(tool: str = "search_evidence", status: str = "ok") -> dict[str, Any]:
    return {"tool": tool, "status": status, "step": 1, "call_index": 0, "handles": []}


# --- item selection and request body ------------------------------------------------------


def test_select_items_filters_split_ids_and_limit() -> None:
    items = [
        {"id": "a", "split": "dev"},
        {"id": "b", "split": "test"},
        {"id": "c", "split": "dev"},
        {"id": "g"},  # grounded-v0 items carry no split
    ]
    assert [i["id"] for i in select_items(items, split="dev")] == ["a", "c"]
    assert [i["id"] for i in select_items(items, split="all")] == ["a", "b", "c", "g"]
    assert [i["id"] for i in select_items(items, split="all", ids="g,b")] == ["b", "g"]
    assert [i["id"] for i in select_items(items, split="dev", limit=1)] == ["a"]


class _RecordingClient:
    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    async def post(self, url: str, json: dict[str, Any]) -> Any:
        if url.endswith("/conversations"):
            return SimpleNamespace(json=lambda: {"conversation_id": "c1"})
        self.bodies.append(json)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"run_id": "r1", "stream_url": "/s"},
        )

    async def get(self, url: str) -> Any:
        if url == "/s":
            return SimpleNamespace(text='event: done\ndata: {"termination_state": "completed"}\n\n')
        return SimpleNamespace(json=lambda: {"mode": "research"})


@pytest.mark.parametrize(("mode", "expected"), [(None, None), ("research", "research")])
def test_run_item_records_requested_mode_only_when_given(
    mode: str | None, expected: str | None
) -> None:
    client = _RecordingClient()
    out = asyncio.run(run_item(client, _item(), mode=mode))  # type: ignore[arg-type]
    assert client.bodies[0].get("mode") == expected
    assert ("mode" in client.bodies[0]) is (mode is not None)
    assert out.mode == mode
    assert out.done == {"termination_state": "completed"}


# --- per-run metrics ------------------------------------------------------------------------


def test_standard_run_metrics() -> None:
    out = _scored(
        _outcome(
            _item(),
            f"### Answer\nFit matters for 27 percent [[{A}]].\n",
            usage={"input_tokens": 500, "output_tokens": 50, "llm_attempts": 1},
        )
    )
    m = out.metrics
    assert m["mode"] == "standard"
    assert m["model_calls"] == 1
    assert m["tool_calls"] == 0
    assert m["retrieval_calls"] == 1
    assert m["steps"] == 0
    assert m["stop_reason"] is None
    assert m["research_fallback"] is False
    assert m["tokens"] == {"input": 500, "output": 50, "cache_read": 0, "cache_write": 0}
    assert m["cost_usd"] == pytest.approx((500 * 2.0 + 50 * 10.0) / 1e6)
    assert m["total_ms"] == 900
    assert m["first_token_ms"] == 300


def test_research_run_metrics_count_agent_calls_tools_and_tokens() -> None:
    trace = [
        _search(),
        _search("search_evidence_keyword"),
        _search("get_evidence"),
        _search(status="timeout"),
    ]
    out = _scored(
        _outcome(
            _item(),
            f"### Answer\nFit matters for 27 percent [[{A}]].\n",
            mode="research",
            agent=_agent(trace),
            usage={"input_tokens": 500, "output_tokens": 50, "llm_attempts": 2},
            timings={"agent_ms": 4000, "total_ms": 6000, "first_token_ms": 4500},
            route={"requested": "research", "decided": "research", "reason": "requested"},
        )
    )
    m = out.metrics
    assert m["mode"] == "research"
    assert m["route_reason"] == "requested"
    assert m["model_calls"] == 4  # 2 agent steps + 2 synthesis attempts
    assert m["tool_calls"] == 4
    assert m["retrieval_calls"] == 3  # 2 semantic searches + 1 keyword (failed calls count)
    assert m["tool_failures"] == 1
    assert m["steps"] == 2
    assert m["stop_reason"] == "finish_research"
    assert m["research_fallback"] is False
    assert m["tokens"]["input"] == 1500
    assert m["tokens"]["output"] == 150
    assert m["cost_usd"] == pytest.approx((1500 * 2.0 + 150 * 10.0) / 1e6)


def test_research_fallback_adds_the_standard_gather() -> None:
    agent = _agent(
        [],
        stop_reason="planner_unavailable",
        flags=["PLANNER_UNAVAILABLE_FALLBACK"],
        steps=1,
        usage={"llm_attempts": 1},
    )
    out = _scored(
        _outcome(
            _item(),
            None,
            mode="research",
            agent=agent,
            timings={"agent_ms": 1, "retrieval_ms": 20, "total_ms": 50},
        )
    )
    assert out.metrics["research_fallback"] is True
    assert out.metrics["retrieval_calls"] == 1
    assert out.metrics["model_calls"] == 1


# --- quality checks -------------------------------------------------------------------------


def test_gold_handle_recall_and_answer_completeness() -> None:
    gold = [
        {"fact_id": "F1", "handles": [C, A], "value": 27, "unit": "percent"},
        {"fact_id": "F2", "handles": [C], "value": 4.2, "unit": "usd_billion"},
    ]
    out = _scored(
        _outcome(_item(gold_facts=gold), f"### Answer\nFit matters for 27 percent [[{A}]].\n")
    )
    assert out.checks["gold_handle_recall"] == 0.5  # F1 via A in the pack; F2's only handle not
    assert out.checks["answer_completeness"] == 0.5
    assert out.checks["gold_coverage"] == 0.5


def test_unsupported_claim_rate_is_an_independent_recheck_of_cited_units() -> None:
    content = (
        f"### Answer\nFit matters for 27 percent [[{A}]].\n\n"
        f"### Key findings\n- Revenue was $9.9 billion [[{B}]].\n"
        "- [inference] Probably 12 more.\n"
    )
    out = _scored(_outcome(_item(), content))
    assert out.checks["cited_units"] == 2
    assert out.checks["unsupported_units"] == 1
    assert out.checks["unsupported_claim_rate"] == 0.5


def test_numeric_recheck_checks_uncited_units_against_pack_only_when_given() -> None:
    content = (
        f"### Answer\nFit matters for 27 percent [[{A}]].\n\n### Gaps & unknowns\n- 31 more.\n"
    )
    cited_only = recheck_content(content, TEXTS)
    assert cited_only["cited_units"] == 1
    assert cited_only["unsupported"] == []
    with_pack = recheck_content(content, TEXTS, pack=[A])
    assert [u["scope"] for u in with_pack["unsupported"]] == ["pack"]
    unresolvable = recheck_content(f"### Answer\nX 5 [[{C}]].\n", TEXTS)
    assert unresolvable["unresolvable_citations"] == [C]


def test_conflict_coverage_needs_both_sides_cited() -> None:
    gold = [
        {"fact_id": "F1", "handles": [A], "value": 27, "unit": None},
        {"fact_id": "F2", "handles": [B], "value": 4.2, "unit": None},
    ]
    one = _scored(_outcome(_item("conflict", gold_facts=gold), f"### Answer\n27 [[{A}]].\n"))
    both = _scored(
        _outcome(_item("conflict", gold_facts=gold), f"### Answer\n27 [[{A}]] vs 4.2 [[{B}]].\n")
    )
    assert one.checks["conflict_covered"] is False
    assert both.checks["conflict_covered"] is True


# --- gates ----------------------------------------------------------------------------------


def _abstained(*, agent: dict[str, Any] | None, usage: dict[str, int]) -> ItemOutcome:
    return _scored(
        _outcome(
            _item("abstain_no_llm"),
            "### Answer\nNo relevant evidence.\n",
            mode="research",
            agent=agent,
            usage=usage,
            pack=[],
            done={"termination_state": "no_relevant_evidence"},
        )
    )


def test_empty_pack_gate_ignores_agent_planning_calls_but_not_synthesis() -> None:
    planning_only = _abstained(agent=_agent([_search()]), usage={})
    assert planning_only.checks["llm_called"] is False
    assert summarize([planning_only])["hard_gates"]["empty_pack_never_calls_llm"]["pass"] is True
    synthesised = _abstained(agent=_agent([_search()]), usage={"input_tokens": 3})
    assert summarize([synthesised])["hard_gates"]["empty_pack_never_calls_llm"]["pass"] is False


def test_empty_pack_gate_is_not_applicable_without_abstain_items_when_not_required() -> None:
    out = _scored(_outcome(_item(), f"### Answer\n27 percent [[{A}]].\n"))
    assert summarize([out])["hard_gates"]["empty_pack_never_calls_llm"]["pass"] is False
    gate = summarize([out], require_empty_pack=False)["hard_gates"]["empty_pack_never_calls_llm"]
    assert gate == {"value": "not applicable", "pass": True}


# --- per-mode summary -------------------------------------------------------------------------


def test_mode_summary_totals_distributions_and_router_agreement() -> None:
    outs = []
    for i, (decided, expected) in enumerate(
        [("research", "research"), ("standard", "research"), ("standard", "standard")]
    ):
        out = _outcome(
            _item(id=f"R-{i}", router_expectation=expected, category=f"c{i % 2}"),
            f"### Answer\nFit matters for 27 percent [[{A}]].\n",
            mode="auto",
            usage={"input_tokens": 100, "output_tokens": 10, "llm_attempts": 1},
            timings={
                "retrieval_ms": 1,
                "first_token_ms": 100 * (i + 1),
                "total_ms": 1000 * (i + 1),
            },
            route={"requested": "auto", "decided": decided, "reason": "cues"},
        )
        outs.append(_scored(out))
    s = mode_summary(outs, mode="auto")
    assert s["n"] == 3
    assert s["model_calls"]["total"] == 3
    assert s["tokens_total"]["input"] == 300
    assert s["cost_usd"]["total"] == pytest.approx(3 * (100 * 2.0 + 10 * 10.0) / 1e6, abs=1e-6)
    assert s["latency_ms"]["total_p50"] == 2000
    assert s["termination_states"] == {"completed": 3}
    assert s["router_agreement"]["k"] == 2
    assert s["router_agreement"]["n"] == 3
    assert s["router_agreement"]["confusion"]["research->standard"] == 1
    assert set(s["categories"]) == {"c0", "c1"}
    assert mode_summary(outs, mode="standard")["router_agreement"] is None


# --- paired comparison and report -----------------------------------------------------------


def _pair(item_id: str, category: str, research_ok: bool) -> tuple[ItemOutcome, ItemOutcome]:
    gold = [{"fact_id": "F", "handles": [A], "value": 27, "unit": "percent"}]
    item = _item(id=item_id, category=category, gold_facts=gold)
    std = _scored(_outcome(item, "### Answer\nNot covered by the evidence.\n", pack=[]))
    content = f"### Answer\nFit matters for 27 percent [[{A}]].\n" if research_ok else None
    res = _scored(
        _outcome(
            item,
            content,
            mode="research",
            agent=_agent([_search(), _search()]),
            timings={"agent_ms": 3000, "first_token_ms": 3500, "total_ms": 5000},
        )
    )
    return std, res


def test_compare_pairs_items_and_reports_deltas_with_cis() -> None:
    pairs = [_pair("R-1", "multi_class", True), _pair("R-2", "reformulation", True)]
    pairs.append(_pair("R-3", "reformulation", False))
    std = [p[0].as_dict() for p in pairs]
    res = [p[1].as_dict() for p in pairs] + [_pair("R-9", "x", True)[1].as_dict()]
    cmp = compare(std, res, samples=200)
    assert cmp["n_pairs"] == 3
    assert cmp["unpaired"] == ["R-9"]
    recall = cmp["metrics"]["gold_handle_recall"]
    assert recall["standard_mean"] == 0.0
    assert recall["research_mean"] == 1.0
    assert recall["delta_mean"] == 1.0
    assert recall["ci"]["low"] <= recall["delta_mean"] <= recall["ci"]["high"]
    behaviour = cmp["metrics"]["behaviour_pass"]
    assert behaviour["kind"] == "rate"
    assert behaviour["mcnemar"]["only_research"] == 2
    assert cmp["metrics"]["total_ms"]["delta_mean"] == pytest.approx(4100.0)
    assert set(cmp["categories"]) == {"multi_class", "reformulation"}
    assert cmp["categories"]["reformulation"]["n"] == 2
    assert [row["id"] for row in cmp["items"]] == ["R-1", "R-2", "R-3"]


def test_comparison_report_has_one_table_categories_and_failures() -> None:
    pairs = [_pair("R-1", "multi_class", True), _pair("R-3", "reformulation", False)]
    std_outs = [p[0] for p in pairs]
    res_outs = [p[1] for p in pairs]
    results = {
        "standard": {
            "summary": {**summarize(std_outs, require_empty_pack=False)},
            "runs": mode_summary(std_outs, mode="standard"),
            "items": [o.as_dict() for o in std_outs],
            "elapsed_s": 1.0,
        },
        "research": {
            "summary": {**summarize(res_outs, require_empty_pack=False)},
            "runs": mode_summary(res_outs, mode="research"),
            "items": [o.as_dict() for o in res_outs],
            "elapsed_s": 2.0,
        },
    }
    cmp = compare(results["standard"]["items"], results["research"]["items"], samples=50)
    text = render_comparison(cmp, results, run={"model": "fake-llm"})
    assert "| Metric | standard | research | research - standard (95% CI) |" in text
    assert "## By category" in text
    assert "### multi_class" in text
    assert "## Per-item failures" in text
    assert "R-3" in text
    assert "## Hard gates" in text


def test_single_mode_report_includes_run_metrics() -> None:
    out = _scored(_outcome(_item(), f"### Answer\nFit matters for 27 percent [[{A}]].\n"))
    result = {
        "summary": summarize([out]),
        "runs": mode_summary([out], mode="standard"),
        "elapsed_s": 1.0,
        "items": [out.as_dict()],
    }
    text = render(result)
    assert "## Runs" in text
    assert "model calls" in text
