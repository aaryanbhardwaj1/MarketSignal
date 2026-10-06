"""Claim context for ``[R#]`` numeric support (``generation/results.py``; GROUNDED_ANSWERING §5.8).

Where a claimed figure sits in its unit decides what it may mean. Every rule here is
deterministic and fails closed: a figure whose occurrence cannot be located is unsupported.

* **Clause.** A figure's clause is the text between the nearest separators around it
  (``; : ( )``, an en or em dash, a comma not inside a number, a sentence end, or
  "but/while/whereas/although/though/yet"). Direction words are only read inside the
  figure's clause.
* **Currency context.** A currency written *after* the number ("812.5 EUR", "812.5 euros",
  "812.5 Canadian dollars") or a foreign prefix the number pattern does not parse ("A$812.5",
  a yen/rupee/won/... sign, "CHF 812.5") makes the claim a non-USD currency; "812.5 USD" and
  "812.5 dollars" are USD.
* **Levels are not changes.** A metric value or count (a level) is unsupported when a change
  or comparison word sits next to it: among the four words before it or the three words
  after it, inside its clause and not past a neighbouring figure ("fell 38.2%", "grew by
  38.2%", "38.2% higher", "38% year over year", "North exceeded South by 41%"). A negative
  level stated unsigned needs a negative-direction word next to it, by the same window
  ("declined 4.5"; not "under-30 respondents ... was 5"); a signed claim needs a negative
  value.
* **Differences have a subject.** A group_compare difference is A - B. An unsigned difference
  with no direction word in its clause is supported only when it is positive and the clause
  names it as a gap ("gap", "difference", "between", "vs", ...). With direction words, they
  must all have one polarity; the subject is the group label nearest *before* the direction
  word nearest the figure, else the group *after* it is the object and the other group the
  subject. The stated sign is (positive word ? +1 : -1) * (subject A ? +1 : -1) and must equal
  the sign of A - B ("South exceeded North by 3.2" is -3.2 when A = North). When the spec
  names both groups but neither can be placed, a direction word is unsupported (whose rate
  was higher is unknown). A zero difference supports no direction word.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Final

from marketsignal.generation.contract import NumberMention

Span = tuple[int, int]

_CLAUSE_SEP_RE: Final = re.compile(
    r"[;:()\u2013\u2014]|,(?!\d)|[.!?](?=\s|$)|\s(?:but|while|whereas|although|though|yet)\s",
    re.IGNORECASE,
)
_WORD_RE: Final = re.compile(r"[A-Za-z][A-Za-z'/-]*")
_BEFORE_WORDS: Final = 4
_AFTER_WORDS: Final = 3
_CHANGE_RE: Final = re.compile(
    r"\b(?:ris(?:e|es|en|ing)|rose|f[ae]ll(?:s|en|ing)?|increas\w*|decreas\w*"
    r"|gr[eo]w(?:s|n|ing|th)?|declin\w*|drop(?:s|ped|ping)?|jump\w*|surg\w*|climb\w*|gain\w*"
    r"|slip\w*|plung\w*|soar\w*|tumbl\w*|slump\w*|spik\w*|shr[ai]nk\w*|shrunk"
    r"|(?<!made )(?<!make )(?<!makes )(?<!making )up|(?<!broken )down"
    r"|higher|lower|more|less|fewer|greater|smaller|larger|bigger|above|below|ahead|behind"
    r"|exceed\w*|outperform\w*|underperform\w*|outpac\w*|trail\w*"
    r"|lag(?:s|ged|ging)?|chang\w*|shift\w*|sw[iu]ng\w*|improv\w*|worsen\w*|boost\w*"
    r"|widen\w*|narrow\w*|vs|versus|compared|yoy|y/y|year[ -]over[ -]year|mom|qoq)\b",
    re.IGNORECASE,
)
_NEGATIVE_RE: Final = re.compile(
    r"\b(?:lower|less|fewer|below|behind|trail(?:s|ed|ing)?|declin(?:e|ed|es|ing)"
    r"|decreas(?:e|ed|es|ing)|drop(?:s|ped)?|fell|fall(?:s|en)?|down|negative|minus|smaller"
    r"|worse|lag(?:s|ged)?|loss|shr[ai]nk|shrunk|contract(?:ed|ion)|deficit|under"
    r"|underperform\w*)\b",
    re.IGNORECASE,
)
_POSITIVE_RE: Final = re.compile(
    r"\b(?:higher|more|greater|above|ahead|exceed(?:s|ed)?|increas(?:e|ed|es|ing)|rose"
    r"|ris(?:e|es|en|ing)|up|grew|grow(?:th|s)?|gain(?:s|ed)?|larger|better|positive|plus"
    r"|lead(?:s|ing)?|led|outperform\w*|outpac\w*)\b",
    re.IGNORECASE,
)
_GAP_CUE_RE: Final = re.compile(
    r"\b(?:gap|differen\w*|differ\w*|spread|margin|between|vs|versus|compared|apart)\b",
    re.IGNORECASE,
)
_CODES: Final = (
    "EUR|GBP|JPY|CNY|RMB|INR|CAD|AUD|NZD|CHF|SEK|NOK|DKK|HKD|SGD|KRW|BRL|MXN|ZAR|RUB|TRY|PLN"
    "|AED|SAR|ILS|THB|IDR|MYR|PHP|TWD|CZK|HUF|VND|NGN|EGP|PKR|ARS|CLP|COP"
)
_FOREIGN_AFTER_RE: Final = re.compile(
    rf"[ \t]*(?:(?:{_CODES})\b|(?:euros?|pounds?|sterling|yen|yuan|renminbi|rupees?|francs?"
    r"|pesos?|rubles?|roubles?|kronas?|kronor|kroner|krone|kr|rand|lira|liras|lire|zloty|zlotys"
    r"|ringgit|baht|dirhams?|riyals?|shekels?|dong|naira"
    r"|(?:canadian|australian|hong[ \t]+kong|singapore|new[ \t]+zealand|taiwan(?:ese)?|mexican"
    r"|nt|hk|nz|aussie)[ \t]+dollars?)\b)",
    re.IGNORECASE,
)
_USD_AFTER_RE: Final = re.compile(r"[ \t]*(?:USD|US[ \t]+dollars?|dollars?|bucks)\b", re.I)
_FOREIGN_BEFORE_RE: Final = re.compile(
    rf"(?:[\u00a5\u20b9\u20a9\u20bd\u20ba\u20b1\u20aa\u0e3f\u20ab\u20a6\u20b4\u20a1\u20b2\u20b5"
    rf"\u20b8]|\b(?:{_CODES}|Rs\.?|Fr\.?))[ \t]*$"
)
_DOLLAR_PREFIX_RE: Final = re.compile(r"(?<![A-Za-z])(?:A|AU|C|CA|HK|NZ|S|SG|NT|R|MX)$")


def occurrences(text: str, mention: NumberMention) -> list[Span]:
    """Where ``mention`` is written in ``text`` (not inside a longer number)."""
    pattern = rf"(?<![\d.,]){re.escape(mention.text)}(?!\d|[.,]\d)"
    return [(m.start(), m.end()) for m in re.finditer(pattern, text)]


def clause(text: str, span: Span) -> Span:
    start, end = span
    lo, hi = 0, len(text)
    for sep in _CLAUSE_SEP_RE.finditer(text):
        if sep.end() <= start:
            lo = sep.end()
        elif sep.start() >= end:
            hi = sep.start()
            break
    return lo, hi


def foreign_currency(text: str, spans: Sequence[Span], mention: NumberMention) -> bool:
    for start, end in spans:
        before = text[:start]
        if _FOREIGN_AFTER_RE.match(text, end) or _FOREIGN_BEFORE_RE.search(before):
            return True
        if mention.text.startswith("$") and _DOLLAR_PREFIX_RE.search(before):
            return True
    return False


def usd_suffix(text: str, spans: Sequence[Span]) -> bool:
    return any(_USD_AFTER_RE.match(text, end) for _, end in spans)


def _near(text: str, span: Span, pattern: re.Pattern[str]) -> bool:
    lo, hi = clause(text, span)
    # Only words between this figure and its neighbouring figures ("NPS above 15 cite ... at
    # 38.2%": "above" belongs to 15).
    before = _WORD_RE.findall(re.split(r"\d", text[lo : span[0]])[-1])[-_BEFORE_WORDS:]
    after = _WORD_RE.findall(re.split(r"\d", text[span[1] : hi])[0])[:_AFTER_WORDS]
    return any(pattern.search(" ".join(words)) for words in (before, after))


def level_ok(text: str, spans: Sequence[Span], mention: NumberMention, value: Decimal) -> bool:
    """A metric value or count: stated as a level, never as a change (module rules)."""
    if mention.mantissa < 0:
        return value < 0
    for span in spans:
        if value < 0:
            if not _near(text, span, _NEGATIVE_RE):
                return False
        elif _near(text, span, _CHANGE_RE):
            return False
    return True


def label_ok(text: str, spans: Sequence[Span], mention: NumberMention, value: Decimal) -> bool:
    if mention.mantissa < 0:
        return value < 0
    if value < 0:
        return all(_near(text, span, _NEGATIVE_RE) for span in spans)
    return True


def _positions(text: str, label: str) -> list[int]:
    if not label.strip():
        return []
    pattern = rf"(?<!\w){re.escape(label)}(?!\w)"
    return [m.start() for m in re.finditer(pattern, text, re.IGNORECASE)]


def _subject_is_a(text: str, word: Span, groups: tuple[str, str]) -> bool | None:
    found = [(pos, side) for side, label in zip((True, False), groups, strict=True)
             for pos in _positions(text, label)]  # fmt: skip
    before = [(pos, side) for pos, side in found if pos < word[0]]
    if before:
        return max(before)[1]
    after = [(pos, side) for pos, side in found if pos >= word[1]]
    if after:
        return not min(after)[1]
    return None


def _distance(span: Span, word: Span) -> int:
    return max(word[0] - span[1], span[0] - word[1], 0)


def difference_ok(
    text: str,
    spans: Sequence[Span],
    mention: NumberMention,
    value: Decimal,
    groups: tuple[str, str] | None,
) -> bool:
    """A group_compare A - B difference: direction and subject agree with its sign."""
    if mention.mantissa < 0:
        return value < 0
    for span in spans:
        lo, hi = clause(text, span)
        words = [
            (m.start(), m.end(), positive)
            for positive, pattern in ((True, _POSITIVE_RE), (False, _NEGATIVE_RE))
            for m in pattern.finditer(text, lo, hi)
        ]
        if not words:
            if value <= 0 or not _GAP_CUE_RE.search(text[lo:hi]):
                return False
            continue
        if value == 0 or len({positive for _, _, positive in words}) > 1:
            return False
        start, end, positive = min(words, key=lambda w: _distance(span, (w[0], w[1])))
        subject_a = True if groups is None else _subject_is_a(text, (start, end), groups)
        if subject_a is None or (positive == subject_a) != (value > 0):
            return False
    return True
