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
  - *sign*: a negative claim needs a negative value; a negative value stated unsigned needs a
    negative-direction word in the unit ("lower", "fell", "declined", ...); a positive
    difference stated with only negative-direction words fails (a sign flip).
  - *counts and labels*: a numerator, denominator, matched-row count, or a numeric group
    label/cell/filter value supports exactly that number, stated plainly (no percent,
    currency or scale).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from html import escape
from typing import Any, Final

from pydantic import ValidationError

from marketsignal.generation.contract import NumberMention, years_in
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
_NEGATIVE_RE: Final = re.compile(
    r"\b(?:lower|less|fewer|below|behind|trail(?:s|ed|ing)?|declin(?:e|ed|es|ing)"
    r"|decreas(?:e|ed|es|ing)|drop(?:s|ped)?|fell|fall(?:s|en)?|down|negative|minus|smaller"
    r"|worse|lag(?:s|ged)?|loss|shr[ai]nk|shrunk|contract(?:ed|ion)|deficit|under)\b",
    re.IGNORECASE,
)
_POSITIVE_RE: Final = re.compile(
    r"\b(?:higher|more|greater|above|ahead|exceed(?:s|ed)?|increas(?:e|ed|es|ing)|rose"
    r"|ris(?:e|es|en|ing)|up|grew|grow(?:th|s)?|gain(?:s|ed)?|larger|better|positive|plus)\b",
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
    text = " ".join(str(value).split())[:LABEL_MAX_CHARS]
    return WITHHELD_LABEL if is_instruction_like(text) else text


def _attr(value: object) -> str:
    return escape(str(value), quote=True).replace("\n", " ")


def _spec_scalars(node: object) -> Iterable[object]:
    """Every filter/condition/comparison value in the normalized spec (recursively)."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in ("value", "group_a", "group_b"):
                yield value
            elif key == "values" and isinstance(value, list):
                yield from value
            else:
                yield from _spec_scalars(value)
    elif isinstance(node, list):
        for value in node:
            yield from _spec_scalars(value)


def _filters_text(spec: Mapping[str, Any]) -> str:
    parts = []
    for flt in spec.get("filters") or []:
        if not isinstance(flt, Mapping):
            continue
        values = flt.get("values")
        shown = (
            ", ".join(_label(v) for v in values)
            if isinstance(values, list)
            else _label(flt.get("value"))
        )
        parts.append(f"{_label(flt.get('column'))} {flt.get('op')} {shown}".strip())
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


def _metric_figures(metric: MetricValue, kind: str) -> list[ResultFigure]:
    figures = [
        ResultFigure(kind, _dec(metric.value), _dec(metric.exact), metric.unit, metric.scale),
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


def build_result_item(alias: str, result: AnalyticsResult) -> ResultItem:
    """One result as the model sees it, plus the figures and lines derived from that view."""
    spec = result.spec
    lines: list[str] = []
    figures: list[ResultFigure] = [ResultFigure("count", Decimal(result.rows_matched))]
    figures += [ResultFigure("label", n) for v in _spec_scalars(spec) if (n := _dec(v)) is not None]
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
        figures.extend(_metric_figures(result.difference, "difference"))
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
        years=years_in(["\n".join(lines)]),
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


def _claim_kind(text: str, mention: NumberMention) -> str:
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
    if mention.currency is not None:
        return "currency" if mention.currency.strip() in _USD else "other_currency"
    return "plain"


def _sign_ok(text: str, mention: NumberMention, figure: ResultFigure, value: Decimal) -> bool:
    if mention.mantissa < 0:
        return value < 0
    if value < 0:
        return _NEGATIVE_RE.search(text) is not None
    if figure.kind == "difference" and value > 0:
        return not (_NEGATIVE_RE.search(text) and not _POSITIVE_RE.search(text))
    return True


def _kind_ok(kind: str, figure: ResultFigure) -> bool:
    if figure.kind in ("count", "label"):
        return kind == "plain"
    if figure.kind == "difference" and figure.unit == "percent":
        return kind in _PERCENT_DIFFERENCE_KINDS
    return kind in _METRIC_KINDS.get(figure.unit, frozenset())


def _decimals(digits: str) -> int:
    return len(digits.split(".", 1)[1]) if "." in digits else 0


def _value_ok(stated: Decimal, decimals: int, value: Decimal, figure: ResultFigure) -> bool:
    if stated == abs(value):
        return True
    if figure.kind in ("count", "label") or figure.exact is None:
        return False
    quantum = Decimal(1).scaleb(-decimals)
    return abs(figure.exact).quantize(quantum, rounding=ROUND_HALF_EVEN) == stated


def figure_supports(text: str, mention: NumberMention, figure: ResultFigure) -> bool:
    """True if ``figure`` backs the claimed ``mention`` in unit ``text`` (module rules)."""
    value = figure.value
    if value is None:
        return False  # zero denominator: no stated number is supported by a null value
    if not _kind_ok(_claim_kind(text, mention), figure):
        return False
    factor = _SCALE_FACTORS.get(figure.scale if figure.kind in ("metric", "difference") else "")
    if factor is None or mention.scale != factor:
        return False
    try:
        stated = Decimal(mention.mantissa_text)
    except InvalidOperation:
        return False
    sign_value = value if value != 0 or figure.exact is None else figure.exact
    if not _sign_ok(text, mention, figure, sign_value):
        return False
    return _value_ok(stated, _decimals(mention.mantissa_text), value, figure)


def result_supports(text: str, mention: NumberMention, items: Iterable[ResultItem]) -> bool:
    """True if any figure of the cited results backs ``mention``."""
    return any(figure_supports(text, mention, f) for item in items for f in item.figures)
