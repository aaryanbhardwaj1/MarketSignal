"""Alias hold-back gate (ADR-0004): grammar, hold-back bound, flush, and split invariance."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from marketsignal.generation.aliases import (
    MALFORMED_ALIAS,
    MAX_HELD_CHARS,
    UNKNOWN_ALIAS,
    AliasGate,
    GateCitation,
    GateEvent,
    GateText,
    GateWarning,
    strip_unknown_aliases,
)
from marketsignal.generation.types import ALIAS_RE

PACK = frozenset(f"E{i}" for i in range(1, 13))  # E1..E12
SMALL_PACK = frozenset(f"E{i}" for i in range(1, 6))  # E1..E5


def normalise(events: Iterable[GateEvent]) -> list[GateEvent]:
    """Merge adjacent text and drop empty text so differently-split runs compare equal."""
    out: list[GateEvent] = []
    for ev in events:
        if isinstance(ev, GateText):
            if not ev.text:
                continue
            if out and isinstance(out[-1], GateText):
                out[-1] = GateText(out[-1].text + ev.text)
                continue
        out.append(ev)
    return out


def run(deltas: Sequence[str], valid: Iterable[str] = PACK) -> list[GateEvent]:
    gate = AliasGate(valid)
    events: list[GateEvent] = []
    for d in deltas:
        events.extend(gate.push(d))
    events.extend(gate.flush())
    return events


def text_of(events: Iterable[GateEvent]) -> str:
    return "".join(e.text for e in events if isinstance(e, GateText))


def citations(events: Iterable[GateEvent]) -> list[str]:
    return [e.alias for e in events if isinstance(e, GateCitation)]


def warnings(events: Iterable[GateEvent]) -> list[GateWarning]:
    return [e for e in events if isinstance(e, GateWarning)]


def chars(s: str) -> list[str]:
    return list(s)


# --- valid aliases ----------------------------------------------------------------------------


def test_valid_alias_kept_with_citation_before_marker() -> None:
    events = normalise(run(["Revenue grew [E3] in Q2."]))
    assert events == [
        GateText("Revenue grew "),
        GateCitation("E3"),
        GateText("[E3] in Q2."),
    ]


@pytest.mark.parametrize(
    "deltas",
    [
        ["Growth [", "E1] ok"],
        ["Growth [E", "1] ok"],
        ["Growth [E1", "] ok"],
        chars("Growth [E1] ok"),
    ],
)
def test_split_inside_single_digit_alias(deltas: list[str]) -> None:
    events = normalise(run(deltas))
    assert events == [GateText("Growth "), GateCitation("E1"), GateText("[E1] ok")]


@pytest.mark.parametrize(
    "deltas",
    [["x [E1", "2] y"], ["x [E12", "] y"], ["x [", "E", "1", "2", "]", " y"], chars("x [E12] y")],
)
def test_split_inside_two_digit_alias(deltas: list[str]) -> None:
    events = normalise(run(deltas))
    assert events == [GateText("x "), GateCitation("E12"), GateText("[E12] y")]


def test_duplicate_alias_yields_one_citation() -> None:
    events = run(["A [E2]. B [E2]. C [E", "2] and [E1][E2]."])
    assert citations(events) == ["E2", "E1"]
    assert text_of(events) == "A [E2]. B [E2]. C [E2] and [E1][E2]."


def test_adjacent_aliases() -> None:
    events = normalise(run(["[E1][E2]"]))
    assert events == [
        GateCitation("E1"),
        GateText("[E1]"),
        GateCitation("E2"),
        GateText("[E2]"),
    ]


@pytest.mark.parametrize(
    ("raw", "aliases"),
    [
        ("Margin hit **27%**[E2].", ["E2"]),
        ("(see [E3])", ["E3"]),
        ("- churn fell [E4],[E5]; then rose", ["E4", "E5"]),
        ("### Answer\nUp 4%.[E1]\n", ["E1"]),
        ("_note_ [E10]!", ["E10"]),
    ],
)
def test_alias_adjacent_to_punctuation_and_markdown(raw: str, aliases: list[str]) -> None:
    events = run(chars(raw))
    assert text_of(events) == raw
    assert citations(events) == aliases
    assert warnings(events) == []


# --- unknown and malformed aliases -----------------------------------------------------------


def test_unknown_alias_removed_and_warned() -> None:
    events = normalise(run(["Share is 12% [E99]."], SMALL_PACK))
    assert events == [
        GateText("Share is 12% "),
        GateWarning(UNKNOWN_ALIAS, "[E99]"),
        GateText("."),
    ]


@pytest.mark.parametrize("marker", ["[E0]", "[E6]", "[E01]", "[E00]"])
def test_well_formed_out_of_pack_aliases_removed(marker: str) -> None:
    events = run(["a ", marker, " b"], SMALL_PACK)
    assert text_of(events) == "a  b"
    assert warnings(events) == [GateWarning(UNKNOWN_ALIAS, marker)]
    assert citations(events) == []


@pytest.mark.parametrize("marker", ["[E]", "[E123]", "[E1234]"])
def test_malformed_alias_attempts_removed(marker: str) -> None:
    events = run(chars(f"x {marker} y"))
    assert text_of(events) == "x  y"
    assert warnings(events) == [GateWarning(MALFORMED_ALIAS, marker)]


def test_long_digit_run_released_verbatim() -> None:
    raw = "ref [E12345] stays"
    events = run(chars(raw))
    assert text_of(events) == raw
    assert warnings(events) == []


def test_every_unknown_occurrence_is_warned() -> None:
    events = run(["[E7] and [E7]"], SMALL_PACK)
    assert text_of(events) == " and "
    assert warnings(events) == [GateWarning(UNKNOWN_ALIAS, "[E7]")] * 2


def test_warning_message() -> None:
    assert "not in this run's evidence pack" in GateWarning(UNKNOWN_ALIAS, "[E9]").message
    assert "malformed" in GateWarning(MALFORMED_ALIAS, "[E]").message


# --- literal brackets ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "Likely transient [inference].",
        "[see note]",
        "footnote [1]",
        "lower [e3]",
        "spaced [E 3]",
        "suffix [E3a]",
        "canonical [[ACME/CRM-EXPORT@v2:p4]]",
        "trailing [",
        "[[E",
        "array[0] and [] and ]",
    ],
)
def test_non_alias_brackets_pass_verbatim(raw: str) -> None:
    events = run(chars(raw))
    assert text_of(events) == raw
    assert citations(events) == []
    assert warnings(events) == []


def test_double_bracket_before_alias() -> None:
    events = run(chars("[[E1]]"))
    assert text_of(events) == "[[E1]]"
    assert citations(events) == ["E1"]


def test_literal_released_as_soon_as_undecidable() -> None:
    gate = AliasGate(PACK)
    assert gate.push("tag [") == [GateText("tag ")]
    assert gate.held == "["
    assert gate.push("i") == [GateText("[i")]
    assert gate.held == ""


# --- hold-back and flush ---------------------------------------------------------------------


def test_text_without_brackets_streams_immediately() -> None:
    gate = AliasGate(PACK)
    chunk = "Revenue rose steadily across all regions. " * 50
    assert gate.push(chunk) == [GateText(chunk)]
    assert gate.held == ""


def test_held_prefix_bounded() -> None:
    gate = AliasGate(PACK)
    gate.push("a [E12")
    assert gate.held == "[E12"
    gate.push("34")
    assert gate.held == "[E1234"
    assert len(gate.held) == MAX_HELD_CHARS
    assert gate.push("5") == [GateText("[E12345")]
    assert gate.held == ""


@pytest.mark.parametrize("partial", ["[", "[E", "[E1", "[E12", "[E123"])
def test_held_partial_flushed_verbatim(partial: str) -> None:
    gate = AliasGate(PACK)
    assert gate.push("end " + partial) == [GateText("end ")]
    assert gate.flush() == [GateText(partial)]
    assert gate.cited == ()


def test_flush_is_idempotent_and_push_after_flush_rejected() -> None:
    gate = AliasGate(PACK)
    gate.push("x [E1")
    assert gate.flush() == [GateText("[E1")]
    assert gate.flush() == []
    with pytest.raises(RuntimeError):
        gate.push("more")


def test_empty_deltas_are_noops() -> None:
    gate = AliasGate(PACK)
    assert gate.push("") == []
    assert gate.push("a [E") == [GateText("a ")]
    assert gate.push("") == []
    assert gate.held == "[E"
    assert normalise(gate.push("2]") + gate.flush()) == [GateCitation("E2"), GateText("[E2]")]


def test_empty_stream() -> None:
    assert run([]) == []
    assert run(["", ""]) == []


def test_unicode_text_and_digits() -> None:
    # Non-ASCII look-alikes never form an alias: Arabic-Indic digit one, Cyrillic capital Ie.
    raw = "Umsatz +12 % — naïve 日本語 [E1] ✓ [E\u0661] [\u04151]"
    events = run(chars(raw))
    assert text_of(events) == raw
    assert citations(events) == ["E1"]


def test_cited_tracks_first_use_order() -> None:
    gate = AliasGate(PACK)
    gate.push("[E5] [E2] [E5] [E11]")
    gate.flush()
    assert gate.cited == ("E5", "E2", "E11")


# --- construction and the non-streaming helper -----------------------------------------------


@pytest.mark.parametrize("bad", ["E", "e1", "E123", "[E1]", "E1 "])
def test_invalid_alias_names_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid alias"):
        AliasGate(["E1", bad])
    with pytest.raises(ValueError, match="invalid alias"):
        strip_unknown_aliases("x", [bad])


def test_strip_unknown_aliases() -> None:
    text, removed = strip_unknown_aliases("A [E1] B [E9] C [E] D [inference] [E1", SMALL_PACK)
    assert text == "A [E1] B  C  D [inference] [E1"
    assert removed == (GateWarning(UNKNOWN_ALIAS, "[E9]"), GateWarning(MALFORMED_ALIAS, "[E]"))


# --- split invariance (property) ------------------------------------------------------------

FRAGMENTS = [
    "[E1]",
    "[E2]",
    "[E12]",
    "[E5]",
    "[E99]",
    "[E0]",
    "[E01]",
    "[E]",
    "[E123]",
    "[E12345]",
    "[inference]",
    "[e3]",
    "[[",
    "]",
    "[",
    "[E",
    "[E1",
    "E",
    "1",
    "**27%**",
    " ",
    ".",
    "é",
    "日本",
    "Revenue grew",
]
model_outputs = st.lists(
    st.one_of(st.sampled_from(FRAGMENTS), st.text(alphabet="[]E0123456789 xé", max_size=6)),
    max_size=30,
).map("".join)
packs = st.integers(min_value=0, max_value=12).map(
    lambda n: frozenset(f"E{i}" for i in range(1, n + 1))
)


@st.composite
def split_outputs(draw: st.DrawFn) -> tuple[str, list[str]]:
    raw = draw(model_outputs)
    cuts = sorted(draw(st.lists(st.integers(min_value=0, max_value=len(raw)), max_size=20)))
    bounds = [0, *cuts, len(raw)]
    return raw, [raw[a:b] for a, b in pairwise(bounds)]


@settings(max_examples=400, deadline=None)
@given(split_outputs(), packs)
def test_any_split_matches_single_delta(case: tuple[str, list[str]], valid: frozenset[str]) -> None:
    raw, deltas = case
    whole = normalise(run([raw], valid))
    streamed = normalise(run(deltas, valid))
    per_char = normalise(run(chars(raw), valid))
    assert streamed == whole
    assert per_char == whole

    stripped, removed = strip_unknown_aliases(raw, valid)
    assert text_of(whole) == stripped
    assert warnings(whole) == list(removed)


@settings(max_examples=300, deadline=None)
@given(split_outputs(), packs)
def test_gate_invariants(case: tuple[str, list[str]], valid: frozenset[str]) -> None:
    _, deltas = case
    gate = AliasGate(valid)
    events: list[GateEvent] = []
    for d in deltas:
        events.extend(gate.push(d))
        assert len(gate.held) <= MAX_HELD_CHARS
        assert all(not (isinstance(e, GateText) and not e.text) for e in events)
    events.extend(gate.flush())
    assert gate.held == ""

    # Every displayed alias is in the pack, and its citation precedes the marker text.
    announced: set[str] = set()
    for ev in events:
        if isinstance(ev, GateCitation):
            assert ev.alias not in announced
            announced.add(ev.alias)
        elif isinstance(ev, GateText):
            for m in ALIAS_RE.finditer(ev.text):
                assert f"E{m.group(1)}" in valid
                assert f"E{m.group(1)}" in announced
    assert all(f"E{m.group(1)}" in valid for m in ALIAS_RE.finditer(text_of(events)))
    assert list(gate.cited) == citations(events)


@pytest.mark.parametrize(
    ("raw", "valid", "shown"),
    [
        ("[E1[E1]]", frozenset(), "[E1 ]"),
        ("[E[E99]1]", frozenset({"E1"}), "[E 1]"),
        ("[[E99]E1]", frozenset({"E1"}), "[ E1]"),
        ("x [E99].", frozenset(), "x ."),
    ],
)
def test_removal_never_assembles_a_new_alias(raw: str, valid: frozenset[str], shown: str) -> None:
    for split in (1, 2, len(raw)):
        gate = AliasGate(valid)
        events = [e for i in range(0, len(raw), split) for e in gate.push(raw[i : i + split])]
        events.extend(gate.flush())
        assert text_of(events) == shown
        assert citations(events) == []
    assert strip_unknown_aliases(raw, valid)[0] == shown
