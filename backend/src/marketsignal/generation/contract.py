"""The answer contract as deterministic text primitives (plan §3.1, ADR-0004, spec §3-§4).

The model answers in plain markdown with fixed section headings (no JSON mode: native
citations and structured outputs do not combine), so everything the verifier checks has to be
recovered from text by rules that never guess:

* :func:`parse_sections` maps ``##``-``####`` headings onto the five canonical sections.
  Anything else (preamble, unknown headings) is kept under ``unrecognized`` so the verifier
  can drop it visibly instead of silently rendering it.
* :func:`split_units` segments a section into checkable *units*: one per bullet, one per
  sentence elsewhere. The splitter is conservative (decimals, abbreviations, citations and
  inline code never split; a lowercase continuation never starts a sentence), because a
  false split strands a citation away from the claim it supports.
* :func:`extract_numbers` finds numeric claims and normalises them to (mantissa, scaled
  value) so "$612.0 million", "612.0" and "$612.0M" compare equal. Numbers glued to letters
  (``Q2``, ``FY26``, ``R0147``, ``3rd``) are identifiers, not claims, except common unit
  suffixes (``340bps``, ``3.2pp``, ``12pts``, ``99pct``). Spelled-out cardinals are claims
  only with a magnitude word or "percent" ("nine hundred million", "twenty-one percent");
  a bare "twenty" or "one" is not checked (known limit, as are fractions like "a third").
  :func:`supports` compares units: when both sides state a scale they must agree, a percent
  claim needs percent evidence or a bare unlabelled figure (a table cell), and stated
  currencies must match.
* :func:`strip_leaks` removes what must never reach the UI: URLs, images, links (text kept),
  HTML, UUIDs, child-id fragments, raw handles and canonical ``[[...]]`` markers, which only
  the verifier itself may write. Removal repeats until nothing changes, so a removal can
  never reassemble a marker.
"""

from __future__ import annotations

import itertools
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final

ANSWER: Final = "answer"
FINDINGS: Final = "findings"
CONFLICTS: Final = "conflicts"
INTERPRETATION: Final = "interpretation"
GAPS: Final = "gaps"
UNRECOGNIZED: Final = "unrecognized"

SECTION_ORDER: Final[tuple[str, ...]] = (ANSWER, FINDINGS, CONFLICTS, INTERPRETATION, GAPS)
SECTION_TITLES: Final[Mapping[str, str]] = MappingProxyType(
    {
        ANSWER: "Answer",
        FINDINGS: "Key findings",
        CONFLICTS: "Conflicting evidence",
        INTERPRETATION: "Interpretation",
        GAPS: "Gaps & unknowns",
    }
)
# Normalised heading text -> section key ("&" is folded to "and", case and emphasis ignored).
_HEADING_KEYS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "answer": ANSWER,
        "key findings": FINDINGS,
        "conflicting evidence": CONFLICTS,
        "interpretation": INTERPRETATION,
        "gaps and unknowns": GAPS,
    }
)

# Anything shaped like an alias citation, including malformed ones ([E], [E123], [e3], [ E3 ],
# [E1, E2]). Only an exact ``[E\d{1,2}]`` naming a pack item survives verification.
ALIASISH_RE: Final = re.compile(r"\[\s*[Ee]\s*\d*(?:\s*,\s*[Ee]?\s*\d+)*\s*\]")
INFERENCE_RE: Final = re.compile(r"\[\s*inference\s*\]", re.IGNORECASE)
CANONICAL_MARKER_RE: Final = re.compile(r"\[\[[^\[\]\n]{0,120}\]\]")
_MARKER: Final = rf"{CANONICAL_MARKER_RE.pattern}|{ALIASISH_RE.pattern}|(?i:{INFERENCE_RE.pattern})"
_MARKERS_RE: Final = re.compile(_MARKER)

# --------------------------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------------------------

_HEADING_RE: Final = re.compile(r"^ {0,3}(#{2,4})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE_RE: Final = re.compile(r"^ {0,3}(?:```|~~~)")


def section_key(heading: str) -> str:
    """Canonical key for a heading's text, or ``unrecognized``."""
    text = heading.replace("&amp;", "&")
    text = re.sub(r"[*_`]", "", text).strip().rstrip(":").replace("&", " and ")
    return _HEADING_KEYS.get(" ".join(text.lower().split()), UNRECOGNIZED)


def parse_sections(text: str) -> dict[str, str]:
    """Ordered ``section -> raw text`` (by first appearance); repeated sections concatenate.

    Recognised sections are kept even when empty (presence matters to the verifier);
    ``unrecognized`` is present only when it holds non-blank text. Headings inside fenced
    code blocks are not headings.
    """
    buckets: dict[str, list[str]] = {}
    current = UNRECOGNIZED
    in_fence = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING_RE.match(line)
        if heading is not None:
            current = section_key(heading.group(2))
            if current in buckets:
                buckets[current].append("")
            else:
                buckets[current] = []
            continue
        buckets.setdefault(current, []).append(line)
    sections = {key: "\n".join(lines).strip() for key, lines in buckets.items()}
    if not sections.get(UNRECOGNIZED):
        sections.pop(UNRECOGNIZED, None)
    return sections


# --------------------------------------------------------------------------------------------
# Units (bullets and sentences)
# --------------------------------------------------------------------------------------------

_BULLET_RE: Final = re.compile(r"^\s*(?:[-*+\u2022]|\d{1,3}[.)])\s+(.*)$")
_RULE_RE: Final = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_QUOTE_RE: Final = re.compile(r"^\s*>\s?")
_PROTECTED_RE: Final = re.compile(r"`[^`]*`|\[\[[^\[\]]*\]\]|\[[^\[\]]*\]|(?:https?://|www\.)\S+")
_TERMINATOR_RE: Final = re.compile(r"[.!?]+[\"'\u201d\u2019)\]*_]*(?=\s|$)")
_TRAILING_MARKERS_RE: Final = re.compile(rf"(?:\s*(?:{_MARKER}))+")
_ABBREVIATIONS: Final = frozenset(
    {
        "e.g", "i.e", "vs", "cf", "al", "approx", "est", "avg", "inc", "co", "corp", "ltd",
        "llc", "plc", "fig", "mr", "mrs", "ms", "dr", "st", "jr", "sr", "u.s", "u.k", "jan",
        "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    }
)  # fmt: skip
_NUMBER_ABBREVIATIONS: Final = frozenset({"no", "nos"})  # "No. 3", but "the answer is no."


def _blocks(text: str) -> list[tuple[bool, str]]:
    """``(is_bullet, joined text)`` blocks; blank lines, rules and fences separate blocks."""
    blocks: list[tuple[bool, str]] = []
    lines: list[str] = []
    is_bullet = False
    for raw_line in text.splitlines():
        line = _QUOTE_RE.sub("", raw_line, count=1)
        bullet = _BULLET_RE.match(line)
        breaks = not line.strip() or _RULE_RE.match(line) or _FENCE_RE.match(line)
        if (breaks or bullet) and lines:
            blocks.append((is_bullet, " ".join(lines)))
            lines = []
        if breaks:
            continue
        if bullet is not None:
            is_bullet, lines = True, [bullet.group(1).strip()]
            continue
        if not lines:
            is_bullet = False
        lines.append(line.strip())  # a non-bullet line right after a bullet continues it
    if lines:
        blocks.append((is_bullet, " ".join(lines)))
    return blocks


def split_units(section_text: str) -> list[str]:
    """One unit per bullet; paragraphs are split into sentences (see :func:`split_sentences`)."""
    units: list[str] = []
    for is_bullet, text in _blocks(section_text):
        if is_bullet:
            units.append(" ".join(text.split()))
        else:
            units.extend(split_sentences(text))
    return [unit for unit in units if unit]


def _is_abbreviation(text: str, terminator: re.Match[str]) -> bool:
    if terminator.group(0)[:1] != "." or terminator.group(0).startswith(".."):
        return False
    before = text[: terminator.start()].rsplit(maxsplit=1)
    token = before[-1].lstrip("([\"'*_\u201c\u2018") if before else ""
    lowered = token.lower()
    if lowered in _NUMBER_ABBREVIATIONS:
        return text[terminator.end() :].lstrip()[:1].isdigit()
    return lowered in _ABBREVIATIONS or (len(token) == 1 and token.isupper())


def split_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences, keeping citations attached to their sentence.

    A boundary is terminal punctuation (plus closing quotes, brackets or emphasis) followed by
    whitespace, not inside a protected span (citations, inline code, URLs), not after a known
    abbreviation, and not followed by a lowercase letter. Citation or ``[inference]`` markers
    right after the punctuation (``"... 27%. [E2] Next"``) belong to the preceding sentence.
    """
    text = " ".join(text.split())
    protected = [(m.start(), m.end()) for m in _PROTECTED_RE.finditer(text)]
    sentences: list[str] = []
    start = 0
    for terminator in _TERMINATOR_RE.finditer(text):
        pos = terminator.start()
        if pos < start or any(lo <= pos < hi for lo, hi in protected):
            continue
        if _is_abbreviation(text, terminator):
            continue
        end = terminator.end()
        trailing = _TRAILING_MARKERS_RE.match(text, end)
        if trailing is not None:
            end = trailing.end()
        rest = text[end:].lstrip()
        if rest[:1].islower():
            continue
        sentence = text[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


# --------------------------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------------------------

REL_TOL: Final = 1e-6
_SCALES: Final[Mapping[str, float]] = MappingProxyType(
    {
        "thousand": 1e3, "k": 1e3,
        "million": 1e6, "m": 1e6, "mn": 1e6, "mm": 1e6,
        "billion": 1e9, "b": 1e9, "bn": 1e9,
        "trillion": 1e12, "t": 1e12, "tn": 1e12,
    }
)  # fmt: skip
_CURRENCIES: Final[Mapping[str, str]] = MappingProxyType(
    {"$": "USD", "US$": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP"}
)
# Glued unit suffixes ("340bps", "3.2pp", "12pts") are claim units, not identifier glue.
_NUMBER_RE: Final = re.compile(
    r"""
    (?P<sign>[-\u2212](?=(?:US\$|[$€£])?\d))?
    (?P<cur>US\$|[$€£]|(?:USD|EUR|GBP)[ \t]?)?
    (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    (?:
        [ \t]?(?P<word>thousand|million|billion|trillion)
      | [ \t]?(?P<abbr>bn|mn|mm|tn)
      | (?P<suffix>[kKmMbBtT])
    )?
    (?P<mult>[x\u00d7])?
    (?P<unit>bps|bp|ppts|ppt|pp|pts|pt)?
    (?:[ \t]?(?P<pct>%|percent(?!age)|per[ \t]cent|pct))?
    (?![A-Za-z0-9_]|[.,]\d)
    """,
    re.VERBOSE,
)
_ORDINAL_RE: Final = re.compile(r"^[ \t]*(?:[-*+\u2022][ \t]+)?\d{1,3}[.)][ \t]+", re.MULTILINE)
# Spelled-out cardinals count only with a magnitude word or "percent" ("nine hundred million",
# "twenty-one percent"); bare "one"/"twenty" are too often prose ("one of the drivers").
_UNITS: Final = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen",
)  # fmt: skip
_TENS: Final = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_SMALL_NUMBERS: Final[Mapping[str, int]] = MappingProxyType(
    {word: value for value, word in enumerate(_UNITS)}
    | {word: 10 * tens for tens, word in enumerate(_TENS, start=2)}
)
_CARDINAL: Final = "|".join(sorted(_SMALL_NUMBERS, key=len, reverse=True))
_MAGNITUDE: Final = "hundred|thousand|million|billion|trillion"
_WORD_NUMBER_RE: Final = re.compile(
    rf"\b(?P<words>(?:{_CARDINAL})(?:(?:[ \t]+and)?[ \t-]+(?:{_CARDINAL}|{_MAGNITUDE}))*)"
    r"(?:[ \t]+(?P<pct>percent(?!age)|per[ \t]cent))?\b",
    re.IGNORECASE,
)
_RANGE_GAP_RE: Final = re.compile(r"(?:[ \t]*(?:to|and|or|[-\u2013\u2014])[ \t]*)?", re.IGNORECASE)
_UNIT_WORD_RE: Final = re.compile(r"[ \t]*([A-Za-z]+)")
_LABEL_RE: Final = re.compile(r"([A-Za-z][^:=;|\n]{0,40}?)[ \t]*[:=][ \t]*$")
_PERCENT_CUE_RE: Final = re.compile(r"%|percent|pct|share|rate|margin|ratio|proportion", re.I)
_FUNCTION_WORDS: Final = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "is", "of", "on", "or",
        "per", "than", "the", "to", "versus", "vs", "was", "were", "with",
    }
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class NumberMention:
    """One numeric claim. ``mantissa`` is the number as written; ``value`` applies the scale.

    ``labelled`` means the figure carries an explicit non-percent unit: a unit word or suffix
    after it ("2,960 respondents", "340bps", "5x") or a ``label:`` before it whose label is
    not percent-like ("Respondents: 2,960").
    """

    text: str
    mantissa_text: str  # digits as written, separators removed ("2,960" -> "2960")
    mantissa: float
    value: float
    percent: bool
    currency: str | None
    scale: float = 1.0
    labelled: bool = False


def _glued(text: str, match: re.Match[str]) -> tuple[bool, bool]:
    """``(is_identifier, sign_is_range_dash)`` from the characters before the match."""
    if match.group("cur"):
        return False, False  # a currency symbol delimits ("A$5", "US$5")
    start = match.start()
    prev = text[start - 1] if start > 0 else ""
    before = text[start - 2] if start > 1 else ""
    if match.group("sign"):
        if prev.isalpha():
            return True, False  # "COVID-19"
        return False, prev.isdigit()  # "14-21" is a range, not -21
    if prev.isalnum() or prev == "_":
        return True, False  # "Q2", "FY26", "R0147", "E3", "v1"
    if prev in ".," and before.isdigit():
        return True, False  # tail of a version-like token ("1.2.3")
    if prev in "-/" and before.isalpha():
        return True, False  # "SURVEY-2026", "NS-KR2"
    return False, False


def _labelled(text: str, start: int, end: int) -> bool:
    """True if the figure at ``text[start:end]`` carries an explicit non-percent unit."""
    after = _UNIT_WORD_RE.match(text, end)
    if after is not None and after.group(1).lower() not in _FUNCTION_WORDS:
        return True
    label = _LABEL_RE.search(text, max(0, start - 48), start)
    return label is not None and _PERCENT_CUE_RE.search(label.group(1)) is None


_Span = tuple[int, int, NumberMention]


def _digit_mention(text: str, match: re.Match[str]) -> NumberMention | None:
    identifier, range_dash = _glued(text, match)
    if identifier:
        return None
    negative = bool(match.group("sign")) and not range_dash
    mantissa_text = match.group("num").replace(",", "")
    scale_word = match.group("word") or match.group("abbr") or match.group("suffix") or ""
    scale = _SCALES.get(scale_word.lower(), 1.0)
    mantissa = (-1.0 if negative else 1.0) * float(mantissa_text)
    written = match.group(0)
    if match.group("sign") and not negative:
        written = written[1:]
    explicit_unit = bool(match.group("unit") or match.group("mult"))
    return NumberMention(
        text=written.strip(),
        mantissa_text=mantissa_text,
        mantissa=mantissa,
        value=mantissa * scale,
        percent=bool(match.group("pct")),
        currency=(match.group("cur") or "").strip() or None,
        scale=scale,
        labelled=explicit_unit or _labelled(text, match.start(), match.end()),
    )


def _spelled_value(words: str) -> tuple[float, float]:
    """``(mantissa, scale)`` of a spelled-out cardinal ("nine hundred million" -> 900, 1e6)."""
    total, current, last_scale = 0.0, 0.0, 1.0
    for word in re.findall(r"[a-z]+", words.lower()):
        if word in _SMALL_NUMBERS:
            current += _SMALL_NUMBERS[word]
        elif word == "hundred":
            current = (current or 1.0) * 100
        elif word in _SCALES:
            total += (current or 1.0) * _SCALES[word]
            current, last_scale = 0.0, _SCALES[word]
    if total and not current:
        return total / last_scale, last_scale
    return total + current, 1.0


def _spelled_spans(text: str) -> list[_Span]:
    spans: list[_Span] = []
    for match in _WORD_NUMBER_RE.finditer(text):
        words, pct = match.group("words"), bool(match.group("pct"))
        if not pct and not re.search(rf"\b(?:{_MAGNITUDE})\b", words, re.IGNORECASE):
            continue
        mantissa, scale = _spelled_value(words)
        mention = NumberMention(
            text=match.group(0),
            mantissa_text=str(int(mantissa)) if mantissa.is_integer() else str(mantissa),
            mantissa=mantissa,
            value=mantissa * scale,
            percent=pct,
            currency=None,
            scale=scale,
            labelled=_labelled(text, match.start(), match.end()),
        )
        spans.append((match.start(), match.end(), mention))
    return spans


def _propagate_ranges(text: str, spans: list[_Span]) -> list[NumberMention]:
    """A bare range start takes the percent of the range end ("14 to 21 percent")."""
    mentions = [mention for _, _, mention in spans]
    for i, ((_, end, low), (start, _, high)) in enumerate(itertools.pairwise(spans)):
        bare = low.scale == 1.0 and low.currency is None and not low.percent
        if bare and high.percent and _RANGE_GAP_RE.fullmatch(text, end, start):
            mentions[i] = replace(low, percent=True, labelled=False)
    return mentions


def extract_numbers(text: str) -> list[NumberMention]:
    """Numeric claims in ``text`` (citation markers and line-start list ordinals ignored)."""
    cleaned = _ORDINAL_RE.sub("", _MARKERS_RE.sub(" ", text))
    spans: list[_Span] = _spelled_spans(cleaned)
    for match in _NUMBER_RE.finditer(cleaned):
        mention = _digit_mention(cleaned, match)
        if mention is not None:
            spans.append((match.start(), match.end(), mention))
    return _propagate_ranges(cleaned, sorted(spans, key=lambda span: span[0]))


def number_values(texts: Iterable[str]) -> tuple[NumberMention, ...]:
    """Every number stated in ``texts`` (the evidence side of :func:`is_faithful`)."""
    return tuple(mention for text in texts for mention in extract_numbers(text))


def _bare(mention: NumberMention) -> bool:
    return mention.scale == 1.0 and mention.currency is None and not mention.labelled


def _units_agree(claim: NumberMention, evidence: NumberMention) -> bool:
    """Percent and currency must agree; a bare figure (a table cell) may stand for a percent."""
    if claim.percent != evidence.percent:
        return _bare(evidence if claim.percent else claim)
    if claim.currency is None or evidence.currency is None:
        return True
    return _CURRENCIES.get(claim.currency) == _CURRENCIES.get(evidence.currency)


def _same(a: float, b: float) -> bool:
    return math.isclose(abs(a), abs(b), rel_tol=REL_TOL)


def supports(claim: NumberMention, evidence: NumberMention) -> bool:
    """True if one evidence figure backs one claimed figure.

    Scaled values must agree ("612,000,000" = "$612.0M"). The mantissa alone is enough only
    when at most one side states a scale, so a bare table cell ("612.0", units in a header)
    backs "$612.0 million" but "612.0 million" never backs "612.0 billion". Sign is ignored
    ("fell 3.2%" and "-3.2%" state the same figure).
    """
    if not _units_agree(claim, evidence):
        return False
    if _same(claim.value, evidence.value):
        return True
    one_unscaled = claim.scale == 1.0 or evidence.scale == 1.0
    return one_unscaled and _same(claim.mantissa, evidence.mantissa)


def is_faithful(mention: NumberMention, values: Sequence[NumberMention]) -> bool:
    """True if some evidence number from :func:`number_values` :func:`supports` the mention."""
    return any(supports(mention, evidence) for evidence in values)


def unsupported_numbers(text: str, values: Sequence[NumberMention]) -> list[NumberMention]:
    return [m for m in extract_numbers(text) if not is_faithful(m, values)]


# --------------------------------------------------------------------------------------------
# Leakage
# --------------------------------------------------------------------------------------------

_RAW_HANDLE: Final = (
    r"[A-Z][A-Z0-9]{1,15}/[A-Z0-9]{1,12}(?:-[A-Z0-9]{1,12}){0,5}@v\d{1,4}"
    r"(?::[A-Z0-9]+(?:\.[A-Z0-9]+)*)?(?:#w\d+)?"
)
_URL: Final = r"(?:(?:https?|ftp)://|www\.)[^\s<>()\[\]]*[^\s<>()\[\].,;:!?'\"]"
_LINK_RE: Final = re.compile(r"\[([^\[\]\n]*)\]\([^)\n]*\)")


def _link_text(match: re.Match[str]) -> str:
    """A link keeps its text (and its brackets when the text is an alias citation)."""
    label = match.group(1)
    return f"[{label}]" if ALIASISH_RE.fullmatch(f"[{label}]") else label


_Replacement = str | Callable[[re.Match[str]], str]
# (kind, pattern, replacement); applied in this order, each occurrence reported once. Images
# go before links (same bracket syntax) and links before bare URLs (so the text survives).
_LEAK_RULES: Final[tuple[tuple[str, re.Pattern[str], _Replacement], ...]] = (
    ("canonical_marker", CANONICAL_MARKER_RE, " "),
    ("html", re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL), " "),
    ("html", re.compile(r"<!--.*?-->", re.DOTALL), " "),
    ("raw_handle", re.compile(rf"\[{_RAW_HANDLE}\]|(?<![A-Za-z0-9]){_RAW_HANDLE}"), " "),
    ("image", re.compile(r"!\[[^\[\]\n]*\]\([^)\n]*\)"), " "),
    ("link", _LINK_RE, _link_text),
    ("url", re.compile(rf"<{_URL}/?>"), " "),
    ("url", re.compile(_URL), " "),
    ("html", re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>"), " "),
    ("uuid", re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b"), " "),
    ("uuid", re.compile(r"\b[0-9a-fA-F]{32}\b"), " "),
    ("child_id", re.compile(r"#w\d+\b"), " "),
)


@dataclass(frozen=True, slots=True)
class LeakScan:
    text: str
    removed: tuple[str, ...]  # leak kind per removed occurrence, in rule order


def tidy(text: str) -> str:
    """Collapse whitespace left behind by removals (line structure and indentation kept)."""
    lines = []
    for line in text.splitlines():
        line = re.sub(r"(?<=\S)[ \t]{2,}", " ", line)
        line = re.sub(r"\(\s*\)", "", line)
        line = re.sub(r"(?<=\S)[ \t]+([.,;:!?])(?=\s|$)", r"\1", line)
        lines.append(line.rstrip())
    return "\n".join(lines)


def _strip_once(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    for kind, pattern, replacement in _LEAK_RULES:
        text, count = pattern.subn(replacement, text)
        removed.extend([kind] * count)
    return text, removed


def strip_leaks(text: str) -> LeakScan:
    """Remove URLs, images, links (text kept), HTML, raw IDs/handles and ``[[...]]`` markers.

    Repeated to a fixpoint: one removal (an empty link, ``()`` dropped by :func:`tidy`) can
    reassemble a marker or handle that an earlier rule already passed over, e.g.
    ``[[[](u)WS/SRC@v[](u)1:P1]]``. Every pass that removes something shortens the text, so
    the loop terminates.
    """
    removed: list[str] = []
    while True:
        text, found = _strip_once(text)
        if not found:
            return LeakScan(text, tuple(removed))
        removed.extend(found)
        text = tidy(text)


# --------------------------------------------------------------------------------------------
# Insufficiency statements
# --------------------------------------------------------------------------------------------

# Conservative: only explicit statements that the evidence does not answer the question.
INSUFFICIENT_RE: Final = re.compile(
    r"\b(?:insufficient|inadequate|not\s+enough|no(?:\s+relevant|\s+direct)?)\s+"
    r"(?:evidence|information|data)\b"
    r"|\b(?:evidence|sources?|documents?|data)\s+(?:provided\s+)?(?:does|do|did)\s+not\s+"
    r"(?:contain|provide|include|address|cover|mention|state|show|support)\b"
    r"|\b(?:cannot|can't|unable\s+to)\s+(?:be\s+)?"
    r"(?:answer(?:ed)?|determined?|confirm(?:ed)?|establish(?:ed)?)\b",
    re.IGNORECASE,
)


def states_insufficient(text: str) -> bool:
    return INSUFFICIENT_RE.search(text) is not None


# Broader than INSUFFICIENT_RE: a Gaps unit that names something missing or uncertain. Anything
# else in Gaps is an uncited claim and is tagged [inference] by the verifier.
_GAP_RE: Final = re.compile(
    r"\b(?:missing|unknown|unclear|uncertain(?:ty)?|unavailable|unverified|unreported|"
    r"unaddressed|absent|lacks?|lacking|gaps?|limited|no\s+(?:\w+\s+){0,3}?"
    r"(?:is|are|was|were)\s+(?:available|provided|reported|given|included|covered)|"
    r"not\s+(?:\w+\s+)?(?:available|reported|covered|included|specified|stated|disclosed|"
    r"provided|known|clear|addressed|captured|broken\s+down|given|found|present))\b",
    re.IGNORECASE,
)


def states_gap(text: str) -> bool:
    """True if ``text`` describes missing or uncertain evidence (what Gaps is for)."""
    return states_insufficient(text) or _GAP_RE.search(text) is not None


def has_content(unit: str) -> bool:
    """True if the unit has any letter or digit once markers are removed."""
    return any(ch.isalnum() for ch in _MARKERS_RE.sub(" ", unit))
