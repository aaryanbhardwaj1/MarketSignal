"""Curated brief v2 grounding hardening: the number tokenizer (leading decimals, labels,
letter-glued digits, signs, thousands groups), the analysis interpretation gate and the prose
number lint over every v2 prose field of the committed brief. No database."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from marketsignal.insights.fixture import (
    Fixture,
    MetricSpec,
    OpportunitySpec,
    SignalSpec,
    load_fixture,
)
from marketsignal.insights.service import _derive
from marketsignal.insights.summary import check_summary, check_text, numbers_in, unmatched


def _payload(status: str = "computed") -> dict[str, Any]:
    ok = status == "computed"
    return {
        "status": status,
        "denominator": {"label": "rows", "value": 1240} if ok else None,
        "rows": [
            {"group": {"c": "A"}, "value": 27.0, "display": "27.0%", "denominator": 500},
            {"group": {"c": "B"}, "value": 2146098, "display": "$2,146,098"},
            {"group": {"c": "C"}, "value": -3.2, "display": "-3.2%"},
            {"group": {"c": "D"}, "value": 0.5, "display": "0.5"},
        ]
        if ok
        else [],
    }


# ── tokenizer ───────────────────────────────────────────────────────────────────────────────


def test_leading_decimal_numbers_are_checked() -> None:
    assert numbers_in("up .5 points") == {Decimal("0.5")}
    assert check_summary("Scores moved .5 points.", _payload())[1] == "verified"
    assert check_summary("Scores moved .7 points.", _payload()) == (None, "unverified")


@pytest.mark.parametrize("text", ["Up x30 on launch.", "Raised USD30M.", "Ranked top10."])
def test_digits_glued_to_letters_count_as_numbers(text: str) -> None:
    assert check_summary(text, _payload()) == (None, "unverified")


def test_period_labels_are_not_numbers() -> None:
    assert numbers_in("Q3 FY27 H1 FY2028 and Q4") == set()
    assert check_summary("In Q3 FY27, H2 sales hit $2,146,098.", _payload())[1] == "verified"


def test_explicit_sign_is_compared_signed() -> None:
    assert numbers_in("fell -3.2% then +27") == {Decimal("-3.2"), Decimal(27)}
    assert check_summary("Satisfaction moved -3.2%.", _payload())[1] == "verified"
    assert check_summary("Satisfaction moved \N{MINUS SIGN}3.2%.", _payload())[1] == "verified"
    assert check_summary("Satisfaction moved +3.2%.", _payload()) == (None, "unverified")
    assert check_summary("Fit moved -27%.", _payload()) == (None, "unverified")
    assert check_summary("Fit moved \N{MINUS SIGN}27%.", _payload()) == (None, "unverified")


def test_unsigned_text_compares_magnitudes_and_ranges_are_not_signs() -> None:
    assert check_summary("Satisfaction fell 3.2 points.", _payload())[1] == "verified"
    assert numbers_in("a 27-500 band") == {Decimal(27), Decimal(500)}


def test_only_thousands_groups_join_digits() -> None:
    assert numbers_in("18,27") == {Decimal(18), Decimal(27)}
    assert numbers_in("2,146,098 and 1,240.") == {Decimal(2146098), Decimal(1240)}
    assert numbers_in("1,2345") == {Decimal(1), Decimal(2345)}
    assert check_summary("Fit hit 27,0 percent.", _payload()) == (None, "unverified")


def test_unmatched_reports_the_stray_figures() -> None:
    allowed = {Decimal(27), Decimal("-3.2")}
    assert unmatched("27 and 3.2 and -3.2", allowed) == set()
    assert unmatched("+3.2 and 28", allowed) == {Decimal("3.2"), Decimal(28)}


# ── interpretation gate ─────────────────────────────────────────────────────────────────────


def test_interpretation_gate_follows_the_summary_rules() -> None:
    text = "Segment A leads."
    assert check_text(text, _payload()) == (text, "verified")
    assert check_text("Segment A leads by 28 points.", _payload()) == (None, "unverified")
    for status in ("mismatch", "unavailable"):
        assert check_text(text, _payload(status)) == (None, "unverified")
    assert check_text(None, _payload()) == (None, "absent")


# ── prose number lint over the committed v2 brief ───────────────────────────────────────────


@pytest.fixture(scope="module")
def brief() -> Fixture:
    fixture = load_fixture("NORTHSTAR")
    assert fixture is not None
    assert fixture.schema_version == 2
    return fixture


def _pinned(fixture: Fixture, analysis_id: str, group: dict[str, str], column: str | None) -> Any:
    analysis = fixture.analysis(analysis_id)
    assert analysis is not None
    row = next(r for r in analysis.expected if r.group == group)
    return row.values[column] if column else row.value


def _metric_numbers(fixture: Fixture, metrics: list[MetricSpec]) -> set[Decimal]:
    """Every pinned value of the analyses the metrics read, plus each derived metric's value."""
    out: set[Decimal] = set()
    for metric in metrics:
        picks = [metric.pick] if metric.pick else list(metric.derive.of if metric.derive else [])
        for pick in picks:
            analysis = fixture.analysis(pick.analysis_id)
            assert analysis is not None
            for row in analysis.expected:
                out.add(Decimal(str(row.value)).normalize())
                out |= {Decimal(str(v)).normalize() for v in row.values.values()}
        if metric.derive is not None:
            a, b = (_pinned(fixture, p.analysis_id, p.group, p.column) for p in metric.derive.of)
            if (value := _derive(metric.derive.op, a, b)) is not None:
                out.add(Decimal(str(value)).normalize())
    return out


def _quoted(evidence: Any) -> set[Decimal]:
    return {n for e in evidence for n in numbers_in(e.quote)}


def _signal_prose(s: SignalSpec) -> list[tuple[str, str]]:
    assert s.implication is not None
    return [
        ("statement", s.statement),
        ("implication", s.implication.text),
        *(("gap", g) for g in s.gaps),
    ]


def _opportunity_prose(o: OpportunitySpec) -> list[tuple[str, str]]:
    assert o.why_it_matters is not None
    assert o.next_investigation is not None
    return [
        ("thesis", o.thesis),
        ("status_rationale", o.status_rationale),
        ("why_it_matters", o.why_it_matters.text),
        ("next_investigation", o.next_investigation),
        ("next_step", o.next_step),
        *(("gap", g) for g in o.gaps),
    ]


def lint(fixture: Fixture) -> list[str]:
    """Every number in v2 prose must appear in the item's own quotes or pinned metric values; a
    risk may repeat only its own quotes; an interpretation only its analysis' pinned values."""
    problems: list[str] = []

    def check(where: str, text: str, allowed: set[Decimal]) -> None:
        if stray := unmatched(text, allowed):
            problems.append(f"{where}: unsupported numbers {sorted(stray)}")

    for s in fixture.signals:
        allowed = _quoted(s.evidence) | _metric_numbers(fixture, s.metrics)
        for field, text in _signal_prose(s):
            check(f"{s.id} {field}", text, allowed)
    for o in fixture.opportunities:
        allowed = _quoted(o.evidence) | _metric_numbers(fixture, o.metrics)
        for field, text in _opportunity_prose(o):
            check(f"{o.id} {field}", text, allowed)
        for n, risk in enumerate(o.risks, 1):
            check(f"{o.id} risk {n}", risk.text, _quoted(risk.evidence))
    for a in fixture.analyses:
        if a.interpretation is not None:
            pinned = {Decimal(str(r.value)).normalize() for r in a.expected}
            check(f"{a.id} interpretation", a.interpretation.text, pinned)
    return problems


def test_every_number_in_v2_prose_is_quoted_or_pinned(brief: Fixture) -> None:
    assert lint(brief) == []


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("signal", "statement"),
        ("signal", "implication"),
        ("signal", "gaps"),
        ("opportunity", "thesis"),
        ("opportunity", "status_rationale"),
        ("opportunity", "why_it_matters"),
        ("opportunity", "next_investigation"),
        ("opportunity", "risk"),
        ("analysis", "interpretation"),
    ],
)
def test_v2_lint_catches_an_invented_figure_in_each_field(
    brief: Fixture, kind: str, field: str
) -> None:
    invented = " It rose 987.6%."
    raw = brief.model_dump(exclude_unset=True)
    if kind == "signal":
        item = raw["signals"][0]
        if field == "implication":
            item["implication"]["text"] += invented
        elif field == "gaps":
            item["gaps"] = [*item.get("gaps", []), invented]
        else:
            item[field] += invented
    elif kind == "opportunity":
        item = raw["opportunities"][0]
        if field == "why_it_matters":
            item["why_it_matters"]["text"] += invented
        elif field == "risk":
            item["risks"][0]["text"] += invented
        else:
            item[field] += invented
    else:
        item = next(a for a in raw["analyses"] if a.get("interpretation"))
        item["interpretation"]["text"] += invented
    problems = lint(Fixture.model_validate(raw))
    assert len(problems) == 1
    assert "987.6" in problems[0]


def test_v2_lint_scopes_risk_numbers_to_the_risks_own_quotes(brief: Fixture) -> None:
    raw = brief.model_dump(exclude_unset=True)
    opp = next(o for o in raw["opportunities"] if _quoted_raw(o["evidence"]))
    borrowed = sorted(_quoted_raw(opp["evidence"]) - _quoted_raw(_risk_refs(opp)))
    assert borrowed, "needs an opportunity quote number that no risk quote repeats"
    opp["risks"][0]["text"] += f" See {borrowed[0]}."
    assert any("risk 1" in p for p in lint(Fixture.model_validate(raw)))


def _quoted_raw(evidence: list[dict[str, Any]]) -> set[Decimal]:
    return {abs(n) for e in evidence for n in numbers_in(e["quote"])}


def _risk_refs(opp: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for r in opp["risks"] for e in r["evidence"]]
