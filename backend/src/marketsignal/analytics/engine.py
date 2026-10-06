"""Pure, deterministic computation over one dataset version's rows (no I/O, no SQL).

* Cells: ``None``/blank strings are null; in numeric columns a non-numeric cell is also null.
  Numbers become ``Decimal`` via their shortest repr (0.1 -> Decimal('0.1')).
* Filters: every predicate is false on a null cell except ``is_null`` (so ``ne``/``not_in``
  exclude nulls, as in SQL). Equality on non-numeric columns compares canonical strings.
* Metrics exclude null cells (``NULLS_EXCLUDED``) and report the rows actually used as
  ``denominator``; zero eligible rows -> value null + ``ZERO_DENOMINATOR`` (``count`` and
  ``count_distinct`` are 0 instead). ``share`` = 100 * condition rows / rows with a non-null
  value in the condition's column.
* No matching rows -> ``EMPTY_SELECTION`` (a valid result). Groups beyond ``max_groups`` (no
  explicit limit) -> ``GROUPS_TRUNCATED``.
* Ordering: groups by ``group`` ascending by default; by ``value`` with nulls last; ties are
  always broken by the group values (numbers before strings before nulls). ``filter_rows``
  breaks ties by row number and reports each row's ``row_number`` and evidence ``handle``.
* Scale: value metrics (sum/mean/median/min/max and a difference) carry the column's
  ``scale``; counts and shares never do.
* ``deadline`` (``time.monotonic``) bounds the scan: past it, ``TimeoutError``.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from marketsignal.analytics.rounding import (
    CTX,
    decimal_places,
    exact_str,
    round_value,
    to_decimal,
)
from marketsignal.analytics.schema import ColumnSpec
from marketsignal.analytics.validate import (
    AggregatePlan,
    FilterRowsPlan,
    GroupComparePlan,
    MetricPlan,
    Pred,
    canon,
)
from marketsignal.tools.analytics_contracts import (
    EMPTY_SELECTION,
    GROUPS_TRUNCATED,
    NULLS_EXCLUDED,
    ZERO_DENOMINATOR,
    MetricValue,
    ResultRow,
)

WARNING_ORDER = (EMPTY_SELECTION, NULLS_EXCLUDED, ZERO_DENOMINATOR, GROUPS_TRUNCATED)
CELL_MAX_CHARS = 160
CHECK_EVERY = 512


@dataclass(frozen=True, slots=True)
class Row:
    number: int
    handle: str
    values: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Computed:
    rows: list[ResultRow]
    rows_scanned: int
    rows_matched: int
    warnings: list[str]
    difference: MetricValue | None = None


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def raw_cell(row: Row, col: ColumnSpec) -> Any:
    v = row.values.get(col.name)
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return v


def cell(row: Row, col: ColumnSpec) -> Any:
    v = raw_cell(row, col)
    if col.type == "numeric":
        return to_decimal(v) if _is_number(v) else None
    return v


def matches(pred: Pred, row: Row) -> bool:
    v = cell(row, pred.column)
    if pred.op == "is_null":
        return v is None
    if v is None:
        return False
    if pred.op == "not_null":
        return True
    key: Any = v if isinstance(v, Decimal) else (str(v) if pred.op in _ORDERED else canon(v))
    ops = pred.operands
    if pred.op == "eq":
        return bool(key == ops[0])
    if pred.op == "ne":
        return bool(key != ops[0])
    if pred.op == "in":
        return key in ops
    if pred.op == "not_in":
        return key not in ops
    if pred.op == "between":
        return bool(ops[0] <= key <= ops[1])
    return bool(_COMPARE[pred.op](key, ops[0]))


_ORDERED = frozenset({"gt", "gte", "lt", "lte", "between"})
_COMPARE = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
}


class _Clock:
    def __init__(self, deadline: float | None) -> None:
        self.deadline = deadline

    def tick(self, i: int) -> None:
        if self.deadline is not None and i % CHECK_EVERY == 0 and time.monotonic() > self.deadline:
            raise TimeoutError("analytics deadline exceeded")


def select(rows: Sequence[Row], preds: Iterable[Pred], clock: _Clock) -> list[Row]:
    preds = tuple(preds)
    out = []
    for i, row in enumerate(rows):
        clock.tick(i)
        if all(matches(p, row) for p in preds):
            out.append(row)
    return out


def metric_value(plan: MetricPlan, rows: Sequence[Row], warnings: set[str]) -> MetricValue:
    col = plan.column
    numerator: int | None = None
    if plan.fn == "count" and col is None:
        n = len(rows)
        return _mv(plan, Decimal(n), n, None, integral=True)
    assert col is not None
    present = [v for v in (cell(r, col) for r in rows) if v is not None]
    if len(present) < len(rows):
        warnings.add(NULLS_EXCLUDED)
    n = len(present)
    if plan.fn == "count":
        return _mv(plan, Decimal(n), n, None, integral=True)
    if plan.fn == "count_distinct":
        return _mv(plan, Decimal(len({canon(v) for v in present})), n, None, integral=True)
    if n == 0:
        warnings.add(ZERO_DENOMINATOR)
        return _null(plan, n)
    if plan.fn == "share":
        assert plan.condition is not None
        numerator = sum(1 for r in rows if matches(plan.condition, r))
        value = CTX.multiply(CTX.divide(Decimal(numerator), Decimal(n)), Decimal(100))
        return _mv(plan, value, n, numerator, integral=False)
    if col.type == "date":  # min/max of ISO dates: exact strings
        text = min(map(str, present)) if plan.fn == "min" else max(map(str, present))
        return MetricValue(
            key=plan.key,
            fn=plan.fn,
            column=col.name,
            value=text,
            exact=text,
            unit="date",
            denominator=n,
        )  # dates are never scaled
    nums: list[Decimal] = present
    integral = all(v == v.to_integral_value() for v in nums)
    if plan.fn == "min":
        return _mv(plan, min(nums), n, None, integral=integral)
    if plan.fn == "max":
        return _mv(plan, max(nums), n, None, integral=integral)
    total = sum(nums, Decimal(0))
    if plan.fn == "sum":
        return _mv(plan, total, n, None, integral=integral)
    if plan.fn == "mean":
        return _mv(plan, CTX.divide(total, Decimal(n)), n, None, integral=integral)
    ordered = sorted(nums)
    mid = n // 2
    median = ordered[mid] if n % 2 else CTX.divide(ordered[mid - 1] + ordered[mid], Decimal(2))
    return _mv(plan, median, n, None, integral=integral)


def _mv(
    plan: MetricPlan, value: Decimal, denominator: int, numerator: int | None, *, integral: bool
) -> MetricValue:
    places = decimal_places(plan.fn, plan.unit, integral=integral)
    return MetricValue(
        key=plan.key,
        fn=plan.fn,
        column=plan.column.name if plan.column else None,
        value=round_value(value, places),
        exact=exact_str(value),
        unit=plan.unit,
        numerator=numerator,
        denominator=denominator,
        scale=plan.scale,
    )


def _null(plan: MetricPlan, denominator: int) -> MetricValue:
    return MetricValue(
        key=plan.key,
        fn=plan.fn,
        column=plan.column.name if plan.column else None,
        value=None,
        exact=None,
        unit=plan.unit,
        numerator=0 if plan.fn == "share" else None,
        denominator=denominator,
        scale=plan.scale,
    )


def _sort_key(value: Any) -> tuple[int, Any]:
    if value is None:
        return (2, "")
    if isinstance(value, Decimal):
        return (0, value)
    if _is_number(value):
        return (0, to_decimal(value))
    return (1, canon(value))


def _group_sort(values: tuple[Any, ...]) -> tuple[tuple[int, Any], ...]:
    return tuple(_sort_key(v) for v in values)


def _bounded(value: Any) -> Any:
    if isinstance(value, str) and len(value) > CELL_MAX_CHARS:
        return value[: CELL_MAX_CHARS - 1] + "…"
    return value


def ordered_warnings(found: set[str]) -> list[str]:
    return [w for w in WARNING_ORDER if w in found]


def aggregate(plan: AggregatePlan, rows: Sequence[Row], *, deadline: float | None) -> Computed:
    clock = _Clock(deadline)
    selected = select(rows, plan.filters, clock)
    warnings: set[str] = set() if selected else {EMPTY_SELECTION}
    if not plan.group_by:
        values = [metric_value(m, selected, warnings) for m in plan.metrics]
        result = [ResultRow(group={}, metrics=values)]
        return Computed(result, len(rows), len(selected), ordered_warnings(warnings))
    groups: dict[tuple[Any, ...], tuple[tuple[Any, ...], list[Row]]] = {}
    for i, row in enumerate(selected):
        clock.tick(i)
        shown = tuple(_bounded(raw_cell(row, g)) for g in plan.group_by)
        ident = tuple(
            None if v is None else canon(cell(row, g))
            for g, v in zip(plan.group_by, shown, strict=True)
        )
        groups.setdefault(ident, (shown, []))[1].append(row)
    keyed = sorted(groups.values(), key=lambda item: _group_sort(item[0]))
    computed = [
        (shown, [metric_value(m, members, warnings) for m in plan.metrics])
        for shown, members in keyed
    ]
    if plan.order_by == "value":
        computed = _order_by_value(computed, plan.order_index, plan.descending)
    elif plan.descending:
        computed = list(reversed(computed))
    cap = plan.limit if plan.limit is not None else plan.max_groups
    if plan.limit is None and len(computed) > cap:
        warnings.add(GROUPS_TRUNCATED)
    names = [g.name for g in plan.group_by]
    result = [
        ResultRow(group=dict(zip(names, shown, strict=True)), metrics=metrics)
        for shown, metrics in computed[:cap]
    ]
    return Computed(result, len(rows), len(selected), ordered_warnings(warnings))


def _order_by_value(
    computed: list[tuple[tuple[Any, ...], list[MetricValue]]], index: int, descending: bool
) -> list[tuple[tuple[Any, ...], list[MetricValue]]]:
    """Input is in group order; the stable sort keeps group order among equal values."""
    present = [c for c in computed if c[1][index].value is not None]
    nulls = [c for c in computed if c[1][index].value is None]
    present.sort(key=lambda c: _sort_key(c[1][index].value), reverse=descending)
    return present + nulls


def group_compare(
    plan: GroupComparePlan, rows: Sequence[Row], *, deadline: float | None
) -> Computed:
    clock = _Clock(deadline)
    selected = select(rows, plan.filters, clock)
    warnings: set[str] = set()
    sides = []
    matched = 0
    for operand, shown in (
        (plan.group_a, plan.spec["group_a"]),
        (plan.group_b, plan.spec["group_b"]),
    ):
        members = select(selected, [Pred(plan.column, "eq", (operand,))], clock)
        matched += len(members)
        sides.append(
            ResultRow(
                group={plan.column.name: shown},
                metrics=[metric_value(plan.metric, members, warnings)],
            )
        )
    if matched == 0:
        warnings.add(EMPTY_SELECTION)
    a, b = sides[0].metrics[0], sides[1].metrics[0]
    difference = _difference(plan.metric, a, b, warnings)
    return Computed(sides, len(rows), matched, ordered_warnings(warnings), difference)


def _difference(
    plan: MetricPlan, a: MetricValue, b: MetricValue, warnings: set[str]
) -> MetricValue:
    key = f"difference({plan.key})"
    denominator = a.denominator + b.denominator
    if a.exact is None or b.exact is None:
        warnings.add(ZERO_DENOMINATOR)
        return MetricValue(
            key=key,
            fn=plan.fn,
            column=a.column,
            value=None,
            exact=None,
            unit=plan.unit,
            denominator=denominator,
            scale=plan.scale,
        )
    diff = CTX.subtract(Decimal(a.exact), Decimal(b.exact))
    integral = all(isinstance(v.value, int) for v in (a, b)) and diff == diff.to_integral_value()
    places = decimal_places(plan.fn, plan.unit, integral=integral)
    return MetricValue(
        key=key,
        fn=plan.fn,
        column=a.column,
        value=round_value(diff, places),
        exact=exact_str(diff),
        unit=plan.unit,
        denominator=denominator,
        scale=plan.scale,
    )


def filter_rows(plan: FilterRowsPlan, rows: Sequence[Row], *, deadline: float | None) -> Computed:
    clock = _Clock(deadline)
    selected = select(rows, plan.filters, clock)
    ordered = sorted(selected, key=lambda r: r.number)
    if plan.order_by is not None:
        col = plan.order_by
        present = [r for r in ordered if cell(r, col) is not None]
        nulls = [r for r in ordered if cell(r, col) is None]
        present.sort(key=lambda r: _sort_key(cell(r, col)), reverse=plan.descending)
        ordered = present + nulls
    result = [
        ResultRow(
            group={c.name: _bounded(raw_cell(r, c)) for c in plan.columns},
            metrics=[],
            row_number=r.number,
            handle=r.handle,
        )
        for r in ordered[: plan.limit]
    ]
    warnings = set() if selected else {EMPTY_SELECTION}
    return Computed(result, len(rows), len(selected), ordered_warnings(warnings))
