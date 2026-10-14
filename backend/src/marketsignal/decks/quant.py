"""Quantitative blocks: a bar chart or a compact table for a computed analysis, and metric
callouts. Every number is a ``display`` string the analytics engine produced; nothing is
re-derived here."""

from __future__ import annotations

from typing import Any

CHART_MAX_ROWS = 8
TABLE_MAX_ROWS = 10


def humanize(value: str) -> str:
    """``"fit_inconsistency" -> "Fit inconsistency"``; human labels pass through unchanged."""
    if "_" not in value or " " in value:
        return value
    text = value.replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def base_text(denominator: dict[str, Any] | None) -> str | None:
    if not denominator or not denominator.get("label"):
        return None
    value = denominator.get("value")
    label = denominator["label"]
    return f"Base: {value:,} {label}" if isinstance(value, int) else f"Base: {label}"


def _numeric(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _varying_keys(rows: list[dict[str, Any]]) -> list[str]:
    keys = list(rows[0]["group"])
    varying = [k for k in keys if len({str(r["group"].get(k)) for r in rows}) > 1]
    return varying or keys


def _chartable(payload: dict[str, Any]) -> bool:
    rows = payload["rows"]
    return (
        payload.get("presentation") == "bar"
        and 0 < len(rows) <= CHART_MAX_ROWS
        and all(_numeric(r.get("value")) and r.get("display") for r in rows)
    )


def _chart(payload: dict[str, Any], cite: int) -> dict[str, Any]:
    rows = payload["rows"]
    keys = _varying_keys(rows)
    values = [float(r["value"]) for r in rows]
    return {
        "type": "chart",
        "chart": "bar",
        "title": payload["title"],
        "unit": payload.get("unit"),
        "categories": [
            " · ".join(humanize(str(r["group"].get(k, ""))) for k in keys) for r in rows
        ],
        "values": values,
        "displays": [str(r["display"]) for r in rows],
        "emphasis": values.index(max(values)),
        "base": base_text(payload.get("denominator")),
        "cites": [cite],
    }


def _table(payload: dict[str, Any], cite: int) -> dict[str, Any]:
    rows = payload["rows"]
    filter_rows = payload.get("op") == "filter_rows"
    keys: list[str] = (
        list(payload.get("columns") or [])
        if filter_rows
        else list(payload.get("group_by") or (rows[0]["group"] if rows else []))
    )
    columns = [humanize(k) for k in keys] + ([] if filter_rows else ["Value"])
    shown = rows[:TABLE_MAX_ROWS]
    body = [
        [humanize(str(r["group"].get(k, ""))) for k in keys]
        + ([] if filter_rows else [str(r.get("display") or "Not computed")])
        for r in shown
    ]
    return {
        "type": "table",
        "title": payload["title"],
        "columns": columns,
        "rows": body,
        "truncated": len(rows) > len(shown),
        "note": f"Showing {len(shown)} of {len(rows)} rows" if len(rows) > len(shown) else None,
        "base": base_text(payload.get("denominator")),
        "cites": [cite],
    }


def analysis_block(payload: dict[str, Any], cite: int) -> dict[str, Any]:
    """A native bar chart for a short bar analysis with every value computed, else a table."""
    return _chart(payload, cite) if _chartable(payload) else _table(payload, cite)


def metric_item(metric: dict[str, Any], cite: int) -> dict[str, Any]:
    label = metric.get("denominator_label")
    return {
        "label": metric["label"],
        "display": metric["display"],
        "base": f"Base: {label}" if label else None,
        "cites": [cite],
    }
