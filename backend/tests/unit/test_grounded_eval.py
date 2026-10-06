"""The grounded evaluator's own checks (they must not trust the verifier)."""

from __future__ import annotations

from marketsignal.evaluation.grounded import _numbers_match, parse_sse, recheck_contract

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
