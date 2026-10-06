"""Computed analytics results in grounded answers (Phase 5, ADR-0006; GROUNDED_ANSWERING §5.8).

The research agent hands synthesis the persisted :class:`AnalyticsResult` dicts of its
computing analytics calls. Here they become run-local ``R1``..``Rn`` aliases
(:class:`ResultItem`), are rendered for the model inside ``<computed_results>``, and define the
only numbers an ``[R#]`` citation can support.

* **Bounded rendering.** At most :data:`MAX_RESULTS` results, :data:`MAX_ROWS` rows each, and
  labels cut to :data:`LABEL_MAX_CHARS`. The verifier sees exactly the rendered figures, never
  rows the model was not shown.
* **Untrusted labels.** Categorical levels, filter values and column names come from
  documents: they are escaped (``& < > "``), and an instruction-like label is withheld.
* **Numeric rules** (:func:`result_supports`), for a claimed figure in a unit citing ``[R#]``:

  - *metric value*: the stated number equals the result's rounded ``value``, or equals its
    ``exact`` value rounded half-even to the number of decimals stated ("38%" for exact
    38.2333, "38.23%" too; "38.3%" for exact 38.25 fails: half-even gives 38.2). A null value
    (zero denominator) supports nothing.
  - *unit*: percent values need a percent claim ("%", "percent", "pct"); a percent
    *difference* (group_compare) may also be stated in points ("3.2 pp", "3.2 percentage
    points"); currency_usd allows "$"/"US$"/"USD" or no symbol, never another currency;
    count needs a plain number; number/rating allow plain or points; ratio allows plain or a
    multiple ("1.5x"); date/text values support no numbers. Basis points never match.
  - *scale*: the claim's scale word must equal the result's scale ("" = none; billion =
    "billion"/"bn"/"b"), so "$12.4 million" never restates a billion-scale 12.4.
    A currency written after the number ("812.5 EUR", "812.5 euros") or a foreign prefix
    ("A$", "\u00a5", "CHF") is another currency.
  - *precision*: a stated 0 needs an exact zero (a non-zero 0.4% is never "0%" or "0.0%");
    an over-precise number (more decimals than the exact value) is unsupported, never an
    arithmetic error.
  - *sign and direction* (``generation/result_claims.py``): a negative claim needs a negative
    value; a level (metric value or count) is never stated as a change ("fell 38.2%"); a
    negative level stated unsigned needs a negative-direction word next to it; a
    group_compare difference (A - B) must agree in sign with its direction word *and* the
    group that is its subject ("South exceeded North by 3.2" is -3.2 when A = North).
  - *counts and labels*: a numerator, denominator, matched-row count, or a numeric group
    label/cell/filter operand supports exactly that number, stated plainly (no percent,
    currency or scale).
* **Years.** A result's years (the temporal qualifiers a cited result supports) come only
  from label text (filter operands, compare groups, group levels/cells that are not plain
  numbers, or any label of a date-like column such as ``year``/``fiscal_year``/``order_date``)
  and from date-unit values, never from counts, denominators or decimal digits.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from html import escape
from typing import Any, Final

from pydantic import ValidationError

from marketsignal.generation import result_claims as claims
from marketsignal.generation.contract import NumberMention, strip_format_chars, years_in
from marketsignal.generation.safe_text import is_instruction_like
from marketsignal.generation.types import EvidencePack, ResultFigure, ResultItem
from marketsignal.telemetry.logging import get_logger
from marketsignal.tools.analytics_contracts import AnalyticsResult, MetricValue, ResultRow

log = get_logger(__name__)

MAX_RESULTS: Final = 8
MAX_ROWS: Final = 20
LABEL_MAX_CHARS: Final = 80
SUMMARY_MAX_CHARS: Final = 240
FALLBACK_LINES: Final = 6
WITHHELD_LABEL: Final = "(label withheld)"

_SCALE_FACTORS: Final[Mapping[str, float]] = {
    "": 1.0,
    "thousand": 1e3,
    "million": 1e6,
    "billion": 1e9,
}
_USD: Final = frozenset({"$", "US$", "USD"})
_METRIC_KINDS: Final[Mapping[str, frozenset[str]]] = {
    "percent": frozenset({"percent"}),
    "currency_usd": frozenset({"currency", "plain"}),
    "count": frozenset({"plain"}),
    "number": frozenset({"plain", "points"}),
    "rating": frozenset({"plain", "points"}),
    "ratio": frozenset({"plain", "multiple"}),
}
_PERCENT_DIFFERENCE_KINDS: Final = frozenset({"percent", "points"})
_POINTS_AFTER: Final = r"[ \t]*(?:percentage[ \t-]+points?|points?|pts?|ppts?|pp)\b"
# Columns whose labels are dates/periods: any of their labels may carry a year.
_TEMPORAL_COLUMN_RE: Final = re.compile(
    r"(?:^|[^a-z])(?:years?|yr|fy|cy|fiscal|dates?|months?|quarters?|qtr|periods?)(?:$|[^a-z])",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------------------------
# Building and rendering
# --------------------------------------------------------------------------------------------


def _dec(value: object) -> Decimal | None:
    """A finite decimal from an int/float/numeric string; ``None`` otherwise (bools too)."""
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, int | float | str):
        return None
    try:
        number = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _fmt(value: object) -> str:
    number = _dec(value)
    if number is None:
        return "null" if value is None else str(value)
    return format(number, "f")


def _label(value: object) -> str:
    """A document-derived label: bounded, instruction-like text withheld (escaped later)."""
    text = " ".join(strip_format_chars(str(value)).split())[:LABEL_MAX_CHARS]
    return WITHHELD_LABEL if is_instruction_like(text) else text


def _attr(value: object) -> str:
    return escape(str(value), quote=True).replace("\n", " ")


def _spec_filters(spec: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Filters plus metric conditions, each ``{column, op, operands}`` (validate._filter_spec)."""
    found = [f for f in spec.get("filters") or [] if isinstance(f, Mapping)]
    metrics = spec.get("metrics")
    candidates = [*(metrics if isinstance(metrics, list) else []), spec.get("metric")]
    found += [
        m["condition"]
        for m in candidates
        if isinstance(m, Mapping) and isinstance(m.get("condition"), Mapping)
    ]
    return found


def _operands(flt: Mapping[str, Any]) -> list[object]:
    operands = flt.get("operands")
    return list(operands) if isinstance(operands, list) else []


def _spec_labels(spec: Mapping[str, Any]) -> list[tuple[object, object]]:
    """``(column, value)`` for every filter/condition operand and compared group."""
    labels = [(f.get("column"), v) for f in _spec_filters(spec) for v in _operands(f)]
    if spec.get("compare_column"):
        labels += [(spec["compare_column"], spec.get(k)) for k in ("group_a", "group_b")]
    return [(column, value) for column, value in labels if value is not None]


def _filters_text(spec: Mapping[str, Any]) -> str:
    parts = []
    for flt in spec.get("filters") or []:
        if not isinstance(flt, Mapping):
            continue
        shown = ", ".join(_label(v) for v in _operands(flt))
        parts.append(f"{_label(flt.get('column'))} {_label(flt.get('op'))} {shown}".strip())
    return "; ".join(parts)


def _grouping_text(spec: Mapping[str, Any]) -> str:
    if spec.get("compare_column"):
        return (
            f"{_label(spec['compare_column'])}: A={_label(spec.get('group_a'))} vs "
            f"B={_label(spec.get('group_b'))}"
        )
    group_by = spec.get("group_by") or []
    return ", ".join(_label(g) for g in group_by) if isinstance(group_by, list) else ""


def _metric_text(metric: MetricValue) -> str:
    parts = [f"value={_fmt(metric.value)}", f"unit={metric.unit}"]
    if metric.scale:
        parts.append(f"scale={metric.scale}")
    if metric.value is None:
        parts.append("(no data: zero denominator)")
    if metric.exact is not None:
        parts.append(f"exact={metric.exact}")
    if metric.numerator is not None:
        parts.append(f"numerator={metric.numerator}")
    parts.append(f"denominator={metric.denominator}")
    return f"{_label(metric.key)}: " + " ".join(parts)


def _metric_figures(
    metric: MetricValue, kind: str, groups: tuple[str, str] | None = None
) -> list[ResultFigure]:
    value, exact = _dec(metric.value), _dec(metric.exact)
    figures = [
        ResultFigure(kind, value, exact, metric.unit, metric.scale, groups),
        ResultFigure("count", Decimal(metric.denominator)),
    ]
    if metric.numerator is not None:
        figures.append(ResultFigure("count", Decimal(metric.numerator)))
    return figures


def _row_line(row: ResultRow) -> tuple[str, list[ResultFigure]]:
    group = " | ".join(f"{_label(k)}={_label(v)}" for k, v in row.group.items())
    figures = [ResultFigure("label", n) for v in row.group.values() if (n := _dec(v)) is not None]
    metrics = []
    for metric in row.metrics:
        metrics.append(_metric_text(metric))
        figures.extend(_metric_figures(metric, "metric"))
    body = " ; ".join(part for part in (group, *metrics) if part)
    return f"row: {body}", figures


def _unit_label(metric: MetricValue) -> str:
    value = _fmt(metric.value)
    scale = f" {metric.scale}" if metric.scale else ""
    if metric.unit == "percent":
        return f"{value}%"
    if metric.unit == "currency_usd":
        return f"USD {value}{scale}"
    return f"{value}{scale} ({metric.unit})"


def _fallback_line(row: ResultRow, metric: MetricValue) -> str:
    group = ", ".join(f"{_label(k)}={_label(v)}" for k, v in row.group.items())
    where = f" for {group}" if group else ""
    value = "no data (zero denominator)" if metric.value is None else _unit_label(metric)
    return f"{_label(metric.key)}{where}: {value}, denominator {metric.denominator}"


def _summary(result: AnalyticsResult) -> str:
    spec = result.spec
    metrics = sorted(
        {_label(m.key) for row in result.rows for m in row.metrics}
        | ({_label(result.difference.key)} if result.difference else set())
    )
    parts = [result.operation, ", ".join(metrics[:4])]
    if grouping := _grouping_text(spec):
        parts.append(f"by {grouping}")
    if filters := _filters_text(spec):
        parts.append(f"filters: {filters}")
    parts.append(f"{result.rows_matched} of {result.rows_scanned} rows")
    return " ".join(" ; ".join(p for p in parts if p).split())[:SUMMARY_MAX_CHARS]


def _temporal_label(column: object, value: object) -> bool:
    """A label that may carry a year: text that is not a plain number, or any label of a
    date-like column ("year", "fiscal_year", "order_date")."""
    return _dec(value) is None or _TEMPORAL_COLUMN_RE.search(str(column)) is not None


def _years(spec: Mapping[str, Any], rows: Sequence[ResultRow]) -> frozenset[int]:
    """Years a cited result supports: labels and date values only (module docstring)."""
    texts = [_label(v) for column, v in _spec_labels(spec) if _temporal_label(column, v)]
    for row in rows:
        texts += [_label(v) for column, v in row.group.items() if _temporal_label(column, v)]
        texts += [
            _label(part)
            for m in row.metrics
            if m.unit == "date"
            for part in (m.value, m.exact)
            if part is not None
        ]
    return years_in(texts)


def _compared_groups(spec: Mapping[str, Any]) -> tuple[str, str] | None:
    a, b = spec.get("group_a"), spec.get("group_b")
    if not spec.get("compare_column") or a is None or b is None:
        return None
    return _label(a), _label(b)


def build_result_item(alias: str, result: AnalyticsResult) -> ResultItem:
    """One result as the model sees it, plus the figures and lines derived from that view."""
    spec = result.spec
    lines: list[str] = []
    figures: list[ResultFigure] = [ResultFigure("count", Decimal(result.rows_matched))]
    figures += [
        ResultFigure("label", n) for _, v in _spec_labels(spec) if (n := _dec(v)) is not None
    ]
    if filters := _filters_text(spec):
        lines.append(f"filters: {filters}")
    if grouping := _grouping_text(spec):
        lines.append(f"grouping: {grouping}")
    fallback: list[str] = []
    for row in result.rows[:MAX_ROWS]:
        line, row_figures = _row_line(row)
        lines.append(line)
        figures.extend(row_figures)
        fallback.extend(_fallback_line(row, metric) for metric in row.metrics)
    if len(result.rows) > MAX_ROWS:
        lines.append(f"({len(result.rows) - MAX_ROWS} more rows not shown)")
    if result.difference is not None:
        lines.append(f"difference (A - B): {_metric_text(result.difference)}")
        groups = _compared_groups(spec)
        figures.extend(_metric_figures(result.difference, "difference", groups))
        difference = _fallback_line(ResultRow(metrics=[]), result.difference)
        fallback.insert(0, f"difference (A - B): {difference}")
    if result.warnings:
        lines.append("warnings: " + ", ".join(_label(w) for w in result.warnings))
    attrs = (
        f'alias="{alias}" dataset="{_attr(result.dataset)}" source="{_attr(result.source_code)}" '
        f'version="{result.source_version}" table="{_attr(_label(result.table))}" '
        f'op="{result.operation}" rows_matched="{result.rows_matched}" '
        f'rows_scanned="{result.rows_scanned}" rounding="{_attr(result.rounding)}"'
    )
    body = escape("\n".join(lines), quote=True)
    rendered = f"<result {attrs}>\n{body}\n</result>"
    return ResultItem(
        alias=alias,
        result_id=result.result_id,
        source_code=result.source_code,
        dataset=result.dataset,
        source_version=result.source_version,
        table=result.table,
        operation=result.operation,
        summary=_summary(result),
        rendered=rendered,
        figures=tuple(figures),
        years=_years(spec, result.rows[:MAX_ROWS]),
        workspace=result.workspace,
        fallback_lines=tuple(fallback[:FALLBACK_LINES]),
    )


def build_result_items(results: Sequence[Mapping[str, Any]]) -> tuple[ResultItem, ...]:
    """``R1``..``Rn`` in order, de-duplicated by ``result_id``, at most :data:`MAX_RESULTS`.
    A dict that is not a valid :class:`AnalyticsResult` is skipped (logged), never guessed."""
    items: list[ResultItem] = []
    seen: set[str] = set()
    for raw in results:
        try:
            result = AnalyticsResult.model_validate(raw)
        except ValidationError as exc:
            log.warning("analytics_result_invalid", errors=exc.error_count())
            continue
        if result.result_id in seen:
            continue
        seen.add(result.result_id)
        items.append(build_result_item(f"R{len(items) + 1}", result))
        if len(items) == MAX_RESULTS:
            break
    return tuple(items)


def with_results(pack: EvidencePack, results: Sequence[Mapping[str, Any]]) -> EvidencePack:
    """The pack with its computed results (replacing any; idempotent for the same input)."""
    return replace(pack, results=build_result_items(results))


def without_result_sources(pack: EvidencePack, codes: Iterable[str]) -> tuple[ResultItem, ...]:
    gone = set(codes)
    return tuple(r for r in pack.results if r.source_code not in gone)


# --------------------------------------------------------------------------------------------
# Numeric support for [R#] citations
# --------------------------------------------------------------------------------------------


def _claim_kind(text: str, mention: NumberMention, spans: Sequence[claims.Span]) -> str:
    written = mention.text.lower()
    if re.search(r"\d[ \t]?bps?$", written):
        return "bps"
    if re.search(r"\d[ \t]?(?:pp|ppts?|pts?)$", written):
        return "points"
    if written.endswith(("x", "\u00d7")):
        return "multiple"
    if mention.percent:
        return "percent"
    if re.search(rf"(?<![\w.]){re.escape(mention.text)}{_POINTS_AFTER}", text, re.IGNORECASE):
        return "points"
    if mention.currency is not None and mention.currency.strip() not in _USD:
        return "other_currency"
    if claims.foreign_currency(text, spans, mention):
        return "other_currency"
    if mention.currency is not None or claims.usd_suffix(text, spans):
        return "currency"
    return "plain"


def _direction_ok(
    text: str,
    spans: Sequence[claims.Span],
    mention: NumberMention,
    figure: ResultFigure,
    value: Decimal,
) -> bool:
    if figure.kind == "difference":
        return claims.difference_ok(text, spans, mention, value, figure.groups)
    if figure.kind == "label":
        return claims.label_ok(text, spans, mention, value)
    return claims.level_ok(text, spans, mention, value)


def _kind_ok(kind: str, figure: ResultFigure) -> bool:
    if figure.kind in ("count", "label"):
        return kind == "plain"
    if figure.kind == "difference" and figure.unit == "percent":
        return kind in _PERCENT_DIFFERENCE_KINDS
    return kind in _METRIC_KINDS.get(figure.unit, frozenset())


def _decimals(digits: str) -> int:
    return len(digits.split(".", 1)[1]) if "." in digits else 0


def _rounds_to(exact: Decimal, decimals: int, stated: Decimal) -> bool:
    """``exact`` rounded half-even to ``decimals`` equals ``stated``. Only a real rounding
    (fewer decimals than ``exact`` has) is computed, with enough precision that an
    over-precise or huge number is a plain mismatch, never ``InvalidOperation``."""
    exponent = exact.as_tuple().exponent
    if not isinstance(exponent, int) or -exponent <= decimals:
        return False  # nothing to round: only an equal number matches (checked by the caller)
    with localcontext() as ctx:
        ctx.prec = max(ctx.prec, len(exact.as_tuple().digits) + 2)
        try:
            return exact.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_EVEN) == stated
        except InvalidOperation:
            return False


def _value_ok(stated: Decimal, decimals: int, value: Decimal, figure: ResultFigure) -> bool:
    if stated == 0 and (figure.exact if figure.exact is not None else value) != 0:
        return False  # a non-zero result is never stated as zero ("0%" for 0.4)
    if stated == value.copy_abs():  # copy_abs: no context rounding of long decimals
        return True
    if figure.kind in ("count", "label") or figure.exact is None:
        return False
    exact = figure.exact.copy_abs()
    return stated == exact or _rounds_to(exact, decimals, stated)


def figure_supports(text: str, mention: NumberMention, figure: ResultFigure) -> bool:
    """True if ``figure`` backs the claimed ``mention`` in unit ``text`` (module rules)."""
    value = figure.value
    if value is None:
        return False  # zero denominator: no stated number is supported by a null value
    spans = claims.occurrences(text, mention)
    if not spans:
        return False  # the claim cannot be placed in its unit: fail closed
    if not _kind_ok(_claim_kind(text, mention, spans), figure):
        return False
    factor = _SCALE_FACTORS.get(figure.scale if figure.kind in ("metric", "difference") else "")
    if factor is None or mention.scale != factor:
        return False
    try:
        stated = Decimal(mention.mantissa_text)
    except InvalidOperation:
        return False
    sign_value = value if value != 0 or figure.exact is None else figure.exact
    if not _direction_ok(text, spans, mention, figure, sign_value):
        return False
    return _value_ok(stated, _decimals(mention.mantissa_text), value, figure)


def result_supports(text: str, mention: NumberMention, items: Iterable[ResultItem]) -> bool:
    """True if any figure of the cited results backs ``mention``."""
    return any(figure_supports(text, mention, f) for item in items for f in item.figures)
