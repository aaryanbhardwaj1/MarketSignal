"""Pure metric functions of the analytics evaluation (synthetic results; no DB)."""

from __future__ import annotations

from typing import Any

from marketsignal.evaluation import analytics_metrics as am

RID = "0b2c4f6e-1111-4a2b-9c3d-123456789abc"


def share_result(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "result_id": RID,
        "workspace": "NORTHSTAR",
        "dataset": "SURVEY-2026:1",
        "operation": "aggregate",
        "spec": {
            "dataset": "SURVEY-2026:1",
            "filters": [{"column": "age_group", "op": "in", "operands": ["18-21", "22-24"]}],
            "metrics": [
                {
                    "fn": "share",
                    "column": None,
                    "condition": {"column": "pain", "op": "eq", "operands": ["fit"]},
                }
            ],
            "group_by": ["segment"],
        },
        "rows": [
            {
                "group": {"segment": "Campus"},
                "metrics": [
                    {
                        "key": "share(pain=fit)",
                        "fn": "share",
                        "column": "pain",
                        "value": 9.4,
                        "exact": "9.375",
                        "unit": "percent",
                        "numerator": 9,
                        "denominator": 96,
                    }
                ],
            }
        ],
        "warnings": [],
    }
    return {**base, **over}


GOLD_ENTRY: dict[str, Any] = {
    "tool": "aggregate",
    "dataset": "SURVEY-2026:1",
    "spec": {
        "dataset": "SURVEY-2026:1",
        "metrics": [{"fn": "share", "condition": {"column": "pain", "op": "eq", "value": "fit"}}],
        "filters": [{"column": "age_group", "op": "in", "values": ["22-24", "18-21"]}],
        "group_by": ["segment"],
    },
    "values": [
        {
            "group": {"segment": "Campus"},
            "metric": "share(pain eq fit)",
            "value": 9.4,
            "exact": "9.375",
            "unit": "percent",
            "rounding": "1dp",
            "denominator": 96,
            "numerator": 9,
        }
    ],
}


def test_cells_cover_metrics_difference_and_filter_rows() -> None:
    compare = {
        "result_id": RID,
        "dataset": "PRODUCT-PERF:2",
        "operation": "group_compare",
        "rows": [
            {"group": {"p": "A"}, "metrics": [{"key": "max(r)", "fn": "max", "value": 16.8}]},
            {"group": {"p": "B"}, "metrics": [{"key": "max(r)", "fn": "max", "value": 13.1}]},
        ],
        "difference": {"key": "difference(max(r))", "fn": "max", "value": 3.7, "exact": "3.7"},
    }
    got = am.cells(compare)
    assert [c.value for c in got] == [16.8, 13.1, 3.7]
    assert got[-1].group == {am.DIFFERENCE: True}
    rows = {
        "result_id": RID,
        "dataset": "CHANNEL-PERF:1",
        "operation": "filter_rows",
        "rows": [
            {"group": {"@row": 116, "@handle": "NORTHSTAR/C@v1:R116", "conv": 3.4}, "metrics": []},
            {"group": {"conv": "2.0"}, "row_number": 3, "handle": "NORTHSTAR/C@v1:R3"},
        ],
    }
    cells = am.cells(rows)
    assert [(c.column, c.exact, c.handle) for c in cells] == [
        ("conv", "3.4", "NORTHSTAR/C@v1:R116"),
        ("conv", "2", "NORTHSTAR/C@v1:R3"),
    ]


def test_match_gold_requires_dataset_metric_group_and_number() -> None:
    gold = am.gold_values(GOLD_ENTRY)[0]
    match = am.match_gold(gold, am.cells(share_result()))
    assert match.matched
    assert match.exact_equal
    assert match.rounded_equal
    assert match.component("denominator")
    assert match.component("unit")
    # exact only (engine rounded differently) still matches; rounding component fails
    off = share_result()
    off["rows"][0]["metrics"][0]["value"] = 9.38
    m2 = am.match_gold(gold, am.cells(off))
    assert m2.matched
    assert not m2.component("rounding")
    wrong_group = share_result()
    wrong_group["rows"][0]["group"] = {"segment": "Other"}
    assert not am.match_gold(gold, am.cells(wrong_group)).matched
    assert not am.match_gold(gold, am.cells(share_result(dataset="X:1"))).matched
    # a filtered scalar (empty group) for a grouped gold value is accepted
    scalar = share_result()
    scalar["rows"][0]["group"] = {}
    assert am.match_gold(gold, am.cells(scalar)).matched
    # null gold (zero denominator) matches a null cell only
    null_gold = {**gold, "value": None, "exact": None}
    assert not am.match_gold(null_gold, am.cells(share_result())).matched


def test_gold_values_append_compare_difference() -> None:
    entry = {
        "tool": "group_compare",
        "dataset": "D:1",
        "values": [{"group": {"p": "A"}, "metric": "max(r)", "value": 1, "exact": "1"}],
        "difference": {"value": 0.5, "exact": "0.5", "unit": "percent", "denominator": 2},
    }
    values = am.gold_values(entry)
    assert values[-1]["group"] == {am.DIFFERENCE: True}
    assert values[-1]["metric"] == "max(r)"
    assert all(v["dataset"] == "D:1" for v in values)


def test_spec_components_normalize_filters_and_grouping() -> None:
    res = share_result()
    comps = am.spec_components("aggregate", GOLD_ENTRY["spec"], "aggregate", res["spec"])
    assert comps == {"filter": True, "aggregation": True, "grouping": True}
    single = am.norm_filter({"column": "c", "op": "in", "values": [2023]})
    assert single == am.norm_filter({"column": "c", "op": "eq", "operands": ["2023.0"]})
    ungrouped = {**res["spec"], "group_by": []}
    assert (
        am.spec_components("aggregate", GOLD_ENTRY["spec"], "aggregate", ungrouped)["grouping"]
        is False
    )
    gold_cmp = {"metric": {"fn": "mean", "column": "x"}, "compare_column": "p", "group_a": "A"}
    gold_cmp["group_b"] = "B"
    spec_cmp = {**gold_cmp, "group_a": "b", "group_b": "a", "filters": []}
    assert am.spec_components("group_compare", gold_cmp, "group_compare", spec_cmp) == {
        "filter": True,
        "aggregation": True,
        "grouping": True,
    }
    lookup = am.spec_components("filter_rows", {"filters": []}, "filter_rows", {"filters": []})
    assert lookup == {"filter": True, "aggregation": None, "grouping": None}
    best = am.best_spec_match(GOLD_ENTRY, [share_result(dataset="X:1"), res])
    assert best["result_id"] == RID
    assert best["dataset"]


def test_statements_respect_rounding_rule_and_formats() -> None:
    gold = {"value": 9.4, "exact": "9.375", "unit": "percent", "rounding": "1dp"}

    def kind(text: str) -> str | None:
        return am.best_statement(gold, am.mentions(text))

    assert kind("9.4% of them") == "stated"
    assert kind("9.38% of them") == "stated"  # more precise than the rule
    assert kind("about 9% of them") == "approximate"
    assert kind("$9.4 spent") is None  # currency is not a percent
    big = {"value": 3034559, "exact": "3034559", "unit": "currency_usd", "rounding": "exact"}
    assert am.best_statement(big, am.mentions("sales were $3,034,559")) == "stated"
    assert am.best_statement(big, am.mentions("sales were $3.0 million")) == "approximate"
    assert am.mentions(f"value [[result:{RID}]] in 2026") == []


def test_recheck_result_units_flags_unsupported_computed_numbers() -> None:
    content = (
        f"### Answer\nCampus picks fit 9.4% of the time (9 of 96) [[result:{RID}]].\n"
        f"Campus share was 31% [[result:{RID}]].\n\n### Key findings\n- Plain text claim 5%.\n"
    )
    out = am.recheck_result_units(content, {RID: share_result()}, {})
    assert out.result_units == 2
    assert out.unsupported_units == 1
    assert out.numbers == 4
    assert out.supported_numbers == 3
    assert out.unsupported[0]["numbers"] == ["31%"]
    # the exact rounded to the stated decimals is supported; an unknown result supports nothing
    assert am.recheck_result_units(f"9.38% [[result:{RID}]]", {RID: share_result()}, {}).numbers
    assert (
        am.recheck_result_units(
            f"9.38% [[result:{RID}]]", {RID: share_result()}, {}
        ).unsupported_units
        == 0
    )
    assert am.recheck_result_units(f"9.4% [[result:{RID}]]", {}, {}).unsupported_units == 1


def test_recheck_accepts_spec_operands_and_row_counts_but_not_other_numbers() -> None:
    """Live dev finding: "a rating of 1", "6 or lower" and "600 rows scanned" restate the
    computation itself (filter operands, matched/scanned rows), not an unsupported figure."""
    result = share_result(
        spec={
            "dataset": "SURVEY-2026:1",
            "filters": [{"column": "nps", "op": "lte", "operands": [6]}],
            "metrics": [
                {"fn": "share", "condition": {"column": "rating", "op": "eq", "operands": [1]}}
            ],
        },
        rows_scanned=600,
        rows_matched=96,
    )
    unit = (
        f"Of 96 matched rows (600 scanned) with NPS 6 or lower and a rating of 1 [[result:{RID}]]."
    )
    assert am.recheck_result_units(unit, {RID: result}, {}).unsupported_units == 0
    other = f"Of 97 rows with NPS 7 [[result:{RID}]]."
    assert am.recheck_result_units(other, {RID: result}, {}).unsupported[0]["numbers"] == [
        "97",
        "7",
    ]


def test_trace_helpers_count_calls() -> None:
    run = {
        "agent": {
            "trace": [
                {"tool": "describe_dataset"},
                {"tool": "aggregate"},
                {"tool": "search_evidence"},
            ]
        },
        "timings": {"retrieval_ms": 3},
    }
    assert len(am.calls(run, am.ANALYTICS_TOOLS)) == 2
    assert len(am.calls(run, am.COMPUTE_TOOLS)) == 1
    assert am.retrieval_calls(run) == 2
    assert am.retrieval_calls({"agent": None, "timings": {}}) == 0
