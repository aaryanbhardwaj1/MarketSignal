"""Governed structured-analytics contract (Phase 5; plan §18 analytics, ADR-0006): the frozen
boundary between the analytics tools, both transports, the research agent and synthesis.

Principles every implementation keeps:

* **Deterministic computation.** The model chooses *what* to compute (dataset, metric,
  filters, grouping); code computes it. No SQL, no expressions, no code: every field is a
  closed enum or a value; dataset and column names are matched against the stored column
  profile (``dataset_tables.columns``) and are only ever used as JSON keys / bound values.
* **Bounded.** Filters, filter values, metrics, group-by fields, groups and rows all have limits
  (input models here; the engine also enforces the configured ``analytics_*`` settings).
* **Provenance.** Every computed result is an :class:`AnalyticsResult` persisted in
  ``analytics_results`` with workspace, dataset, source version, the normalized spec, the
  denominator and the rounding rule, under a ``result_id``. Answers cite it as a computed
  result (``[R#]`` → ``[[result:<id>]]``), never as a text evidence handle.
* **Untrusted values.** Categorical levels come from documents: they are data, never
  instructions, and are escaped in observations.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from marketsignal.tools.contracts import _In, _Out

ANALYTICS_TOOL_NAMES = ("aggregate", "describe_dataset", "filter_rows", "group_compare")

DATASET_ID_MAX_CHARS = 120
COLUMN_MAX_CHARS = 64
VALUE_MAX_CHARS = 120

DatasetId = Annotated[str, StringConstraints(min_length=3, max_length=DATASET_ID_MAX_CHARS)]
Column = Annotated[str, StringConstraints(min_length=1, max_length=COLUMN_MAX_CHARS)]
# Finite floats only: NaN/Infinity (which ``json`` emits and pydantic parses by default) can
# never be compared or stored in jsonb, so they fail validation (VALIDATION_ERROR) up front.
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
Scalar = (
    Annotated[str, StringConstraints(max_length=VALUE_MAX_CHARS)] | int | FiniteFloat | bool | None
)

AggFn = Literal["count", "count_distinct", "sum", "mean", "median", "min", "max", "share"]
FilterOp = Literal[
    "eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "between", "is_null", "not_null"
]
Unit = Literal["count", "percent", "currency_usd", "number", "rating", "ratio", "date", "text"]
# The magnitude a column's values are stated in, inferred from its name's tokens (``_k``/
# ``thousand(s)``, ``_m``/``mn``/``million(s)``, ``_bn``/``billion(s)``): ``value_usd_bn`` = 15.1
# means USD 15.1 billion. Percent, rating, ratio, date and text values are never scaled.
Scale = Literal["", "thousand", "million", "billion"]

# Warnings / result states (also used as ToolResult warnings).
EMPTY_SELECTION = "EMPTY_SELECTION"  # the filters matched no rows (a valid, empty result)
ZERO_DENOMINATOR = "ZERO_DENOMINATOR"  # a share/mean over zero eligible rows: value is null
NULLS_EXCLUDED = "NULLS_EXCLUDED"  # null/empty cells were excluded from a metric
GROUPS_TRUNCATED = "GROUPS_TRUNCATED"


class Filter(_In):
    """One predicate on one column. ``value`` for scalar ops, ``values`` for in/not_in/between
    (between = [low, high], inclusive)."""

    column: Column
    op: FilterOp
    value: Scalar = None
    values: list[Scalar] | None = Field(default=None, max_length=20)


class Metric(_In):
    """``share`` = percentage of the (filtered) rows that also satisfy ``condition``;
    denominator = filtered rows with a non-null value in the condition's column. ``count``
    needs no column (counts rows)."""

    fn: AggFn
    column: Column | None = None
    condition: Filter | None = None  # share only
    # ``label`` is a caller-side note kept only in the result's ``spec``; it never renames the
    # metric (``MetricValue.key`` is always derived from fn/column/condition).
    label: Annotated[str, StringConstraints(max_length=40)] | None = None


class Order(_In):
    by: Literal["value", "group"] = "value"
    metric_index: int = Field(default=0, ge=0, le=3)
    direction: Literal["asc", "desc"] = "desc"


class DescribeDatasetIn(_In):
    """``describe_dataset``: list the workspace's analysable datasets (no ``dataset``), or the
    schema of one dataset: columns, types, categorical levels, row count, source version."""

    dataset: DatasetId | None = None


class AggregateIn(_In):
    """``aggregate``: metrics over filtered rows, optionally grouped (≤2 columns), ordered and
    limited (top/bottom-N)."""

    dataset: DatasetId
    metrics: list[Metric] = Field(min_length=1, max_length=4)
    filters: list[Filter] | None = Field(default=None, max_length=5)
    group_by: list[Column] | None = Field(default=None, max_length=2)
    order: Order | None = None
    limit: int | None = Field(default=None, ge=1, le=50)


class GroupCompareIn(_In):
    """``group_compare``: one metric for two levels of one column (A vs B), with the difference
    and both denominators."""

    dataset: DatasetId
    metric: Metric
    compare_column: Column
    group_a: Scalar
    group_b: Scalar
    filters: list[Filter] | None = Field(default=None, max_length=5)


class FilterRowsIn(_In):
    """``filter_rows``: a bounded listing of matching rows (≤20), selected columns (≤8)."""

    dataset: DatasetId
    filters: list[Filter] | None = Field(default=None, max_length=5)
    columns: list[Column] | None = Field(default=None, max_length=8)
    order_by: Column | None = None
    direction: Literal["asc", "desc"] = "asc"
    limit: int | None = Field(default=None, ge=1, le=20)


# --- outputs ---------------------------------------------------------------------------------


class ColumnInfo(_Out):
    name: str
    type: str  # numeric | categorical | text | date (from the stored profile)
    unit: Unit
    levels: list[str] = Field(default_factory=list)  # categorical levels (≤ profile cap)
    non_empty: int
    scale: Scale = ""  # see :data:`Scale`


class DatasetInfo(_Out):
    dataset: str  # stable id: "<SOURCE_CODE>:<sheet_ordinal>"
    source_code: str
    source_version: int
    title: str
    table: str
    source_class: str
    row_count: int
    columns: list[ColumnInfo] = Field(default_factory=list)  # empty in the listing view


class DescribeDatasetOut(_Out):
    datasets: list[DatasetInfo]
    warnings: list[str] = Field(default_factory=list)


class MetricValue(_Out):
    key: str  # e.g. "share(top_pain_point=delivery_speed)", "mean(nps)"
    fn: AggFn
    column: str | None
    value: float | int | str | None  # rounded per ``rounding``; null on zero denominator
    exact: str | None  # the unrounded value as a decimal string (audit)
    unit: Unit
    numerator: int | None = None  # share: rows satisfying the condition
    denominator: int  # rows the metric was computed over (after filters and null exclusion)
    # The column's scale for sum/mean/median/min/max (and their difference); "" for count,
    # count_distinct and share, and for unscaled units. ``value``/``exact`` are in this scale.
    scale: Scale = ""


class ResultRow(_Out):
    """aggregate/group_compare: ``group`` (column -> level) and ``metrics``. filter_rows: one
    listed table row: ``group`` holds the selected cells (column -> value), ``metrics`` is
    empty, and ``row_number`` (the stored row number, as in the handle) and ``handle`` (the
    row's citable evidence handle) identify it."""

    group: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    metrics: list[MetricValue]
    row_number: int | None = None  # filter_rows only
    handle: str | None = None  # filter_rows only


class AnalyticsResult(_Out):
    """The canonical, persisted computed result (one per analytics call that computes)."""

    result_id: str  # analytics_results.id
    workspace: str  # workspace code
    dataset: str
    source_code: str
    source_version: int
    table: str
    operation: Literal["aggregate", "group_compare", "filter_rows"]
    spec: dict[str, object]  # the normalized, validated request (filters/grouping/metrics)
    rows: list[ResultRow]
    rows_scanned: int  # rows in the dataset version considered
    rows_matched: int  # rows after filters
    rounding: str  # e.g. "half_even; percent 1dp; currency 2dp; mean 2dp; counts exact"
    # group_compare: A - B (same unit and scale); its ``denominator`` is denA + denB (the rows
    # behind both sides), its ``numerator`` is null.
    difference: MetricValue | None = None
    warnings: list[str] = Field(default_factory=list)


class AnalyticsOut(_Out):
    """Output of ``aggregate`` / ``group_compare`` / ``filter_rows``."""

    result: AnalyticsResult
    warnings: list[str] = Field(default_factory=list)


ANALYTICS_INPUT_MODELS: dict[str, type[_In]] = {
    "describe_dataset": DescribeDatasetIn,
    "aggregate": AggregateIn,
    "group_compare": GroupCompareIn,
    "filter_rows": FilterRowsIn,
}
ANALYTICS_OUTPUT_MODELS: dict[str, type[_Out]] = {
    "describe_dataset": DescribeDatasetOut,
    "aggregate": AnalyticsOut,
    "group_compare": AnalyticsOut,
    "filter_rows": AnalyticsOut,
}
