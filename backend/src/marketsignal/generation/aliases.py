"""Streaming hold-back gate for run-local ``[E#]``/``[R#]`` alias citations (ADR-0004, plan §10.1,
§21). ``[R#]`` (Phase 5) cites a computed analytics result; it follows exactly the same grammar,
hold-back and removal rules as ``[E#]`` with the letter ``R``; everything below that says
``[E…]`` applies to ``[R…]`` too.

The model cites evidence with run-local aliases ``[E1]``…``[E12]``. Text deltas arrive in
arbitrary pieces, so an alias can be split across deltas (``"… growth [E"`` + ``"3] …"``). The
gate sits between the LLM text deltas and the SSE ``token`` events and guarantees that:

* an unknown alias is never displayed, not even for one frame: it is removed before emission
  and reported as a warning (never guessed, never fuzzy-matched);
* a valid alias produces exactly one :class:`GateCitation` on first use, and that citation is
  emitted *before* the text carrying the marker, so the UI already knows the alias→handle
  binding when ``[E3]`` arrives and can render the chip at once ("chips render only after a
  ``citation`` event");
* the output does not depend on how the stream was split: for every split of the same model
  output the (adjacent-text-merged) event sequence is identical.

Grammar (``_classify``) — a candidate always starts at ``[`` and is decided as one of:

``ALIAS``      ``[E`` + 1-2 ASCII digits + ``]``. Same shape as ``types.ALIAS_RE``. Kept in the
               text when the alias is in the pack; otherwise removed with ``UNKNOWN_ALIAS``
               (this covers ``[E99]`` beyond the pack, ``[E0]`` and zero-padded ``[E01]`` —
               aliases are compared as exact strings, never normalised).
``MALFORMED``  ``[E]`` or ``[E`` + 3-4 ASCII digits + ``]`` (``[E123]``, ``[E1234]``): an
               evident alias attempt that can never be valid. Removed with
               ``MALFORMED_ALIAS``.
``LITERAL``    anything else: the ``[`` is ordinary text and scanning resumes right after it.
               ``[inference]``, ``[see note]``, ``[1]``, lowercase ``[e3]``, ``[E 3]``,
               ``[E3a]``, ``[E12345]`` and canonical ``[[WS/SRC@v1:p1]]`` all pass verbatim.

Hold-back: text from a ``[`` is held only while the candidate is still undecided. A prefix of a
valid alias holds at most 4 chars (``[E12``), as ADR-0004 states; the malformed-attempt rule
extends the worst case to :data:`MAX_HELD_CHARS` = 6 (``[E1234``) so ``[E123]`` can be dropped
rather than shown. Text with no ``[`` is never held. At end of stream (:meth:`AliasGate.flush`)
an undecided partial such as ``[E1`` is not an alias and is released verbatim (spec open item
12).

Removal is exact: the marker is cut and surrounding whitespace is left as-is (``"x [E99]."``
becomes ``"x ."``). One exception keeps removal from *creating* a marker: when the kept text
before a removed marker ends in an alias prefix (``[``, ``[E``, ``[E1``…), a single space is
inserted, so ``"[E1[E99]]"`` becomes ``"[E1 ]"``, never ``"[E1]"``. The decision depends only on
text before the marker, so it is split-invariant. Tidying would require holding whitespace
too; the verifier owns normalisation of final text. Every removed occurrence is reported, not
just the first, so the gate and :func:`strip_unknown_aliases` agree on counts.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from marketsignal.generation.types import EvidencePack

WarningCode = Literal["UNKNOWN_ALIAS", "MALFORMED_ALIAS"]
UNKNOWN_ALIAS: Final[WarningCode] = "UNKNOWN_ALIAS"
MALFORMED_ALIAS: Final[WarningCode] = "MALFORMED_ALIAS"

MAX_VALID_DIGITS = 2  # [E1]..[E99] are well-formed; the pack only ever uses E1..E12
MAX_ATTEMPT_DIGITS = 4  # [E123] / [E1234] are malformed attempts; longer runs are plain text
MAX_HELD_CHARS = 2 + MAX_ATTEMPT_DIGITS  # "[E1234" — the longest undecided prefix

_ASCII_DIGITS = frozenset("0123456789")
_ALIAS_LETTERS = frozenset("ER")  # E: evidence item, R: computed result (Phase 5)
_ALIAS_NAME_RE = re.compile(r"[ER][0-9]{1,2}")
_PREFIX_TAIL_RE = re.compile(r"\[(?:[ER][0-9]*)?\Z")
_TAIL_CHARS = MAX_HELD_CHARS + 1


def _separator(kept_tail: str) -> str:
    """Space to insert for a removed marker when the kept text ends in an alias prefix."""
    return " " if _PREFIX_TAIL_RE.search(kept_tail) else ""


@dataclass(frozen=True, slots=True)
class GateText:
    """Safe-to-display text. May contain valid alias markers, never unknown ones."""

    text: str


@dataclass(frozen=True, slots=True)
class GateCitation:
    """First use of a valid alias (``"E3"``); emitted just before the text carrying the marker."""

    alias: str


@dataclass(frozen=True, slots=True)
class GateWarning:
    """An alias marker removed from the text (``alias_text`` is the marker, e.g. ``"[E99]"``)."""

    code: WarningCode
    alias_text: str

    @property
    def message(self) -> str:
        if self.code == UNKNOWN_ALIAS:
            return f"Removed citation {self.alias_text}: not in this run's evidence pack."
        return f"Removed malformed citation {self.alias_text}."


GateEvent = GateText | GateCitation | GateWarning


class _Verdict(enum.Enum):
    ALIAS = "alias"
    MALFORMED = "malformed"
    LITERAL = "literal"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class _Marker:
    """A decided ``[E…]`` candidate: ``ALIAS`` (valid or unknown) or ``MALFORMED``."""

    verdict: _Verdict
    text: str


_Segment = str | _Marker


def _classify(buf: str, start: int, *, at_end: bool) -> tuple[_Verdict, int]:
    """Decide the candidate at ``buf[start] == "["``; return the verdict and its end offset.

    ``PENDING`` means the candidate runs off the end of ``buf`` and could still change verdict;
    with ``at_end`` there is no more input, so it becomes ``LITERAL``. The decision reads at most
    ``MAX_HELD_CHARS + 1`` chars, which is what makes the gate split-invariant.
    """
    n = len(buf)
    undecided = _Verdict.LITERAL if at_end else _Verdict.PENDING
    j = start + 1
    if j == n:
        return undecided, j
    if buf[j] not in _ALIAS_LETTERS:
        return _Verdict.LITERAL, j
    j += 1
    digits_start = j
    while j < n and buf[j] in _ASCII_DIGITS:
        j += 1
        if j - digits_start > MAX_ATTEMPT_DIGITS:
            return _Verdict.LITERAL, j
    if j == n:
        return undecided, j
    if buf[j] != "]":
        return _Verdict.LITERAL, j
    digits = j - digits_start
    verdict = _Verdict.ALIAS if 1 <= digits <= MAX_VALID_DIGITS else _Verdict.MALFORMED
    return verdict, j + 1


def _scan(buf: str, *, at_end: bool) -> tuple[list[_Segment], str]:
    """Split ``buf`` into text and decided markers; return them plus the undecided tail."""
    segments: list[_Segment] = []
    text_start = 0
    pos = 0
    while (i := buf.find("[", pos)) >= 0:
        verdict, end = _classify(buf, i, at_end=at_end)
        if verdict is _Verdict.PENDING:
            if i > text_start:
                segments.append(buf[text_start:i])
            return segments, buf[i:]
        if verdict is _Verdict.LITERAL:
            pos = i + 1
            continue
        if i > text_start:
            segments.append(buf[text_start:i])
        segments.append(_Marker(verdict, buf[i:end]))
        text_start = pos = end
    if len(buf) > text_start:
        segments.append(buf[text_start:])
    return segments, ""


def _validate_aliases(valid: Iterable[str]) -> frozenset[str]:
    aliases = frozenset(valid)
    bad = sorted(a for a in aliases if not _ALIAS_NAME_RE.fullmatch(a))
    if bad:
        raise ValueError(f"invalid alias names (expected E|R<1-2 digits>): {bad}")
    return aliases


def _warning_for(marker: _Marker, valid: frozenset[str]) -> GateWarning | None:
    """``None`` for a valid alias; otherwise the warning that justifies removing the marker."""
    if marker.verdict is _Verdict.MALFORMED:
        return GateWarning(MALFORMED_ALIAS, marker.text)
    if marker.text[1:-1] in valid:
        return None
    return GateWarning(UNKNOWN_ALIAS, marker.text)


class AliasGate:
    """Stateful per-attempt gate: ``push`` each LLM text delta, then ``flush`` once at the end.

    Each call returns the events now decided, in stream order, with adjacent text merged. A
    regeneration after ``draft_reset`` should use a fresh gate (same pack, so same aliases) so
    citations are re-announced for the new attempt.
    """

    __slots__ = ("_cited", "_closed", "_held", "_tail", "_valid")

    def __init__(self, valid_aliases: Iterable[str]) -> None:
        self._valid = _validate_aliases(valid_aliases)
        self._held = ""
        self._cited: list[str] = []
        self._closed = False
        self._tail = ""  # last chars of decided text, for the removal separator

    @classmethod
    def from_pack(cls, pack: EvidencePack) -> AliasGate:
        return cls(pack.aliases())

    @property
    def valid_aliases(self) -> frozenset[str]:
        return self._valid

    @property
    def held(self) -> str:
        """The undecided tail (``""`` or a prefix such as ``"[E1"``; at most 6 chars)."""
        return self._held

    @property
    def cited(self) -> tuple[str, ...]:
        """Valid aliases in first-use order."""
        return tuple(self._cited)

    def push(self, delta: str) -> list[GateEvent]:
        if self._closed:
            raise RuntimeError("AliasGate.push() after flush()")
        if not delta:
            return []
        segments, self._held = _scan(self._held + delta, at_end=False)
        return self._events(segments)

    def flush(self) -> list[GateEvent]:
        """End of stream: decide the held tail (a partial alias is released verbatim)."""
        if self._closed:
            return []
        self._closed = True
        segments, self._held = _scan(self._held, at_end=True)
        return self._events(segments)

    def _events(self, segments: list[_Segment]) -> list[GateEvent]:
        events: list[GateEvent] = []
        pending_text: list[str] = []

        def emit_text() -> None:
            if pending_text:
                events.append(GateText("".join(pending_text)))
                pending_text.clear()

        def keep(text: str) -> None:
            pending_text.append(text)
            self._tail = (self._tail + text)[-_TAIL_CHARS:]

        for seg in segments:
            if isinstance(seg, str):
                keep(seg)
                continue
            warning = _warning_for(seg, self._valid)
            if warning is not None:
                emit_text()
                events.append(warning)
                if sep := _separator(self._tail):
                    keep(sep)
                continue
            alias = seg.text[1:-1]
            if alias not in self._cited:
                emit_text()
                self._cited.append(alias)
                events.append(GateCitation(alias))
            keep(seg.text)
        emit_text()
        return events


def strip_unknown_aliases(
    text: str, valid_aliases: Iterable[str]
) -> tuple[str, tuple[GateWarning, ...]]:
    """Non-streaming form of the gate: same grammar, same output text, same warnings.

    Returns the text with unknown and malformed alias markers removed, plus one warning per
    removed occurrence in text order. Equivalent to one :meth:`AliasGate.push` of ``text``
    followed by :meth:`AliasGate.flush`, with citations ignored.
    """
    valid = _validate_aliases(valid_aliases)
    segments, _ = _scan(text, at_end=True)  # at_end leaves no undecided tail
    kept: list[str] = []
    removed: list[GateWarning] = []
    for seg in segments:
        if isinstance(seg, str):
            kept.append(seg)
            continue
        warning = _warning_for(seg, valid)
        if warning is None:
            kept.append(seg.text)
        else:
            removed.append(warning)
            kept.append(_separator("".join(kept)[-_TAIL_CHARS:]))
    return "".join(kept), tuple(removed)
