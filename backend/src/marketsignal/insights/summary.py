"""The analysis text number check (curated brief v2).

A curated analysis carries a one-sentence plain-language ``summary`` and an optional
``interpretation``. Each is shown only when the analysis recomputed (``computed``) and every
number in it equals a computed row's value or display string, a row's denominator, or the
analysis denominator. Otherwise it is withheld (``unverified``).

What counts as a number (:func:`numbers_in`):

* Digits, an optional decimal part, and leading-decimal figures (".5" is 0.5).
* Commas join digits only as thousands groups ("2,146,098"); "18,27" is two numbers.
* A currency sign or a percent sign is ignored ("27%" matches a row of 27.0 shown as "27.0%").
* Period labels — ``Q1``-``Q4``, ``H1``/``H2`` and ``FY`` plus two or four digits — are removed
  first; they name a period, not a figure. Any other digits glued to letters still count
  ("x30", "USD30M", "top10"), so an unknown label fails closed.
* Sign: a ``-``, a minus sign (U+2212) or ``+`` immediately before the number, and not after a
  letter or digit (so "9-10" is a range, not -10), is an explicit sign. A signed figure must
  equal an allowed value with that sign; an unsigned figure is compared by magnitude, so "fell
  3.2 points" matches -3.2 (and so does "rose 3.2 points": the direction word is not checked).

Not checked: quantities spelled out in words ("three times", "two thirds"). The check is a
guard against invented figures, not proof that every quantity in the sentence is grounded.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

SummaryStatus = Literal["verified", "unverified", "absent"]
LABEL = re.compile(r"\b(?:Q[1-4]|H[12]|FY(?:\d{4}|\d{2}))\b")
NUMBER = re.compile(
    r"(?:(?<![A-Za-z0-9])(?P<sign>[-\u2212+]))?"
    r"(?<![0-9])(?P<num>(?:\d{1,3}(?:,\d{3})+(?![0-9])|\d+)(?:\.\d+)?|\.\d+)"
)


def _decimal(text: str, negative: bool = False) -> Decimal | None:
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None
    return (-value if negative else value).normalize()


def _figures(text: str) -> list[tuple[Decimal, bool]]:
    """``(value, explicitly signed)`` for every number in ``text``."""
    out = []
    for m in NUMBER.finditer(LABEL.sub(" ", text)):
        sign = m.group("sign")
        value = _decimal(m.group("num"), negative=sign in ("-", "\N{MINUS SIGN}"))
        if value is not None:
            out.append((value, sign is not None))
    return out


def numbers_in(text: str) -> set[Decimal]:
    """Every number in ``text`` as a normalized decimal, negative only when explicitly signed."""
    return {value for value, _signed in _figures(text)}


def unmatched(text: str, allowed: set[Decimal]) -> set[Decimal]:
    """The numbers in ``text`` that ``allowed`` does not support: a signed figure must match
    with its sign, an unsigned one by magnitude."""
    magnitudes = {abs(a) for a in allowed}
    return {
        value
        for value, signed in _figures(text)
        if (value not in allowed if signed else abs(value) not in magnitudes)
    }


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return _decimal(str(value))


def allowed_numbers(payload: dict[str, Any]) -> set[Decimal]:
    """The figures a summary may repeat: computed rows and denominators of a contract
    ``Analysis``."""
    allowed: set[Decimal] = set()
    for row in payload.get("rows") or []:
        for cell in (row.get("value"), row.get("denominator")):
            if (n := _number(cell)) is not None:
                allowed.add(n)
        allowed |= numbers_in(row.get("display") or "")
    denominator = payload.get("denominator") or {}
    if (n := _number(denominator.get("value"))) is not None:
        allowed.add(n)
    return allowed


def check_text(text: str | None, payload: dict[str, Any]) -> tuple[str | None, SummaryStatus]:
    """``(text, "verified")``, ``(None, "unverified")`` or ``(None, "absent")``."""
    if not text or not text.strip():
        return None, "absent"
    if payload.get("status") != "computed":
        return None, "unverified"
    if unmatched(text, allowed_numbers(payload)):
        return None, "unverified"
    return text, "verified"


check_summary = check_text
