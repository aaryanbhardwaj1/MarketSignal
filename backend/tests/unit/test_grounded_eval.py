"""The grounded evaluator's own checks (they must not trust the verifier)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from marketsignal.evaluation.grounded import (
    ItemOutcome,
    _numbers_match,
    parse_sse,
    recheck_contract,
    score,
    summarize,
)
from marketsignal.evaluation.grounded_report import render

H = "[[NORTHSTAR/MEMO@v1:S1.B1]]"


def test_contract_recheck_flags_uncited_claims_and_leaks() -> None:
    good = (
        f"### Answer\nFit is the top issue for 27 percent {H}.\n\n"
        f"### Key findings\n- 27 percent {H}.\n"
    )
    assert recheck_contract(good) == []
    uncited = (
        "### Answer\nFit is the top issue for 27 percent.\n\n### Key findings\n- 27 percent.\n"
    )
    problems = recheck_contract(uncited)
    assert any("uncited answer" in p for p in problems)
    assert any("uncited finding" in p for p in problems)
    assert (
        recheck_contract(f"### Answer\nSee [E3] {H}.\n")[0] == "run-local alias in stored content"
    )
    assert any("leak" in p for p in recheck_contract(f"### Answer\nhttps://x.example {H}.\n"))
    assert recheck_contract("### Answer\n[inference] Likely a sizing issue.\n") == []


def test_numeric_correctness_uses_normalised_values() -> None:
    assert _numbers_match(27, "27 percent of buyers")
    assert _numbers_match(612.0, "$612.0 million")
    assert _numbers_match(19.4, "19.4%")
    assert not _numbers_match(21, "19.4%")
    assert _numbers_match("dependable fit brand", "anything")  # non-numeric facts not scored


def test_sse_parser() -> None:
    raw = (
        'id: 1\nevent: run_started\ndata: {"seq": 1}\n\n: ping\n\n'
        'id: 2\nevent: done\ndata: {"seq": 2}\n\n'
    )
    events = parse_sse(raw)
    assert [e["event"] for e in events] == ["run_started", "done"]
    assert events[1]["data"]["seq"] == 2


class _Client:
    """Every cited handle resolves (to a text stating the numbers the tests cite)."""

    async def get(self, _url: str) -> Any:
        return SimpleNamespace(status_code=200, json=lambda: {"text": "27 percent; 40 percent"})


def _item(expect: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": f"i-{expect}",
        "category": "cat",
        "question": "q?",
        "workspace": "NORTHSTAR",
        "expect": expect,
        "gold_facts": [],
    }
    base.update(extra)
    return base


def _outcome(
    item: dict[str, Any],
    content: str | None,
    *,
    sections: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    usage: dict[str, int] | None = None,
    done: dict[str, Any] | None = None,
    pack: list[str] | None = None,
) -> ItemOutcome:
    final = None if content is None else {"content": content, "sections": sections or {}}
    return ItemOutcome(
        item,
        events or [],
        final,
        {"termination_state": "completed"} if done is None else done,
        {"pack_handles": pack if pack is not None else [H[2:-2]], "usage": usage or {}},
    )


def _scored(out: ItemOutcome) -> ItemOutcome:
    asyncio.run(score(_Client(), out))  # type: ignore[arg-type]
    return out


ANSWERED = f"### Answer\nFit is the top issue for 27 percent {H}.\n"


def test_runs_without_final_fail_hard_gates_and_are_reported() -> None:
    outs = [_scored(_outcome(_item("answer"), None, done={})) for _ in range(2)]
    summary = summarize(outs)
    gates = summary["hard_gates"]
    assert gates["citation_resolvability"]["pass"] is False
    assert gates["citation_resolvability"]["value"] == "not evaluated"
    assert gates["citation_in_pack"]["pass"] is False
    assert gates["every_run_done"]["pass"] is False
    assert gates["answer_items_have_final"]["pass"] is False
    assert gates["empty_pack_never_calls_llm"]["pass"] is False  # no abstain items present
    assert [f["problems"] for f in summary["contract_recheck_failures"]] == [["no final"]] * 2


def test_healthy_run_passes_all_hard_gates() -> None:
    answer = _scored(_outcome(_item("answer"), ANSWERED, usage={"output_tokens": 5}))
    empty = _scored(
        _outcome(
            _item("abstain_no_llm"),
            "### Answer\nNo relevant evidence.\n",
            sections={"abstained": True},
            done={"termination_state": "no_relevant_evidence"},
            pack=[],
        )
    )
    gates = summarize([answer, empty])["hard_gates"]
    assert all(g["pass"] for g in gates.values()), gates


def test_abstain_item_without_final_does_not_need_one_but_needs_done() -> None:
    empty = _scored(
        _outcome(_item("abstain_no_llm"), None, done={"termination_state": "no_relevant_evidence"})
    )
    gates = summarize([empty])["hard_gates"]
    assert gates["answer_items_have_final"]["pass"] is True
    assert gates["every_run_done"]["pass"] is True


def test_llm_called_detects_failed_attempts() -> None:
    status = {"event": "status", "data": {"phase": "synthesizing"}}
    failed = _scored(_outcome(_item("abstain_no_llm"), None, events=[status]))
    assert failed.checks["llm_called"] is True
    assert failed.checks["pass_behaviour"] is False
    input_only = _scored(_outcome(_item("answer"), None, usage={"input_tokens": 9}))
    assert input_only.checks["llm_called"] is True
    none = _scored(_outcome(_item("answer"), None))
    assert none.checks["llm_called"] is False


def test_insufficiency_is_judged_on_answer_section_only() -> None:
    gaps_only = (
        f"### Answer\nRegional split is 40 percent {H}.\n\n"
        "### Gaps & unknowns\nThe evidence does not cover regional splits.\n"
    )
    out = _scored(_outcome(_item("insufficient"), gaps_only))
    assert out.checks["pass_behaviour"] is False
    stated = f"### Answer\nThe evidence does not cover regional splits, though {H} mentions fit.\n"
    assert _scored(_outcome(_item("insufficient"), stated)).checks["pass_behaviour"] is True
    assert _scored(_outcome(_item("insufficient"), None, done={})).checks["pass_behaviour"] is False


def test_gold_metrics_only_credit_llm_answers_and_fallbacks_are_separate() -> None:
    gold = [{"handles": [H[2:-2]], "value": 27}]
    answered = _scored(_outcome(_item("answer", gold_facts=gold), ANSWERED))
    assert answered.checks["answered"] is True
    assert answered.checks["gold_coverage"] == 1.0
    fallback = _scored(
        _outcome(
            _item("answer", gold_facts=gold),
            f"### Evidence\n27 percent {H}\n",
            sections={"evidence_only": ["x"]},
        )
    )
    assert "gold_coverage" not in fallback.checks
    assert "numeric_correct" not in fallback.checks
    assert fallback.checks["fallback_gold_coverage"] == 1.0
    cat = summarize([answered, fallback])["categories"]["cat"]
    assert cat["gold_coverage_mean"] == 1.0
    assert cat["answered"] == 1
    assert cat["fallback_gold_coverage_mean"] == 1.0


def test_report_renders_new_fields() -> None:
    answered = _scored(_outcome(_item("answer"), ANSWERED, usage={"output_tokens": 5}))
    result = {"summary": summarize([answered]), "elapsed_s": 1.0, "items": [answered.as_dict()]}
    text = render(result)
    assert "every_run_done" in text
    assert "answered" in text
    assert "llm_called" in text
