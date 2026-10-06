"""A request checked against the dataset's stored column profile and the configured limits.

Rules (any violation -> ``AnalyticsInputError`` -> ``VALIDATION_ERROR``; messages never echo
document data):

* every referenced column exists in the profile (exact, case-sensitive name match);
* limits: filters <= ``analytics_max_filters``, values per filter <=
  ``analytics_max_filter_values``, metrics <= ``analytics_max_metrics``, group_by <=
  ``analytics_max_group_by`` (no duplicates), limit <= ``analytics_max_groups`` (aggregate) /
  ``analytics_max_rows`` (filter_rows);
* ``eq``/``ne`` need a non-null ``value``; ``in``/``not_in`` need 1+ non-null ``values``;
  ``between`` needs exactly 2 non-null ``values`` with low <= high; ``is_null``/``not_null``
  take neither; ``value`` and ``values`` are never both given;
* numeric operands are finite (never NaN/Infinity, never bool); numeric columns take numeric
  operands only; ``gt``/``gte``/``lt``/``lte``/``between`` apply to numeric and date columns
  only;
* date operands of ordered ops are real ISO dates ``YYYY-MM-DD`` or months ``YYYY-MM``, parsed
  into a :class:`Period` (a day, or every day of the month), never compared as text. Date cells
  are periods too, and a cell matches only when its *whole* period satisfies the predicate:
  ``gte X``: cell start >= X start; ``gt X``: cell start > X end; ``lte X``: cell end <= X end;
  ``lt X``: cell end < X start; ``between [A, B]``: cell start >= A start and cell end <= B end
  (A start <= B end is required). So ``lte 2024-01`` includes 2024-01-31 and a month cell
  ``2024-02`` matches neither ``gte 2024-02-15`` nor ``lte 2024-02-15``. A cell that is not a
  real date never matches an ordered filter. ``eq``/``ne``/``in``/``not_in`` on a date column
  compare the stored ISO text exactly;
* a categorical column whose stored levels are complete accepts only known levels in ``eq``/
  ``ne``/``in``/``not_in`` and as ``group_a``/``group_b`` (an unknown level is almost always a
  typo; ``describe_dataset`` lists the levels). Columns with a capped level list accept any
  string, and a value that matches nothing yields ``EMPTY_SELECTION``;
* metrics: ``sum``/``mean``/``median`` numeric columns only; ``min``/``max`` numeric or date;
  ``count_distinct`` any column; ``count`` an optional column (non-null count); ``share``
  requires a ``condition`` (not ``is_null``/``not_null``) and its ``column`` is null or the
  condition's column; ``condition`` is only allowed on ``share``;
* ``order.metric_index`` < number of metrics; ``order.by = "group"`` needs ``group_by``;
* group_compare: ``group_a`` != ``group_b``, both non-null; the metric must be numeric-valued
  (``min``/``max`` of a date column cannot be differenced).
"""

from __future__ import annotations

import calendar
import datetime as dt
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from marketsignal.analytics.rounding import to_decimal
from marketsignal.analytics.schema import ColumnSpec, DatasetRef
from marketsignal.config import Settings
from marketsignal.tools.analytics_contracts import (
    AggFn,
    AggregateIn,
    Filter,
    FilterOp,
    FilterRowsIn,
    GroupCompareIn,
    Metric,
    Scale,
    Unit,
)
from marketsignal.tools.env import ToolInputError

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
_ORDERED = frozenset({"gt", "gte", "lt", "lte", "between"})
_LEVEL_OPS = frozenset({"eq", "ne", "in", "not_in"})
_NUMERIC_FNS = frozenset({"sum", "mean", "median"})
_SYMBOL = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


class AnalyticsInputError(ToolInputError):
    """A request that passes the schema but not the dataset/limit checks."""


@dataclass(frozen=True, slots=True)
class Limits:
    filters: int
    filter_values: int
    metrics: int
    group_by: int
    groups: int
    rows: int
    scan_rows: int
    timeout_s: float

    @classmethod
    def from_settings(cls, s: Settings) -> Limits:
        return cls(
            filters=s.analytics_max_filters,
            filter_values=s.analytics_max_filter_values,
            metrics=s.analytics_max_metrics,
            group_by=s.analytics_max_group_by,
            groups=s.analytics_max_groups,
            rows=s.analytics_max_rows,
            scan_rows=s.analytics_max_scan_rows,
            timeout_s=s.analytics_timeout_s,
        )


@dataclass(frozen=True, slots=True)
class Period:
    """A parsed ISO date (one day) or month (its first..last day); ``text`` is the input."""

    text: str
    start: dt.date
    end: dt.date

    def __str__(self) -> str:
        return self.text


def parse_period(value: Any) -> Period | None:
    """``YYYY-MM-DD`` -> that day; ``YYYY-MM`` -> the whole month; anything else -> ``None``."""
    if not isinstance(value, str) or not ISO_DATE_RE.match(value):
        return None
    try:
        if len(value) == 7:
            year, month = int(value[:4]), int(value[5:])
            start = dt.date(year, month, 1)
            return Period(value, start, start.replace(day=calendar.monthrange(year, month)[1]))
        day = dt.date.fromisoformat(value)
    except ValueError:
        return None
    return Period(value, day, day)


Operand = Decimal | str | Period


@dataclass(frozen=True, slots=True)
class Pred:
    column: ColumnSpec
    op: FilterOp
    operands: tuple[Operand, ...]  # numeric columns: Decimal; otherwise canonical strings

    def label(self) -> str:
        name, ops = self.column.name, [canon(v) for v in self.operands]
        if self.op in _SYMBOL:
            return f"{name}{_SYMBOL[self.op]}{ops[0]}"
        if self.op in ("in", "not_in", "between"):
            return f"{name} {self.op} [{'|'.join(ops)}]"
        return f"{name} {self.op}"


@dataclass(frozen=True, slots=True)
class MetricPlan:
    fn: AggFn
    column: ColumnSpec | None
    condition: Pred | None
    key: str

    @property
    def unit(self) -> Unit:
        if self.fn in ("count", "count_distinct"):
            return "count"
        if self.fn == "share":
            return "percent"
        assert self.column is not None
        unit = self.column.unit
        return "number" if unit == "count" and self.fn in ("mean", "median") else unit

    @property
    def scale(self) -> Scale:
        """The column's scale for value metrics; counts and shares are never scaled."""
        if self.fn in ("count", "count_distinct", "share") or self.column is None:
            return ""
        return self.column.scale


@dataclass(frozen=True, slots=True)
class AggregatePlan:
    ref: DatasetRef
    filters: tuple[Pred, ...]
    metrics: tuple[MetricPlan, ...]
    group_by: tuple[ColumnSpec, ...]
    order_by: str  # "value" | "group"
    order_index: int
    descending: bool
    limit: int | None
    max_groups: int
    spec: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GroupComparePlan:
    ref: DatasetRef
    filters: tuple[Pred, ...]
    metric: MetricPlan
    column: ColumnSpec
    group_a: Any
    group_b: Any
    spec: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FilterRowsPlan:
    ref: DatasetRef
    filters: tuple[Pred, ...]
    columns: tuple[ColumnSpec, ...]
    order_by: ColumnSpec | None
    descending: bool
    limit: int
    spec: dict[str, Any]


def canon(value: Any) -> str:
    """Canonical string of a cell/operand for equality: ``2023`` == ``"2023"`` == ``2023.0``.

    Cells and operands take the form the ingestion profile stores categorical levels in
    (``str(cell)``, with integral floats stored as ints), so a level listed by
    ``describe_dataset`` matches its cells: ``True`` -> ``"True"``, ``1e-07`` -> ``"1e-07"``.
    Decimals (parsed numeric operands, numeric-column labels) are plain decimal strings."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, Decimal):
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    return str(value)


def _fail(message: str) -> AnalyticsInputError:
    return AnalyticsInputError(message)


def _short(name: str) -> str:
    return name[:64]


def column(ref: DatasetRef, name: str, *, what: str = "column") -> ColumnSpec:
    spec = ref.column(name)
    if spec is None:
        raise _fail(f"unknown {what} '{_short(name)}' in dataset {ref.dataset}")
    return spec


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _operand(col: ColumnSpec, op: str, value: Any) -> Operand:
    if value is None:
        raise _fail(f"filter on '{_short(col.name)}' ({op}) needs non-null operands")
    if isinstance(value, float) and not math.isfinite(value):
        raise _fail(f"filter on '{_short(col.name)}' ({op}) needs finite numbers")
    if col.type == "numeric":
        if not _is_number(value):
            raise _fail(f"column '{_short(col.name)}' is numeric: operands must be numbers")
        return to_decimal(value)
    if op in _ORDERED:
        if col.type != "date":
            raise _fail(f"{op} applies to numeric or date columns, not '{_short(col.name)}'")
        period = parse_period(value)
        if period is None:
            raise _fail(f"date column '{_short(col.name)}' needs real ISO dates (YYYY-MM[-DD])")
        return period
    text = canon(value)
    if op in _LEVEL_OPS and col.complete_levels and text not in col.levels:
        raise _fail(
            f"value is not a known level of column '{_short(col.name)}' (see describe_dataset)"
        )
    return text


def predicate(ref: DatasetRef, f: Filter, limits: Limits) -> Pred:
    col = column(ref, f.column)
    if f.value is not None and f.values is not None:
        raise _fail(f"filter on '{_short(col.name)}': give value or values, not both")
    if f.op in ("is_null", "not_null"):
        if f.value is not None or f.values is not None:
            raise _fail(f"{f.op} takes no value")
        return Pred(col, f.op, ())
    if f.op in ("in", "not_in", "between"):
        values = f.values or []
        if not values:
            raise _fail(f"{f.op} on '{_short(col.name)}' needs values")
        if len(values) > limits.filter_values:
            raise _fail(f"too many filter values (max {limits.filter_values})")
        if f.op == "between" and len(values) != 2:
            raise _fail("between needs exactly two values [low, high]")
        operands = tuple(_operand(col, f.op, v) for v in values)
        if f.op == "between" and _gt(operands[0], operands[1]):
            raise _fail("between needs low <= high")
        return Pred(col, f.op, operands)
    if f.values is not None:
        raise _fail(f"{f.op} takes a single value")
    return Pred(col, f.op, (_operand(col, f.op, f.value),))


def _gt(a: Operand, b: Operand) -> bool:
    if isinstance(a, Period) and isinstance(b, Period):
        return a.start > b.end  # between [A, B] is empty only when A starts after B ends
    return bool(a > b)  # type: ignore[operator]  # both Decimal (same column)


def filters(ref: DatasetRef, raw: list[Filter] | None, limits: Limits) -> tuple[Pred, ...]:
    raw = raw or []
    if len(raw) > limits.filters:
        raise _fail(f"too many filters (max {limits.filters})")
    return tuple(predicate(ref, f, limits) for f in raw)


def metric(ref: DatasetRef, m: Metric, limits: Limits) -> MetricPlan:
    col = column(ref, m.column) if m.column is not None else None
    if m.condition is not None and m.fn != "share":
        raise _fail("condition is only allowed for share")
    if m.fn == "share":
        if m.condition is None:
            raise _fail("share requires a condition")
        cond = predicate(ref, m.condition, limits)
        if cond.op in ("is_null", "not_null"):
            raise _fail("share condition cannot be is_null/not_null")
        if col is not None and col.name != cond.column.name:
            raise _fail("share column must be null or the condition's column")
        return MetricPlan("share", cond.column, cond, f"share({cond.label()})")
    if m.fn == "count":
        return MetricPlan("count", col, None, f"count({col.name if col else '*'})")
    if col is None:
        raise _fail(f"{m.fn} requires a column")
    if m.fn in _NUMERIC_FNS and col.type != "numeric":
        raise _fail(f"{m.fn} needs a numeric column, '{_short(col.name)}' is {col.type}")
    if m.fn in ("min", "max") and col.type not in ("numeric", "date"):
        raise _fail(f"{m.fn} needs a numeric or date column, '{_short(col.name)}' is {col.type}")
    return MetricPlan(m.fn, col, None, f"{m.fn}({col.name})")


def _metrics(ref: DatasetRef, raw: list[Metric], limits: Limits) -> tuple[MetricPlan, ...]:
    if len(raw) > limits.metrics:
        raise _fail(f"too many metrics (max {limits.metrics})")
    plans = tuple(metric(ref, m, limits) for m in raw)
    if len({p.key for p in plans}) != len(plans):
        raise _fail("duplicate metrics")
    return plans


def aggregate_plan(ref: DatasetRef, args: AggregateIn, limits: Limits) -> AggregatePlan:
    preds = filters(ref, args.filters, limits)
    metrics = _metrics(ref, args.metrics, limits)
    names = args.group_by or []
    if len(names) > limits.group_by:
        raise _fail(f"too many group_by columns (max {limits.group_by})")
    if len(set(names)) != len(names):
        raise _fail("duplicate group_by columns")
    groups = tuple(column(ref, n, what="group_by column") for n in names)
    order = args.order
    by, index, desc = (
        ("value", 0, True)
        if order is None
        else (
            order.by,
            order.metric_index,
            order.direction == "desc",
        )
    )
    if order is None and groups:
        by, desc = "group", False
    if index >= len(metrics):
        raise _fail("order.metric_index is out of range")
    if by == "group" and not groups:
        raise _fail("order by group needs group_by")
    if args.limit is not None and args.limit > limits.groups:
        raise _fail(f"limit exceeds the maximum ({limits.groups})")
    spec = {
        "dataset": ref.dataset,
        "filters": [_filter_spec(p) for p in preds],
        "metrics": [_metric_spec(p, m) for p, m in zip(metrics, args.metrics, strict=True)],
        "group_by": [g.name for g in groups],
        "order": {"by": by, "metric_index": index, "direction": "desc" if desc else "asc"},
        "limit": args.limit,
    }
    return AggregatePlan(
        ref, preds, metrics, groups, by, index, desc, args.limit, limits.groups, spec
    )


def group_compare_plan(ref: DatasetRef, args: GroupCompareIn, limits: Limits) -> GroupComparePlan:
    preds = filters(ref, args.filters, limits)
    plan = metric(ref, args.metric, limits)
    if plan.fn in ("min", "max") and plan.column is not None and plan.column.type == "date":
        raise _fail("group_compare needs a numeric metric")
    col = column(ref, args.compare_column, what="compare_column")
    a, b = (_operand(col, "eq", v) for v in (args.group_a, args.group_b))
    if a == b:
        raise _fail("group_a and group_b must differ")
    spec = {
        "dataset": ref.dataset,
        "filters": [_filter_spec(p) for p in preds],
        "metric": _metric_spec(plan, args.metric),
        "compare_column": col.name,
        "group_a": args.group_a,
        "group_b": args.group_b,
    }
    return GroupComparePlan(ref, preds, plan, col, a, b, spec)


def filter_rows_plan(ref: DatasetRef, args: FilterRowsIn, limits: Limits) -> FilterRowsPlan:
    preds = filters(ref, args.filters, limits)
    names = args.columns or [c.name for c in ref.columns[:8]]
    if len(set(names)) != len(names):
        raise _fail("duplicate columns")
    cols = tuple(column(ref, n) for n in names)
    order = column(ref, args.order_by, what="order_by column") if args.order_by else None
    limit = args.limit if args.limit is not None else limits.rows
    if limit > limits.rows:
        raise _fail(f"limit exceeds the maximum ({limits.rows})")
    spec = {
        "dataset": ref.dataset,
        "filters": [_filter_spec(p) for p in preds],
        "columns": [c.name for c in cols],
        "order_by": order.name if order else None,
        "direction": args.direction,
        "limit": limit,
    }
    return FilterRowsPlan(ref, preds, cols, order, args.direction == "desc", limit, spec)


def _filter_spec(p: Pred) -> dict[str, Any]:
    return {"column": p.column.name, "op": p.op, "operands": [canon(v) for v in p.operands]}


def _metric_spec(plan: MetricPlan, raw: Metric) -> dict[str, Any]:
    out: dict[str, Any] = {
        "fn": plan.fn,
        "column": plan.column.name if plan.column else None,
        "key": plan.key,
    }
    if plan.condition is not None:
        out["condition"] = _filter_spec(plan.condition)
    if raw.label:
        out["label"] = raw.label
    return out
