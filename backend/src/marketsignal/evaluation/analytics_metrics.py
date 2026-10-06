"""Pure metric functions of the analytics evaluation (Phase 5; no DB, no HTTP).

Inputs are what the production path stored: persisted :class:`AnalyticsResult` dicts
(``analytics_results.result``), the run record (route, agent trace, usage, timings) and the
stored canonical answer (``[[HANDLE]]`` evidence and ``[[result:<uuid>]]`` result markers).
Golds come from ``eval/datasets/analytics-v0/items.json`` (``gold.analytics[].values``).

Definitions (exact):
* **cell** - one computed number of a result: every ``rows[].metrics[]`` entry of an
  aggregate/group_compare result, its ``difference`` (group ``{"__difference__": true}``), and
  every non-reserved column cell of a ``filter_rows`` row (metric = column name).
* **gold value match** - a cell of a result on the gold dataset whose metric agrees (same
  ``fn``; same column unless ``share``; filter_rows: same column), whose group agrees with the
  gold group (every shared key equal after canonicalisation; when both groups are non-empty
  they must share a key; the difference only matches the gold difference) and whose ``exact``
  equals the gold ``exact`` or whose rounded ``value`` equals the gold ``value`` (Decimal
  equality; a null gold value matches a null cell).
* **spec components** (best result on the gold dataset, ranked by components correct):
  aggregation = gold metrics (fn, column; share: fn + normalized condition) are a subset of the
  result's; grouping = aggregate ``group_by`` set equality / group_compare ``compare_column``
  + unordered ``{group_a, group_b}``; filter = normalized filter set equality, each filter
  ``(column, op, {canonical operands})`` with single-operand ``in``/``not_in`` read as
  ``eq``/``ne``. filter_rows has no aggregation/grouping component (None).
* **stated** - a non-temporal number in the answer (thousands separators, ``%`` and currency
  tolerated) equal to the gold rounded value, or equal to the gold exact rounded half-even to
  the number's own decimals when those are at least the gold rounding's decimals;
  **approximately stated** - additionally any coarser half-even rounding of the exact.
  allowed-rounding rate = stated / approximately stated.
* **provenance** - a stated gold value whose stating unit cites a ``[[result:…]]`` result that
  itself matches the gold value.
* **unsupported computed claim** - a unit citing ``[[result:…]]`` containing a number not
  supported by the cited results (value, exact, denominator, numerator, numeric group labels,
  unit-agreeing; or the exact rounded half-even to the stated decimals) nor by the texts of the
  evidence handles the unit cites (``contract.supports``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from marketsignal.generation import contract
from marketsignal.generation.types import CANONICAL_RE

RESULT_RE = re.compile(r"\[\[result:([0-9a-fA-F-]{36})\]\]")
COMPUTE_TOOLS = frozenset({"aggregate", "group_compare", "filter_rows"})
ANALYTICS_TOOLS = COMPUTE_TOOLS | {"describe_dataset"}
SEARCH_TOOLS = frozenset({"search_evidence", "search_evidence_keyword"})
DIFFERENCE = "__difference__"
_RESERVED_PREFIX = "@"
_SCALES = {"": 1, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_GOLD_METRIC_RE = re.compile(r"^(\w+)(?:\(([^\s)]*))?")
_DP_RE = re.compile(r"^(\d)dp$")


# ------------------------------------------------------------------------------------------
# Canonical values
# ------------------------------------------------------------------------------------------


def dec(value: Any) -> Decimal | None:
    """A Decimal for numbers and numeric strings (``"3,034,559"`` too); None otherwise."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def canon(value: Any) -> str:
    """Canonical comparison string: ``2023 == "2023" == "2023.0"``; text is case-folded."""
    if isinstance(value, bool):
        return "true" if value else "false"
    number = dec(value)
    if number is not None:
        text = format(number, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    return " ".join(str(value).split()).casefold()


def same_number(a: Any, b: Any) -> bool:
    x, y = dec(a), dec(b)
    return x is not None and y is not None and x == y


# ------------------------------------------------------------------------------------------
# Result cells
# ------------------------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Cell:
    result_id: str
    dataset: str
    operation: str
    group: dict[str, Any]
    key: str
    fn: str | None
    column: str | None
    value: Any
    exact: str | None
    unit: str | None
    denominator: int | None = None
    numerator: int | None = None
    scale: str = ""
    handle: str | None = None


def _metric_cell(result: Mapping[str, Any], group: dict[str, Any], m: Mapping[str, Any]) -> Cell:
    return Cell(
        result_id=str(result.get("result_id")),
        dataset=str(result.get("dataset")),
        operation=str(result.get("operation")),
        group=group,
        key=str(m.get("key")),
        fn=m.get("fn"),
        column=m.get("column"),
        value=m.get("value"),
        exact=m.get("exact"),
        unit=m.get("unit"),
        denominator=m.get("denominator"),
        numerator=m.get("numerator"),
        scale=str(m.get("scale") or ""),
    )


def _row_cells(result: Mapping[str, Any], row: Mapping[str, Any]) -> list[Cell]:
    raw = dict(row.get("group") or {})
    handle = row.get("handle") or raw.get("@handle")
    group = {k: v for k, v in raw.items() if not str(k).startswith(_RESERVED_PREFIX)}
    return [
        Cell(
            result_id=str(result.get("result_id")),
            dataset=str(result.get("dataset")),
            operation="filter_rows",
            group=group,
            key=name,
            fn=None,
            column=name,
            value=value,
            exact=canon(value) if dec(value) is not None else None,
            unit=None,
            denominator=1,
            handle=str(handle) if handle else None,
        )
        for name, value in group.items()
    ]


def cells(result: Mapping[str, Any]) -> list[Cell]:
    """Every computed number of one persisted result (see module docstring)."""
    rows = result.get("rows") or []
    if result.get("operation") == "filter_rows":
        return [c for row in rows for c in _row_cells(result, row)]
    out = [
        _metric_cell(result, dict(row.get("group") or {}), m)
        for row in rows
        for m in row.get("metrics") or []
    ]
    if result.get("difference"):
        out.append(_metric_cell(result, {DIFFERENCE: True}, result["difference"]))
    return out


# ------------------------------------------------------------------------------------------
# Gold value matching
# ------------------------------------------------------------------------------------------


def gold_values(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The gold values of one ``gold.analytics`` entry, with the compare difference appended."""
    values = [dict(v) for v in entry.get("values") or []]
    diff = entry.get("difference")
    if diff:
        values.append(
            {
                "group": {DIFFERENCE: True},
                "metric": values[0]["metric"] if values else diff.get("key"),
                **{k: diff.get(k) for k in ("value", "exact", "unit", "rounding", "denominator")},
            }
        )
    for v in values:
        v.setdefault("dataset", entry.get("dataset"))
        v.setdefault("tool", entry.get("tool"))
    return values


def parse_gold_metric(metric: str, tool: str | None) -> tuple[str | None, str | None]:
    """``(fn, column)``: ``share(c eq x)`` -> (share, c); filter_rows metric = column name."""
    if tool == "filter_rows":
        return None, metric
    match = _GOLD_METRIC_RE.match(metric or "")
    if not match:
        return None, None
    return match.group(1), match.group(2) or None


def _metric_agrees(gold: Mapping[str, Any], cell: Cell) -> bool:
    fn, column = parse_gold_metric(str(gold.get("metric") or ""), gold.get("tool"))
    if gold.get("tool") == "filter_rows" or cell.operation == "filter_rows":
        return cell.operation == "filter_rows" and cell.column == column
    if fn is not None and cell.fn != fn:
        return False
    return fn == "share" or column is None or cell.column == column


def group_agrees(gold_group: Mapping[str, Any], cell_group: Mapping[str, Any]) -> bool:
    if (DIFFERENCE in gold_group) != (DIFFERENCE in cell_group):
        return False
    shared = set(gold_group) & set(cell_group)
    if gold_group and cell_group and not shared:
        return False
    return all(canon(gold_group[k]) == canon(cell_group[k]) for k in shared)


def numbers_agree(gold: Mapping[str, Any], cell: Cell) -> tuple[bool, bool]:
    """``(exact_equal, rounded_equal)``; a null gold value matches a null cell."""
    if gold.get("value") is None and gold.get("exact") is None:
        empty = cell.value is None and cell.exact is None
        return empty, empty
    exact_eq = same_number(cell.exact, gold.get("exact"))
    if dec(gold.get("value")) is None:
        return exact_eq, canon(cell.value) == canon(gold.get("value"))
    return exact_eq, same_number(cell.value, gold.get("value"))


@dataclass
class GoldMatch:
    gold: dict[str, Any]
    cell: Cell | None = None
    exact_equal: bool = False
    rounded_equal: bool = False

    @property
    def matched(self) -> bool:
        return self.cell is not None

    def component(self, name: str) -> bool | None:
        """denominator / unit / rounding of the matched cell (None if not applicable)."""
        if self.cell is None:
            return False
        if name == "denominator":
            if self.gold.get("denominator") is None:
                return None
            return self.cell.denominator == self.gold.get("denominator")
        if name == "unit":
            return None if self.cell.unit is None else self.cell.unit == self.gold.get("unit")
        return self.rounded_equal


def match_gold(gold: Mapping[str, Any], candidates: Iterable[Cell]) -> GoldMatch:
    best = GoldMatch(dict(gold))
    for cell in candidates:
        if cell.dataset != gold.get("dataset") or not _metric_agrees(gold, cell):
            continue
        if not group_agrees(gold.get("group") or {}, cell.group):
            continue
        exact_eq, rounded_eq = numbers_agree(gold, cell)
        if not (exact_eq or rounded_eq):
            continue
        if best.cell is None or (exact_eq + rounded_eq) > (best.exact_equal + best.rounded_equal):
            best = GoldMatch(dict(gold), cell, exact_eq, rounded_eq)
    return best


# ------------------------------------------------------------------------------------------
# Spec components
# ------------------------------------------------------------------------------------------

FilterKey = tuple[str, str, frozenset[str]]


def norm_filter(f: Mapping[str, Any]) -> FilterKey:
    if f.get("operands") is not None:
        operands = list(f["operands"])
    elif f.get("values") is not None:
        operands = list(f["values"])
    else:
        operands = [] if f.get("value") is None else [f["value"]]
    op = str(f.get("op"))
    if len(operands) == 1 and op in ("in", "not_in"):
        op = "eq" if op == "in" else "ne"
    return str(f.get("column")), op, frozenset(canon(v) for v in operands)


def norm_filters(filters: Iterable[Mapping[str, Any]] | None) -> frozenset[FilterKey]:
    return frozenset(norm_filter(f) for f in filters or [])


def norm_metric(m: Mapping[str, Any]) -> tuple[str, str | None, FilterKey | None]:
    fn = str(m.get("fn"))
    if fn == "share":
        cond = m.get("condition")
        return fn, None, norm_filter(cond) if cond else None
    return fn, m.get("column"), None


def _metrics_of(tool: str, spec: Mapping[str, Any]) -> set[tuple[str, str | None, Any]]:
    if tool == "group_compare":
        return {norm_metric(spec["metric"])} if spec.get("metric") else set()
    return {norm_metric(m) for m in spec.get("metrics") or []}


def spec_components(
    gold_tool: str, gold_spec: Mapping[str, Any], tool: str, spec: Mapping[str, Any]
) -> dict[str, bool | None]:
    """aggregation / grouping / filter correctness of one result spec against the gold spec."""
    out: dict[str, bool | None] = {
        "filter": norm_filters(gold_spec.get("filters")) == norm_filters(spec.get("filters"))
    }
    if gold_tool == "filter_rows":
        return {**out, "aggregation": None, "grouping": None}
    gold_metrics = _metrics_of(gold_tool, gold_spec)
    out["aggregation"] = bool(gold_metrics) and gold_metrics <= _metrics_of(tool, spec)
    if gold_tool == "group_compare":
        sides = {canon(gold_spec.get("group_a")), canon(gold_spec.get("group_b"))}
        out["grouping"] = (
            tool == "group_compare"
            and spec.get("compare_column") == gold_spec.get("compare_column")
            and {canon(spec.get("group_a")), canon(spec.get("group_b"))} == sides
        )
    else:
        out["grouping"] = tool == "aggregate" and set(gold_spec.get("group_by") or []) == set(
            spec.get("group_by") or []
        )
    return out


def best_spec_match(
    entry: Mapping[str, Any], results: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """The run result on the gold dataset with the most correct spec components."""
    tool = str(entry.get("tool"))
    best: dict[str, Any] = {
        "result_id": None,
        "dataset": False,
        "aggregation": None if tool == "filter_rows" else False,
        "grouping": None if tool == "filter_rows" else False,
        "filter": False,
    }
    best_score = -1
    for result in results:
        if result.get("dataset") != entry.get("dataset"):
            continue
        comps = spec_components(
            tool, entry.get("spec") or {}, str(result.get("operation")), result.get("spec") or {}
        )
        score = sum(1 for v in comps.values() if v) + (result.get("operation") == tool)
        if score > best_score:
            best_score = score
            best = {"result_id": result.get("result_id"), "dataset": True, **comps}
    return best


# ------------------------------------------------------------------------------------------
# Answer statements
# ------------------------------------------------------------------------------------------


def strip_markers(text: str) -> str:
    return CANONICAL_RE.sub(" ", RESULT_RE.sub(" ", text))


def mentions(text: str) -> list[contract.NumberMention]:
    """Quantitative numbers of ``text`` (markers stripped; calendar years excluded)."""
    return [m for m in contract.extract_numbers(strip_markers(text)) if not m.temporal]


def _decimals(text: str) -> int:
    return len(text.split(".", 1)[1]) if "." in text else 0


def rule_decimals(gold: Mapping[str, Any]) -> int:
    match = _DP_RE.match(str(gold.get("rounding") or ""))
    if match:
        return int(match.group(1))
    return _decimals(str(gold.get("exact") or ""))


def _rounded(number: Decimal, places: int) -> Decimal:
    return number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


def _frames(m: contract.NumberMention) -> list[tuple[Decimal, int]]:
    """The mention as written (mantissa) and, when scaled, its full value: (number, decimals)."""
    mantissa = abs(Decimal(m.mantissa_text))
    places = _decimals(m.mantissa_text)
    frames = [(mantissa, places)]
    if m.scale != 1.0:
        scale = Decimal(str(m.scale)).normalize()
        frames.append((mantissa * scale, places - int(scale.adjusted())))
    return frames


def _unit_compatible(m: contract.NumberMention, unit: str | None) -> bool:
    if m.percent and unit not in (None, "percent", "ratio", "number"):
        return False
    return not (m.currency and unit not in (None, "currency_usd"))


def statement(gold: Mapping[str, Any], m: contract.NumberMention) -> str | None:
    """``"stated"``, ``"approximate"`` (a coarser rounding) or None for one mention."""
    exact, value = dec(gold.get("exact")), dec(gold.get("value"))
    if (exact is None and value is None) or not _unit_compatible(m, gold.get("unit")):
        return None
    needed = rule_decimals(gold)
    approximate = False
    for number, places in _frames(m):
        if value is not None and number == abs(value):
            return "stated"
        if exact is not None and _rounded(abs(exact), places) == number:
            if places >= needed:
                return "stated"
            approximate = True
    return "approximate" if approximate else None


def best_statement(gold: Mapping[str, Any], found: Iterable[contract.NumberMention]) -> str | None:
    kinds = {statement(gold, m) for m in found}
    return "stated" if "stated" in kinds else ("approximate" if "approximate" in kinds else None)


def answer_units(content: str) -> list[str]:
    sections = contract.parse_sections(content)
    return [u for body in sections.values() for u in contract.split_units(body)]


# ------------------------------------------------------------------------------------------
# Result-citing unit re-check
# ------------------------------------------------------------------------------------------


def _render(value: Any, unit: str | None, scale: str) -> str:
    word = f" {scale}" if scale else ""
    if unit == "percent":
        return f"{value}%"
    if unit == "currency_usd":
        return f"${value}{word}"
    return f"{value}{word}"


def support_texts(results: Iterable[Mapping[str, Any]]) -> list[str]:
    """Each computed number of ``results`` rendered with its unit (support-side mentions)."""
    texts: list[str] = []
    for result in results:
        for c in cells(result):
            for v in (c.value, c.exact):
                if dec(v) is not None:
                    texts.append(_render(canon(v), c.unit, c.scale))
            texts.extend(str(n) for n in (c.denominator, c.numerator) if n is not None)
            texts.extend(str(v) for v in c.group.values() if v is not None and v is not True)
    return texts


def _exact_rounding_supports(m: contract.NumberMention, result_cells: Sequence[Cell]) -> bool:
    for c in result_cells:
        exact = dec(c.exact)
        if exact is None or not _unit_compatible(m, c.unit):
            continue
        full = exact * _SCALES.get(c.scale, 1)
        for number, places in _frames(m):
            if number in (_rounded(abs(exact), places), _rounded(abs(full), places)):
                return True
    return False


@dataclass
class ResultRecheck:
    result_units: int = 0
    unsupported_units: int = 0
    numbers: int = 0
    supported_numbers: int = 0
    unsupported: list[dict[str, Any]] = field(default_factory=list)


def recheck_result_units(
    content: str,
    results_by_id: Mapping[str, Mapping[str, Any]],
    texts: Mapping[str, str],
) -> ResultRecheck:
    """Re-check every unit citing ``[[result:…]]`` against what it cites (see docstring)."""
    out = ResultRecheck()
    for unit in answer_units(content):
        rids = [r.lower() for r in RESULT_RE.findall(unit)]
        if not rids:
            continue
        out.result_units += 1
        cited = [results_by_id[r] for r in rids if r in results_by_id]
        result_cells = [c for r in cited for c in cells(r)]
        pool = contract.number_values(
            [*support_texts(cited), *(texts[h] for h in CANONICAL_RE.findall(unit) if h in texts)]
        )
        missing = [
            m.text
            for m in mentions(unit)
            if not (contract.is_faithful(m, pool) or _exact_rounding_supports(m, result_cells))
        ]
        found = len(mentions(unit))
        out.numbers += found
        out.supported_numbers += found - len(missing)
        if missing:
            out.unsupported_units += 1
            out.unsupported.append({"numbers": missing, "unit": unit[:240]})
    return out


# ------------------------------------------------------------------------------------------
# Trace helpers
# ------------------------------------------------------------------------------------------


def trace_of(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list((run.get("agent") or {}).get("trace") or [])


def calls(run: Mapping[str, Any], tools: frozenset[str]) -> list[dict[str, Any]]:
    return [t for t in trace_of(run) if t.get("tool") in tools]


def retrieval_calls(run: Mapping[str, Any]) -> int:
    """Search tool calls; a run whose standard gather ran (``retrieval_ms``) counts one more."""
    gathered = 1 if "retrieval_ms" in (run.get("timings") or {}) else 0
    return len(calls(run, SEARCH_TOOLS)) + gathered
