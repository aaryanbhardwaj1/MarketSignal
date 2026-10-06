"""Phase B contract tweaks: scale inference, scaled metrics/observations, filter_rows row fields."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from marketsignal.analytics import engine
from marketsignal.analytics.engine import Row
from marketsignal.analytics.schema import ColumnSpec, DatasetRef, infer_scale, infer_unit
from marketsignal.analytics.validate import (
    Limits,
    aggregate_plan,
    filter_rows_plan,
    group_compare_plan,
)
from marketsignal.tools.analytics_contracts import (
    AggregateIn,
    AnalyticsResult,
    FilterRowsIn,
    GroupCompareIn,
    ResultRow,
)
from marketsignal.tools.observation import render

LIMITS = Limits(5, 20, 4, 2, 50, 20, 1000, 5.0)


@pytest.mark.parametrize(
    ("name", "ctype", "scale"),
    [
        ("value_usd_bn", "numeric", "billion"),
        ("revenue_billions", "numeric", "billion"),
        ("fy25_revenue_usd_m", "numeric", "million"),
        ("sales_mn", "numeric", "million"),
        ("units_millions", "numeric", "million"),
        ("units_k", "numeric", "thousand"),
        ("visits_thousand", "numeric", "thousand"),
        ("net_sales_usd", "numeric", ""),
        ("share_pct_m", "numeric", ""),  # percent is never scaled
        ("growth_percent_bn", "numeric", ""),
        ("avg_rating_k", "numeric", ""),  # ratings and ratios are never scaled
        ("value_bn", "categorical", ""),
        ("month", "date", ""),
        ("mmm", "numeric", ""),
    ],
)
def test_scale_inference(name: str, ctype: str, scale: str) -> None:
    assert infer_scale(name, ctype) == scale


def _col(name: str, ctype: str, levels: tuple[str, ...] = ()) -> ColumnSpec:
    return ColumnSpec(
        name,
        ctype,
        "x",
        infer_unit(name, ctype),
        levels,
        len(levels),
        3,
        infer_scale(name, ctype),
    )


REF = DatasetRef(
    dataset="SIZING:1",
    table_id=uuid.uuid4(),
    source_version_id=uuid.uuid4(),
    source_code="SIZING",
    source_version=1,
    title="Sizing",
    table="Market",
    source_class="market",
    row_count=3,
    columns=(
        _col("market", "categorical", ("EU", "US")),
        _col("value_usd_bn", "numeric"),
        _col("units_k", "numeric"),
    ),
)
ROWS = [
    Row(2, "WS/SIZING@v1:SH1.R2", {"market": "US", "value_usd_bn": 15.1, "units_k": 3}),
    Row(3, "WS/SIZING@v1:SH1.R3", {"market": "US", "value_usd_bn": 16.2, "units_k": 4}),
    Row(4, "WS/SIZING@v1:SH1.R4", {"market": "EU", "value_usd_bn": 9.9, "units_k": 2}),
]


def test_column_info_carries_scale() -> None:
    cols = {c.name: c for c in REF.info(with_columns=True).columns}
    assert (cols["value_usd_bn"].unit, cols["value_usd_bn"].scale) == ("currency_usd", "billion")
    assert cols["units_k"].scale == "thousand"
    assert cols["market"].scale == ""


def test_metric_scale_follows_the_column_but_not_counts_or_shares() -> None:
    plan = aggregate_plan(
        REF,
        AggregateIn(
            dataset="SIZING:1",
            metrics=[
                {"fn": "sum", "column": "value_usd_bn"},
                {"fn": "mean", "column": "units_k"},
                {"fn": "count"},
                {
                    "fn": "share",
                    "condition": {"column": "market", "op": "eq", "value": "US"},
                },
            ],
        ),
        LIMITS,
    )
    metrics = engine.aggregate(plan, ROWS, deadline=None).rows[0].metrics
    assert [(m.unit, m.scale) for m in metrics] == [
        ("currency_usd", "billion"),
        ("number", "thousand"),
        ("count", ""),
        ("percent", ""),
    ]
    assert metrics[0].value == 41.2


def test_group_compare_difference_keeps_the_scale_and_sums_denominators() -> None:
    plan = group_compare_plan(
        REF,
        GroupCompareIn(
            dataset="SIZING:1",
            metric={"fn": "sum", "column": "value_usd_bn"},
            compare_column="market",
            group_a="US",
            group_b="EU",
        ),
        LIMITS,
    )
    c = engine.group_compare(plan, ROWS, deadline=None)
    assert c.difference is not None
    assert (c.difference.value, c.difference.scale) == (21.4, "billion")
    assert c.difference.denominator == 3  # denA + denB


def test_filter_rows_sets_row_number_and_handle_outside_group() -> None:
    plan = filter_rows_plan(
        REF,
        FilterRowsIn(dataset="SIZING:1", columns=["market", "value_usd_bn"], limit=2),
        LIMITS,
    )
    rows = engine.filter_rows(plan, ROWS, deadline=None).rows
    assert [(r.row_number, r.handle) for r in rows] == [
        (2, "WS/SIZING@v1:SH1.R2"),
        (3, "WS/SIZING@v1:SH1.R3"),
    ]
    assert rows[0].group == {"market": "US", "value_usd_bn": 15.1}


def test_columns_named_like_the_old_reserved_keys_are_ordinary() -> None:
    ref = DatasetRef(**_ref_with("@row"))
    plan = filter_rows_plan(ref, FilterRowsIn(dataset="SIZING:1", columns=["@row"]), LIMITS)
    rows = engine.filter_rows(plan, [Row(2, "WS/X@v1:R2", {"@row": "x"})], deadline=None).rows
    assert rows[0].group == {"@row": "x"}
    assert rows[0].row_number == 2


def _ref_with(name: str) -> dict[str, Any]:
    return {
        "dataset": "SIZING:1",
        "table_id": REF.table_id,
        "source_version_id": REF.source_version_id,
        "source_code": "SIZING",
        "source_version": 1,
        "title": "t",
        "table": "t",
        "source_class": "market",
        "row_count": 1,
        "columns": (_col(name, "text"),),
    }


def _out(rows: list[ResultRow], operation: str = "aggregate") -> dict[str, Any]:
    result = AnalyticsResult(
        result_id="00000000-0000-0000-0000-000000000001",
        workspace="WS",
        dataset="SIZING:1",
        source_code="SIZING",
        source_version=1,
        table="Market",
        operation=operation,  # type: ignore[arg-type]
        spec={},
        rows=rows,
        rows_scanned=3,
        rows_matched=3,
        rounding="half_even",
    )
    return {"result": result.model_dump(mode="json"), "warnings": []}


def test_observation_states_the_scale() -> None:
    plan = aggregate_plan(
        REF,
        AggregateIn(dataset="SIZING:1", metrics=[{"fn": "max", "column": "value_usd_bn"}]),
        LIMITS,
    )
    out = render("aggregate", _out(engine.aggregate(plan, ROWS, deadline=None).rows), 2000)
    assert "max(value_usd_bn) = 16.2 billion USD (exact 16.2; n=3)" in out


def test_filter_rows_observation_uses_row_fields() -> None:
    row = ResultRow(group={"market": "US"}, metrics=[], row_number=2, handle="WS/S@v1:SH1.R2")
    out = render("filter_rows", _out([row], "filter_rows"), 2000)
    assert '<row n="2" handle="WS/S@v1:SH1.R2">market=US</row>' in out


def test_describe_observation_states_the_scale() -> None:
    output = {"datasets": [REF.info(with_columns=True).model_dump(mode="json")], "warnings": []}
    out = render("describe_dataset", output, 2000)
    assert 'name="value_usd_bn" type="numeric" unit="currency_usd" scale="billion"' in out
    assert 'name="market" type="categorical" unit="text" non_empty' in out
