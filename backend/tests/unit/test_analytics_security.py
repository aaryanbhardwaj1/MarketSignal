"""Phase 5 security-review fixes on the analytics engine/contract (no database).

Covers: boolean categorical levels (canon == profile form), date range semantics (parsed
periods, never lexical compares of mixed precision), huge numeric cells (exact sums, rounding
with enough precision), NaN/Infinity operands (VALIDATION_ERROR), numeric group_by over
non-numeric cells (one group per raw value) and ToolResult.handles() for analytics outputs.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from marketsignal.analytics import engine
from marketsignal.analytics.engine import Row
from marketsignal.analytics.rounding import round_value
from marketsignal.analytics.schema import ColumnSpec, DatasetRef, infer_unit
from marketsignal.analytics.validate import (
    AnalyticsInputError,
    Limits,
    aggregate_plan,
    canon,
    group_compare_plan,
)
from marketsignal.tools.analytics_contracts import AggregateIn, Filter, GroupCompareIn
from marketsignal.tools.contracts import ToolResult

LIMITS = Limits(
    filters=5,
    filter_values=20,
    metrics=4,
    group_by=2,
    groups=50,
    rows=20,
    scan_rows=1000,
    timeout_s=5.0,
)


def _col(name: str, ctype: str, levels: tuple[str, ...] = (), distinct: int = 0) -> ColumnSpec:
    return ColumnSpec(name, ctype, "x", infer_unit(name, ctype), levels, distinct, 0)


def _ref(*cols: ColumnSpec) -> DatasetRef:
    return DatasetRef(
        dataset="T:1",
        table_id=uuid.uuid4(),
        source_version_id=uuid.uuid4(),
        source_code="T",
        source_version=1,
        title="t",
        table="t",
        source_class="customer",
        row_count=0,
        columns=cols,
    )


def _rows(data: list[dict[str, Any]]) -> list[Row]:
    return [Row(i + 1, f"WS/T@v1:R{i + 1}", v) for i, v in enumerate(data)]


def _count(ref: DatasetRef, rows: list[Row], filters: list[dict[str, Any]]) -> int:
    plan = aggregate_plan(
        ref, AggregateIn(dataset="T:1", metrics=[{"fn": "count"}], filters=filters), LIMITS
    )
    value = engine.aggregate(plan, rows, deadline=None).rows[0].metrics[0].value
    assert isinstance(value, int)
    return value


# --- 2: boolean categorical columns ------------------------------------------------------------

# the ingestion profile stores levels as str(cell): a TRUE/FALSE column has ('True', 'False')
BOOL_REF = _ref(_col("subscribed", "categorical", ("True", "False"), 2), _col("spend", "numeric"))
BOOL_ROWS = _rows(
    [
        {"subscribed": True, "spend": 10},
        {"subscribed": False, "spend": 4},
        {"subscribed": True, "spend": 20},
        {"subscribed": None, "spend": 1},
    ]
)


def test_canon_matches_the_profile_form() -> None:
    assert canon(True) == str(True)
    assert canon(False) == str(False)
    assert canon(1e-07) == str(1e-07)  # profile levels use str(); so must equality
    assert canon(2023.0) == canon(2023) == canon("2023") == "2023"


@pytest.mark.parametrize("operand", [True, "True"])
def test_bool_column_eq_matches(operand: Any) -> None:
    filters = [{"column": "subscribed", "op": "eq", "value": operand}]
    assert _count(BOOL_REF, BOOL_ROWS, filters) == 2


def test_bool_column_in_and_ne() -> None:
    assert (
        _count(BOOL_REF, BOOL_ROWS, [{"column": "subscribed", "op": "in", "values": [False]}]) == 1
    )
    assert _count(BOOL_REF, BOOL_ROWS, [{"column": "subscribed", "op": "ne", "value": True}]) == 1


def test_bool_column_unknown_spelling_is_a_validation_error() -> None:
    with pytest.raises(AnalyticsInputError):
        _count(BOOL_REF, BOOL_ROWS, [{"column": "subscribed", "op": "eq", "value": "yes"}])


def test_bool_column_group_compare_and_share() -> None:
    args = GroupCompareIn(
        dataset="T:1",
        metric={"fn": "sum", "column": "spend"},
        compare_column="subscribed",
        group_a=True,
        group_b=False,
    )
    out = engine.group_compare(group_compare_plan(BOOL_REF, args, LIMITS), BOOL_ROWS, deadline=None)
    assert [r.metrics[0].value for r in out.rows] == [30, 4]
    assert out.difference is not None
    assert out.difference.value == 26
    share = AggregateIn(
        dataset="T:1",
        metrics=[{"fn": "share", "condition": {"column": "subscribed", "op": "eq", "value": True}}],
    )
    value = engine.aggregate(aggregate_plan(BOOL_REF, share, LIMITS), BOOL_ROWS, deadline=None)
    metric = value.rows[0].metrics[0]
    assert (metric.numerator, metric.denominator) == (2, 3)


# --- 3: date range filters ---------------------------------------------------------------------

DATE_REF = _ref(_col("d", "date"))
DATE_ROWS = _rows(
    [
        {"d": "2024-01-15"},
        {"d": "2024-02"},
        {"d": "2024-03-01"},
        {"d": "2024-03-20"},
        {"d": "2023-12-31"},
    ]
)


@pytest.mark.parametrize(
    ("op", "value", "expected"),
    [
        ("lte", "2024-01", 2),  # a month operand means the whole month: <= 2024-01-31
        ("lt", "2024-01", 1),  # < 2024-01-01
        ("gte", "2024-02", 3),  # >= 2024-02-01 (the month cell 2024-02 lies entirely inside)
        ("gt", "2024-02", 2),  # > 2024-02-29
        ("gte", "2024-02-15", 2),  # month cell 2024-02 is not entirely on/after the 15th
        ("lte", "2024-02-15", 2),  # ...nor entirely on/before it
        ("gte", "2024-03-01", 2),
        ("lte", "2024-01-15", 2),
    ],
)
def test_date_comparisons_use_parsed_periods(op: str, value: str, expected: int) -> None:
    assert _count(DATE_REF, DATE_ROWS, [{"column": "d", "op": op, "value": value}]) == expected


def test_date_between_with_month_upper_bound_keeps_the_whole_month() -> None:
    filters = [{"column": "d", "op": "between", "values": ["2024-01-01", "2024-03"]}]
    assert _count(DATE_REF, DATE_ROWS, filters) == 4


@pytest.mark.parametrize("value", ["2024-99-99", "2024-13", "2024-02-30", "2024-00-10"])
def test_impossible_date_operands_are_rejected(value: str) -> None:
    with pytest.raises(AnalyticsInputError):
        _count(DATE_REF, DATE_ROWS, [{"column": "d", "op": "gte", "value": value}])


def test_between_low_after_high_by_period_is_rejected() -> None:
    with pytest.raises(AnalyticsInputError):
        _count(
            DATE_REF,
            DATE_ROWS,
            [{"column": "d", "op": "between", "values": ["2024-04", "2024-03-31"]}],
        )


def test_invalid_date_cells_never_match_ordered_filters() -> None:
    rows = _rows([{"d": "2024-99-99"}, {"d": "2024-01-02"}])
    assert _count(DATE_REF, rows, [{"column": "d", "op": "gte", "value": "2000-01"}]) == 1


# --- 5: very large numeric cells --------------------------------------------------------------

BIG_REF = _ref(_col("rev_usd", "numeric"), _col("n", "numeric"))


def test_round_value_handles_values_beyond_28_digits() -> None:
    assert round_value(Decimal("1e30"), 2) == 1e30
    assert round_value(Decimal("123456789012345678901234567890.125"), 2) == pytest.approx(
        1.2345678901234568e29
    )


@pytest.mark.parametrize("fn", ["sum", "mean", "median"])
def test_huge_cells_do_not_break_rounding(fn: str) -> None:
    rows = _rows([{"rev_usd": 10**30, "n": 1}, {"rev_usd": 3, "n": 2}, {"rev_usd": 2.5, "n": 3}])
    plan = aggregate_plan(
        BIG_REF, AggregateIn(dataset="T:1", metrics=[{"fn": fn, "column": "rev_usd"}]), LIMITS
    )
    metric = engine.aggregate(plan, rows, deadline=None).rows[0].metrics[0]
    assert metric.value is not None
    if fn == "sum":
        assert metric.exact == "1000000000000000000000000000005.5"  # exact, not 28 digits
    if fn == "median":
        assert metric.exact == "3"


def test_huge_float_cells_sum_exactly() -> None:
    rows = _rows([{"rev_usd": 1e300, "n": 1}, {"rev_usd": 1.5, "n": 2}])
    plan = aggregate_plan(
        BIG_REF, AggregateIn(dataset="T:1", metrics=[{"fn": "sum", "column": "rev_usd"}]), LIMITS
    )
    metric = engine.aggregate(plan, rows, deadline=None).rows[0].metrics[0]
    assert metric.exact is not None
    assert metric.exact.endswith("1.5")
    assert metric.value == 1e300


def test_group_compare_difference_of_huge_values_is_exact() -> None:
    ref = _ref(_col("seg", "categorical", ("a", "b"), 2), _col("rev_usd", "numeric"))
    rows = _rows([{"seg": "a", "rev_usd": 10**28 + 1}, {"seg": "b", "rev_usd": 10**28}])
    args = GroupCompareIn(
        dataset="T:1",
        metric={"fn": "sum", "column": "rev_usd"},
        compare_column="seg",
        group_a="a",
        group_b="b",
    )
    out = engine.group_compare(group_compare_plan(ref, args, LIMITS), rows, deadline=None)
    assert out.difference is not None
    assert out.difference.exact == "1"


# --- 6: NaN / Infinity operands ----------------------------------------------------------------

NAN_PAYLOADS = [
    {
        "dataset": "T:1",
        "metrics": [{"fn": "count"}],
        "filters": [{"column": "n", "op": "gt", "value": v}],
    }
    for v in (float("nan"), float("inf"), float("-inf"))
] + [
    {
        "dataset": "T:1",
        "metrics": [{"fn": "count"}],
        "filters": [{"column": "n", "op": "between", "values": [0, float("nan")]}],
    }
]


@pytest.mark.parametrize("payload", NAN_PAYLOADS)
def test_non_finite_operands_fail_the_strict_contract(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AggregateIn.model_validate_json(json.dumps(payload), strict=True)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_group_compare_levels_fail_the_contract(value: float) -> None:
    payload = {
        "dataset": "T:1",
        "metric": {"fn": "count"},
        "compare_column": "n",
        "group_a": value,
        "group_b": 1,
    }
    with pytest.raises(ValidationError):
        GroupCompareIn.model_validate_json(json.dumps(payload), strict=True)


def test_non_finite_operands_fail_validation_even_if_constructed() -> None:
    bad = Filter.model_construct(column="n", op="gt", value=float("nan"), values=None)
    args = AggregateIn(dataset="T:1", metrics=[{"fn": "count"}]).model_copy(
        update={"filters": [bad]}
    )
    with pytest.raises(AnalyticsInputError):
        aggregate_plan(BIG_REF, args, LIMITS)


# --- 8: numeric group_by over non-numeric cells ------------------------------------------------


def test_numeric_group_by_keeps_distinct_raw_values_apart() -> None:
    ref = _ref(_col("spend", "numeric"))
    rows = _rows([{"spend": "x"}, {"spend": "-"}, {"spend": 5}, {"spend": 7}, {"spend": "x"}])
    plan = aggregate_plan(
        ref, AggregateIn(dataset="T:1", metrics=[{"fn": "count"}], group_by=["spend"]), LIMITS
    )
    out = engine.aggregate(plan, rows, deadline=None)
    got = [(r.group["spend"], r.metrics[0].value) for r in out.rows]
    assert got == [(5, 1), (7, 1), ("-", 1), ("x", 2)]


# --- 7 / 20: analytics handles -----------------------------------------------------------------


def _tool_result(name: str, result: dict[str, Any]) -> ToolResult:
    return ToolResult(
        call_id="c",
        name=name,
        ok=True,
        output={"result": result, "warnings": []},
        observation="",
    )


def test_computing_tools_report_their_source_version_handle() -> None:
    result = {
        "workspace": "WS",
        "source_code": "SURVEY-2026",
        "source_version": 3,
        "operation": "aggregate",
        "rows": [{"group": {}, "metrics": []}],
    }
    assert _tool_result("aggregate", result).handles() == ("WS/SURVEY-2026@v3",)


def test_filter_rows_reports_version_and_row_handles() -> None:
    result = {
        "workspace": "WS",
        "source_code": "S",
        "source_version": 1,
        "operation": "filter_rows",
        "rows": [
            {"group": {}, "metrics": [], "row_number": 2, "handle": "WS/S@v1:R2"},
            {"group": {}, "metrics": [], "row_number": 9, "handle": "WS/S@v1:R9"},
        ],
    }
    assert _tool_result("filter_rows", result).handles() == (
        "WS/S@v1",
        "WS/S@v1:R2",
        "WS/S@v1:R9",
    )


def test_failed_or_malformed_analytics_outputs_have_no_handles() -> None:
    bad = ToolResult(call_id="c", name="aggregate", ok=False, output=None, observation="")
    assert bad.handles() == ()
    assert _tool_result("aggregate", {"workspace": "WS"}).handles() == ()
