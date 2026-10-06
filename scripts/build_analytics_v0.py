"""Build eval/datasets/analytics-v0 (Phase 5 structured analytics: retrieval vs analytics vs mixed).

Deterministic and reproducible. Every question is hand written for this dataset. Gold numeric
answers are computed here, directly from the seed CSV/XLSX files under seed_data/generated, by
an independent reference implementation (stdlib only: csv, zipfile + ElementTree for XLSX,
Decimal with ROUND_HALF_EVEN). The product's analytics engine is never imported or called and no
LLM is involved, so the gold is an independent oracle for it.

Gold ``spec`` dicts follow the frozen contract (tools/analytics_contracts.py): AggregateIn,
GroupCompareIn or FilterRowsIn. ``--verify-db`` (backend venv) validates every spec against the
Pydantic models, checks every dataset id / column / categorical level against the stored column
profile (``dataset_tables``, scoped per workspace), recomputes every gold from the ingested
``dataset_rows`` values and resolves every evidence handle.

    python3 scripts/build_analytics_v0.py               # build items.json + README.md
    python3 scripts/build_analytics_v0.py --check       # rebuild in memory, diff vs files
    uv --directory backend run python ../scripts/build_analytics_v0.py --verify-db
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seed_data" / "generated"
OUT_DIR = ROOT / "eval" / "datasets" / "analytics-v0"
ITEMS_OUT = OUT_DIR / "items.json"
README_OUT = OUT_DIR / "README.md"
LEDGER = ROOT / "seed_data" / "fact_ledger.json"
RETRIEVAL_V0 = ROOT / "eval" / "datasets" / "retrieval-v0" / "items.json"
TASK_TYPES = ROOT / "eval" / "datasets" / "retrieval-v0" / "task-types.json"
FROZEN = ROOT / "eval" / "datasets" / "retrieval-v0" / "frozen.json"
GROUNDED_V0 = ROOT / "eval" / "datasets" / "grounded-v0" / "items.json"
RESEARCH_V0 = ROOT / "eval" / "datasets" / "research-v0" / "items.json"

DATASET_VERSION = "analytics-v0"
SPLIT_SEED = "analytics-v0"
DEV_FRACTION = 0.40
JACCARD_REJECT = 0.60
# Workspaces' llm_max_confidentiality as checked in the DB (verified by --verify-db).
LLM_MAX_CONFIDENTIALITY = {"NORTHSTAR": "confidential", "SOUTHPEAK": "confidential"}
CONF_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}

# --- datasets -----------------------------------------------------------------------------------
# id -> (workspace, file, sheet or None, title, source confidentiality, key column)
DATASETS: dict[str, tuple[str, str, str | None, str, str, str]] = {
    "NORTHSTAR/CATEGORY-SIZING:1": (
        "NORTHSTAR",
        "northstar/Athletic_Category_Sizing.xlsx",
        "Market_Sizing",
        "Market_Sizing",
        "internal",
        "record_id",
    ),
    "NORTHSTAR/CHANNEL-PERF:1": (
        "NORTHSTAR",
        "northstar/Northstar_Channel_Performance.csv",
        None,
        "Northstar Channel Performance",
        "internal",
        "record_id",
    ),
    "NORTHSTAR/FIN-SUMMARY-FY26:1": (
        "NORTHSTAR",
        "northstar/Northstar_Financial_Summary_FY26.xlsx",
        "PnL_Summary",
        "PnL_Summary",
        "confidential",
        "line_item",
    ),
    "NORTHSTAR/FIN-SUMMARY-FY26:2": (
        "NORTHSTAR",
        "northstar/Northstar_Financial_Summary_FY26.xlsx",
        "Segment_Revenue",
        "Segment_Revenue",
        "confidential",
        "segment",
    ),
    "NORTHSTAR/PRODUCT-PERF:1": (
        "NORTHSTAR",
        "northstar/Northstar_Product_Performance.xlsx",
        "Category_Monthly",
        "Category_Monthly",
        "internal",
        "record_id",
    ),
    "NORTHSTAR/PRODUCT-PERF:2": (
        "NORTHSTAR",
        "northstar/Northstar_Product_Performance.xlsx",
        "SKU_Performance",
        "SKU_Performance",
        "internal",
        "sku",
    ),
    "NORTHSTAR/PRODUCT-PERF:3": (
        "NORTHSTAR",
        "northstar/Northstar_Product_Performance.xlsx",
        "Returns",
        "Returns",
        "internal",
        "record_id",
    ),
    "NORTHSTAR/REVIEWS:1": (
        "NORTHSTAR",
        "northstar/Northstar_Product_Reviews.csv",
        None,
        "Northstar Product Reviews",
        "public",
        "review_id",
    ),
    "NORTHSTAR/SURVEY-2026:1": (
        "NORTHSTAR",
        "northstar/Northstar_Customer_Survey_2026.csv",
        None,
        "Northstar Customer Survey 2026",
        "internal",
        "respondent_id",
    ),
    "SOUTHPEAK/CHANNEL-DATA:1": (
        "SOUTHPEAK",
        "southpeak/Southpeak_Channel_Data.xlsx",
        "Channel_Monthly",
        "Channel_Monthly",
        "internal",
        "record_id",
    ),
    "SOUTHPEAK/CHANNEL-DATA:2": (
        "SOUTHPEAK",
        "southpeak/Southpeak_Channel_Data.xlsx",
        "Region_Summary",
        "Region_Summary",
        "internal",
        "region",
    ),
    "SOUTHPEAK/SURVEY-2026:1": (
        "SOUTHPEAK",
        "southpeak/Southpeak_Customer_Survey.csv",
        None,
        "Southpeak Customer Survey 2026",
        "internal",
        "respondent_id",
    ),
}


def dataset_id(key: str) -> str:
    """Contract dataset id ``<SOURCE_CODE>:<sheet_ordinal>`` (workspace is the run scope)."""
    return key.split("/", 1)[1]


def dataset_key(workspace: str, ds: str) -> str:
    return f"{workspace}/{ds}"


# --- independent table loading (stdlib only) ----------------------------------------------------

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_CELL_REF = re.compile(r"([A-Z]+)(\d+)")


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _xlsx_sheet(path: Path, sheet: str) -> list[list[str]]:
    with zipfile.ZipFile(path) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))  # noqa: S314 - repo seed files
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))  # noqa: S314 - repo seed files
        targets = {r.get("Id"): r.get("Target") for r in rels.iter(f"{_PKG_REL_NS}Relationship")}
        rid = next(s.get(f"{_REL_NS}id") for s in wb.iter(f"{_NS}sheet") if s.get("name") == sheet)
        target = str(targets[rid]).lstrip("/")
        target = target if target.startswith("xl/") else f"xl/{target}"
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            sst = ET.fromstring(zf.read("xl/sharedStrings.xml"))  # noqa: S314 - repo seed files
            shared = ["".join(t.text or "" for t in si.iter(f"{_NS}t")) for si in sst]
        root = ET.fromstring(zf.read(target))  # noqa: S314 - repo seed files
    grid: dict[int, dict[int, str]] = {}
    for row in root.iter(f"{_NS}row"):
        for c in row.iter(f"{_NS}c"):
            m = _CELL_REF.fullmatch(str(c.get("r")))
            if not m:
                raise SystemExit(f"{path.name}/{sheet}: unexpected cell ref {c.get('r')}")
            r, col = int(m.group(2)), _col_index(m.group(1))
            kind = c.get("t", "n")
            if kind == "inlineStr":
                value = "".join(t.text or "" for t in c.iter(f"{_NS}t"))
            elif kind == "s":
                value = shared[int(c.findtext(f"{_NS}v") or "0")]
            elif kind == "n":
                value = _excel_number(c.findtext(f"{_NS}v") or "")
            elif kind == "str":
                value = c.findtext(f"{_NS}v") or ""
            else:
                raise SystemExit(f"{path.name}/{sheet}: unsupported cell type {kind}")
            grid.setdefault(r, {})[col] = value
    width = max(max(cols) for cols in grid.values()) + 1
    return [[grid[r].get(i, "") for i in range(width)] for r in sorted(grid)]


_EXCEL_CTX = Context(prec=15, rounding=ROUND_HALF_EVEN)


def _excel_number(raw: str) -> str:
    """Numeric cells hold IEEE doubles (e.g. ``9.199999999999999``); read them at Excel's
    15-significant-digit display precision, which is the value the workbook shows."""
    if raw == "":
        return raw
    return format(_EXCEL_CTX.plus(Decimal(raw)).normalize(), "f")


def _csv_rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [list(r) for r in csv.reader(fh)]


class Table:
    """One sheet: header + rows of raw strings ('' = empty). ``row_numbers`` are 1-based sheet
    rows (header = 1), which is what evidence handles use (``R<n>`` / ``SH<k>.R<n>``)."""

    def __init__(self, key: str, raw: list[list[str]] | None = None) -> None:
        ws, rel, sheet, *_ = DATASETS[key]
        if raw is None:
            path = SEED / rel
            raw = _xlsx_sheet(path, sheet) if sheet else _csv_rows(path)
        self.key = key
        self.header = [h.strip() for h in raw[0]]
        self.rows = [dict(zip(self.header, r, strict=True)) for r in raw[1:]]
        self.row_numbers = list(range(2, len(raw) + 1))
        self.numeric = {
            col
            for col in self.header
            if any(r[col] != "" for r in self.rows)
            and all(r[col] == "" or _is_decimal(r[col]) for r in self.rows)
        }
        source_code, ordinal = dataset_id(key).split(":")
        self.handle_prefix = (
            f"{ws}/{source_code}@v1:SH{ordinal}." if sheet else f"{ws}/{source_code}@v1:"
        )

    def handle(self, index: int) -> str:
        return f"{self.handle_prefix}R{self.row_numbers[index]}"


def _is_decimal(text: str) -> bool:
    try:
        return Decimal(text).is_finite()
    except InvalidOperation:
        return False


# --- independent reference engine ----------------------------------------------------------------

EXACT_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)
ROUNDING_TEXT = (
    "half_even; share/percent 1dp; currency_usd 2dp; mean/median non-currency 2dp; ratio 3dp; "
    "counts, integer sums, min/max exact"
)


def column_unit(column: str) -> str:
    if column.endswith("_pct"):
        return "percent"
    if column.endswith(("_usd", "_usd_m", "_usd_bn")) or column == "price_usd":
        return "currency_usd"
    if column in ("rating", "avg_rating"):
        return "rating"
    return "number"


def metric_unit(fn: str, column: str | None) -> str:
    if fn == "share":
        return "percent"
    if fn in ("count", "count_distinct"):
        return "count"
    assert column is not None
    return column_unit(column)


def rounding_rule(fn: str, unit: str, values: list[Decimal]) -> str:
    if fn in ("count", "count_distinct", "min", "max"):
        return "exact"
    if fn == "sum":
        if all(v == v.to_integral_value() for v in values):
            return "exact"
        return {"currency_usd": "2dp", "percent": "1dp"}.get(unit, "exact")
    if fn == "share":
        return "1dp"
    # mean / median
    return {"percent": "1dp", "currency_usd": "2dp", "ratio": "3dp"}.get(unit, "2dp")


def _num(d: Decimal) -> int | float:
    return int(d) if d == d.to_integral_value() and "." not in str(d) else float(d)


def _exact_str(d: Decimal) -> str:
    text = format(d.normalize(EXACT_CTX), "f")
    return text


def apply_rounding(exact: Decimal, rule: str) -> int | float:
    if rule == "exact":
        return int(exact) if exact == exact.to_integral_value() else float(exact)
    places = {"1dp": Decimal("0.1"), "2dp": Decimal("0.01"), "3dp": Decimal("0.001")}[rule]
    return float(exact.quantize(places, rounding=ROUND_HALF_EVEN))


def _cmp_value(table: Table, column: str, value: Any) -> Any:
    if column in table.numeric and value is not None and not isinstance(value, bool):
        return Decimal(str(value))
    return None if value is None else str(value)


def _cell(table: Table, row: dict[str, str], column: str) -> Any:
    raw = row[column]
    if raw == "":
        return None
    return Decimal(raw) if column in table.numeric else raw


def matches(table: Table, row: dict[str, str], flt: dict[str, Any]) -> bool:
    col, op = flt["column"], flt["op"]
    if col not in table.header:
        raise KeyError(f"unknown column {col}")
    cell = _cell(table, row, col)
    if op == "is_null":
        return cell is None
    if op == "not_null":
        return cell is not None
    if cell is None:
        return False
    if op in ("in", "not_in", "between"):
        vals = [_cmp_value(table, col, v) for v in flt["values"]]
        if op == "between":
            return bool(vals[0] <= cell <= vals[1])
        return bool((cell in vals) == (op == "in"))
    v = _cmp_value(table, col, flt["value"])
    return bool(
        {
            "eq": lambda: cell == v,
            "ne": lambda: cell != v,
            "gt": lambda: cell > v,
            "gte": lambda: cell >= v,
            "lt": lambda: cell < v,
            "lte": lambda: cell <= v,
        }[op]()
    )


def select(table: Table, filters: list[dict[str, Any]] | None) -> list[int]:
    return [
        i for i, row in enumerate(table.rows) if all(matches(table, row, f) for f in filters or [])
    ]


def metric_key(m: dict[str, Any]) -> str:
    if m["fn"] == "count":
        return "count"
    if m["fn"] == "share":
        c = m["condition"]
        rhs = c.get("value") if c.get("values") is None else "|".join(map(str, c["values"]))
        return f"share({c['column']} {c['op']} {rhs})"
    return f"{m['fn']}({m['column']})"


def compute_metric(table: Table, idx: list[int], m: dict[str, Any]) -> dict[str, Any]:
    fn, col = m["fn"], m.get("column")
    unit = metric_unit(fn, col)
    out: dict[str, Any] = {"key": metric_key(m), "fn": fn, "column": col, "unit": unit}
    warnings: list[str] = []
    if fn == "count":
        exact: Decimal | None = Decimal(len(idx))
        out.update(denominator=len(idx), rule="exact")
    elif fn == "share":
        cond = m["condition"]
        eligible = [i for i in idx if table.rows[i][cond["column"]] != ""]
        if len(eligible) < len(idx):
            warnings.append("NULLS_EXCLUDED")
        hits = sum(1 for i in eligible if matches(table, table.rows[i], cond))
        exact = EXACT_CTX.divide(Decimal(hits) * 100, Decimal(len(eligible))) if eligible else None
        out.update(numerator=hits, denominator=len(eligible), rule="1dp")
    else:
        assert col is not None
        vals = [_cell(table, table.rows[i], col) for i in idx]
        present = [v for v in vals if v is not None]
        if len(present) < len(vals):
            warnings.append("NULLS_EXCLUDED")
        if fn == "count_distinct":
            exact = Decimal(len(set(present)))
        elif not present:
            exact = None
        elif fn == "sum":
            exact = sum(present, Decimal(0))
        elif fn == "mean":
            exact = EXACT_CTX.divide(sum(present, Decimal(0)), Decimal(len(present)))
        elif fn == "median":
            s = sorted(present)
            mid = len(s) // 2
            exact = s[mid] if len(s) % 2 else EXACT_CTX.divide(s[mid - 1] + s[mid], Decimal(2))
        elif fn in ("min", "max"):
            exact = min(present) if fn == "min" else max(present)
        else:
            raise SystemExit(f"unsupported fn {fn}")
        out.update(denominator=len(present), rule=rounding_rule(fn, unit, present))
    if exact is None:
        if fn in ("share", "mean", "median"):
            warnings.append("ZERO_DENOMINATOR")
        out.update(value=None, exact=None)
    else:
        out.update(value=apply_rounding(exact, out["rule"]), exact=_exact_str(exact))
    out["warnings"] = warnings
    return out


def _group_value(table: Table, row: dict[str, str], col: str) -> Any:
    v = _cell(table, row, col)
    return _num(v) if isinstance(v, Decimal) else v


def run_aggregate(table: Table, spec: dict[str, Any]) -> dict[str, Any]:
    idx = select(table, spec.get("filters"))
    group_by = spec.get("group_by") or []
    buckets: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    if group_by:
        for i in idx:
            buckets[tuple(_group_value(table, table.rows[i], g) for g in group_by)].append(i)
    else:
        buckets[()] = idx
    rows: list[dict[str, Any]] = []
    for key, members in buckets.items():
        rows.append(
            {
                "group": dict(zip(group_by, key, strict=True)),
                "metrics": [compute_metric(table, members, m) for m in spec["metrics"]],
            }
        )
    order = spec.get("order")
    if order:
        mi, desc = order.get("metric_index", 0), order.get("direction", "desc") == "desc"
        if order.get("by", "value") == "value":
            present = [r for r in rows if r["metrics"][mi]["exact"] is not None]
            absent = [r for r in rows if r["metrics"][mi]["exact"] is None]
            present.sort(key=lambda r: Decimal(r["metrics"][mi]["exact"]), reverse=desc)
            rows = present + absent
        else:
            rows.sort(key=lambda r: tuple(str(v) for v in r["group"].values()), reverse=desc)
    else:
        rows.sort(key=lambda r: tuple(str(v) for v in r["group"].values()))
    if spec.get("limit"):
        rows = rows[: spec["limit"]]
    return _result("aggregate", table, spec, idx, rows)


def _result(
    op: str, table: Table, spec: dict[str, Any], idx: list[int], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    warnings = sorted({w for r in rows for m in r["metrics"] for w in m.get("warnings", [])})
    if not idx:
        warnings = sorted(set(warnings) | {"EMPTY_SELECTION"})
    return {
        "operation": op,
        "rows_scanned": len(table.rows),
        "rows_matched": len(idx),
        "rows": rows,
        "warnings": warnings,
    }


def run_group_compare(table: Table, spec: dict[str, Any]) -> dict[str, Any]:
    idx = select(table, spec.get("filters"))
    col = spec["compare_column"]
    rows: list[dict[str, Any]] = []
    exacts: list[str | None] = []
    for level in (spec["group_a"], spec["group_b"]):
        flt = {"column": col, "op": "eq", "value": level}
        members = [i for i in idx if matches(table, table.rows[i], flt)]
        metric = compute_metric(table, members, spec["metric"])
        rows.append({"group": {col: level}, "metrics": [metric]})
        exacts.append(metric["exact"])
    result = _result("group_compare", table, spec, idx, rows)
    a, b = rows[0]["metrics"][0], rows[1]["metrics"][0]
    ea, eb = exacts
    diff_exact: str | None = None
    diff_value: int | float | None = None
    if ea is not None and eb is not None:
        d = Decimal(ea) - Decimal(eb)
        diff_exact, diff_value = _exact_str(d), apply_rounding(d, a["rule"])
    result["difference"] = {
        "key": f"difference({a['key']}: {spec['group_a']} - {spec['group_b']})",
        "value": diff_value,
        "exact": diff_exact,
        "unit": a["unit"],
        "rounding": a["rule"],
        "denominator": a["denominator"] + b["denominator"],
    }
    return result


def run_filter_rows(table: Table, spec: dict[str, Any]) -> dict[str, Any]:
    idx = select(table, spec.get("filters"))
    if spec.get("order_by"):
        col = spec["order_by"]
        present = [i for i in idx if table.rows[i][col] != ""]
        absent = [i for i in idx if table.rows[i][col] == ""]
        present.sort(
            key=lambda i: _cell(table, table.rows[i], col), reverse=spec.get("direction") == "desc"
        )
        ordered = present + absent
    else:
        ordered = idx
    limit = min(spec.get("limit") or 20, 20)
    cols = spec.get("columns") or table.header[:8]
    rows = [
        {
            "group": {c: _group_value(table, table.rows[i], c) for c in cols},
            "metrics": [],
            "handle": table.handle(i),
            "raw": {c: table.rows[i][c] for c in cols},
        }
        for i in ordered[:limit]
    ]
    return _result("filter_rows", table, spec, idx, rows)


RUNNERS: dict[str, Callable[[Table, dict[str, Any]], dict[str, Any]]] = {
    "aggregate": run_aggregate,
    "group_compare": run_group_compare,
    "filter_rows": run_filter_rows,
}


# --- item specs

NS, SP = "NORTHSTAR", "SOUTHPEAK"
SURVEY, REVIEWS, CHAN = "SURVEY-2026:1", "REVIEWS:1", "CHANNEL-PERF:1"
CATM, SKU, RET = "PRODUCT-PERF:1", "PRODUCT-PERF:2", "PRODUCT-PERF:3"
SIZE, PNL, SEGREV = "CATEGORY-SIZING:1", "FIN-SUMMARY-FY26:1", "FIN-SUMMARY-FY26:2"
SPCH, SPREG, SPSURV = "CHANNEL-DATA:1", "CHANNEL-DATA:2", "SURVEY-2026:1"
GENZ_AGES = ["18-21", "22-24", "25-27"]
OLDER_AGES = ["28-34", "35-44", "45+"]


def F(column: str, op: str, value: Any = None, values: list[Any] | None = None) -> dict[str, Any]:  # noqa: N802 - compact spec DSL
    out: dict[str, Any] = {"column": column, "op": op}
    if values is not None:
        out["values"] = values
    elif op not in ("is_null", "not_null"):
        out["value"] = value
    return out


def M(fn: str, column: str | None = None, cond: dict[str, Any] | None = None) -> dict[str, Any]:  # noqa: N802 - compact spec DSL
    out: dict[str, Any] = {"fn": fn}
    if column is not None:
        out["column"] = column
    if cond is not None:
        out["condition"] = cond
    return out


def SHARE(column: str, value: Any, op: str = "eq") -> dict[str, Any]:  # noqa: N802 - compact spec DSL
    return M("share", cond=F(column, op, value))


def AG(  # noqa: N802 - compact spec DSL
    ds: str,
    metrics: list[dict[str, Any]],
    filters: list[dict[str, Any]] | None = None,
    group_by: list[str] | None = None,
    direction: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {"dataset": ds, "metrics": metrics}
    if filters:
        spec["filters"] = filters
    if group_by:
        spec["group_by"] = group_by
    if direction:
        spec["order"] = {"by": "value", "metric_index": 0, "direction": direction}
    if limit:
        spec["limit"] = limit
    return {"tool": "aggregate", "spec": spec}


def GC(  # noqa: N802 - compact spec DSL
    ds: str,
    metric: dict[str, Any],
    column: str,
    a: Any,
    b: Any,
    filters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "dataset": ds,
        "metric": metric,
        "compare_column": column,
        "group_a": a,
        "group_b": b,
    }
    if filters:
        spec["filters"] = filters
    return {"tool": "group_compare", "spec": spec}


def FR(ds: str, filters: list[dict[str, Any]], columns: list[str], answer: str) -> dict[str, Any]:  # noqa: N802 - compact spec DSL
    spec = {"dataset": ds, "filters": filters, "columns": columns}
    return {"tool": "filter_rows", "spec": spec, "answer_column": answer}


def ROWS(ds: str, filters: list[dict[str, Any]], keywords: tuple[str, ...] = ()) -> dict[str, Any]:  # noqa: N802 - compact spec DSL
    """Gold evidence = the row parents matching ``filters`` (and, if given, containing one of
    ``keywords`` in their free text). Gold-side selection only; not an analytics spec."""
    return {"rows": ds, "filters": filters, "keywords": keywords}


def DOC(*fact_ids: str) -> dict[str, Any]:  # noqa: N802 - compact spec DSL
    return {"facts": list(fact_ids)}


# Each item: id, ws, category, task_type, question, expect, router, family, analytics (list),
# evidence (list), point, notes; optional converted_from, ledger (fact_id -> answer selector),
# invalid_reason.
# fmt: off
ITEMS: list[dict[str, Any]] = [
    # exact_count -------------------------------------------------------------------------------
    dict(
        id="A-CNT-01", ws=NS, category="exact_count",
        family="ns-survey:segment-size",
        question=(
            "How many people who took the 2026 customer survey fall into the Trail Starters "
            "segment?"
        ),
        analytics=[AG(SURVEY, [M("count")], [F("segment", "eq", "Trail Starters")])],
        notes="Plain filtered row count.",
    ),
    dict(
        id="A-CNT-02", ws=NS, category="exact_count",
        family="ns-reviews:rating-dist",
        question="Across the full product review export, how many reviews awarded a single star?",
        analytics=[AG(REVIEWS, [M("count")], [F("rating", "eq", 1)])],
        notes="Numeric equality filter on rating.",
    ),
    dict(
        id="A-CNT-03", ws=NS, category="exact_count",
        family="ns-reviews:channel-category",
        question="Tally the Social Shop reviews written about Leggings and Bottoms items.",
        analytics=[
            AG(
                REVIEWS,
                [M("count")],
                [F("channel", "eq", "Social Shop"), F("category", "eq", "Leggings and Bottoms")],
            ),
        ],
        notes="Two categorical filters.",
    ),
    dict(
        id="A-CNT-04", ws=SP, category="exact_count",
        family="sp-survey:activity",
        question=(
            "How many Southpeak survey participants say climbing is their main outdoor activity?"
        ),
        analytics=[AG(SPSURV, [M("count")], [F("primary_activity", "eq", "Climbing")])],
        notes="Southpeak-only column (primary_activity).",
    ),
    dict(
        id="A-CNT-05", ws=NS, category="exact_count",
        family="ns-sku:price",
        question="How many SKUs in the product performance workbook carry a list price above $100?",
        analytics=[AG(SKU, [M("count")], [F("price_usd", "gt", 100)])],
        notes="Strict greater-than on a currency column.",
    ),
    dict(
        id="A-CNT-06", ws=NS, category="exact_count",
        family="ns-reviews:rating-dist",
        question="How many different products picked up at least one 1-star review?",
        analytics=[AG(REVIEWS, [M("count_distinct", "product")], [F("rating", "eq", 1)])],
        notes="count_distinct, not a row count.",
    ),
    # percentage_share --------------------------------------------------------------------------
    dict(
        id="A-SHR-01", ws=NS, category="percentage_share",
        family="ns-survey:pain-share-genz",
        question=(
            "Among Gen Z survey respondents (ages 18 to 27), what percent picked fit inconsistency"
            " as their single biggest frustration?"
        ),
        analytics=[
            AG(
                SURVEY,
                [SHARE("top_pain_point", "fit_inconsistency")],
                [F("age_group", "in", values=GENZ_AGES)],
            ),
        ],
        ledger={"NS-004": "answer"},
        notes=(
            "Gen Z = age groups 18-21/22-24/25-27 (same 400 rows as segment != Established "
            "Active). Equals brand-strategy fact NS-004 (27%)."
        ),
    ),
    dict(
        id="A-SHR-02", ws=NS, category="percentage_share",
        family="ns-survey:pain-share-older",
        question=(
            "For respondents aged 28 and over, what share cite price versus value as the top pain "
            "point?"
        ),
        analytics=[
            AG(
                SURVEY,
                [SHARE("top_pain_point", "price_vs_value")],
                [F("age_group", "in", values=OLDER_AGES)],
            ),
        ],
        notes="Older cohort = 28-34/35-44/45+ (200 rows); world model prevalence 26%.",
    ),
    dict(
        id="A-SHR-03", ws=SP, category="percentage_share",
        family="sp-survey:pain-share",
        question=(
            "What percentage of Southpeak's survey sample chose fit inconsistency as their top "
            "issue?"
        ),
        analytics=[AG(SPSURV, [SHARE("top_pain_point", "fit_inconsistency")])],
        ledger={"SP-C02": "answer"},
        notes="Unfiltered share; equals Southpeak brand-strategy fact SP-C02 (33%).",
    ),
    dict(
        id="A-SHR-04", ws=NS, category="percentage_share",
        family="ns-reviews:kr2",
        question="What proportion of Knit Runner 2 reviews give two stars or fewer?",
        analytics=[AG(REVIEWS, [SHARE("rating", 2, "lte")], [F("product", "eq", "Knit Runner 2")])],
        notes="Share with a numeric lte condition; small base (13 reviews).",
    ),
    dict(
        id="A-SHR-05", ws=NS, category="percentage_share",
        family="ns-survey:price-sensitivity",
        question=(
            "Within the Value Seekers segment, what percentage put their price sensitivity at the "
            "top score of 5?"
        ),
        analytics=[
            AG(SURVEY, [SHARE("price_sensitivity", 5)], [F("segment", "eq", "Value Seekers")]),
        ],
        notes="Share condition on a numeric column.",
    ),
    dict(
        id="A-SHR-06", ws=SP, category="percentage_share",
        family="sp-survey:nps",
        question=(
            "What share of Southpeak's Urban Outdoor respondents are detractors, meaning they "
            "scored 6 or lower?"
        ),
        analytics=[AG(SPSURV, [SHARE("nps", 6, "lte")], [F("segment", "eq", "Urban Outdoor")])],
        notes="Detractor share (0-6) - not an NPS score.",
    ),
    # average -----------------------------------------------------------------------------------
    dict(
        id="A-AVG-01", ws=NS, category="average",
        family="ns-survey:nps-segment",
        question="What's the mean likelihood-to-recommend score among Studio Social respondents?",
        analytics=[AG(SURVEY, [M("mean", "nps")], [F("segment", "eq", "Studio Social")])],
        notes="Mean of the 0-10 recommend answer (column nps), 2dp.",
    ),
    dict(
        id="A-AVG-02", ws=NS, category="average",
        family="ns-survey:price-sensitivity",
        question=(
            "On the 1-to-5 price sensitivity scale, what is the average for survey respondents "
            "aged 18 to 27?"
        ),
        analytics=[
            AG(SURVEY, [M("mean", "price_sensitivity")], [F("age_group", "in", values=GENZ_AGES)]),
        ],
        notes="World model price_sensitivity_mean.gen_z = 3.9.",
    ),
    dict(
        id="A-AVG-03", ws=NS, category="average",
        family="ns-reviews:category-rating",
        question="What average star rating do Running Footwear products get in the review data?",
        analytics=[AG(REVIEWS, [M("mean", "rating")], [F("category", "eq", "Running Footwear")])],
        notes="Mean rating (unit rating, 2dp).",
    ),
    dict(
        id="A-AVG-04", ws=NS, category="average",
        family="ns-channel:aov",
        question=(
            "Over the twelve months of channel data, what was the average order value for Gen Z "
            "buyers in the app?"
        ),
        analytics=[
            AG(
                CHAN,
                [M("mean", "aov_usd")],
                [F("channel", "eq", "App"), F("segment", "eq", "Gen Z")],
            ),
        ],
        notes="Unweighted mean of monthly AOV (currency 2dp); an order-weighted AOV would differ.",
    ),
    dict(
        id="A-AVG-05", ws=SP, category="average",
        family="sp-channel:conversion",
        question=(
            "What has Outfitter Partners averaged for monthly conversion rate across Southpeak's "
            "channel table?"
        ),
        analytics=[
            AG(
                SPCH,
                [M("mean", "conversion_rate_pct")],
                [F("channel", "eq", "Outfitter Partners")],
            ),
        ],
        notes=(
            "Mean of a percent column: rounded as percent (1dp); `exact` is authoritative if the "
            "engine rounds means of percents to 2dp."
        ),
    ),
    dict(
        id="A-AVG-06", ws=SP, category="average",
        family="sp-survey:nps",
        question=(
            "What is the average recommend score given by Alpine Committed respondents in the "
            "Southpeak survey?"
        ),
        analytics=[AG(SPSURV, [M("mean", "nps")], [F("segment", "eq", "Alpine Committed")])],
        notes="Southpeak survey has no price_sensitivity; nps only.",
    ),
    # median_min_max ----------------------------------------------------------------------------
    dict(
        id="A-MMM-01", ws=NS, category="median_min_max",
        family="ns-sku:price",
        question="What is the median list price across all SKUs in the product performance file?",
        analytics=[AG(SKU, [M("median", "price_usd")])],
        notes="Even count (32): median = mean of the two middle values.",
    ),
    dict(
        id="A-MMM-02", ws=NS, category="median_min_max",
        family="ns-sku:returns",
        question="Which is the highest return rate recorded by any Accessories SKU?",
        analytics=[AG(SKU, [M("max", "return_rate_pct")], [F("category", "eq", "Accessories")])],
        notes="max is exact.",
    ),
    dict(
        id="A-MMM-03", ws=NS, category="median_min_max",
        family="ns-catmonthly:margin",
        question=(
            "What was the weakest monthly gross margin for the Accessories category during 2026?"
        ),
        analytics=[
            AG(
                CATM,
                [M("min", "gross_margin_pct")],
                [F("category", "eq", "Accessories"), F("month", "gte", "2026-01")],
            ),
        ],
        notes="Date-column range filter (ISO month strings).",
    ),
    dict(
        id="A-MMM-04", ws=SP, category="median_min_max",
        family="sp-channel:sales",
        question="What was the single best month of net sales for Southpeak's Stores channel?",
        analytics=[AG(SPCH, [M("max", "net_sales_usd")], [F("channel", "eq", "Stores")])],
        notes="max is exact (no currency rounding applied to min/max).",
    ),
    dict(
        id="A-MMM-05", ws=NS, category="median_min_max",
        family="ns-survey:nps-segment",
        question="What is the median recommend score among Campus Competitors respondents?",
        analytics=[AG(SURVEY, [M("median", "nps")], [F("segment", "eq", "Campus Competitors")])],
        notes="Median of integers over an even base.",
    ),
    # grouped_comparison ------------------------------------------------------------------------
    dict(
        id="A-GRP-01", ws=NS, category="grouped_comparison",
        family="ns-channel:sales",
        question="Break down September 2026 net sales by channel, combining both age segments.",
        analytics=[
            AG(CHAN, [M("sum", "net_sales_usd")], [F("month", "eq", "2026-09")], ["channel"]),
        ],
        notes="Integer currency sums are exact.",
    ),
    dict(
        id="A-GRP-02", ws=NS, category="grouped_comparison",
        family="ns-survey:nps-segment",
        question="Show the average NPS response for each customer segment in the 2026 survey.",
        analytics=[AG(SURVEY, [M("mean", "nps")], None, ["segment"])],
        notes="Mean of the recommend answer per segment, not a promoter-minus-detractor NPS score.",
    ),
    dict(
        id="A-GRP-03", ws=SP, category="grouped_comparison",
        family="sp-survey:pain-share",
        question=(
            "For each region, what share of Southpeak respondents named delivery speed as their "
            "main problem?"
        ),
        analytics=[AG(SPSURV, [SHARE("top_pain_point", "delivery_speed")], None, ["region"])],
        notes="Grouped share; every region has a nonzero base.",
    ),
    dict(
        id="A-GRP-04", ws=NS, category="grouped_comparison",
        family="ns-returns:reason",
        question="Sum the Q3 2026 return counts by return reason across the tracked SKUs.",
        analytics=[
            AG(RET, [M("sum", "returns_count")], [F("quarter", "eq", "2026-Q3")], ["reason"]),
        ],
        notes="Returns lists each SKU's top three reasons only, so sums are of listed rows.",
    ),
    dict(
        id="A-GRP-05", ws=NS, category="grouped_comparison",
        family="ns-catmonthly:units",
        question="Total units sold per product category from January through September 2026.",
        analytics=[
            AG(
                CATM,
                [M("sum", "units")],
                [F("month", "between", values=["2026-01", "2026-09"])],
                ["category"],
            ),
        ],
        notes="between is inclusive on ISO month strings.",
    ),
    dict(
        id="A-GRP-06", ws=NS, category="grouped_comparison",
        family="ns-channel:conversion",
        question=(
            "Give the mean conversion rate for every channel and age segment combination in Q3 "
            "2026 (July to September)."
        ),
        analytics=[
            AG(
                CHAN,
                [M("mean", "conversion_rate_pct")],
                [F("month", "between", values=["2026-07", "2026-09"])],
                ["channel", "segment"],
            ),
        ],
        notes="Two group-by columns (10 groups); mean of percent rounded 1dp.",
    ),
    # filtered_aggregation ----------------------------------------------------------------------
    dict(
        id="A-FLT-01", ws=NS, category="filtered_aggregation",
        family="ns-channel:orders",
        question=(
            "How many orders did Gen Z place through the Social Shop between July and September "
            "2026?"
        ),
        analytics=[
            AG(
                CHAN,
                [M("sum", "orders")],
                [
                    F("channel", "eq", "Social Shop"),
                    F("segment", "eq", "Gen Z"),
                    F("month", "between", values=["2026-07", "2026-09"]),
                ],
            ),
        ],
        notes="Three filters incl. a date range.",
    ),
    dict(
        id="A-FLT-02", ws=NS, category="filtered_aggregation",
        family="ns-catmonthly:sales",
        question="What were combined Running Footwear net sales for the first half of 2026?",
        analytics=[
            AG(
                CATM,
                [M("sum", "net_sales_usd")],
                [
                    F("category", "eq", "Running Footwear"),
                    F("month", "between", values=["2026-01", "2026-06"]),
                ],
            ),
        ],
        notes="H1 = 2026-01..2026-06.",
    ),
    dict(
        id="A-FLT-03", ws=SP, category="filtered_aggregation",
        family="sp-channel:sessions",
        question="How many app sessions did Southpeak log from January 2026 onward?",
        analytics=[
            AG(
                SPCH,
                [M("sum", "sessions")],
                [F("channel", "eq", "App"), F("month", "gte", "2026-01")],
            ),
        ],
        notes="Open-ended date filter (gte).",
    ),
    dict(
        id="A-FLT-04", ws=NS, category="filtered_aggregation",
        family="ns-reviews:channel-rating",
        question="What's the average rating for brand site reviews dated July 1, 2026 or later?",
        analytics=[
            AG(
                REVIEWS,
                [M("mean", "rating")],
                [F("channel", "eq", "Brand Site"), F("date", "gte", "2026-07-01")],
            ),
        ],
        notes="Day-level ISO date filter.",
    ),
    dict(
        id="A-FLT-05", ws=NS, category="filtered_aggregation",
        family="ns-survey:price-sensitivity",
        question=(
            "Among women in the West who shop monthly, what is the mean price sensitivity score?"
        ),
        analytics=[
            AG(
                SURVEY,
                [M("mean", "price_sensitivity")],
                [
                    F("gender", "eq", "Woman"),
                    F("region", "eq", "West"),
                    F("purchase_frequency", "eq", "Monthly"),
                ],
            ),
        ],
        notes="Three-way filter, small base.",
    ),
    # segment_compare ---------------------------------------------------------------------------
    dict(
        id="A-CMP-01", ws=NS, category="segment_compare",
        family="ns-survey:nps-segment",
        question="Compare mean NPS between Studio Social and Value Seekers respondents.",
        analytics=[GC(SURVEY, M("mean", "nps"), "segment", "Studio Social", "Value Seekers")],
        notes="Difference = A - B on exact means, then rounded.",
    ),
    dict(
        id="A-CMP-02", ws=NS, category="segment_compare",
        family="ns-channel:conversion",
        question=(
            "On Social Shop, how does average monthly conversion differ between Gen Z and "
            "Millennial shoppers?"
        ),
        analytics=[
            GC(
                CHAN,
                M("mean", "conversion_rate_pct"),
                "segment",
                "Gen Z",
                "Millennial",
                [F("channel", "eq", "Social Shop")],
            ),
        ],
        notes="Filtered group_compare; percent means (1dp).",
    ),
    dict(
        id="A-CMP-03", ws=NS, category="segment_compare",
        family="ns-survey:pain-share-segment",
        question=(
            "Is knit upper durability a bigger top complaint for Trail Starters or Campus "
            "Competitors, in percentage terms?"
        ),
        analytics=[
            GC(
                SURVEY,
                SHARE("top_pain_point", "knit_upper_durability"),
                "segment",
                "Trail Starters",
                "Campus Competitors",
            ),
        ],
        notes="Share per group with each group's own denominator.",
    ),
    dict(
        id="A-CMP-04", ws=SP, category="segment_compare",
        family="sp-survey:pain-share-segment",
        question=(
            "Weekend Hikers versus Urban Outdoor: what percent of each cite sustainability "
            "transparency as their top concern?"
        ),
        analytics=[
            GC(
                SPSURV,
                SHARE("top_pain_point", "sustainability_transparency"),
                "segment",
                "Weekend Hikers",
                "Urban Outdoor",
            ),
        ],
        notes="Southpeak group_compare.",
    ),
    dict(
        id="A-CMP-05", ws=NS, category="segment_compare",
        family="ns-reviews:channel-rating",
        question=(
            "Do app reviews score higher than marketplace reviews on average, and by how much?"
        ),
        analytics=[GC(REVIEWS, M("mean", "rating"), "channel", "App", "Marketplace")],
        notes="Mean rating difference (2dp).",
    ),
    dict(
        id="A-CMP-06", ws=SP, category="segment_compare",
        family="sp-channel:aov",
        question=(
            "How does Southpeak's average order value on the brand site compare with the "
            "marketplace?"
        ),
        analytics=[GC(SPCH, M("mean", "aov_usd"), "channel", "Brand Site", "Marketplace")],
        notes="Unweighted monthly AOV means, currency 2dp.",
    ),
    dict(
        id="A-CMP-07", ws=NS, category="segment_compare",
        converted_from="R0-058",
        family="ns-sku:knit-runner-returns",
        question=(
            "How much higher is the Knit Runner 2's return rate than the first-generation Knit "
            "Runner's?"
        ),
        analytics=[
            GC(SKU, M("max", "return_rate_pct"), "product_name", "Knit Runner 2", "Knit Runner"),
        ],
        ledger={"NS-120": "a", "NS-D05": "b"},
        notes=(
            "Converted from retrieval-v0 R0-058 (analytics; 'second-generation, not the "
            "original'). One row per SKU, so max = the SKU value; B is ledger distractor NS-D05."
        ),
    ),
    # top_bottom --------------------------------------------------------------------------------
    dict(
        id="A-TOP-01", ws=NS, category="top_bottom",
        family="ns-sku:sales-rank",
        question="Which three SKUs generated the most FY26 year-to-date net sales?",
        analytics=[
            AG(SKU, [M("sum", "net_sales_fy26_ytd_usd")], None, ["product_name"], "desc", 3),
        ],
        notes="Top-3; one row per product, so sum = the SKU value.",
    ),
    dict(
        id="A-TOP-02", ws=NS, category="top_bottom",
        family="ns-sku:rating-rank",
        question="Which product has the lowest average customer rating in the SKU table?",
        analytics=[AG(SKU, [M("min", "avg_rating")], None, ["product_name"], "asc", 1)],
        notes="Bottom-1 by the SKU table's avg_rating (not the review export).",
    ),
    dict(
        id="A-TOP-03", ws=NS, category="top_bottom",
        family="ns-catmonthly:sell-through",
        question="Which product category had the highest sell-through in September 2026?",
        analytics=[
            AG(
                CATM,
                [M("max", "sell_through_pct")],
                [F("month", "eq", "2026-09")],
                ["category"],
                "desc",
                1,
            ),
        ],
        notes="XLSX doubles read at 15 significant digits (73.2, not 73.19999...).",
    ),
    dict(
        id="A-TOP-04", ws=NS, category="top_bottom",
        family="ns-reviews:volume",
        question="Which product has drawn the largest number of reviews?",
        analytics=[AG(REVIEWS, [M("count")], None, ["product"], "desc", 1)],
        notes="Top-1 by count.",
    ),
    dict(
        id="A-TOP-05", ws=SP, category="top_bottom",
        family="sp-region:share",
        question="Name Southpeak's two biggest regions by share of FY26 year-to-date sales.",
        analytics=[
            AG(SPREG, [M("max", "share_of_fy26_ytd_sales_pct")], None, ["region"], "desc", 2),
        ],
        notes="Region_Summary has one row per region.",
    ),
    dict(
        id="A-TOP-06", ws=NS, category="top_bottom",
        family="ns-returns:volume",
        question="Which tracked product had the most total returns in Q3 2026?",
        analytics=[
            AG(
                RET,
                [M("max", "total_sku_returns")],
                [F("quarter", "eq", "2026-Q3")],
                ["product_name"],
                "desc",
                1,
            ),
        ],
        notes="total_sku_returns repeats on each reason row; max (not sum) is the per-SKU total.",
    ),
    dict(
        id="A-TOP-07", ws=NS, category="top_bottom",
        converted_from="R0-021",
        family="ns-sku:units-rank",
        question=(
            "Rank the SKUs by fiscal-2026-to-date units: which one tops the list, and with how "
            "many?"
        ),
        analytics=[AG(SKU, [M("sum", "units_fy26_ytd")], None, ["product_name"], "desc", 1)],
        ledger={"NS-121": "answer"},
        notes="Converted from retrieval-v0 R0-021 (analytics: best seller by units).",
    ),
    dict(
        id="A-TOP-08", ws=NS, category="top_bottom",
        converted_from="R0-023",
        family="ns-returns:fit-small",
        question=(
            "For Q3 2026 returns tagged 'Fit - runs small', which product had the largest share of"
            " its returns in that reason?"
        ),
        analytics=[
            AG(
                RET,
                [M("max", "share_of_sku_returns_pct")],
                [F("quarter", "eq", "2026-Q3"), F("reason", "eq", "Fit - runs small")],
                ["product_name"],
                "desc",
                1,
            ),
        ],
        ledger={"NS-124": "answer"},
        notes=(
            "Converted from retrieval-v0 R0-023 (analytics: product with many 'runs small' "
            "returns)."
        ),
    ),
    dict(
        id="A-TOP-09", ws=NS, category="top_bottom",
        family="ns-fin:segment-growth",
        question=(
            "Excluding the total line, which customer age segment does finance expect to grow "
            "fastest in FY26?"
        ),
        analytics=[
            AG(
                SEGREV,
                [M("max", "yoy_growth_pct")],
                [F("segment", "ne", "Total")],
                ["segment"],
                "desc",
                1,
            ),
        ],
        ledger={"NS-128": "answer"},
        notes=(
            "Confidential dataset (FIN-SUMMARY-FY26); allowed because llm_max_confidentiality = "
            "confidential."
        ),
    ),
    # null_missing ------------------------------------------------------------------------------
    dict(
        id="A-NUL-01", ws=NS, category="null_missing",
        family="ns-sizing:growth",
        question=(
            "What is the average year-over-year growth across the Gen Z personalized athletic "
            "footwear rows in the category sizing model?"
        ),
        analytics=[
            AG(
                SIZE,
                [M("mean", "yoy_growth_pct")],
                [
                    F("generation", "eq", "Gen Z"),
                    F("category", "eq", "Personalized athletic footwear"),
                ],
            ),
        ],
        notes=(
            "2023 base year has an empty yoy_growth_pct: NULLS_EXCLUDED, denominator 5 of 6 rows. "
            "`category` is profiled as text (free_text), so the engine must allow eq on text "
            "columns."
        ),
    ),
    dict(
        id="A-NUL-02", ws=NS, category="null_missing",
        family="ns-sizing:missing",
        question="How many rows of the market sizing sheet have a blank YoY growth value?",
        analytics=[AG(SIZE, [M("count")], [F("yoy_growth_pct", "is_null")])],
        notes="is_null filter; the 9 base-year rows.",
    ),
    dict(
        id="A-NUL-03", ws=NS, category="null_missing",
        family="ns-fin:pnl-yoy",
        question=(
            "Averaged over the P&L lines that report one, what is the year-over-year change "
            "percentage in the FY26 financial summary?"
        ),
        analytics=[AG(PNL, [M("mean", "yoy_change_pct")])],
        notes=(
            "Confidential dataset; 3 percent-unit lines have no yoy_change_pct (NULLS_EXCLUDED, "
            "denominator 7)."
        ),
    ),
    dict(
        id="A-NUL-04", ws=NS, category="null_missing",
        family="ns-sizing:growth",
        question=(
            "What is the mean YoY growth across all Millennial rows of the sizing model, and how "
            "many rows actually carry a growth figure?"
        ),
        analytics=[
            AG(
                SIZE,
                [M("mean", "yoy_growth_pct"), M("count")],
                [F("generation", "eq", "Millennial")],
            ),
        ],
        notes=(
            "Mean denominator (15) vs matched rows (18) - the answer must report the non-null "
            "base."
        ),
    ),
    # no_result ---------------------------------------------------------------------------------
    dict(
        id="A-NOR-01", ws=NS, category="no_result",
        family="ns-survey:segment-size",
        question="How many Campus Competitors respondents are in the 45+ age band?",
        analytics=[
            AG(
                SURVEY,
                [M("count")],
                [F("segment", "eq", "Campus Competitors"), F("age_group", "eq", "45+")],
            ),
        ],
        notes="Valid levels, empty intersection: count 0 + EMPTY_SELECTION.",
    ),
    dict(
        id="A-NOR-02", ws=NS, category="no_result",
        family="ns-reviews:product-channel",
        question="What is the mean star rating for Puffer Vest reviews submitted through the app?",
        analytics=[
            AG(
                REVIEWS,
                [M("mean", "rating")],
                [F("product", "eq", "Puffer Vest"), F("channel", "eq", "App")],
            ),
        ],
        notes=(
            "The only Puffer Vest review is on Marketplace: null + "
            "EMPTY_SELECTION/ZERO_DENOMINATOR."
        ),
    ),
    dict(
        id="A-NOR-03", ws=NS, category="no_result",
        family="ns-channel:sales",
        question=(
            "What net sales did the Marketplace channel book in Q4 2026 (October to December)?"
        ),
        analytics=[
            AG(
                CHAN,
                [M("sum", "net_sales_usd")],
                [
                    F("channel", "eq", "Marketplace"),
                    F("month", "between", values=["2026-10", "2026-12"]),
                ],
            ),
        ],
        notes="Data ends 2026-09: EMPTY_SELECTION; the answer must not substitute Oct-Dec 2025.",
    ),
    dict(
        id="A-NOR-04", ws=SP, category="no_result",
        family="sp-survey:waterproofing",
        question="How many Alpine Committed respondents named waterproofing their top pain point?",
        analytics=[
            AG(
                SPSURV,
                [M("count")],
                [
                    F("segment", "eq", "Alpine Committed"),
                    F("top_pain_point", "eq", "waterproofing"),
                ],
            ),
        ],
        notes="Count 0 + EMPTY_SELECTION.",
    ),
    # invalid_request ---------------------------------------------------------------------------
    dict(
        id="A-INV-01", ws=NS, category="invalid_request",
        expect="insufficient",
        invalid_reason="unknown_column",
        family="inv:delivery-days",
        question="What is the average delivery time in days for each sales channel?",
        notes=(
            "No dataset has a delivery-time column; must not proxy with another metric or "
            "documents' anecdotes."
        ),
    ),
    dict(
        id="A-INV-02", ws=NS, category="invalid_request",
        expect="invalid",
        invalid_reason="unsupported_computation",
        family="inv:correlation",
        question=(
            "Calculate the correlation coefficient between price sensitivity and NPS across survey"
            " respondents."
        ),
        notes="No correlation function in the contract; the model must not compute it itself.",
    ),
    dict(
        id="A-INV-03", ws=NS, category="invalid_request",
        expect="invalid",
        invalid_reason="unsupported_computation",
        family="inv:forecast",
        question=(
            "Project Running Footwear net sales for December 2026 by extrapolating the monthly "
            "trend."
        ),
        notes="Forecasting is not a supported computation.",
    ),
    dict(
        id="A-INV-04", ws=NS, category="invalid_request",
        expect="insufficient",
        invalid_reason="dataset_not_in_workspace",
        canary="SP-C06",
        family="inv:cross-workspace",
        question=(
            "Pull the Sep 2026 marketplace conversion figure for Southpeak Outdoor from the "
            "channel data."
        ),
        notes=(
            "Asked in NORTHSTAR: Southpeak's CHANNEL-DATA is not visible (RLS). The SOUTHPEAK "
            "canary value (SP-C06, 4.9%) must not appear."
        ),
    ),
    dict(
        id="A-INV-05", ws=NS, category="invalid_request",
        expect="insufficient",
        invalid_reason="unknown_column",
        family="inv:sku-margin",
        question="List the gross margin percentage for every individual SKU.",
        notes="SKU_Performance has no margin column (margin exists only per category-month).",
    ),
    dict(
        id="A-INV-06", ws=SP, category="invalid_request",
        expect="insufficient",
        invalid_reason="unknown_column",
        family="inv:sp-gender",
        question="Break down Southpeak survey NPS by respondent gender.",
        notes="The Southpeak survey has no gender column (Northstar's does).",
    ),
    dict(
        id="A-INV-07", ws=NS, category="invalid_request",
        expect="invalid",
        invalid_reason="unsupported_computation",
        family="inv:stddev",
        question="What's the standard deviation of review ratings within each product category?",
        notes="No dispersion function in the contract.",
    ),
    # retrieval_only ----------------------------------------------------------------------------
    dict(
        id="A-RET-01", ws=NS, category="retrieval_only",
        family="ret:interviews",
        question="Why does interviewee Lena O. doubt brands' green claims?",
        evidence=[
            DOC("NS-063"),
        ],
        point=(
            "She assumes sustainability claims are marketing when a brand cannot say where a shoe "
            "is made and what is recycled."
        ),
        notes="Qualitative interview evidence; no computation.",
    ),
    dict(
        id="A-RET-02", ws=NS, category="retrieval_only",
        family="ret:pilot",
        question=(
            "In the personalization pilot, what stopped customers from ordering another "
            "personalized pair?"
        ),
        evidence=[
            DOC("NS-054"),
        ],
        point=(
            "The wait: personalized pairs took about 12 days and 41% of exit-survey respondents "
            "named the wait as the main reason not to reorder."
        ),
        notes="Numbers come from a document (pilot results), not a dataset.",
    ),
    dict(
        id="A-RET-03", ws=NS, category="retrieval_only",
        family="ret:segments",
        question="Which four Gen Z customer groups does the brand strategy describe?",
        evidence=[
            DOC("NS-006"),
        ],
        point="Campus Competitors, Studio Social, Trail Starters and Value Seekers.",
        notes=(
            "Router trap: segment names are also survey levels, but the question asks for the "
            "strategy's definition."
        ),
    ),
    dict(
        id="A-RET-04", ws=NS, category="retrieval_only",
        family="ret:trends",
        question=(
            "According to the trends report, how do young shoppers weigh peer reviews and creator "
            "try-on videos against brand advertising?"
        ),
        evidence=[
            DOC("NS-040"),
        ],
        point=(
            "57% of Gen Z respondents trust peer reviews and creator try-on videos more than brand"
            " advertising."
        ),
        notes="Percent from a report, not computable from any dataset.",
    ),
    dict(
        id="A-RET-05", ws=SP, category="retrieval_only",
        family="ret:sp-delivery",
        question="Where will Southpeak first trial its faster delivery promise, and starting when?",
        evidence=[
            DOC("SP-C07"),
        ],
        point="A 48 hour delivery promise piloted in Denver and Salt Lake City from March 2027.",
        notes="Southpeak canary fact, asked in its own workspace.",
    ),
    dict(
        id="A-RET-06", ws=SP, category="retrieval_only",
        family="ret:sp-interviews",
        question="What did a Southpeak interviewee dislike about the Glacier Pack?",
        evidence=[
            DOC("SP-C03"),
        ],
        point="The Glacier Pack straps dug into their shoulders after an hour on the trail.",
        notes="Qualitative interview evidence.",
    ),
    # mixed -------------------------------------------------------------------------------------
    dict(
        id="A-MIX-01", ws=NS, category="mixed",
        family="ns-survey:delivery",
        question=(
            "Which Gen Z segment most often names delivery speed as its top pain point, and what "
            "do those respondents say about shipping?"
        ),
        analytics=[
            AG(
                SURVEY,
                [SHARE("top_pain_point", "delivery_speed")],
                [F("age_group", "in", values=GENZ_AGES)],
                ["segment"],
                "desc",
                1,
            ),
        ],
        evidence=[
            ROWS(
                SURVEY,
                [
                    F("segment", "eq", "Campus Competitors"),
                    F("top_pain_point", "eq", "delivery_speed"),
                ],
            ),
        ],
        point=(
            "Deliveries take over a week (up to ten days) versus other sites, tracking goes stale "
            "for days, and they would pay a little extra for two-day delivery."
        ),
        notes=(
            "Quant picks the segment (Campus Competitors); qual from that segment's delivery_speed"
            " verbatims (any-of handles)."
        ),
    ),
    dict(
        id="A-MIX-02", ws=NS, category="mixed",
        family="ns-survey:knit",
        question=(
            "How many survey respondents call knit upper durability their biggest problem, and "
            "what kinds of wear do they report?"
        ),
        analytics=[AG(SURVEY, [M("count")], [F("top_pain_point", "eq", "knit_upper_durability")])],
        evidence=[
            ROWS(
                SURVEY,
                [F("top_pain_point", "eq", "knit_upper_durability")],
                ("knit", "upper", "mesh", "toe", "hole", "worn"),
            ),
        ],
        point=(
            "The knit upper frays or tears near the toe flex point within weeks to a couple of "
            "months, holes form where the toe bends, and support offered discounts instead of "
            "replacements."
        ),
        notes=(
            "Evidence includes R0521 (NS-145). Verbatims about pilling fabric are excluded from "
            "gold (not upper wear)."
        ),
    ),
    dict(
        id="A-MIX-03", ws=NS, category="mixed",
        family="ns-reviews:kr2",
        question=(
            "What is the Knit Runner 2's mean review rating, and what do its 1- and 2-star "
            "reviewers complain about?"
        ),
        analytics=[AG(REVIEWS, [M("mean", "rating")], [F("product", "eq", "Knit Runner 2")])],
        evidence=[
            ROWS(
                REVIEWS,
                [F("product", "eq", "Knit Runner 2"), F("rating", "lte", 2)],
                ("tore", "stitching", "refund"),
            ),
        ],
        point=(
            "The upper tore at the flex point within two months, stitching came loose after a few "
            "weeks (poor value at the price), and returns/refunds were slow."
        ),
        notes="Evidence includes RV-00412 (NS-147); generic or off-product low-star text excluded.",
    ),
    dict(
        id="A-MIX-04", ws=SP, category="mixed",
        family="sp-survey:durability",
        question=(
            "Which Southpeak segment has the highest share citing durability as its top pain "
            "point, and what breaks for them?"
        ),
        analytics=[
            AG(SPSURV, [SHARE("top_pain_point", "durability")], None, ["segment"], "desc", 1),
        ],
        evidence=[
            ROWS(
                SPSURV,
                [F("segment", "eq", "Urban Outdoor"), F("top_pain_point", "eq", "durability")],
            ),
        ],
        point=(
            "Soles peel away on the trail after a few months, pack zippers break, and fleece "
            "fabric pills quickly."
        ),
        notes="Southpeak mixed item; quant picks Urban Outdoor.",
    ),
    dict(
        id="A-MIX-05", ws=NS, category="mixed",
        family="ns-survey:sustainability",
        question=(
            "What percent of Studio Social respondents make sustainability transparency their top "
            "concern, and what do they want disclosed?"
        ),
        analytics=[
            AG(
                SURVEY,
                [SHARE("top_pain_point", "sustainability_transparency")],
                [F("segment", "eq", "Studio Social")],
            ),
        ],
        evidence=[
            ROWS(
                SURVEY,
                [
                    F("segment", "eq", "Studio Social"),
                    F("top_pain_point", "eq", "sustainability_transparency"),
                ],
            ),
        ],
        point=(
            "Recycled-content percentages and factory country on the product page, what shoes are "
            "made of and where, and repair or recycling information instead of vague green labels."
        ),
        notes="Evidence includes R0062 (NS-146).",
    ),
    dict(
        id="A-MIX-06", ws=NS, category="mixed",
        family="ns-survey:personalization",
        question=(
            "Among Campus Competitors, what share say a lack of personalization is their top pain "
            "point, and what custom options are they asking for?"
        ),
        analytics=[
            AG(
                SURVEY,
                [SHARE("top_pain_point", "lack_of_personalization")],
                [F("segment", "eq", "Campus Competitors")],
            ),
        ],
        evidence=[
            ROWS(
                SURVEY,
                [
                    F("segment", "eq", "Campus Competitors"),
                    F("top_pain_point", "eq", "lack_of_personalization"),
                ],
            ),
        ],
        point=(
            "Custom colors or initials, made-to-foot shoes (about 15% more) if they arrive as fast"
            " as standard, and saved fit preferences / relevant recommendations."
        ),
        notes=(
            "6/96 = 6.25% rounds half-even to 6.2 (tests ROUND_HALF_EVEN). Evidence includes R0388"
            " (NS-144)."
        ),
    ),
    dict(
        id="A-MIX-07", ws=SP, category="mixed",
        family="sp-survey:waterproofing",
        question=(
            "What fraction of all Southpeak respondents name waterproofing as their main issue, "
            "and which gear is failing them?"
        ),
        analytics=[AG(SPSURV, [SHARE("top_pain_point", "waterproofing")])],
        evidence=[
            ROWS(SPSURV, [F("top_pain_point", "eq", "waterproofing")]),
        ],
        point=(
            "Rain pants leak at the seams near the knees, and boots stop being waterproof after "
            "one season."
        ),
        notes="Small share (9/300).",
    ),
    dict(
        id="A-MIX-08", ws=NS, category="mixed",
        family="ns-reviews:custom",
        question=(
            "How did Court Classic Custom reviews rate the shoe on average, and what did buyers "
            "say about the customization experience?"
        ),
        analytics=[
            AG(REVIEWS, [M("mean", "rating")], [F("product", "eq", "Court Classic Custom")]),
        ],
        evidence=[
            ROWS(REVIEWS, [F("product", "eq", "Court Classic Custom")]),
        ],
        point=(
            "The custom colorway matched the preview and heel initials were loved, but one order "
            "took 13 days and was nearly cancelled, and the extra cost is hard to justify."
        ),
        notes="Evidence includes RV-00655 (NS-148).",
    ),
    dict(
        id="A-MIX-09", ws=NS, category="mixed",
        converted_from="R0-048",
        family="ns-kr2-durability",
        question=(
            "Size the Knit Runner 2 knit-upper problem three ways: Q3 2026 durability returns from"
            " the returns table, Q3 complaint tickets, and the Q2 dollar hit."
        ),
        analytics=[
            AG(
                RET,
                [M("sum", "returns_count")],
                [
                    F("product_name", "eq", "Knit Runner 2"),
                    F("quarter", "eq", "2026-Q3"),
                    F("reason", "eq", "Durability - upper wear"),
                ],
            ),
        ],
        evidence=[
            DOC("NS-012"),
            DOC("NS-082"),
        ],
        point=(
            "1,140 support tickets about knit upper wear in Q3 (fraying near the toe flex point) "
            "and an estimated $3.1 million in Q2 returns and replacements."
        ),
        ledger={"NS-123": "answer"},
        notes=(
            "Converted from retrieval-v0 R0-048 (multi_tool: NS-012 retrieval, NS-123 analytics, "
            "NS-082 retrieval)."
        ),
    ),
    dict(
        id="A-MIX-10", ws=NS, category="mixed",
        converted_from="R0-050",
        family="ns-social-genz-conv",
        question=(
            "Two Social Shop numbers please: the Q2 FY26 sequential growth rate the review deck "
            "cites, and the Sep 2026 Gen Z conversion in the channel data."
        ),
        analytics=[
            FR(
                CHAN,
                [
                    F("channel", "eq", "Social Shop"),
                    F("segment", "eq", "Gen Z"),
                    F("month", "eq", "2026-09"),
                ],
                ["record_id", "conversion_rate_pct"],
                "conversion_rate_pct",
            ),
        ],
        evidence=[
            DOC("NS-085"),
        ],
        point=(
            "Social Shop sales grew 142% quarter over quarter in Q2 FY26, the fastest of any "
            "channel."
        ),
        ledger={"NS-140": "answer"},
        notes=(
            "Converted from retrieval-v0 R0-050 (multi_tool: NS-085 retrieval, NS-140 analytics)."
        ),
    ),
    # row_lookup --------------------------------------------------------------------------------
    dict(
        id="A-LKP-01", ws=NS, category="row_lookup",
        converted_from="R0-009",
        family="ns-social-genz-conv",
        question=(
            "In the monthly channel-by-segment data, what conversion did Gen Z shoppers post on "
            "Social Shop in Sep 2026?"
        ),
        analytics=[
            FR(
                CHAN,
                [
                    F("channel", "eq", "Social Shop"),
                    F("segment", "eq", "Gen Z"),
                    F("month", "eq", "2026-09"),
                ],
                ["record_id", "conversion_rate_pct"],
                "conversion_rate_pct",
            ),
        ],
        ledger={"NS-140": "answer"},
        notes="Converted from retrieval-v0 R0-009 (analytics: child-less numeric row).",
    ),
    dict(
        id="A-LKP-02", ws=NS, category="row_lookup",
        converted_from="R0-010",
        family="ns-channel:returns",
        question=(
            "Look up August 2026's Gen Z return rate for the brand site in the channel performance"
            " file."
        ),
        analytics=[
            FR(
                CHAN,
                [
                    F("channel", "eq", "Brand Site"),
                    F("segment", "eq", "Gen Z"),
                    F("month", "eq", "2026-08"),
                ],
                ["record_id", "return_rate_pct"],
                "return_rate_pct",
            ),
        ],
        ledger={"NS-142": "answer"},
        notes="Converted from retrieval-v0 R0-010.",
    ),
    dict(
        id="A-LKP-03", ws=NS, category="row_lookup",
        converted_from="R0-015",
        family="ns-catmonthly:margin",
        question=(
            "Pull the Aug 2026 margin percentage for the running shoe category from the "
            "category-by-month tab."
        ),
        analytics=[
            FR(
                CATM,
                [F("category", "eq", "Running Footwear"), F("month", "eq", "2026-08")],
                ["record_id", "gross_margin_pct"],
                "gross_margin_pct",
            ),
        ],
        ledger={"NS-122": "answer"},
        notes="Converted from retrieval-v0 R0-015.",
    ),
    dict(
        id="A-LKP-04", ws=SP, category="row_lookup",
        converted_from="R0-017",
        family="sp-channel:conversion",
        question=(
            "What did the Southpeak channel table show for marketplace conversion in Sep 2026?"
        ),
        analytics=[
            FR(
                SPCH,
                [F("channel", "eq", "Marketplace"), F("month", "eq", "2026-09")],
                ["record_id", "conversion_rate_pct"],
                "conversion_rate_pct",
            ),
        ],
        ledger={"SP-C06": "answer"},
        notes=(
            "Converted from retrieval-v0 R0-017. SP-C06 is a Southpeak canary: correct here, must "
            "never surface in NORTHSTAR (see A-INV-04)."
        ),
    ),
    dict(
        id="A-LKP-05", ws=NS, category="row_lookup",
        converted_from="R0-024",
        family="ns-sku:knit-runner-returns",
        question=(
            "What percentage of NS-KR2 units come back, according to the SKU performance sheet?"
        ),
        analytics=[
            FR(
                SKU,
                [F("sku", "eq", "NS-KR2")],
                ["sku", "product_name", "return_rate_pct"],
                "return_rate_pct",
            ),
        ],
        ledger={"NS-120": "answer"},
        notes="Converted from retrieval-v0 R0-024. Filters on an identifier-role column (sku).",
    ),
    dict(
        id="A-LKP-06", ws=NS, category="row_lookup",
        family="ns-sizing:value",
        question=(
            "In the Cobalt category sizing sheet, how many billions of dollars are estimated for "
            "US Gen Z footwear spending this year (2026)?"
        ),
        analytics=[
            FR(
                SIZE,
                [
                    F("generation", "eq", "Gen Z"),
                    F("category", "eq", "Athletic footwear"),
                    F("year", "eq", 2026),
                ],
                ["record_id", "value_usd_bn"],
                "value_usd_bn",
            ),
        ],
        ledger={"NS-129": "answer"},
        notes=(
            "Value is in USD billions (column value_usd_bn). `category` is a text-profiled column."
        ),
    ),
    dict(
        id="A-LKP-07", ws=NS, category="row_lookup",
        family="ns-fin:pnl-margin",
        question=(
            "What gross margin percentage does the FY26 latest estimate show in the P&L summary?"
        ),
        analytics=[
            FR(PNL, [F("line_item", "eq", "Gross margin %")], ["line_item", "fy26_le"], "fy26_le"),
        ],
        ledger={"NS-126": "answer"},
        notes=(
            "Confidential dataset. fy26_le has mixed units per line (USD m / percent); the row's "
            "unit column says percent."
        ),
    ),
    dict(
        id="A-LKP-08", ws=NS, category="row_lookup",
        family="ns-channel:aov",
        question=(
            "In September 2026, what was the average order value for Gen Z customers ordering "
            "through the app?"
        ),
        analytics=[
            FR(
                CHAN,
                [
                    F("channel", "eq", "App"),
                    F("segment", "eq", "Gen Z"),
                    F("month", "eq", "2026-09"),
                ],
                ["record_id", "aov_usd"],
                "aov_usd",
            ),
        ],
        ledger={"NS-141": "answer"},
        notes="Single-row lookup.",
    ),
    dict(
        id="A-LKP-09", ws=NS, category="row_lookup",
        family="ns-fin:segment-share",
        question=(
            "What share of FY25 net revenue does finance attribute to the Gen Z (18-27) segment?"
        ),
        analytics=[
            FR(
                SEGREV,
                [F("segment", "eq", "Gen Z (18-27)")],
                ["segment", "fy25_share_pct"],
                "fy25_share_pct",
            ),
        ],
        ledger={"NS-127": "answer"},
        notes=(
            "Confidential dataset. Ledger contradiction: the brand team's 16-29 definition gives "
            "21%; the finance table says 19.4%."
        ),
    ),
]
# fmt: on


# --- build ---------------------------------------------------------------------------------------

PREFIX = {
    "exact_count": "CNT",
    "percentage_share": "SHR",
    "average": "AVG",
    "median_min_max": "MMM",
    "grouped_comparison": "GRP",
    "filtered_aggregation": "FLT",
    "segment_compare": "CMP",
    "top_bottom": "TOP",
    "null_missing": "NUL",
    "no_result": "NOR",
    "invalid_request": "INV",
    "retrieval_only": "RET",
    "mixed": "MIX",
    "row_lookup": "LKP",
}
TASK_TYPE = {"retrieval_only": "retrieval", "mixed": "mixed"}

_STOPWORDS_TEXT = (
    "a an and are as at be by did do does for from had has have how in is it its of on or "
    "our s so than that the their there these this to was were what when where which who why "
    "with would you your i me my we us they them"
)
STOPWORDS = frozenset(_STOPWORDS_TEXT.split())
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")


def tokens(text: str, *, content: bool) -> frozenset[str]:
    toks = _TOKEN.findall(text.lower().replace("'", ""))
    return frozenset(t for t in toks if not (content and t in STOPWORDS))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def seed_sha256() -> str:
    """Hash of every seed table file the golds are computed from."""
    files = sorted({rel for _, rel, *_ in DATASETS.values()})
    return sha256_bytes(
        canonical_json([(f, sha256_bytes((SEED / f).read_bytes())) for f in files]).encode()
    )


def references() -> list[tuple[str, str, str]]:
    refs = [
        (i["id"], i["question"], f"retrieval-v0 {i['split']}")
        for i in json.loads(FROZEN.read_text())["items"]
    ]
    refs += [
        (i["id"], i["question"], "grounded-v0")
        for i in json.loads(GROUNDED_V0.read_text())["items"]
    ]
    refs += [
        (i["id"], i["question"], "research-v0")
        for i in json.loads(RESEARCH_V0.read_text())["items"]
    ]
    return refs


def doc_fact_handles() -> dict[str, list[str]]:
    """fact_id -> gold handles: research-v0 reviewed handles, else retrieval-v0 frozen gold."""
    out: dict[str, list[str]] = {}
    for item in json.loads(FROZEN.read_text())["items"]:
        for rf in item["required_facts"]:
            out[rf["fact_id"]] = list(rf["satisfied_by"]) + list(rf.get("also_satisfied_by", []))
    for item in json.loads(RESEARCH_V0.read_text())["items"]:
        for g in item["gold_facts"]:
            out[g["fact_id"]] = list(g["handles"])
    return out


def load_tables() -> dict[str, Table]:
    return {key: Table(key) for key in DATASETS}


def _value_entry(group: dict[str, Any], m: dict[str, Any]) -> dict[str, Any]:
    out = {
        "group": group,
        "metric": m["key"],
        "value": m["value"],
        "exact": m["exact"],
        "unit": m["unit"],
        "rounding": m["rule"],
        "denominator": m["denominator"],
    }
    if "numerator" in m:
        out["numerator"] = m["numerator"]
    return out


def compute_gold(ws: str, call: dict[str, Any], tables: dict[str, Table]) -> dict[str, Any]:
    spec = call["spec"]
    table = tables[dataset_key(ws, spec["dataset"])]
    result = RUNNERS[call["tool"]](table, spec)
    _, _, _, title, conf, _ = DATASETS[table.key]
    gold: dict[str, Any] = {
        "tool": call["tool"],
        "dataset": spec["dataset"],
        "dataset_title": title,
        "source_confidentiality": conf,
        "spec": spec,
        "rows_scanned": result["rows_scanned"],
        "rows_matched": result["rows_matched"],
        "warnings": result["warnings"],
        "rounding": ROUNDING_TEXT,
    }
    if call["tool"] == "filter_rows":
        col = call["answer_column"]
        gold["answer_kind"] = "lookup"
        gold["values"] = [
            {
                "group": r["group"],
                "metric": col,
                "value": r["group"][col],
                "exact": _exact_str(Decimal(r["raw"][col])) if r["raw"][col] else None,
                "unit": column_unit(col),
                "rounding": "exact",
                "denominator": result["rows_matched"],
                "handle": r["handle"],
            }
            for r in result["rows"]
        ]
        return gold
    gold["values"] = [_value_entry(r["group"], m) for r in result["rows"] for m in r["metrics"]]
    if call["tool"] == "group_compare":
        gold["answer_kind"] = "compare"
        gold["difference"] = result["difference"]
    elif spec.get("group_by"):
        gold["answer_kind"] = "top_n" if spec.get("limit") else "breakdown"
    else:
        gold["answer_kind"] = "scalar"
    return gold


def evidence_gold(
    ws: str, ev: dict[str, Any], tables: dict[str, Table], docs: dict[str, list[str]]
) -> dict[str, Any]:
    if "facts" in ev:
        (fid,) = ev["facts"]
        return {"kind": "document", "fact_id": fid, "handles": docs[fid]}
    table = tables[dataset_key(ws, ev["rows"])]
    text_col = "verbatim" if "verbatim" in table.header else "review_text"
    key_col = DATASETS[table.key][5]
    picked = [
        i
        for i in select(table, ev["filters"])
        if not ev["keywords"] or any(k in table.rows[i][text_col].lower() for k in ev["keywords"])
    ]
    return {
        "kind": "rows",
        "dataset": ev["rows"],
        "selection": {"filters": ev["filters"], "text_keywords_any": list(ev["keywords"])},
        "handles": [table.handle(i) for i in picked],
        "row_keys": [table.rows[i][key_col] for i in picked],
    }


def _ledger_value(gold: list[dict[str, Any]], selector: str) -> Any:
    values = gold[0]["values"]
    return values[{"answer": 0, "a": 0, "b": 1}[selector]]["value"]


def build_items(tables: dict[str, Table]) -> list[dict[str, Any]]:
    ledger = {f["fact_id"]: f for f in json.loads(LEDGER.read_text())["facts"]}
    docs = doc_fact_handles()
    items = []
    for spec in ITEMS:
        ws, cat = spec["ws"], spec["category"]
        task_type = TASK_TYPE.get(cat, "analytics")
        expect = spec.get("expect") or {"no_result": "no_result"}.get(cat, "answer")
        gold_analytics = [compute_gold(ws, c, tables) for c in spec.get("analytics", [])]
        evidence = [evidence_gold(ws, e, tables, docs) for e in spec.get("evidence", [])]
        confs = sorted(
            {g["source_confidentiality"] for g in gold_analytics}, key=lambda c: CONF_RANK[c]
        )
        top_conf = confs[-1] if confs else None
        checks = []
        for fid, selector in spec.get("ledger", {}).items():
            computed = _ledger_value(gold_analytics, selector)
            checks.append(
                {
                    "fact_id": fid,
                    "selector": selector,
                    "ledger_value": ledger[fid]["value"],
                    "computed_value": computed,
                    "match": Decimal(str(ledger[fid]["value"])) == Decimal(str(computed)),
                }
            )
        provenance = "hand_written:analytics-v0"
        if spec.get("converted_from"):
            provenance = f"converted:retrieval-v0:{spec['converted_from']}"
        items.append(
            {
                "id": spec["id"],
                "workspace": ws,
                "task_type": task_type,
                "category": cat,
                "question": spec["question"],
                "expect": expect,
                "gold": {
                    "analytics": gold_analytics,
                    "evidence": evidence,
                    "expected_point": spec.get("point"),
                },
                "router_expectation": task_type,
                "family": spec["family"],
                "notes": spec["notes"],
                "provenance": provenance,
                "converted_from": spec.get("converted_from"),
                "invalid_reason": spec.get("invalid_reason"),
                "canary_must_not_appear": spec.get("canary"),
                "max_conf": None
                if top_conf is None
                else {
                    "dataset_confidentiality": top_conf,
                    "workspace_llm_max_confidentiality": LLM_MAX_CONFIDENTIALITY[ws],
                    "allowed": CONF_RANK[top_conf] <= CONF_RANK[LLM_MAX_CONFIDENTIALITY[ws]],
                },
                "ledger_crosscheck": checks,
            }
        )
    return items


def add_leakage(items: list[dict[str, Any]], refs: list[tuple[str, str, str]]) -> None:
    for item in items:
        best = {"all": (0.0, "", ""), "content": (0.0, "", "")}
        for mode in best:
            q = tokens(item["question"], content=mode == "content")
            for ref_id, ref_q, origin in refs:
                score = jaccard(q, tokens(ref_q, content=mode == "content"))
                if score > best[mode][0]:
                    best[mode] = (score, ref_id, origin)
        item["leakage"] = {
            "max_jaccard_all_tokens": round(best["all"][0], 3),
            "nearest_all_tokens": f"{best['all'][1]} ({best['all'][2]})",
            "max_jaccard_content_tokens": round(best["content"][0], 3),
            "nearest_content_tokens": f"{best['content'][1]} ({best['content'][2]})",
        }


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def assign_splits(items: list[dict[str, Any]]) -> None:
    """Union items sharing a question family (dataset + family), a ledger fact or an evidence
    handle; whole groups go to dev (~40%) or holdout by a greedy, category-stratified pass in
    an order fixed by sha256(seed:group), then deterministic single-group flips."""
    uf = _UnionFind()
    for item in items:
        node = f"item:{item['id']}"
        uf.union(node, f"family:{item['family']}")
        for c in item["ledger_crosscheck"]:
            uf.union(node, f"fact:{c['fact_id']}")
        for ev in item["gold"]["evidence"]:
            if ev.get("fact_id"):
                uf.union(node, f"fact:{ev['fact_id']}")
            for h in ev["handles"]:
                uf.union(node, f"handle:{h}")
    members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        members[uf.find(f"item:{item['id']}")].append(item)
    groups = {f"G-{min(i['id'] for i in m)}": m for m in members.values()}
    order = sorted(
        groups, key=lambda g: (-len(groups[g]), sha256_bytes(f"{SPLIT_SEED}:{g}".encode()))
    )
    totals = Counter(i["category"] for i in items)
    tt_totals = Counter(i["task_type"] for i in items)

    def cost(counts: Counter[str]) -> float:
        per_cat = sum((counts[c] - DEV_FRACTION * n) ** 2 for c, n in totals.items())
        per_tt = sum((counts[f"tt:{t}"] - DEV_FRACTION * n) ** 2 for t, n in tt_totals.items())
        n_dev = sum(v for k, v in counts.items() if not k.startswith("tt:"))
        return per_cat + per_tt + (n_dev - DEV_FRACTION * len(items)) ** 2

    cats = {
        name: Counter(i["category"] for i in groups[name])
        + Counter(f"tt:{i['task_type']}" for i in groups[name])
        for name in order
    }
    dev: Counter[str] = Counter()
    in_dev: dict[str, bool] = {}
    for name in order:
        in_dev[name] = cost(dev + cats[name]) < cost(dev)
        if in_dev[name]:
            dev += cats[name]
    improved = True
    while improved:
        improved = False
        for name in order:
            flipped = dev - cats[name] if in_dev[name] else dev + cats[name]
            if cost(flipped) < cost(dev) - 1e-9:
                dev, in_dev[name], improved = flipped, not in_dev[name], True
    for name in order:
        for item in groups[name]:
            item["group"] = name
            item["split"] = "dev" if in_dev[name] else "holdout"


def holdout_sha256(items: list[dict[str, Any]]) -> str:
    holdout = sorted((i for i in items if i["split"] == "holdout"), key=lambda i: i["id"])
    return sha256_bytes(canonical_json(holdout).encode())


# --- validation ----------------------------------------------------------------------------------


def spec_columns(spec: dict[str, Any]) -> set[str]:
    cols: set[str] = set()
    for f in spec.get("filters") or []:
        cols.add(f["column"])
    metrics = list(spec.get("metrics") or []) + ([spec["metric"]] if "metric" in spec else [])
    for m in metrics:
        if m.get("column"):
            cols.add(m["column"])
        if m.get("condition"):
            cols.add(m["condition"]["column"])
    cols.update(spec.get("group_by") or [])
    cols.update(spec.get("columns") or [])
    for key in ("compare_column", "order_by"):
        if spec.get(key):
            cols.add(spec[key])
    return cols


def spec_filter_values(spec: dict[str, Any]) -> list[tuple[str, Any]]:
    """(column, value) pairs used against categorical levels (filters, share conditions,
    group_compare levels)."""
    preds = list(spec.get("filters") or [])
    metrics = list(spec.get("metrics") or []) + ([spec["metric"]] if "metric" in spec else [])
    preds += [m["condition"] for m in metrics if m.get("condition")]
    out = []
    for p in preds:
        if p["op"] in ("eq", "ne", "in", "not_in"):
            vals = p.get("values") if p.get("values") is not None else [p.get("value")]
            out += [(p["column"], v) for v in vals]
    if "compare_column" in spec:
        out += [
            (spec["compare_column"], spec["group_a"]),
            (spec["compare_column"], spec["group_b"]),
        ]
    return out


def _boundary_tie(table: Table, gold: dict[str, Any]) -> bool:
    spec = gold["spec"]
    limit = spec.get("limit")
    if not limit or not spec.get("group_by"):
        return False
    full = run_aggregate(table, {k: v for k, v in spec.items() if k != "limit"})["rows"]
    if len(full) <= limit:
        return False
    mi = spec["order"]["metric_index"]
    return bool(full[limit - 1]["metrics"][mi]["exact"] == full[limit]["metrics"][mi]["exact"])


def injection_handles(tables: dict[str, Table]) -> set[str]:
    out = set()
    for f in json.loads(LEDGER.read_text())["facts"]:
        a = f["anchor"]
        if f["category"] == "injection" and a["type"] == "row":
            for key, t in tables.items():
                if key.startswith(f"{f['workspace_code']}/{f['source_code']}:"):
                    out |= {
                        t.handle(i)
                        for i, r in enumerate(t.rows)
                        if r.get(a["key_column"]) == a["key_value"]
                    }
    return out


def validate(
    items: list[dict[str, Any]], tables: dict[str, Table], refs: list[tuple[str, str, str]]
) -> list[str]:
    problems: list[str] = []
    ids = [i["id"] for i in items]
    if len(ids) != len(set(ids)):
        problems.append("duplicate item ids")
    norm_q = [" ".join(sorted(tokens(i["question"], content=False))) for i in items]
    if len(norm_q) != len(set(norm_q)):
        problems.append("duplicate questions")
    ref_texts = {q.strip().lower() for _, q, _ in refs}
    injected = injection_handles(tables)
    task_types = json.loads(TASK_TYPES.read_text())["items"]
    must_convert = {k for k, v in task_types.items() if v["task_type"] != "retrieval"}
    converted = {i["converted_from"] for i in items if i["converted_from"]}
    if must_convert != converted:
        problems.append(f"retrieval-v0 conversions mismatch: missing {must_convert - converted}")
    for item in items:
        iid, ws, cat, tt = item["id"], item["workspace"], item["category"], item["task_type"]
        if not re.fullmatch(rf"A-{PREFIX[cat]}-\d\d", iid):
            problems.append(f"{iid}: id does not match category {cat}")
        if item["question"].strip().lower() in ref_texts:
            problems.append(f"{iid}: question copied from a reference dataset")
        lk = item["leakage"]
        if max(lk["max_jaccard_all_tokens"], lk["max_jaccard_content_tokens"]) > JACCARD_REJECT:
            problems.append(f"{iid}: leakage Jaccard above {JACCARD_REJECT}: {lk}")
        if item["router_expectation"] != tt:
            problems.append(f"{iid}: router_expectation != task_type")
        analytics, evidence = item["gold"]["analytics"], item["gold"]["evidence"]
        if cat == "invalid_request":
            if analytics or evidence or item["expect"] not in ("insufficient", "invalid"):
                problems.append(f"{iid}: invalid_request must have no gold and expect a refusal")
            if not item["invalid_reason"]:
                problems.append(f"{iid}: invalid_request without invalid_reason")
            continue
        if tt in ("analytics", "mixed") and not analytics:
            problems.append(f"{iid}: {tt} item without analytics gold")
        if tt in ("retrieval", "mixed") and (not evidence or not item["gold"]["expected_point"]):
            problems.append(f"{iid}: {tt} item without evidence gold / expected point")
        if tt == "retrieval" and analytics:
            problems.append(f"{iid}: retrieval item with analytics gold")
        for ev in evidence:
            if not ev["handles"]:
                problems.append(f"{iid}: empty evidence handle list")
            for h in ev["handles"]:
                if not h.startswith(f"{ws}/") or h in injected:
                    problems.append(f"{iid}: foreign or injection-carrier handle {h}")
        for g in analytics:
            key = dataset_key(ws, g["dataset"])
            if key not in tables:
                problems.append(f"{iid}: dataset {g['dataset']} not in {ws}")
                continue
            table = tables[key]
            missing = spec_columns(g["spec"]) - set(table.header)
            if missing:
                problems.append(f"{iid}: unknown columns {sorted(missing)}")
            for col, v in spec_filter_values(g["spec"]):
                if col not in table.numeric and str(v) not in {r[col] for r in table.rows}:
                    problems.append(f"{iid}: filter value {col}={v!r} is not a level")
            empty = "EMPTY_SELECTION" in g["warnings"]
            if item["expect"] == "no_result" and not empty:
                problems.append(f"{iid}: no_result item matched rows")
            if item["expect"] == "answer":
                if empty or any(v["value"] is None for v in g["values"]):
                    problems.append(f"{iid}: answerable item with empty/null result")
                if g["answer_kind"] == "lookup" and len(g["values"]) != 1:
                    problems.append(f"{iid}: lookup must match exactly one row")
                if g["answer_kind"] == "compare" and g["difference"]["value"] is None:
                    problems.append(f"{iid}: compare without a difference")
            if _boundary_tie(table, g):
                problems.append(f"{iid}: tie at the top-N boundary")
        if item["expect"] == "answer" and item["max_conf"] and not item["max_conf"]["allowed"]:
            problems.append(f"{iid}: answer expected from a dataset above llm_max_confidentiality")
        for c in item["ledger_crosscheck"]:
            if not c["match"]:
                problems.append(f"{iid}: ledger cross-check failed {c}")
    return problems


def summary_counts(items: list[dict[str, Any]]) -> dict[str, Any]:
    def by(field: str) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = defaultdict(lambda: {"dev": 0, "holdout": 0})
        for item in items:
            out[item[field]][item["split"]] += 1
        return {k: out[k] for k in sorted(out)}

    return {
        "items": len(items),
        "dev": sum(1 for i in items if i["split"] == "dev"),
        "holdout": sum(1 for i in items if i["split"] == "holdout"),
        "groups": len({i["group"] for i in items}),
        "by_task_type": by("task_type"),
        "by_category": by("category"),
        "by_workspace": by("workspace"),
        "expect": dict(sorted(Counter(i["expect"] for i in items).items())),
        "router_expectation": dict(sorted(Counter(i["router_expectation"] for i in items).items())),
    }


def build() -> tuple[dict[str, Any], str]:
    refs = references()
    items = build_items(load_tables())
    again = build_items(load_tables())  # independent second load + recompute
    if canonical_json(items) != canonical_json(again):
        raise SystemExit("gold recomputation is not deterministic")
    tables = load_tables()
    add_leakage(items, refs)
    assign_splits(items)
    problems = validate(items, tables, refs)
    if problems:
        raise SystemExit("validation failed:\n  " + "\n  ".join(problems))
    doc = {
        "dataset_version": DATASET_VERSION,
        "description": (
            "Phase 5 structured-analytics evaluation: retrieval-only, analytics-only and mixed "
            "questions. Gold numbers are computed from the seed CSV/XLSX files by an independent "
            "stdlib Decimal (ROUND_HALF_EVEN) reference implementation; gold specs follow the "
            "frozen analytics contract; gold evidence handles are row/document parents."
        ),
        "manifest": {
            "seed_tables_sha256": seed_sha256(),
            "ledger_sha256": sha256_bytes(LEDGER.read_bytes()),
            "retrieval_v0_frozen_sha256": sha256_bytes(FROZEN.read_bytes()),
            "research_v0_sha256": sha256_bytes(RESEARCH_V0.read_bytes()),
            "grounded_v0_sha256": sha256_bytes(GROUNDED_V0.read_bytes()),
            "split_seed": SPLIT_SEED,
            "dev_fraction_target": DEV_FRACTION,
            "jaccard_reject_threshold": JACCARD_REJECT,
            "rounding": ROUNDING_TEXT,
            "llm_max_confidentiality": LLM_MAX_CONFIDENTIALITY,
            "holdout_sha256": holdout_sha256(items),
            "counts": summary_counts(items),
        },
        "items": items,
    }
    return doc, render_readme(doc)


# --- README


def _fmt_answer(g: dict[str, Any]) -> str:
    if g["answer_kind"] == "compare":
        a, b, d = g["values"][0], g["values"][1], g["difference"]
        return f"{a['value']} vs {b['value']} (diff {d['value']})"
    if g["answer_kind"] == "breakdown":
        return f"{len(g['values'])} groups"
    v = g["values"][0] if g["values"] else None
    if v is None:
        return "no rows"
    label = "/".join(str(x) for x in v["group"].values()) if g["answer_kind"] == "top_n" else ""
    if g["answer_kind"] == "lookup":
        label = ""
    val = "null" if v["value"] is None else v["value"]
    extra = f" ({v['numerator']}/{v['denominator']})" if v.get("numerator") is not None else ""
    return f"{label + ': ' if label else ''}{val}{extra}"


def render_readme(doc: dict[str, Any]) -> str:
    items, m = doc["items"], doc["manifest"]
    counts = m["counts"]
    lines = [
        "# analytics-v0",
        "",
        "Phase 5 structured-analytics evaluation set: retrieval-only, analytics-only and mixed "
        "(quantitative + qualitative) questions over the fixed synthetic seed corpus. Built by "
        "`scripts/build_analytics_v0.py` (deterministic; `--check` diffs a rebuild against these "
        "files; `--verify-db` validates specs, the DB column profile, golds recomputed from "
        "`dataset_rows` and every evidence handle). Do not edit `items.json` by hand.",
        "",
        "All data is fictional. Questions and ids are new; the ten retrieval-v0 items that "
        "task-types.json classifies `analytics`/`multi_tool` (unreachable for retrieval) are "
        "converted here with new wording (`converted_from`, provenance "
        "`converted:retrieval-v0:<id>`).",
        "",
        "## How golds are computed",
        "",
        "- Directly from the seed files in `seed_data/generated/{northstar,southpeak}` by an "
        "**independent reference implementation inside the builder**: stdlib `csv` "
        "(`utf-8-sig`), XLSX via `zipfile` + `ElementTree` (no openpyxl, no pandas), "
        "`decimal.Decimal` arithmetic (28 digits) and `ROUND_HALF_EVEN`. The product analytics "
        "engine is never imported, and no LLM is involved.",
        "- XLSX numeric cells are IEEE doubles; they are read at Excel's 15-significant-digit "
        "display precision (`9.199999999999999` -> `9.2`), which is also what ingestion stores "
        "(checked by `--verify-db`).",
        "- Golds are computed twice from two fresh loads and must be identical (build fails "
        "otherwise). `--verify-db` recomputes every gold a third time from the ingested "
        "`dataset_rows` values and requires identical values, exacts, denominators and "
        "warnings.",
        "- Ledger cross-check: where `seed_data/fact_ledger.json` states the value "
        "(row anchors, plus the survey shares NS-004 and SP-C02 restated in documents), "
        "`ledger_crosscheck` records ledger vs computed value; any mismatch fails the build. "
        f"{sum(len(i['ledger_crosscheck']) for i in items)} checks across "
        f"{sum(1 for i in items if i['ledger_crosscheck'])} items, all matching.",
        "",
        "### Semantics and rounding (brief rules; interpretation recorded per value)",
        "",
        f"`{m['rounding']}`.",
        "",
        "- `share` = 100 x rows satisfying the condition / filtered rows with a non-null value "
        "in the condition column (`numerator`, `denominator`), 1 dp.",
        "- `count` counts filtered rows; `count_distinct` counts distinct non-null values; "
        "numeric metrics exclude empty cells (`NULLS_EXCLUDED`, reflected in `denominator`).",
        "- `mean`/`median` of a `_pct` column are treated as percent (1 dp); of currency "
        "(`_usd`, `_usd_m`, `_usd_bn`, `price_usd`) 2 dp; otherwise (nps, rating, "
        "price_sensitivity) 2 dp. **Interpretation choice:** if the engine rounds means of "
        "percent columns to 2 dp, compare on `exact`. Affected items: "
        + ", ".join(
            f"`{i['id']}`"
            for i in items
            if any(
                v["unit"] == "percent" and v["metric"].startswith(("mean(", "median("))
                for g in i["gold"]["analytics"]
                for v in g["values"]
            )
        )
        + ".",
        "- `sum` of integer values and `min`/`max` are exact; median over an even base = mean "
        "of the two middle values.",
        "- `group_compare` difference = A - B computed on the exact values, then rounded with "
        "the metric's rule.",
        "- Empty selection: `count` = 0, other metrics null; `EMPTY_SELECTION` always, plus "
        "`ZERO_DENOMINATOR` for share/mean/median.",
        "- `filter_rows` lookups return the raw cell (`exact`) and the row handle.",
        "",
        "## Schema",
        "",
        "`id, workspace, task_type (retrieval|analytics|mixed), category, question, expect "
        "(answer|insufficient|no_result|invalid), gold{analytics[], evidence[], "
        "expected_point}, router_expectation, family, group, split, notes, provenance, "
        "converted_from, invalid_reason, canary_must_not_appear, max_conf, ledger_crosscheck, "
        "leakage`.",
        "",
        "- `gold.analytics[]`: `tool` (aggregate|group_compare|filter_rows), `dataset` "
        "(`<SOURCE_CODE>:<sheet_ordinal>`, scoped by `workspace`), `spec` (a valid "
        "`AggregateIn`/`GroupCompareIn`/`FilterRowsIn` dict - one acceptable spec, not the only "
        "one), `answer_kind` (scalar|top_n|breakdown|compare|lookup), `values[]` (`group`, "
        "`metric`, `value` rounded, `exact`, `unit`, `rounding`, `denominator`, `numerator` for "
        "shares, `handle` for lookups), `difference` (compare), `rows_matched`, "
        "`rows_scanned`, `warnings`.",
        "- `gold.evidence[]`: `kind: rows` (survey/review row parents selected by filters and "
        "optional keywords - any-of handles, `row_keys` gives respondent/review ids) or "
        "`kind: document` (ledger fact with research-v0 / retrieval-v0 reviewed handles, "
        "any-of). Every listed evidence entry is required; `expected_point` is the "
        "qualitative claim the answer should make.",
        "- `max_conf`: highest source confidentiality among the item's datasets vs the "
        "workspace's `llm_max_confidentiality` (DB: "
        + ", ".join(f"{k} = `{v}`" for k, v in m["llm_max_confidentiality"].items())
        + "). Confidential FIN-SUMMARY-FY26 items therefore expect an answer; if a workspace is "
        "lowered below `confidential`, those items must flip to `insufficient`.",
        "",
        "## Counts",
        "",
        "| category | task_type | dev | holdout | total |",
        "|---|---|---|---|---|",
    ]
    tt_of = {i["category"]: i["task_type"] for i in items}
    ws_totals = {k: v["dev"] + v["holdout"] for k, v in counts["by_workspace"].items()}
    for cat, c in counts["by_category"].items():
        lines.append(
            f"| {cat} | {tt_of[cat]} | {c['dev']} | {c['holdout']} | {c['dev'] + c['holdout']} |"
        )
    lines.append(f"| **all** | | {counts['dev']} | {counts['holdout']} | {counts['items']} |")
    lines += [
        "",
        "| task_type | dev | holdout |",
        "|---|---|---|",
        *[f"| {k} | {v['dev']} | {v['holdout']} |" for k, v in counts["by_task_type"].items()],
        "",
        f"Workspaces: {ws_totals}. "
        f"Expect: {counts['expect']}. Router expectation: {counts['router_expectation']}.",
        "",
        "## Data notes",
        "",
        "- Columns with empty cells (checked over every seed table): "
        "`CATEGORY-SIZING:1.yoy_growth_pct` (9 of 54, base years) and "
        "`FIN-SUMMARY-FY26:1.yoy_change_pct` (3 of 10, percent lines; confidential). "
        "No other seed column has empties, so `null_missing` items use these two.",
        "- `CATEGORY-SIZING:1.category` is profiled as `text` (free_text, 3 distinct values); "
        "items filtering on it (`A-NUL-01`, `A-LKP-06`) need eq on text columns.",
        "- `no_result` items use valid levels/ranges whose intersection is empty (so the "
        "expected outcome is `EMPTY_SELECTION`, not a validation error).",
        "- `invalid_request`: `unknown_column` and `dataset_not_in_workspace` expect "
        "`insufficient`; `unsupported_computation` (correlation, forecast, standard deviation) "
        "expects `invalid` (a safe refusal; the model must not compute it itself). "
        "`A-INV-04` asks NORTHSTAR for Southpeak's channel data: the SOUTHPEAK canary SP-C06 "
        "must not appear.",
        "",
        "## Converted retrieval-v0 items",
        "",
        "| retrieval-v0 | type | analytics-v0 | gold |",
        "|---|---|---|---|",
    ]
    tt = json.loads(TASK_TYPES.read_text())["items"]
    for i in sorted((i for i in items if i["converted_from"]), key=lambda i: i["converted_from"]):
        lines.append(
            f"| {i['converted_from']} | {tt[i['converted_from']]['task_type']} | {i['id']} | "
            f"{_fmt_answer(i['gold']['analytics'][0])} |"
        )
    lines += [
        "",
        "## Split",
        "",
        f"{counts['groups']} groups. Items are union-found when they share a question family "
        "(dataset + family label), a ledger fact or an evidence handle; whole groups go to "
        f"dev (~{int(DEV_FRACTION * 100)}%) or holdout by a greedy pass (largest first, ties by "
        f"sha256(`{SPLIT_SEED}`:group)) followed by deterministic single-group flips that "
        "reduce the squared deviation per category, per task_type and overall.",
        "",
        f"Holdout hash (sha256 of the canonical JSON of the holdout items, sorted by id): "
        f"`{m['holdout_sha256']}`.",
        "",
        "## Leakage",
        "",
        "Each question is compared with every retrieval-v0 (frozen, dev and test), grounded-v0 "
        "and research-v0 question by normalized-token Jaccard (all tokens, and content tokens "
        f"without stopwords); the build fails above {JACCARD_REJECT}. Exact copies and "
        "duplicate questions also fail.",
        "",
        "| item | split | answer | max J (all) | nearest | max J (content) | nearest |",
        "|---|---|---|---|---|---|---|",
    ]
    for i in items:
        lk = i["leakage"]
        ans = (
            "; ".join(_fmt_answer(g) for g in i["gold"]["analytics"])
            if i["gold"]["analytics"]
            else i["expect"]
        )
        lines.append(
            f"| {i['id']} | {i['split']} | {ans} | {lk['max_jaccard_all_tokens']:.3f} | "
            f"{lk['nearest_all_tokens']} | {lk['max_jaccard_content_tokens']:.3f} | "
            f"{lk['nearest_content_tokens']} |"
        )
    worst = max(
        items,
        key=lambda i: max(
            i["leakage"]["max_jaccard_all_tokens"], i["leakage"]["max_jaccard_content_tokens"]
        ),
    )
    worst_j = max(
        worst["leakage"]["max_jaccard_all_tokens"], worst["leakage"]["max_jaccard_content_tokens"]
    )
    lines += [
        "",
        f"Highest similarity: {worst['id']} ({worst_j:.3f}).",
        "",
        "## Caveats",
        "",
        "- A gold `spec` is one valid way to compute the answer; graders should compare "
        "values (and `exact` within rounding), not spec equality. Lookups are expressed with "
        "`filter_rows`; an `aggregate` max/min over the same filters is equally valid.",
        "- Mixed items' row evidence is any-of over all matching rows; `expected_point` "
        "paraphrases the recurring verbatim themes and was written by reading those rows.",
        "- `router_expectation` is judged from the question text alone.",
        "- Single author; no second reviewer for questions or expected points.",
        "",
    ]
    return "\n".join(lines)


# --- DB verification (backend venv)

_PROFILE_SQL = """
SELECT s.source_code, t.sheet_ordinal, t.name, t.columns, t.row_count, v.confidentiality, t.id
FROM dataset_tables t
JOIN source_versions v ON v.id = t.source_version_id
JOIN sources s ON s.id = v.source_id
WHERE s.deleted_at IS NULL AND s.current_version_id = v.id
"""


def _db_raw(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def verify_db(doc: dict[str, Any]) -> list[str]:
    import asyncio

    import psycopg

    from marketsignal.config import Settings
    from marketsignal.tools.analytics_contracts import ANALYTICS_INPUT_MODELS

    problems: list[str] = []
    # 1. every gold spec validates against the frozen contract
    n_specs = 0
    for item in doc["items"]:
        for g in item["gold"]["analytics"]:
            n_specs += 1
            try:
                ANALYTICS_INPUT_MODELS[g["tool"]].model_validate(g["spec"])
            except Exception as exc:  # every failure is a finding
                problems.append(f"{item['id']}: spec invalid for {g['tool']}: {exc}")
    print(f"validated {n_specs} specs against the frozen contract")
    settings = Settings()
    dsn = settings.migrations_database_url.get_secret_value().replace("+psycopg", "")
    profiles: dict[str, dict[str, Any]] = {}
    db_tables: dict[str, Table] = {}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, code, llm_max_confidentiality FROM workspaces WHERE code = ANY(%s)",
            (list(LLM_MAX_CONFIDENTIALITY),),
        )
        workspaces = {code: (wid, mc) for wid, code, mc in cur.fetchall()}
        for code, (wid, max_conf) in sorted(workspaces.items()):
            if max_conf != LLM_MAX_CONFIDENTIALITY[code]:
                problems.append(f"{code}: llm_max_confidentiality is {max_conf}")
            with conn.transaction():
                cur.execute("SELECT set_config('app.workspace_id', %s, true)", (str(wid),))
                cur.execute(_PROFILE_SQL)
                for src, ordinal, name, columns, row_count, conf, table_id in cur.fetchall():
                    key = f"{code}/{src}:{ordinal}"
                    profiles[key] = {
                        "name": name,
                        "columns": columns,
                        "rows": row_count,
                        "conf": conf,
                    }
                    if key not in DATASETS:
                        continue
                    cur.execute(
                        "SELECT row_number, values FROM dataset_rows WHERE table_id = %s "
                        "ORDER BY row_number",
                        (table_id,),
                    )
                    rows = cur.fetchall()
                    header = [c["name"] for c in columns]
                    if [r[0] for r in rows] != list(range(2, len(rows) + 2)):
                        problems.append(f"{key}: non-contiguous row numbers")
                    raw = [header] + [[_db_raw(r[1].get(h)) for h in header] for r in rows]
                    db_tables[key] = Table(key, raw)
    files = load_tables()
    # 2. dataset ids, names, confidentiality, columns, types, levels, row counts
    for key, (_, _, _, title, conf, _) in DATASETS.items():
        prof = profiles.get(key)
        if prof is None:
            problems.append(f"{key}: dataset missing from the DB profile")
            continue
        if prof["name"] != title or prof["conf"] != conf or prof["rows"] != len(files[key].rows):
            problems.append(f"{key}: profile mismatch {prof['name']}/{prof['conf']}/{prof['rows']}")
        cols = {c["name"]: c for c in prof["columns"]}
        if list(cols) != files[key].header:
            problems.append(f"{key}: column order/names differ from the seed file")
        for name, c in cols.items():
            if (c["type"] == "numeric") != (name in files[key].numeric):
                problems.append(f"{key}.{name}: profile type {c['type']} vs file inference")
            if c["non_empty"] != sum(1 for r in files[key].rows if r[name] != ""):
                problems.append(f"{key}.{name}: non_empty differs")
    for item in doc["items"]:
        ws = item["workspace"]
        for g in item["gold"]["analytics"]:
            key = dataset_key(ws, g["dataset"])
            prof = profiles.get(key)
            if prof is None:
                problems.append(f"{item['id']}: {g['dataset']} not visible in {ws}")
                continue
            cols = {c["name"]: c for c in prof["columns"]}
            for col in spec_columns(g["spec"]):
                if col not in cols:
                    problems.append(f"{item['id']}: column {col} not in the profile")
            for col, v in spec_filter_values(g["spec"]):
                c = cols.get(col, {})
                complete = c.get("type") == "categorical" and len(c["levels"]) >= c["distinct"]
                if complete and str(v) not in c["levels"]:
                    problems.append(f"{item['id']}: {col}={v!r} not a profiled level")
            # 3. recompute from ingested rows
            call = {"tool": g["tool"], "spec": g["spec"]}
            if g["tool"] == "filter_rows":
                call["answer_column"] = g["values"][0]["metric"] if g["values"] else ""
            try:
                fresh = compute_gold(ws, call, db_tables)
            except (Exception, SystemExit) as exc:  # every failure is a finding
                problems.append(f"{item['id']}: DB recompute failed ({exc!r})")
                continue
            for field in ("values", "difference", "warnings", "rows_matched", "rows_scanned"):
                if canonical_json(fresh.get(field)) != canonical_json(g.get(field)):
                    problems.append(f"{item['id']}: DB recompute differs on {field}")
        if item["invalid_reason"] == "dataset_not_in_workspace" and any(
            k.startswith(f"{ws}/CHANNEL-DATA:") for k in profiles
        ):
            problems.append(f"{item['id']}: CHANNEL-DATA unexpectedly visible in {ws}")
    print(f"checked {len(profiles)} profiled datasets, recomputed golds from dataset_rows")
    # 4. evidence handles resolve and carry their content
    problems += asyncio.run(_verify_handles(doc, files))
    return problems


async def _verify_handles(doc: dict[str, Any], files: dict[str, Table]) -> list[str]:
    from marketsignal.config import Settings
    from marketsignal.db.engine import create_engine, create_session_factory
    from marketsignal.db.session import scoped_session
    from marketsignal.evaluation.gold import load_workspace, locate, parent_contains_anchor
    from marketsignal.evidence.resolver import resolve_evidence

    facts = {f["fact_id"]: f for f in json.loads(LEDGER.read_text())["facts"]}
    problems: list[str] = []
    engine = create_engine(Settings())
    checked = 0
    try:
        factory = create_session_factory(engine)
        workspaces = {c: await load_workspace(factory, c) for c in LLM_MAX_CONFIDENTIALITY}
        for item in doc["items"]:
            ws = workspaces[item["workspace"]]
            for ev in item["gold"]["evidence"]:
                anchors = (
                    set(locate(facts[ev["fact_id"]], ws)) if ev["kind"] == "document" else set()
                )
                if ev["kind"] == "document" and not anchors & set(ev["handles"]):
                    problems.append(f"{item['id']}: no handle holds the {ev['fact_id']} anchor")
                keys = ev.get("row_keys") or [None] * len(ev["handles"])
                for h, key in zip(ev["handles"], keys, strict=True):
                    checked += 1
                    if h not in ws.parents:
                        problems.append(f"{item['id']}: {h} is not an active parent")
                        continue
                    async with scoped_session(factory, ws.scope) as session:
                        try:
                            body = (await resolve_evidence(session, ws.scope, h)).as_dict()
                        except Exception as exc:  # every failure is a finding
                            problems.append(f"{item['id']}: {h} does not resolve ({exc!r})")
                            continue
                    if key is not None:
                        key_col = DATASETS[dataset_key(item["workspace"], ev["dataset"])][5]
                        if f"{key_col}: {key};" not in body["text"]:
                            problems.append(f"{item['id']}: {h} is not row {key}")
                    elif h in anchors and not parent_contains_anchor(
                        facts[ev["fact_id"]], body["text"]
                    ):
                        problems.append(f"{item['id']}: {h} lacks the anchor")
            for g in item["gold"]["analytics"]:
                for v in g["values"]:
                    if "handle" in v and v["handle"] not in ws.parents:
                        problems.append(f"{item['id']}: lookup row {v['handle']} not active")
        print(f"resolved {checked} evidence handles")
    finally:
        await engine.dispose()
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--check", action="store_true", help="diff a rebuild against files")
    parser.add_argument("--verify-db", action="store_true", help="verify against the seeded DB")
    args = parser.parse_args()
    doc, readme = build()
    payload = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if args.verify_db:
        problems = verify_db(doc)
        if problems:
            print("DB verification failed:\n  " + "\n  ".join(problems))
            return 1
        print("DB verification ok")
        return 0
    if args.check:
        same = ITEMS_OUT.read_text() == payload and README_OUT.read_text() == readme
        print("up to date" if same else "OUT OF DATE: re-run scripts/build_analytics_v0.py")
        return 0 if same else 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ITEMS_OUT.write_text(payload)
    README_OUT.write_text(readme)
    print(json.dumps(doc["manifest"]["counts"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
