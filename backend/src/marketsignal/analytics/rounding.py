"""Rounding rules (Phase 5 brief; the verifier relies on them). Decimal, ``ROUND_HALF_EVEN``.

* ``count``/``count_distinct`` and ``min``/``max`` -> exact (a count, or an actual cell value);
* ``share`` -> percent, 1 dp;
* ``sum``/``mean``/``median`` by the column unit: percent 1 dp, currency_usd 2 dp, ratio 3 dp;
  otherwise ``mean``/``median`` 2 dp, ``sum`` exact when every summed value is an integer and
  2 dp when any is fractional;
* a ``group_compare`` difference is ``exact(A) - exact(B)`` rounded with the metric's rule.

``exact`` always holds the unrounded value as a plain decimal string (28 significant digits
for non-terminating quotients); ``value`` is the rounded number (``int`` when the rule is exact
and the value is integral).

Magnitude: sums and differences are exact at any size (:data:`EXACT`), quotients keep at least
:data:`QUOTIENT_FRACTION_DIGITS` fractional digits however large the dividend (:func:`divide`),
and rounding quantizes in a context sized to the value, so one huge cell (``1e30``) never makes
a metric fail; ``value`` is then the nearest float.
"""

from __future__ import annotations

from decimal import MAX_EMAX, MAX_PREC, MIN_EMIN, ROUND_HALF_EVEN, Context, Decimal

from marketsignal.tools.analytics_contracts import AggFn, Unit

ROUNDING = (
    "half_even; percent 1dp; currency_usd 2dp; ratio 3dp; mean/median 2dp; "
    "fractional sums 2dp; counts, integer sums, min/max exact"
)
CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)
# additions/subtractions only (never a division): exact whatever the operands' magnitudes
EXACT = Context(prec=MAX_PREC, rounding=ROUND_HALF_EVEN, Emax=MAX_EMAX, Emin=MIN_EMIN)
QUOTIENT_FRACTION_DIGITS = 10
_UNIT_DP: dict[str, int] = {"percent": 1, "currency_usd": 2, "ratio": 3}


def decimal_places(fn: AggFn, unit: Unit, *, integral: bool) -> int | None:
    """Decimal places for a metric, ``None`` meaning exact."""
    if fn in ("count", "count_distinct", "min", "max"):
        return None
    if fn == "share":
        return 1
    if unit in _UNIT_DP:
        return _UNIT_DP[unit]
    if fn == "sum" and integral:
        return None
    return 2


def to_decimal(value: int | float) -> Decimal:
    """Shortest-repr conversion: 0.1 -> Decimal('0.1') (never the binary expansion)."""
    return Decimal(value) if isinstance(value, int) else Decimal(repr(value))


def exact_str(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def exact_sum(values: list[Decimal]) -> Decimal:
    total = Decimal(0)
    for v in values:
        total = EXACT.add(total, v)
    return total


def divide(dividend: Decimal, divisor: Decimal) -> Decimal:
    """``CTX`` (28 significant digits) unless the dividend is so large that fewer than
    :data:`QUOTIENT_FRACTION_DIGITS` fractional digits would remain."""
    prec = max(CTX.prec, dividend.adjusted() + 1 + QUOTIENT_FRACTION_DIGITS)
    return Context(prec=prec, rounding=ROUND_HALF_EVEN).divide(dividend, divisor)


def round_value(value: Decimal, places: int | None) -> int | float:
    if places is None:
        return int(value) if value == value.to_integral_value() else float(value)
    ctx = Context(prec=max(CTX.prec, value.adjusted() + places + 2), rounding=ROUND_HALF_EVEN)
    quantized = value.quantize(Decimal(1).scaleb(-places), context=ctx)
    if not places:
        return int(quantized)
    return float(quantized) if quantized else 0.0  # never "-0.0"
