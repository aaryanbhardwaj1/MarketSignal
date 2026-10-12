"""Display strings for recomputed values. Formatting never changes a value: it only renders the
engine's rounded number with the unit's conventional precision."""

from __future__ import annotations

from marketsignal.analytics.rounding import exact_str, to_decimal

_PLACES = {"percent": 1, "score": 2, "ratio": 3}


def format_value(
    value: int | float | None, unit: str, *, places: int | None = None, signed: bool = False
) -> str | None:
    """``27.0 -> "27.0%"``, ``2146098 -> "$2,146,098"``, ``3.9 -> "3.90"``. ``places=-1`` trims
    trailing zeros (a derived difference such as an NPS of 22)."""
    if value is None:
        return None
    d = to_decimal(value)
    sign = "+" if signed and d > 0 else ""
    if unit == "usd":
        return f"{sign}${d:,.0f}" if d == d.to_integral_value() else f"{sign}${d:,.2f}"
    if unit == "count":
        return f"{sign}{d:,.0f}" if d == d.to_integral_value() else f"{sign}{exact_str(d)}"
    digits = _PLACES.get(unit, 2) if places is None else places
    text = exact_str(d) if digits < 0 else f"{d:,.{digits}f}"
    return f"{sign}{text}%" if unit == "percent" else f"{sign}{text}"
