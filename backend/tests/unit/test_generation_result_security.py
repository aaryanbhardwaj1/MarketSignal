"""Phase 5 security review, generation side: computed-result rendering and [R#] verification
(findings 1, 4, 10, 11, 13, 14, 15, 16, 17, 18, 22)."""

from __future__ import annotations

import sys
import unicodedata
import uuid
from decimal import Decimal
from typing import Any

import pytest

from marketsignal.analytics.schema import ColumnSpec, DatasetRef, infer_scale, infer_unit
from marketsignal.analytics.validate import Limits, aggregate_plan, group_compare_plan
from marketsignal.generation import fallback
from marketsignal.generation.contract import FORMAT_CHAR_RE, extract_numbers, strip_leaks
from marketsignal.generation.results import build_result_items, figure_supports
from marketsignal.generation.types import ResultFigure, result_marker
from marketsignal.generation.verifier import verify_answer
from marketsignal.runs.conversation import answer_digest
from marketsignal.tools.analytics_contracts import AggregateIn, GroupCompareIn
from tests.unit.test_results_in_answers import (
    RID,
    SHARE_PACK,
    item,
    kept,
    metric,
    pack_with,
    result,
    verify,
)

LIMITS = Limits(5, 20, 4, 2, 50, 20, 1000, 5.0)


def _col(name: str, ctype: str, levels: tuple[str, ...] = ()) -> ColumnSpec:
    return ColumnSpec(
        name, ctype, "x", infer_unit(name, ctype), levels, len(levels), 600,
        infer_scale(name, ctype),
    )  # fmt: skip


REF = DatasetRef(
    dataset="SURVEY-2026:1",
    table_id=uuid.uuid4(),
    source_version_id=uuid.uuid4(),
    source_code="SURVEY-2026",
    source_version=2,
    title="Survey",
    table="Responses",
    source_class="survey",
    row_count=600,
    columns=(
        _col("region", "categorical", ("North", "South")),
        _col("segment", "categorical", ("Value", "Premium")),
        _col("top_pain_point", "categorical", ("delivery_speed", "price")),
        _col("nps", "numeric"),
        _col("year", "categorical", ("2024", "2025")),
    ),
)
SHARE_METRIC = {"fn": "share", "condition": {"column": "top_pain_point", "op": "eq",
                                              "value": "delivery_speed"}}  # fmt: skip


def real_spec(filters: list[dict[str, Any]]) -> dict[str, Any]:
    """The spec exactly as the analytics engine stores it (validate.aggregate_plan)."""
    args = AggregateIn(dataset="SURVEY-2026:1", filters=filters, metrics=[SHARE_METRIC])
    return dict(aggregate_plan(REF, args, LIMITS).spec)


def compare_spec(group_a: str = "North", group_b: str = "South") -> dict[str, Any]:
    args = GroupCompareIn(
        dataset="SURVEY-2026:1",
        metric=SHARE_METRIC,
        compare_column="region",
        group_a=group_a,
        group_b=group_b,
    )
    return dict(group_compare_plan(REF, args, LIMITS).spec)


# --- finding 1: the real {column, op, operands} filter shape ---------------------------------

FILTERED = result(
    metric(38.2, "38.2333"),
    spec=real_spec(
        [{"column": "region", "op": "eq", "value": "North"},
         {"column": "nps", "op": "gte", "value": 15}]
    ),
)  # fmt: skip


def test_real_spec_shape_uses_operands() -> None:
    spec = FILTERED["spec"]
    assert spec["filters"][0] == {"column": "region", "op": "eq", "operands": ["North"]}


def test_filters_render_operands_not_none() -> None:
    rendered = build_result_items([FILTERED])[0].rendered
    assert "filters: region eq North; nps gte 15" in rendered
    assert "None" not in rendered
    assert "region eq North; nps gte 15" in build_result_items([FILTERED])[0].summary


def test_filter_operands_are_label_figures() -> None:
    p = pack_with(FILTERED)
    assert kept("Among North respondents with an NPS of 15 or more, 38.2% cite delivery [R1].", p)
    assert (
        kept("Among respondents with an NPS of 16 or more, 38.2% cite delivery [R1].", p) is False
    )


def test_metric_condition_operands_render_in_spec_scalars() -> None:
    labels = [f.value for f in build_result_items([FILTERED])[0].figures if f.kind == "label"]
    assert Decimal(15) in labels


# --- finding 10: invisible format characters --------------------------------------------------


@pytest.mark.parametrize("glue", ["\u200b", "\u2060", "\ufeff", "\u202e", "\u2066", "\u00ad"])
def test_format_characters_cannot_glue_supported_figures(glue: str) -> None:
    content, _ = verify(
        f"Delivery speed was cited by 600{glue}38.2% of respondents [R1].", SHARE_PACK
    )
    assert glue not in content
    assert "60038.2%" not in content
    assert "38.2% of respondents" not in content  # the glued unit is not kept in any form


def test_strip_leaks_removes_and_reports_format_characters() -> None:
    scan = strip_leaks("A\u200bB\u202e C")
    assert scan.text == "AB C"
    assert "format_char" in scan.removed


def test_format_char_pattern_covers_every_cf_code_point() -> None:
    missing = [
        hex(cp)
        for cp in range(sys.maxunicode + 1)
        if unicodedata.category(chr(cp)) == "Cf" and not FORMAT_CHAR_RE.fullmatch(chr(cp))
    ]
    assert missing == []


def test_format_characters_cannot_hide_a_marker_from_leak_rules() -> None:
    out = verify_answer(
        "### Answer\n38.2% cite delivery speed [R1] [\u200b[OTHER/SECRET@v1:P1]\u200b].\n",
        SHARE_PACK,
        pack_truncated=False,
    )
    assert "SECRET" not in out.content


# --- finding 11: non-USD currency written after the number ----------------------------------

AOV_METRIC = metric(812.5, "812.5", unit="currency_usd", fn="mean", key="mean(order_value_usd)",
                    numerator=None, denominator=600)  # fmt: skip
AOV = pack_with(result(AOV_METRIC))


@pytest.mark.parametrize(
    ("claim", "ok"),
    [
        ("The average order value was $812.5 [R1].", True),
        ("The average order value was 812.5 [R1].", True),
        ("The average order value was 812.5 USD [R1].", True),
        ("The average order value was 812.5 dollars [R1].", True),
        ("The average order value was 812.5 US dollars [R1].", True),
        ("The average order value was 812.5 euros [R1].", False),
        ("The average order value was 812.5 EUR [R1].", False),
        ("The average order value was 812.5 GBP [R1].", False),
        ("The average order value was 812.5 yen [R1].", False),
        ("The average order value was 812.5 pounds [R1].", False),
        ("The average order value was 812.5 Canadian dollars [R1].", False),
        ("The average order value was A$812.5 [R1].", False),
        ("The average order value was \u00a5812.5 [R1].", False),
        ("The average order value was \u20b9812.5 [R1].", False),
        ("The average order value was CHF 812.5 [R1].", False),
    ],
)
def test_suffix_and_foreign_prefix_currencies_are_rejected(claim: str, ok: bool) -> None:
    assert kept(claim, AOV) is ok


# --- finding 13: direction, subject group and level-vs-change -------------------------------

COMPARE = pack_with(
    result(
        rows=[
            {"group": {"region": "North"}, "metrics": [metric(41.0, "41.0")]},
            {"group": {"region": "South"}, "metrics": [metric(37.8, "37.8")]},
        ],
        difference=metric(3.2, "3.2", numerator=None, denominator=1200),
        operation="group_compare",
        spec=compare_spec(),
    )
)


@pytest.mark.parametrize(
    ("claim", "ok"),
    [
        ("North's rate was 3.2 points higher than South's [R1].", True),
        ("North exceeded South by 3.2 percentage points [R1].", True),
        ("South trails North by 3.2 points [R1].", True),
        ("The rate was 3.2 points higher than in the South [R1].", True),  # object -> subject A
        ("The gap between North and South is 3.2 points [R1].", True),  # no direction
        ("South's rate was 3.2 points higher than North's [R1].", False),  # subject swapped
        ("South exceeded North by 3.2 percentage points [R1].", False),
        ("North trails South by 3.2 points [R1].", False),
        ("In the South, the rate was 3.2 points higher than in the North [R1].", False),
        ("The rate was 3.2 points higher [R1].", False),  # which group? unknown subject
        ("North exceeded South by 41% [R1].", False),  # a level as a difference
        ("North was 41 points higher than South [R1].", False),
        ("In the North, the rate rose 41% [R1].", False),  # a level as a change
        ("North's rate was 41% [R1].", True),  # the level itself
        ("South's rate was 37.8% [R1].", True),
    ],
)
def test_group_compare_subject_and_direction(claim: str, ok: bool) -> None:
    assert kept(claim, COMPARE) is ok


@pytest.mark.parametrize(
    ("claim", "ok"),
    [
        ("Delivery speed was cited by 38.2% of respondents [R1].", True),
        ("Delivery-speed complaints fell 38.2% [R1].", False),
        ("Delivery-speed complaints rose 38% year over year [R1].", False),
        ("Delivery-speed complaints were up 38.2% [R1].", False),
        ("Delivery-speed complaints: 38.2% higher than price [R1].", False),
        ("Complaints about delivery grew by 38.2% [R1].", False),
        ("Delivery speed: 38% year over year [R1].", False),
    ],
)
def test_level_figures_are_not_changes(claim: str, ok: bool) -> None:
    assert kept(claim) is ok


def test_negative_level_direction_word_must_be_in_the_clause() -> None:
    p = pack_with(result(metric(-5, "-5", unit="number", fn="mean", key="mean(nps)",
                                numerator=None, denominator=600)))  # fmt: skip
    assert kept("Mean NPS was -5 [R1].", p)
    assert kept("Mean NPS declined 5 points below zero [R1].", p)
    assert kept("Mean NPS was 5, with fewer detractors than expected [R1].", p) is False
    assert kept("Mean NPS among under-30 respondents was 5 [R1].", p) is False


# --- finding 14: result years only from labels and dates -------------------------------------


@pytest.mark.parametrize(
    ("fig", "claim"),
    [
        (
            metric(38.2, "38.2333", denominator=2025),
            "In 2025, 38% of respondents cited delivery [R1].",
        ),
        (metric(38.2, "38.2333", numerator=2019), "Since 2019, 38% cited delivery [R1]."),
        (metric(38.2, "38.2019"), "In 2019, delivery speed led at 38.2% [R1]."),
    ],
)
def test_years_never_come_from_counts_or_decimals(fig: dict[str, Any], claim: str) -> None:
    assert kept(claim, pack_with(result(fig))) is False


def test_years_from_filter_operands_and_date_values() -> None:
    by_year = result(metric(38.2, "38.2333"),
                     spec=real_spec([{"column": "year", "op": "eq", "value": "2024"}]))  # fmt: skip
    assert kept("In 2024, 38.2% cited delivery [R1].", pack_with(by_year))
    assert kept("In 2023, 38.2% cited delivery [R1].", pack_with(by_year)) is False
    first = metric("2023-01-05", "2023-01-05", unit="date", fn="min", key="min(order_date)",
                   numerator=None, denominator=600)  # fmt: skip
    assert kept("The first order arrived in 2023 [R1].", pack_with(result(first)))


def test_numeric_label_on_non_temporal_column_is_not_a_year() -> None:
    spec = real_spec([{"column": "nps", "op": "gte", "value": 2020}])
    p = pack_with(result(metric(38.2, "38.2333"), spec=spec))
    assert kept("In 2020, 38.2% cited delivery [R1].", p) is False


# --- findings 4 and 16: over-precise numbers --------------------------------------------------


@pytest.mark.parametrize(
    "claim",
    [
        "38.23333333333333333333333333333% cite delivery speed [R1].",
        "38.2333000000000000000000000000000001% cite delivery speed [R1].",
    ],
)
def test_over_precise_claim_is_unsupported_not_an_error(claim: str) -> None:
    assert kept(claim) is False


def test_over_precise_exact_never_raises() -> None:
    fig = ResultFigure(
        "metric", Decimal("20"), Decimal("1234567890123456789012345678.12"), "number"
    )
    for text in ("1234567890123456789012345678.1", "20.0000000000000000000000000000001"):
        mention = extract_numbers(text)[0]
        assert figure_supports(text, mention, fig) is (text.endswith(".1"))


# --- finding 15: the budget keeps the [R#] that supports a figure -----------------------------


def test_citation_budget_never_drops_the_result_supporting_a_figure() -> None:
    p = pack_with(result(metric(38.2, "38.2333")), items=(item(1, "Panel score 38 overall."),))
    raw = (
        "### Answer\nDelivery speed is the top pain point [R1].\n\n### Key findings\n"
        "- Delivery speed was cited by 38% of respondents [E1][R1].\n"
    )
    out = verify_answer(raw, p, pack_truncated=False, max_citations=2)
    bullet = out.sections["findings"][0]
    assert result_marker(RID) in bullet
    assert "WS/SRC1" not in bullet
    assert not any("removed citation R1" in r for r in out.report.repairs)


# --- finding 17: a non-zero value is never stated as zero ------------------------------------


@pytest.mark.parametrize(
    ("value", "exact", "claim", "ok"),
    [
        (0.4, "0.4", "0%", False),
        (0.4, "0.4", "0.4%", True),
        (0.0, "0.04", "0.0%", False),
        (0.0, "0.04", "0%", False),
        (0.0, "0.04", "0.04%", True),
        (0.0, "0", "0%", True),
        (0.6, "0.6", "1%", True),  # half-even to 0 dp, non-zero
    ],
)
def test_nonzero_value_not_stated_as_zero(value: float, exact: str, claim: str, ok: bool) -> None:
    p = pack_with(result(metric(value, exact, numerator=None)))
    assert kept(f"Delivery speed was cited by {claim} of respondents [R1].", p) is ok


# --- finding 18: fallback result lines are safe markdown --------------------------------------


def test_fallback_result_lines_strip_bidi_and_escape_markdown() -> None:
    rows = [
        {"group": {"region": "North\u202e"}, "metrics": [metric(38.2, "38.2333")]},
        {"group": {"region": "**Bold** `x` _y_ ~~d~~ |t|"}, "metrics": [metric(41.0, "41.0")]},
    ]
    unit = fallback.result_unit(build_result_items([result(rows=rows)])[0])
    assert "\u202e" not in unit
    assert unit.startswith("**Computed result**")
    body = unit.removeprefix("**Computed result**")
    for raw in ("**Bold**", "`x`", " _y_", "~~d~~", "|t|"):
        assert raw not in body
    assert "\\*\\*Bold\\*\\*" in body
    assert "38.2%, denominator 600" in body


def test_result_labels_drop_format_characters_for_the_model() -> None:
    rows = [{"group": {"region": "No\u200brth\u202e"}, "metrics": [metric(38.2, "38.2333")]}]
    rendered = build_result_items([result(rows=rows)])[0].rendered
    assert "region=North" in rendered
    assert FORMAT_CHAR_RE.search(rendered) is None


# --- finding 22: conversation digest strips result markers ----------------------------------


def test_answer_digest_strips_result_markers() -> None:
    digest = answer_digest({"answer": [f"Mean NPS was 42.7 {result_marker(RID)}."]})
    assert digest == "Mean NPS was 42.7."
