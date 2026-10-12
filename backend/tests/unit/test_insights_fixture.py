"""Curated analyst brief fixture (plan §5.4): schema, curation rules, the numeric lint, quote
matching, derived metrics and display formatting. No database."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from marketsignal.insights.analyses import FlatRow, matches_expected
from marketsignal.insights.evidence import collapse, find_quote
from marketsignal.insights.fixture import (
    FIXTURE_DIR,
    ExpectedRow,
    Fixture,
    FixtureError,
    load_fixture,
    parse_fixture,
)
from marketsignal.insights.format import format_value
from marketsignal.insights.service import _derive

FIXTURE_PATH = FIXTURE_DIR / "NORTHSTAR.v1.json"
INJECTION = ("NORTHSTAR/KINETIC-WEB@v1:S1.B12", "NORTHSTAR/REVIEWS@v1:R578")
# A number not glued to a letter: "27%", "9.5", "2,146,098" count; "FY27", "Q3", "SL5" do not.
NUMBER = re.compile(r"(?<![A-Za-z0-9.])\d[\d,]*(?:\.\d+)?")


def _raw() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def fixture() -> Fixture:
    loaded = load_fixture("NORTHSTAR")
    assert loaded is not None
    return loaded


def _numbers(text: str) -> set[Decimal]:
    return {Decimal(m.replace(",", "")).normalize() for m in NUMBER.findall(text)}


def test_northstar_fixture_validates_and_has_the_planned_shape(fixture: Fixture) -> None:
    assert fixture.workspace == "NORTHSTAR"
    assert fixture.label == "Curated analyst brief"
    assert len(fixture.signals) == 6
    assert [o.id for o in fixture.opportunities] == ["O1", "O2", "O3", "O4"]
    assert 6 <= len(fixture.analyses) <= 10
    assert {o.status for o in fixture.opportunities} == {
        "supported",
        "mixed_evidence",
        "emerging",
        "needs_research",
    }
    assert all(o.status_rationale.strip() for o in fixture.opportunities)


def test_no_workspace_without_a_fixture() -> None:
    assert load_fixture("SOUTHPEAK") is None


def test_handles_stay_in_northstar_and_never_cite_planted_or_superseded_text(
    fixture: Fixture,
) -> None:
    handles = [e.handle for e in fixture.all_evidence()]
    assert handles
    assert all(h.startswith("NORTHSTAR/") for h in handles)
    assert not any(h.startswith("NORTHSTAR/GENZ-TRENDS@v1") for h in handles)
    assert not any(h.startswith(INJECTION) for h in handles)
    raw = FIXTURE_PATH.read_text(encoding="utf-8")
    assert "GENZ-TRENDS@v1" not in raw
    assert not any(i in raw for i in INJECTION)


def test_no_scores_or_rankings_in_the_brief() -> None:
    raw = _raw()
    for item in [*raw["signals"], *raw["opportunities"]]:
        assert not {"score", "rank", "priority", "confidence"} & set(item)


def _allowed_numbers(fixture: Fixture, item: Any) -> set[Decimal]:
    allowed: set[Decimal] = set()
    for ev in item.evidence:
        allowed |= _numbers(ev.quote)
    for metric in item.metrics:
        picks = [metric.pick] if metric.pick else list(metric.derive.of if metric.derive else [])
        for pick in picks:
            analysis = fixture.analysis(pick.analysis_id)
            assert analysis is not None
            for row in analysis.expected:
                allowed.add(Decimal(str(row.value)).normalize())
                allowed |= {Decimal(str(v)).normalize() for v in row.values.values()}
    return allowed


def test_every_number_in_brief_prose_is_quoted_or_pinned(fixture: Fixture) -> None:
    """Mirrors the verifier's numeric rule: prose may only repeat numbers that appear in the
    item's own quotes or in the pinned values of the analyses its metrics read."""
    for signal in fixture.signals:
        stray = _numbers(signal.statement) - _allowed_numbers(fixture, signal)
        assert not stray, f"{signal.id}: unsupported numbers {stray}"
    for opp in fixture.opportunities:
        prose = " ".join([opp.thesis, *opp.gaps, opp.next_step])
        stray = _numbers(prose) - _allowed_numbers(fixture, opp)
        assert not stray, f"{opp.id}: unsupported numbers {stray}"


def test_number_lint_catches_an_invented_figure(fixture: Fixture) -> None:
    signal = fixture.signals[0]
    invented = signal.statement + " Abandonment rose 63%."
    assert _numbers(invented) - _allowed_numbers(fixture, signal) == {Decimal(63)}


def test_every_metric_reads_a_pinned_value(fixture: Fixture) -> None:
    for metric in fixture.all_metrics():
        assert (metric.pick is None) != (metric.derive is None)


def _mutate(path: list[Any], value: Any) -> dict[str, Any]:
    raw = _raw()
    node: Any = raw
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return raw


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["signals", 0, "evidence", 0, "handle"], "SOUTHPEAK/BRAND-STRATEGY@v1:P4.B2"),
        (["signals", 0, "evidence", 0, "handle"], "NORTHSTAR/REVIEWS@v1:R578"),
        (["signals", 0, "evidence", 0, "handle"], "NORTHSTAR/GENZ-TRENDS@v1:P2.B2"),
        (["signals", 0, "evidence", 0, "handle"], "not a handle"),
        (["signals", 0, "metrics", 0, "pick", "group"], {"cohort": "nobody"}),
        (["signals", 0, "score"], 9),
        (["opportunities", 0, "status"], "top_priority"),
        (["analyses", 0, "parts", 0, "spec", "dataset"], "OTHER:1"),
        (["analyses", 0, "parts", 0, "spec", "metrics"], []),
    ],
)
def test_fixture_rules_fail_closed(path: list[Any], value: Any) -> None:
    with pytest.raises(FixtureError):
        parse_fixture(_mutate(path, value))


def test_quote_match_collapses_whitespace_and_maps_raw_offsets() -> None:
    passage = "Intro line.\n\nFit  inconsistency is\nthe top   pain point. Tail."
    match = find_quote(passage, "Fit inconsistency is the top pain point.")
    assert match is not None
    assert passage[match.start : match.end] == "Fit  inconsistency is\nthe top   pain point."
    assert find_quote(passage, "Fit is fine.") is None
    collapsed, index = collapse("a \n b")
    assert collapsed == "a b"
    assert index == [0, 1, 4]


def test_expected_rows_compare_positionally_after_rounding() -> None:
    rows = [FlatRow({"g": "a", "measure": "x"}, 27.0), FlatRow({"g": "b", "measure": "x"}, 3.9)]
    pins = [ExpectedRow(group={"g": "a"}, value=27), ExpectedRow(group={"g": "b"}, value=3.90)]
    assert matches_expected(rows, pins)
    assert not matches_expected(list(reversed(rows)), pins)
    assert not matches_expected(rows[:1], pins)
    assert not matches_expected([rows[0], FlatRow({"g": "b"}, 3.91)], pins)
    cells = [FlatRow({"c": "S"}, 3.4, cells={"aov_usd": 61.6})]
    assert matches_expected(
        cells, [ExpectedRow(group={"c": "S"}, value=3.4, values={"aov_usd": 61.6})]
    )
    assert not matches_expected(
        cells, [ExpectedRow(group={"c": "S"}, value=3.4, values={"aov_usd": 61.7})]
    )


def test_derived_metrics() -> None:
    assert _derive("pct_change", 886762, 2146098) == 142.0
    assert _derive("diff", 40.0, 18.0) == 22
    assert _derive("pct_change", 0, 5) is None


@pytest.mark.parametrize(
    ("value", "unit", "kwargs", "expected"),
    [
        (27.0, "percent", {}, "27.0%"),
        (2146098, "usd", {}, "$2,146,098"),
        (61.6, "usd", {}, "$61.60"),
        (5085, "count", {}, "5,085"),
        (3.9, "score", {}, "3.90"),
        (22, "score", {"places": -1}, "22"),
        (142.0, "percent", {"signed": True}, "+142.0%"),
        (None, "percent", {}, None),
    ],
)
def test_display_formatting(value: Any, unit: str, kwargs: dict[str, Any], expected: Any) -> None:
    assert format_value(value, unit, **kwargs) == expected


def test_newest_fixture_compares_versions_numerically(tmp_path: Path) -> None:
    from marketsignal.insights.fixture import newest_fixture_path

    for name in ("ACME.v2.json", "ACME.v10.json", "ACME.v9.json", "ACME.vX.json", "ACME.v3.bak"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    newest = newest_fixture_path("ACME", tmp_path)
    assert newest is not None
    assert newest.name == "ACME.v10.json"
    assert newest_fixture_path("OTHER", tmp_path) is None
