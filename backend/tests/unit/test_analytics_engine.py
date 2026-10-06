"""Deterministic analytics engine: correctness, rounding, nulls, ordering, validation."""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any

import pytest

from marketsignal.analytics import engine
from marketsignal.analytics.engine import Row
from marketsignal.analytics.rounding import decimal_places, exact_str, round_value
from marketsignal.analytics.schema import ColumnSpec, DatasetRef, infer_unit, parse_dataset_id
from marketsignal.analytics.validate import (
    AnalyticsInputError,
    Limits,
    aggregate_plan,
    filter_rows_plan,
    group_compare_plan,
)
from marketsignal.tools.analytics_contracts import AggregateIn, FilterRowsIn, GroupCompareIn

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


REF = DatasetRef(
    dataset="SURV:1",
    table_id=uuid.uuid4(),
    source_version_id=uuid.uuid4(),
    source_code="SURV",
    source_version=1,
    title="Survey",
    table="survey",
    source_class="customer",
    row_count=8,
    columns=(
        _col("id", "text"),
        _col("segment", "categorical", ("Gen Z", "Millennial", "Gen X"), 3),
        _col("region", "categorical", ("North", "South"), 5),  # capped level list
        _col("nps", "numeric"),
        _col("spend_usd", "numeric"),
        _col("rate_pct", "numeric"),
        _col("survey_date", "date"),
        _col("delta", "numeric"),
    ),
)
DATA: list[dict[str, Any]] = [
    {
        "id": "a",
        "segment": "Gen Z",
        "region": "North",
        "nps": 9,
        "spend_usd": 10.005,
        "rate_pct": 12.25,
        "survey_date": "2026-01-03",
        "delta": -1.5,
    },
    {
        "id": "b",
        "segment": "Gen Z",
        "region": "South",
        "nps": 7,
        "spend_usd": 20,
        "rate_pct": 12.35,
        "survey_date": "2026-02-01",
        "delta": -2.5,
    },
    {
        "id": "c",
        "segment": "Millennial",
        "region": "North",
        "nps": None,
        "spend_usd": 30,
        "rate_pct": None,
        "survey_date": "2026-01-15",
        "delta": 0.5,
    },
    {
        "id": "d",
        "segment": "Millennial",
        "region": "West",
        "nps": 5,
        "spend_usd": "n/a",
        "rate_pct": 10,
        "survey_date": None,
        "delta": 2,
    },
    {
        "id": "e",
        "segment": "Gen X",
        "region": "East",
        "nps": 10,
        "spend_usd": 15.5,
        "rate_pct": 20,
        "survey_date": "2025-12-31",
        "delta": 0,
    },
    {
        "id": "f",
        "segment": "Gen Z",
        "region": "North",
        "nps": 8,
        "spend_usd": 0.125,
        "rate_pct": 5,
        "survey_date": "2026-03-01",
        "delta": 1,
    },
    {
        "id": "g",
        "segment": None,
        "region": "",
        "nps": 6,
        "spend_usd": 1,
        "rate_pct": 1,
        "survey_date": "2026-03-02",
        "delta": 3,
    },
    {
        "id": "h",
        "segment": "Gen X",
        "region": "Far North",
        "nps": 9,
        "spend_usd": 2,
        "rate_pct": 2,
        "survey_date": "2026-03-03",
        "delta": -4,
    },
]
ROWS = [Row(i + 1, f"WS/SURV@v1:R{i + 1}", v) for i, v in enumerate(DATA)]


def agg(**kw: Any) -> engine.Computed:
    return engine.aggregate(
        aggregate_plan(REF, AggregateIn(dataset="SURV:1", **kw), LIMITS), ROWS, deadline=None
    )


def one(c: engine.Computed, i: int = 0) -> dict[str, Any]:
    return c.rows[0].metrics[i].model_dump()


# --- rounding ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [
        ("12.25", 1, 12.2),  # half-even: 2 is even
        ("12.35", 1, 12.4),
        ("0.125", 2, 0.12),
        ("0.135", 2, 0.14),
        ("-2.5", 0, -2),
        ("-0.004", 2, 0.0),  # never -0.0
        ("7", None, 7),
        ("7.5", None, 7.5),
    ],
)
def test_round_half_even(value: str, places: int | None, expected: float) -> None:
    out = round_value(Decimal(value), places)
    assert out == expected
    assert str(out) != "-0.0"


def test_rounding_rules_by_fn_and_unit() -> None:
    assert decimal_places("count", "count", integral=True) is None
    assert decimal_places("min", "percent", integral=False) is None
    assert decimal_places("share", "percent", integral=False) == 1
    assert decimal_places("mean", "currency_usd", integral=False) == 2
    assert decimal_places("mean", "ratio", integral=False) == 3
    assert decimal_places("mean", "rating", integral=True) == 2
    assert decimal_places("sum", "number", integral=True) is None
    assert decimal_places("sum", "number", integral=False) == 2
    assert exact_str(Decimal("1.500")) == "1.5"
    assert exact_str(Decimal("-0")) == "0"


@pytest.mark.parametrize(
    ("name", "ctype", "unit"),
    [
        ("conversion_rate_pct", "numeric", "percent"),
        ("net_sales_usd", "numeric", "currency_usd"),
        ("value_usd_bn", "numeric", "currency_usd"),
        ("avg_rating", "numeric", "rating"),
        ("nps", "numeric", "rating"),
        ("orders", "numeric", "count"),
        ("returns_count", "numeric", "count"),
        ("units_fy26_ytd", "numeric", "count"),
        ("year", "numeric", "number"),
        ("debt_ratio", "numeric", "ratio"),
        ("segment", "categorical", "text"),
        ("verbatim", "text", "text"),
        ("survey_date", "date", "date"),
    ],
)
def test_unit_inference(name: str, ctype: str, unit: str) -> None:
    assert infer_unit(name, ctype) == unit


@pytest.mark.parametrize(
    "raw",
    [
        "x'; DROP TABLE dataset_rows;--",
        "values->>'a'",
        "1=1",
        "SURV",
        "SURV:0",
        "surv:1",
        "SURV:1:1",
        "SURV:01",
        ":1",
        "SURV:99999",
        "SURV: 1",
    ],
)
def test_dataset_id_parsing_rejects_everything_else(raw: str) -> None:
    assert parse_dataset_id(raw) is None


def test_dataset_id_parsing() -> None:
    assert parse_dataset_id("SURVEY-2026:1") == ("SURVEY-2026", 1)
    assert parse_dataset_id("FIN-SUMMARY-FY26:2") == ("FIN-SUMMARY-FY26", 2)


# --- metrics ----------------------------------------------------------------------------------


def test_count_and_count_distinct() -> None:
    c = agg(metrics=[{"fn": "count"}, {"fn": "count_distinct", "column": "segment"}])
    assert one(c, 0)["value"] == 8
    assert one(c, 0)["key"] == "count(*)"
    assert one(c, 1)["value"] == 3
    assert one(c, 1)["denominator"] == 7
    assert c.warnings == ["NULLS_EXCLUDED"]
    assert c.rows_scanned == 8
    assert c.rows_matched == 8


def test_sum_mean_median_min_max() -> None:
    c = agg(
        metrics=[
            {"fn": "sum", "column": "nps"},
            {"fn": "mean", "column": "nps"},
            {"fn": "median", "column": "nps"},
            {"fn": "max", "column": "delta"},
        ]
    )
    s, mean, median, mx = (one(c, i) for i in range(4))
    assert (s["value"], s["exact"], s["denominator"], s["unit"]) == (54, "54", 7, "rating")
    assert mean["value"] == 7.71  # 54 / 7 = 7.714285...
    assert mean["exact"].startswith("7.714285714285714285")
    assert median["value"] == 8.0
    assert mx["value"] == 3
    assert "NULLS_EXCLUDED" in c.warnings


def test_currency_sum_and_non_numeric_cell_is_null() -> None:
    c = agg(metrics=[{"fn": "sum", "column": "spend_usd"}, {"fn": "min", "column": "spend_usd"}])
    s = one(c, 0)
    assert s["exact"] == "78.63"
    assert s["value"] == 78.63
    assert s["unit"] == "currency_usd"
    assert s["denominator"] == 7  # "n/a" is not a number
    assert one(c, 1)["value"] == 0.125  # min is exact


def test_median_even_and_negatives() -> None:
    c = agg(metrics=[{"fn": "median", "column": "delta"}, {"fn": "sum", "column": "delta"}])
    assert one(c, 0)["exact"] == "0.25"  # sorted: -4 -2.5 -1.5 0 | 0.5 1 2 3
    assert one(c, 0)["value"] == 0.25
    assert one(c, 1)["value"] == -1.5
    assert one(c, 1)["exact"] == "-1.5"


def test_share_with_condition_and_filters() -> None:
    c = agg(
        metrics=[
            {
                "fn": "share",
                "condition": {"column": "segment", "op": "eq", "value": "Gen Z"},
            }
        ],
        filters=[{"column": "nps", "op": "gte", "value": 7}],
    )
    m = one(c)
    assert c.rows_matched == 5  # a b e f h
    assert (m["numerator"], m["denominator"], m["unit"]) == (3, 5, "percent")
    assert m["value"] == 60.0
    assert m["key"] == "share(segment=Gen Z)"


def test_share_rounding_half_even() -> None:
    # 1 of 8 = 12.5 exactly at 1 dp; 1/16 = 6.25 -> 6.2
    rows = [Row(i, "h", {"segment": "Gen Z" if i == 0 else "Gen X"}) for i in range(16)]
    plan = aggregate_plan(
        REF,
        AggregateIn(
            dataset="SURV:1",
            metrics=[
                {"fn": "share", "condition": {"column": "segment", "op": "eq", "value": "Gen Z"}}
            ],
        ),
        LIMITS,
    )
    m = engine.aggregate(plan, rows, deadline=None).rows[0].metrics[0]
    assert (m.value, m.exact) == (6.2, "6.25")


def test_empty_selection_and_zero_denominator() -> None:
    c = agg(
        metrics=[{"fn": "count"}, {"fn": "mean", "column": "nps"}],
        filters=[{"column": "nps", "op": "gt", "value": 100}],
    )
    assert c.warnings == ["EMPTY_SELECTION", "ZERO_DENOMINATOR"]
    assert one(c, 0)["value"] == 0
    assert one(c, 1)["value"] is None
    assert one(c, 1)["exact"] is None
    grouped = agg(
        metrics=[{"fn": "count"}],
        group_by=["segment"],
        filters=[{"column": "nps", "op": "gt", "value": 100}],
    )
    assert grouped.rows == []
    assert grouped.warnings == ["EMPTY_SELECTION"]


def test_grouped_ordering_ties_and_nulls() -> None:
    c = agg(metrics=[{"fn": "count"}, {"fn": "mean", "column": "nps"}], group_by=["segment"])
    assert [r.group["segment"] for r in c.rows] == ["Gen X", "Gen Z", "Millennial", None]
    by_count = agg(
        metrics=[{"fn": "count"}],
        group_by=["segment"],
        order={"by": "value", "metric_index": 0, "direction": "desc"},
    )
    # Gen Z 3; then Gen X 2 and Millennial 2 tie -> group order; then the null group (1)
    assert [r.group["segment"] for r in by_count.rows] == ["Gen Z", "Gen X", "Millennial", None]
    bottom = agg(
        metrics=[{"fn": "mean", "column": "nps"}],
        group_by=["segment"],
        order={"by": "value", "metric_index": 0, "direction": "asc"},
        limit=2,
    )
    assert [r.group["segment"] for r in bottom.rows] == ["Millennial", None]
    assert bottom.rows[0].metrics[0].value == 5.0


def test_two_column_group_by_and_truncation() -> None:
    plan = aggregate_plan(
        REF,
        AggregateIn(dataset="SURV:1", metrics=[{"fn": "count"}], group_by=["segment", "region"]),
        LIMITS,
    )
    c = engine.aggregate(plan, ROWS, deadline=None)
    assert len(c.rows) == 7  # (Gen Z, North) holds rows a and f
    assert c.rows[2].group == {"segment": "Gen Z", "region": "North"}
    assert c.rows[2].metrics[0].value == 2
    small = Limits(5, 20, 4, 2, 3, 20, 1000, 5.0)
    truncated = engine.aggregate(
        aggregate_plan(
            REF, AggregateIn(dataset="SURV:1", metrics=[{"fn": "count"}], group_by=["id"]), small
        ),
        ROWS,
        deadline=None,
    )
    assert len(truncated.rows) == 3
    assert truncated.warnings == ["GROUPS_TRUNCATED"]


def test_filters_semantics() -> None:
    def matched(f: dict[str, Any]) -> int:
        return agg(metrics=[{"fn": "count"}], filters=[f]).rows_matched

    assert matched({"column": "segment", "op": "ne", "value": "Gen Z"}) == 4  # null excluded
    assert matched({"column": "segment", "op": "in", "values": ["Gen Z", "Gen X"]}) == 5
    assert matched({"column": "segment", "op": "not_in", "values": ["Gen Z"]}) == 4
    assert matched({"column": "segment", "op": "is_null"}) == 1
    assert matched({"column": "region", "op": "is_null"}) == 1  # blank string is null
    assert matched({"column": "nps", "op": "between", "values": [6, 8]}) == 3
    assert matched({"column": "delta", "op": "lt", "value": 0}) == 3
    assert matched({"column": "survey_date", "op": "gte", "value": "2026-03"}) == 3
    assert (
        matched({"column": "survey_date", "op": "between", "values": ["2026-01-01", "2026-01-31"]})
        == 2
    )
    assert matched({"column": "region", "op": "eq", "value": "Nowhere"}) == 0  # capped levels


def test_group_compare_difference() -> None:
    plan = group_compare_plan(
        REF,
        GroupCompareIn(
            dataset="SURV:1",
            metric={"fn": "mean", "column": "nps"},
            compare_column="segment",
            group_a="Gen Z",
            group_b="Millennial",
        ),
        LIMITS,
    )
    c = engine.group_compare(plan, ROWS, deadline=None)
    a, b = c.rows[0].metrics[0], c.rows[1].metrics[0]
    assert (a.value, b.value) == (8.0, 5.0)
    assert c.rows[0].group == {"segment": "Gen Z"}
    assert c.difference is not None
    assert (c.difference.value, c.difference.exact, c.difference.unit) == (3.0, "3", "rating")
    assert c.difference.denominator == 4
    assert c.warnings == ["NULLS_EXCLUDED"]


def test_group_compare_zero_denominator() -> None:
    plan = group_compare_plan(
        REF,
        GroupCompareIn(
            dataset="SURV:1",
            metric={"fn": "mean", "column": "nps"},
            compare_column="region",
            group_a="North",
            group_b="Atlantis",
        ),
        LIMITS,
    )
    c = engine.group_compare(plan, ROWS, deadline=None)
    assert c.rows[1].metrics[0].value is None
    assert c.difference is not None
    assert c.difference.value is None
    assert "ZERO_DENOMINATOR" in c.warnings


def test_filter_rows_order_handles_and_limit() -> None:
    plan = filter_rows_plan(
        REF,
        FilterRowsIn(
            dataset="SURV:1",
            columns=["id", "nps"],
            order_by="nps",
            direction="desc",
            limit=3,
            filters=[{"column": "segment", "op": "not_null"}],
        ),
        LIMITS,
    )
    c = engine.filter_rows(plan, ROWS, deadline=None)
    assert [r.group["id"] for r in c.rows] == ["e", "a", "h"]  # 10, 9 (row 1), 9 (row 8)
    assert c.rows[0].handle == "WS/SURV@v1:R5"
    assert c.rows[0].row_number == 5
    assert set(c.rows[0].group) == {"id", "nps"}
    assert c.rows_matched == 7


def test_deterministic_repeat() -> None:
    kw = {"metrics": [{"fn": "mean", "column": "spend_usd"}], "group_by": ["segment"]}
    assert agg(**kw) == agg(**kw)


def test_deadline_raises_timeout() -> None:
    rows = [Row(i, "h", {"nps": i}) for i in range(5000)]
    plan = aggregate_plan(REF, AggregateIn(dataset="SURV:1", metrics=[{"fn": "count"}]), LIMITS)
    with pytest.raises(TimeoutError):
        engine.aggregate(plan, rows, deadline=time.monotonic() - 1)


# --- validation -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"metrics": [{"fn": "count", "column": "x'; DROP TABLE dataset_rows;--"}]},
        {"metrics": [{"fn": "sum", "column": "values->>'a'"}]},
        {"metrics": [{"fn": "count"}], "filters": [{"column": "1=1", "op": "is_null"}]},
        {"metrics": [{"fn": "count"}], "group_by": ["NPS"]},  # case-sensitive
        {"metrics": [{"fn": "sum", "column": "segment"}]},
        {"metrics": [{"fn": "mean", "column": "survey_date"}]},
        {"metrics": [{"fn": "max", "column": "id"}]},
        {"metrics": [{"fn": "mean"}]},
        {"metrics": [{"fn": "share"}]},
        {"metrics": [{"fn": "share", "condition": {"column": "nps", "op": "is_null"}}]},
        {
            "metrics": [
                {
                    "fn": "share",
                    "column": "nps",
                    "condition": {"column": "segment", "op": "eq", "value": "Gen Z"},
                }
            ]
        },
        {"metrics": [{"fn": "count", "condition": {"column": "nps", "op": "gt", "value": 1}}]},
        {"metrics": [{"fn": "count"}, {"fn": "count"}]},
        {"metrics": [{"fn": "count"}], "filters": [{"column": "nps", "op": "eq", "value": "9"}]},
        {"metrics": [{"fn": "count"}], "filters": [{"column": "nps", "op": "eq", "value": True}]},
        {"metrics": [{"fn": "count"}], "filters": [{"column": "nps", "op": "eq"}]},
        {
            "metrics": [{"fn": "count"}],
            "filters": [{"column": "segment", "op": "gt", "value": "a"}],
        },
        {
            "metrics": [{"fn": "count"}],
            "filters": [{"column": "survey_date", "op": "gt", "value": "yesterday"}],
        },
        {
            "metrics": [{"fn": "count"}],
            "filters": [{"column": "segment", "op": "eq", "value": "gen z"}],
        },
        {
            "metrics": [{"fn": "count"}],
            "filters": [{"column": "nps", "op": "between", "values": [9, 1]}],
        },
        {
            "metrics": [{"fn": "count"}],
            "filters": [{"column": "nps", "op": "between", "values": [1]}],
        },
        {"metrics": [{"fn": "count"}], "filters": [{"column": "nps", "op": "in", "values": []}]},
        {
            "metrics": [{"fn": "count"}],
            "filters": [{"column": "nps", "op": "in", "values": [1, None]}],
        },
        {"metrics": [{"fn": "count"}], "filters": [{"column": "nps", "op": "is_null", "value": 1}]},
        {
            "metrics": [{"fn": "count"}],
            "filters": [{"column": "nps", "op": "eq", "value": 1, "values": [1]}],
        },
        {"metrics": [{"fn": "count"}], "group_by": ["segment", "segment"]},
        {"metrics": [{"fn": "count"}], "order": {"by": "value", "metric_index": 1}},
        {"metrics": [{"fn": "count"}], "order": {"by": "group"}},
    ],
)
def test_invalid_requests(kw: dict[str, Any]) -> None:
    with pytest.raises(AnalyticsInputError) as err:
        aggregate_plan(REF, AggregateIn(dataset="SURV:1", **kw), LIMITS)
    assert "DROP" not in str(err.value).upper() or "column" in str(err.value)


def test_limits_from_settings_are_enforced() -> None:
    tight = Limits(1, 2, 1, 1, 50, 5, 1000, 5.0)
    cases = [
        {"metrics": [{"fn": "count"}, {"fn": "count", "column": "nps"}]},
        {"metrics": [{"fn": "count"}], "group_by": ["segment", "region"]},
        {
            "metrics": [{"fn": "count"}],
            "filters": [{"column": "nps", "op": "is_null"}, {"column": "id", "op": "is_null"}],
        },
        {
            "metrics": [{"fn": "count"}],
            "filters": [{"column": "nps", "op": "in", "values": [1, 2, 3]}],
        },
    ]
    for kw in cases:
        with pytest.raises(AnalyticsInputError):
            aggregate_plan(REF, AggregateIn(dataset="SURV:1", **kw), tight)
    with pytest.raises(AnalyticsInputError):
        filter_rows_plan(REF, FilterRowsIn(dataset="SURV:1", limit=6), tight)


def test_group_compare_validation() -> None:
    for kw in (
        {"group_a": "Gen Z", "group_b": "Gen Z"},
        {"group_a": "Gen Z", "group_b": "gen-z"},  # unknown level (complete level list)
        {"group_a": None, "group_b": "Gen Z"},
    ):
        with pytest.raises(AnalyticsInputError):
            group_compare_plan(
                REF,
                GroupCompareIn(
                    dataset="SURV:1", metric={"fn": "count"}, compare_column="segment", **kw
                ),
                LIMITS,
            )
    with pytest.raises(AnalyticsInputError):
        group_compare_plan(
            REF,
            GroupCompareIn(
                dataset="SURV:1",
                metric={"fn": "max", "column": "survey_date"},
                compare_column="segment",
                group_a="Gen Z",
                group_b="Gen X",
            ),
            LIMITS,
        )
