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
  (``Q2``, ``FY26``, ``R0147``, ``3rd``) are identifiers, not claims.
* :func:`strip_leaks` removes what must never reach the UI: URLs, images, links (text kept),
  HTML, UUIDs, child-id fragments, raw handles and canonical ``[[...]]`` markers, which only
  the verifier itself may write.
"""

from __future__ import annotations

import bisect
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
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
    (?:[ \t]?(?P<pct>%|percent(?!age)|per[ \t]cent))?
    (?![A-Za-z0-9_]|[.,]\d)
    """,
    re.VERBOSE,
)
_ORDINAL_RE: Final = re.compile(r"^[ \t]*(?:[-*+\u2022][ \t]+)?\d{1,3}[.)][ \t]+", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class NumberMention:
    """One numeric claim. ``mantissa`` is the number as written; ``value`` applies the scale."""

    text: str
    mantissa_text: str  # digits as written, separators removed ("2,960" -> "2960")
    mantissa: float
    value: float
    percent: bool
    currency: str | None


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


def extract_numbers(text: str) -> list[NumberMention]:
    """Numeric claims in ``text`` (citation markers and line-start list ordinals ignored)."""
    cleaned = _ORDINAL_RE.sub("", _MARKERS_RE.sub(" ", text))
    mentions: list[NumberMention] = []
    for match in _NUMBER_RE.finditer(cleaned):
        identifier, range_dash = _glued(cleaned, match)
        if identifier:
            continue
        negative = bool(match.group("sign")) and not range_dash
        mantissa_text = match.group("num").replace(",", "")
        scale_word = match.group("word") or match.group("abbr") or match.group("suffix") or ""
        scale = _SCALES.get(scale_word.lower(), 1.0)
        sign = -1.0 if negative else 1.0
        mantissa = sign * float(mantissa_text)
        written = match.group(0)
        if match.group("sign") and not negative:
            written = written[1:]
        mentions.append(
            NumberMention(
                text=written.strip(),
                mantissa_text=mantissa_text,
                mantissa=mantissa,
                value=mantissa * scale,
                percent=bool(match.group("pct")),
                currency=(match.group("cur") or "").strip() or None,
            )
        )
    return mentions


def number_values(texts: Iterable[str]) -> tuple[float, ...]:
    """Sorted absolute mantissas and scaled values of every number in ``texts``."""
    values: set[float] = set()
    for text in texts:
        for mention in extract_numbers(text):
            values.add(abs(mention.mantissa))
            values.add(abs(mention.value))
    return tuple(sorted(values))


def _contains(values: Sequence[float], target: float) -> bool:
    margin = abs(target) * REL_TOL * 2
    index = bisect.bisect_left(values, target - margin)
    while index < len(values) and values[index] <= target + margin:
        if math.isclose(values[index], target, rel_tol=REL_TOL):
            return True
        index += 1
    return False


def is_faithful(mention: NumberMention, values: Sequence[float]) -> bool:
    """True if the mention's mantissa or scaled value equals a value from :func:`number_values`.

    Sign is ignored ("fell 3.2%" and "-3.2%" state the same figure).
    """
    return _contains(values, abs(mention.mantissa)) or _contains(values, abs(mention.value))


def unsupported_numbers(text: str, values: Sequence[float]) -> list[NumberMention]:
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


def strip_leaks(text: str) -> LeakScan:
    """Remove URLs, images, links (text kept), HTML, raw IDs/handles and ``[[...]]`` markers."""
    removed: list[str] = []
    for kind, pattern, replacement in _LEAK_RULES:
        text, count = pattern.subn(replacement, text)
        removed.extend([kind] * count)
    return LeakScan(tidy(text) if removed else text, tuple(removed))


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


def has_content(unit: str) -> bool:
    """True if the unit has any letter or digit once markers are removed."""
    return any(ch.isalnum() for ch in _MARKERS_RE.sub(" ", unit))
