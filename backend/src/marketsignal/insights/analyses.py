"""Recompute a named analysis with the deterministic engine (plan §5.4 step 2).

The dataset is resolved through ``analytics.schema.find_datasets`` (current, ready versions
only), rows are read with ``analytics.store.fetch_rows`` and the plan is built and run with
``analytics.validate`` / ``analytics.engine``. Nothing is persisted: ``save_result`` and the
tool wrappers are never called. Each engine call is flattened to one row per (result row,
metric) and compared, in order, with the fixture's pinned rows:

* ``computed``    - every pinned row matches;
* ``mismatch``    - a value, a row or the row order differs; every number is withheld;
* ``unavailable`` - the dataset is missing, not ready, too large, or the spec no longer fits it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.analytics import engine
from marketsignal.analytics.rounding import to_decimal
from marketsignal.analytics.schema import DatasetRef, find_datasets
from marketsignal.analytics.store import ScanLimitError, fetch_rows
from marketsignal.analytics.validate import (
    AnalyticsInputError,
    Limits,
    aggregate_plan,
    filter_rows_plan,
    group_compare_plan,
)
from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.domain.enums import Confidentiality
from marketsignal.insights.fixture import SPEC_MODELS, AnalysisSpec, ExpectedRow, Part
from marketsignal.insights.format import format_value
from marketsignal.tools.analytics_contracts import AggregateIn, FilterRowsIn, GroupCompareIn

Status = Literal["computed", "mismatch", "unavailable"]
ALL_LEVELS = [c.value for c in Confidentiality]
MEASURE = "measure"


@dataclass(frozen=True, slots=True)
class FlatRow:
    group: dict[str, str]
    value: int | float | None
    numerator: int | None = None
    denominator: int | None = None
    cells: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Recomputed:
    status: Status
    payload: dict[str, Any]  # the contract ``Analysis``
    rows: list[FlatRow]  # empty unless computed


def _cell_text(value: Any) -> str:
    return "" if value is None else str(value)


def _flatten(spec: AnalysisSpec, part: Part, computed: engine.Computed) -> list[FlatRow]:
    labels = [m.get("label") or m.get("fn", "") for m in part.spec.get("metrics", [])]
    multi = len(labels) > 1
    out: list[FlatRow] = []
    for row in computed.rows:
        if spec.op == "filter_rows":
            cells = dict(row.group)
            group = {**part.group, **{k: _cell_text(v) for k, v in cells.items()}}
            value = cells.get(spec.value_column or "")
            number = (
                value if isinstance(value, int | float) and not isinstance(value, bool) else None
            )
            out.append(FlatRow(group, number, cells=cells))
            continue
        base = {**part.group, **{k: _cell_text(v) for k, v in row.group.items()}}
        for i, mv in enumerate(row.metrics):
            group = {**base, MEASURE: str(labels[i])} if multi else base
            value = mv.value if isinstance(mv.value, int | float) else None
            out.append(FlatRow(group, value, mv.numerator, mv.denominator))
    if spec.op == "group_compare" and computed.difference is not None:
        diff = computed.difference
        value = diff.value if isinstance(diff.value, int | float) else None
        out.append(FlatRow({**part.group, MEASURE: "difference"}, value))
    return out


def _same(actual: Any, expected: float | int) -> bool:
    if not isinstance(actual, int | float) or isinstance(actual, bool):
        return False
    return to_decimal(actual) == to_decimal(expected)


def matches_expected(rows: list[FlatRow], expected: list[ExpectedRow]) -> bool:
    """Positional comparison: same row count, each pinned group a subset of the row's group,
    the row value and every pinned cell equal after rounding."""
    if len(rows) != len(expected):
        return False
    for row, pin in zip(rows, expected, strict=True):
        if any(row.group.get(k) != v for k, v in pin.group.items()):
            return False
        if not _same(row.value, pin.value):
            return False
        if any(not _same(row.cells.get(c), v) for c, v in pin.values.items()):
            return False
    return True


def _plan(spec: AnalysisSpec, ref: DatasetRef, part: Part, limits: Limits) -> Any:
    args = SPEC_MODELS[spec.op].model_validate(part.spec)
    if isinstance(args, AggregateIn):
        return aggregate_plan(ref, args, limits)
    if isinstance(args, FilterRowsIn):
        return filter_rows_plan(ref, args, limits)
    assert isinstance(args, GroupCompareIn)
    return group_compare_plan(ref, args, limits)


_RUN: dict[str, Callable[..., engine.Computed]] = {
    "aggregate": engine.aggregate,
    "filter_rows": engine.filter_rows,
    "group_compare": engine.group_compare,
}


def _common_filters(spec: AnalysisSpec) -> list[dict[str, Any]]:
    first = spec.parts[0].spec.get("filters") or []
    shared = [f for f in first if all(f in (p.spec.get("filters") or []) for p in spec.parts)]
    return [
        {
            "column": f["column"],
            "label": spec.filter_labels.get(f["column"], f["column"]),
            "op": f["op"],
            "values": list(f.get("values") or ([] if f.get("value") is None else [f["value"]])),
        }
        for f in shared
    ]


def _group_by(spec: AnalysisSpec) -> list[str]:
    part = spec.parts[0]
    keys = list(part.group)
    keys += list(part.spec.get("group_by") or [])
    if spec.op == "group_compare":
        keys.append(str(part.spec.get("compare_column", "")))
    if len(part.spec.get("metrics") or []) > 1 or spec.op == "group_compare":
        keys.append(MEASURE)
    return keys


def _row_payload(spec: AnalysisSpec, row: FlatRow) -> dict[str, Any]:
    out: dict[str, Any] = {
        "group": row.group,
        "value": row.value,
        "display": format_value(row.value, spec.unit),
    }
    if row.numerator is not None:
        out["numerator"] = row.numerator
    if row.denominator is not None and spec.op != "filter_rows":
        out["denominator"] = row.denominator
    return out


def _payload(
    spec: AnalysisSpec,
    status: Status,
    ref: DatasetRef | None,
    rows: list[FlatRow],
    rows_matched: int | None,
    computed_at: str,
    corpus_version: int,
) -> dict[str, Any]:
    ok = status == "computed"
    single = rows[0] if ok and len(rows) == 1 else None
    code = spec.dataset.rpartition(":")[0]
    denominator = (
        {"label": spec.denominator_label, "value": rows_matched}
        if ok and spec.denominator_label and len(spec.parts) == 1 and rows_matched is not None
        else None
    )
    specs: Any = (
        spec.parts[0].spec
        if len(spec.parts) == 1
        else [{"group": p.group, "spec": p.spec} for p in spec.parts]
    )
    payload: dict[str, Any] = {
        "id": spec.id,
        "title": spec.title,
        "question": spec.question,
        "category": spec.category,
        "status": status,
        "op": spec.op,
        "unit": spec.unit,
        "presentation": spec.presentation,
        "denominator": denominator,
        "filters": _common_filters(spec),
        "group_by": _group_by(spec) if spec.op != "filter_rows" else [],
        "value": single.value if single else None,
        "display": format_value(single.value, spec.unit) if single else None,
        "rows": [_row_payload(spec, r) for r in rows] if ok else [],
        "provenance": {
            "dataset": spec.dataset,
            "source_code": ref.source_code if ref else code,
            "source_title": ref.title if ref else "",
            "version": ref.source_version if ref else corpus_version,
            "table": ref.table if ref else "",
            "rows_matched": rows_matched if ok else None,
            "computed_at": computed_at,
        },
        "caveats": list(spec.caveats),
        "spec": specs,
    }
    if spec.op == "filter_rows":
        payload["columns"] = list(spec.parts[0].spec.get("columns") or [])
    return payload


@dataclass(frozen=True, slots=True)
class Run:
    ref: DatasetRef | None
    rows: list[FlatRow]
    rows_matched: int | None
    available: bool


async def run_parts(
    session: AsyncSession, scope: WorkspaceScope, settings: Settings, spec: AnalysisSpec
) -> Run:
    """Run every part of ``spec`` through the engine (read-only), without comparing."""
    refs = await find_datasets(
        session,
        scope.workspace_id,
        confidentiality=ALL_LEVELS,
        classes=[],
        dataset=spec.dataset,
        limit=1,
    )
    if not refs:
        return Run(None, [], None, available=False)
    ref = refs[0]
    limits = Limits.from_settings(settings)
    try:
        data = await fetch_rows(session, scope.workspace_id, ref.table_id, limits.scan_rows)
        flat: list[FlatRow] = []
        matched = 0
        for part in spec.parts:
            computed = _RUN[spec.op](_plan(spec, ref, part, limits), data, deadline=None)
            matched += computed.rows_matched
            flat.extend(_flatten(spec, part, computed))
    except (AnalyticsInputError, ScanLimitError):
        return Run(ref, [], None, available=False)
    return Run(ref, flat, matched, available=True)


async def recompute(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    spec: AnalysisSpec,
    *,
    computed_at: str,
    corpus_version: int,
) -> Recomputed:
    run = await run_parts(session, scope, settings, spec)
    status: Status
    if not run.available:
        status = "unavailable"
    elif matches_expected(run.rows, spec.expected):
        status = "computed"
    else:
        status = "mismatch"
    ok = status == "computed"
    rows = run.rows if ok else []
    payload = _payload(
        spec, status, run.ref, rows, run.rows_matched if ok else None, computed_at, corpus_version
    )
    return Recomputed(status, payload, rows)


def pick_row(rows: list[FlatRow], group: dict[str, str]) -> FlatRow | None:
    hits = [r for r in rows if all(r.group.get(k) == v for k, v in group.items())]
    return hits[0] if len(hits) == 1 else None
