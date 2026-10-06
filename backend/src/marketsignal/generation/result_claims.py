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
  value. "vs"/"versus"/"compared" with a figure on its other side is juxtaposition ("4.22
  for App versus 4.18 for Marketplace"), not a change; gap nouns ("lead", "gap",
  "difference", "leads by") next to a level are; "leads with 209 reviews" is a level. The
  far-side figure must be of the same kind and not a year. "Fall into" is classification.
* **Names are not claims.** Direction and change words are read with the result's labels
  (group levels, filter operands, the table title; matched case-sensitively, as shown) and
  the words (3+ letters) of the *figure's own* column name blanked: "Trail Starters is 76"
  has no "trail", "mean YoY growth is 6.7%" names the metric. Another column's name never
  blanks anything; a count (numerator, denominator) blanks its metric's direction-like words
  only after the count and before a count noun ("15 carry a growth figure"; never "YoY
  growth was 15" or "the price change value was 120"); a label
  that is itself a direction word ("Up") is never blanked.
* **Digits in names.** A plain number inside a label (case-sensitive) is part of the name
  only when glued to a letter ("NS-KR2", "Q4") or after a capitalised word that is not a
  quantity word ("Crew Sock 3 Pack", "Knit Runner 2"); never at a label's start ("5 stars")
  or after "Over"/"Top"/"Under"/... ("Over 65").
* **Rows scanned** back a plain count only next to strong scanned/total wording ("600 rows
  scanned", "600 respondents in total", "in the dataset") or right after "(out) of (the)",
  and, for a filtered result, never in a clause naming one of its subgroups (filter operands
  or group levels, case-insensitive): "76 of 600 Trail Starters" is a subgroup.
* **Differences have a subject.** A group_compare difference is A - B. An unsigned difference
  with no direction word in its clause is supported only when it is positive and its clause
  names it as a gap ("gap", "difference", "between", "vs", ...; for this cue a parenthesis
  does not end the clause: "The difference (A minus B) is 0.03"). A group label that is
  itself a direction word ("Up", "Lower") supports no unsigned difference, and a group
  position overlapping a direction word is not a position. With direction words, they
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

from marketsignal.generation.contract import NumberMention, extract_numbers

Span = tuple[int, int]

_CLAUSE_SEP_RE: Final = re.compile(
    r"[;:()\u2013\u2014]|,(?!\d)|[.!?](?=\s|$)|\s(?:but|while|whereas|although|though|yet)\s",
    re.IGNORECASE,
)
# The gap cue of an unsigned difference reads across a parenthesis ("difference (A - B) is").
_CUE_SEP_RE: Final = re.compile(
    r"[;:\u2013\u2014]|,(?!\d)|[.!?](?=\s|$)|\s(?:but|while|whereas|although|though|yet)\s",
    re.IGNORECASE,
)
_WORD_RE: Final = re.compile(r"[A-Za-z][A-Za-z'/-]*")
_JUXTAPOSE_RE: Final = re.compile(r"\b(?:vs|versus|compared)\b", re.IGNORECASE)
_JUXTAPOSE_WORDS: Final = 4
_SCANNED_RE: Final = re.compile(
    r"\b(?:scanned|total|overall|entire|whole|dataset|table|sheet)\b", re.IGNORECASE
)
_OF_BEFORE_RE: Final = re.compile(r"\b(?:out[ \t]+)?of[ \t]+(?:the[ \t]+)?$", re.IGNORECASE)
_COUNT_NOUN_AFTER_RE: Final = re.compile(
    r"[ \t]+(?:figures?|values?|rows?|entries|records|data|readings|numbers?)\b", re.IGNORECASE
)
_QUANTITY_WORDS: Final = frozenset(
    {
        "over",
        "under",
        "above",
        "below",
        "top",
        "bottom",
        "up",
        "to",
        "less",
        "more",
        "than",
        "plus",
        "least",
        "most",
        "first",
        "last",
        "aged",
        "age",
        "ages",
        "min",
        "max",
        "minimum",
        "maximum",
        "at",
        "from",
        "between",
        "and",
        "or",
        "no",
        "not",
        "only",
        "next",
        "past",
        "within",
        "upto",
        "the",
        "a",
        "an",
        "about",
        "around",
        "approx",
        "approximately",
        "roughly",
        "nearly",
        "almost",
        "exactly",
        "just",
        "some",
        "every",
        "each",
        "per",
        "circa",
        "",
    }
)
_BEFORE_WORDS: Final = 4
_AFTER_WORDS: Final = 3
# "76 respondents fall into the Trail Starters segment": classification, not a change.
_NOT_CATEGORY: Final = r"(?![ \t]+into\b)"
_CHANGE_RE: Final = re.compile(
    rf"\b(?:ris(?:e|es|en|ing)|rose|f[ae]ll(?:s|en|ing)?{_NOT_CATEGORY}|increas\w*|decreas\w*"
    r"|gr[eo]w(?:s|n|ing|th)?|declin\w*|drop(?:s|ped|ping)?|jump\w*|surg\w*|climb\w*|gain\w*"
    r"|slip\w*|plung\w*|soar\w*|tumbl\w*|slump\w*|spik\w*|shr[ai]nk\w*|shrunk"
    r"|(?<!made )(?<!make )(?<!makes )(?<!making )up|(?<!broken )down"
    r"|higher|lower|more|less|fewer|greater|smaller|larger|bigger|above|below|ahead|behind"
    r"|exceed\w*|outperform\w*|underperform\w*|outpac\w*|trail\w*"
    r"|lag(?:s|ged|ging)?|chang\w*|shift\w*|sw[iu]ng\w*|improv\w*|worsen\w*|boost\w*"
    r"|widen\w*|narrow\w*|vs|versus|compared|gaps?|difference|lead"
    r"|leads?[ \t]+by|leading[ \t]+by|led[ \t]+by"
    r"|yoy|y/y|year[ -]over[ -]year|mom|qoq)\b",
    re.IGNORECASE,
)
_NEGATIVE_RE: Final = re.compile(
    r"\b(?:lower|less|fewer|below|behind|trail(?:s|ed|ing)?|declin(?:e|ed|es|ing)"
    rf"|decreas(?:e|ed|es|ing)|drop(?:s|ped)?|(?:fell|fall(?:s|en)?){_NOT_CATEGORY}|down|negative"
    r"|minus|smaller"
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


def label_spans(text: str, labels: Sequence[str]) -> list[Span]:
    """Where each label is written in ``text``, exactly as shown (case-sensitive, not inside
    a longer word)."""
    return [
        (m.start(), m.end())
        for label in labels
        if label.strip()
        for m in re.finditer(rf"(?<!\w){re.escape(label)}(?!\w)", text)
    ]


def _part_of_name(text: str, span: Span, label: Span) -> bool:
    lo, hi = label
    if not (lo <= span[0] and span[1] <= hi):
        return False
    if (span[0] > lo and text[span[0] - 1].isalpha()) or (span[1] < hi and text[span[1]].isalpha()):
        return True  # glued to a letter: "NS-KR2", "Q4"
    previous = _WORD_RE.findall(text[lo : span[0]])
    return (
        bool(previous)
        and previous[-1][0].isupper()
        and (previous[-1].lower() not in _QUANTITY_WORDS)
    )


def inside_labels(text: str, spans: Sequence[Span], labels: Sequence[str]) -> bool:
    """Every occurrence of a number is part of a label's name (module rules, "Digits in
    names")."""
    named = label_spans(text, labels)
    return bool(spans) and all(any(_part_of_name(text, s, n) for n in named) for s in spans)


def blank(
    text: str,
    labels: Sequence[str],
    terms: frozenset[str],
    noun_terms: frozenset[str] = frozenset(),
    after: int = 0,
) -> str:
    """``text`` with every label and column-name word replaced by spaces (same length, so
    spans still line up): what direction and change words are read from. A label that is
    only a direction word ("Up") is never blanked; ``noun_terms`` are blanked only at or after
    ``after`` (the counted figure's end) and before a count noun ("15 carry a growth figure",
    never "the growth figure was 15")."""
    chars = list(text)
    spans = label_spans(text, [label for label in labels if not is_direction_word(label)])
    for m in _WORD_RE.finditer(text):
        word = m.group().lower()
        counted = m.start() >= after and _COUNT_NOUN_AFTER_RE.match(text, m.end())
        if word in terms or (word in noun_terms and counted):
            spans.append((m.start(), m.end()))
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def occurrences(text: str, mention: NumberMention) -> list[Span]:
    """Where ``mention`` is written in ``text`` (not inside a longer number)."""
    pattern = rf"(?<![\d.,]){re.escape(mention.text)}(?!\d|[.,]\d)"
    return [(m.start(), m.end()) for m in re.finditer(pattern, text)]


def clause(text: str, span: Span, separators: re.Pattern[str] = _CLAUSE_SEP_RE) -> Span:
    start, end = span
    lo, hi = 0, len(text)
    for sep in separators.finditer(text):
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


def _comparable(snippet: str, mention: NumberMention | None) -> bool:
    """``snippet`` holds a figure of the same kind as ``mention`` (never a year)."""
    for other in extract_numbers(snippet):
        if other.temporal:
            continue
        if mention is None or (
            other.percent == mention.percent
            and (other.currency is None) == (mention.currency is None)
            and other.labelled == mention.labelled
        ):
            return True
    return False


def _unjuxtaposed(text: str, span: Span, lo: int, hi: int, mention: NumberMention | None) -> str:
    """``text`` with each "vs"/"versus"/"compared" blanked when a comparable figure sits
    within a few words on its far side ("4.22 for App versus 4.18 for Marketplace")."""
    chars = list(text)
    for word in _JUXTAPOSE_RE.finditer(text, lo, hi):
        if word.end() <= span[0]:
            other = " ".join(text[lo : word.start()].split()[-_JUXTAPOSE_WORDS:])
        else:
            other = " ".join(text[word.end() : hi].split()[:_JUXTAPOSE_WORDS])
        if _comparable(other, mention):
            chars[word.start() : word.end()] = " " * (word.end() - word.start())
    return "".join(chars)


def _near(
    text: str, span: Span, pattern: re.Pattern[str], mention: NumberMention | None = None
) -> bool:
    lo, hi = clause(text, span)
    text = _unjuxtaposed(text, span, lo, hi, mention)
    # Only words between this figure and its neighbouring figures ("NPS above 15 cite ... at
    # 38.2%": "above" belongs to 15).
    before = _WORD_RE.findall(re.split(r"\d", text[lo : span[0]])[-1])[-_BEFORE_WORDS:]
    after = _WORD_RE.findall(re.split(r"\d", text[span[1] : hi])[0])[:_AFTER_WORDS]
    return any(pattern.search(" ".join(words)) for words in (before, after))


def scanned_ok(
    text: str, words: str, spans: Sequence[Span], mention: NumberMention, subgroups: Sequence[str]
) -> bool:
    """The rows scanned: a plain count next to strong scanned/total wording, or right after
    "(out) of (the)", and never in a clause naming a subgroup of a filtered result ("76 of 600
    Trail Starters", "Trail Starters total 600"; case-insensitive)."""
    if mention.mantissa < 0:
        return False
    for span in spans:
        lo, hi = clause(text, span)
        named = text[lo:hi].lower()
        if any(g.strip() and re.search(rf"(?<!\w){re.escape(g.lower())}(?!\w)", named)
               for g in subgroups):  # fmt: skip
            return False
        if not (_near(words, span, _SCANNED_RE) or _OF_BEFORE_RE.search(text[: span[0]])):
            return False
    return True


def level_ok(text: str, spans: Sequence[Span], mention: NumberMention, value: Decimal) -> bool:
    """A metric value or count: stated as a level, never as a change (module rules)."""
    if mention.mantissa < 0:
        return value < 0
    for span in spans:
        if value < 0:
            if not _near(text, span, _NEGATIVE_RE):
                return False
        elif _near(text, span, _CHANGE_RE, mention):
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


def _subject_is_a(
    text: str, word: Span, groups: tuple[str, str], directions: Sequence[Span] = ()
) -> bool | None:
    found = [(pos, side) for side, label in zip((True, False), groups, strict=True)
             for pos in _positions(text, label)
             if not any(lo < pos + len(label) and pos < hi for lo, hi in directions)]  # fmt: skip
    before = [(pos, side) for pos, side in found if pos < word[0]]
    if before:
        return max(before)[1]
    after = [(pos, side) for pos, side in found if pos >= word[1]]
    if after:
        return not min(after)[1]
    return None


def is_direction_word(label: str) -> bool:
    stripped = label.strip()
    return any(p.fullmatch(stripped) for p in (_POSITIVE_RE, _NEGATIVE_RE, _CHANGE_RE))


def _distance(span: Span, word: Span) -> int:
    return max(word[0] - span[1], span[0] - word[1], 0)


def difference_ok(
    text: str,
    spans: Sequence[Span],
    mention: NumberMention,
    value: Decimal,
    groups: tuple[str, str] | None,
    *,
    words: str | None = None,
) -> bool:
    """A group_compare A - B difference: direction and subject agree with its sign.
    Direction words are read from ``words`` (``text`` with names blanked, see :func:`blank`);
    group positions from ``text``."""
    if mention.mantissa < 0:
        return value < 0
    if groups is not None and any(is_direction_word(g) for g in groups):
        return False  # "Up is 0.03 down": which side a direction word names is unknowable
    scan = text if words is None else words
    for span in spans:
        lo, hi = clause(text, span)
        found = [
            (m.start(), m.end(), positive)
            for positive, pattern in ((True, _POSITIVE_RE), (False, _NEGATIVE_RE))
            for m in pattern.finditer(scan, lo, hi)
        ]
        if not found:
            if value <= 0 or not _GAP_CUE_RE.search(scan, *clause(text, span, _CUE_SEP_RE)):
                return False
            continue
        if value == 0 or len({positive for _, _, positive in found}) > 1:
            return False
        start, end, positive = min(found, key=lambda w: _distance(span, (w[0], w[1])))
        directions = [(w[0], w[1]) for w in found]
        subject_a = (
            True if groups is None else _subject_is_a(text, (start, end), groups, directions)
        )
        if subject_a is None or (positive == subject_a) != (value > 0):
            return False
    return True
