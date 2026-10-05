"""Evidence-handle grammar: round-trip properties, fuzzing, and the rejection contract."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from marketsignal.evidence.handles import (
    MAX_HANDLE_LENGTH,
    EvidenceHandle,
    ForeignWorkspaceHandleError,
    LocatorKind,
    LocatorUnit,
    MalformedHandleError,
    build_handle,
    parse_handle,
    parse_rendered_handle,
    require_workspace,
    try_parse_handle,
)

UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALNUM = UPPER + "0123456789"


def _raw(ws: str, src: str, ver: int, loc: tuple[LocatorUnit, ...]) -> str:
    """Serialise without validation, so the strategy can filter on length."""
    return f"{ws}/{src}@v{ver}:" + ".".join(str(u) for u in loc)


workspace_codes = st.builds(
    lambda head, tail: head + tail,
    st.sampled_from(UPPER),
    st.text(alphabet=ALNUM, min_size=1, max_size=15),
)
source_codes = st.lists(
    st.text(alphabet=ALNUM, min_size=1, max_size=12), min_size=1, max_size=6
).map("-".join)
versions = st.integers(min_value=1, max_value=9999)
units = st.builds(
    LocatorUnit, st.sampled_from(list(LocatorKind)), st.integers(min_value=1, max_value=9_999_999)
)
structural_handles = st.builds(
    lambda ws, src, ver, loc: (ws, src, ver, tuple(loc)),
    workspace_codes,
    source_codes,
    versions,
    st.lists(units, min_size=1, max_size=4),
).filter(lambda parts: len(_raw(*parts)) <= MAX_HANDLE_LENGTH)
analytic_ids = st.text(alphabet="0123456789ABCDEF", min_size=12, max_size=12)


@given(structural_handles)
def test_structural_round_trip(parts: tuple[str, str, int, tuple[LocatorUnit, ...]]) -> None:
    handle = EvidenceHandle(*parts)
    text = str(handle)
    assert parse_handle(text) == handle
    assert str(parse_handle(text)) == text
    assert parse_rendered_handle(handle.rendered()) == handle


@given(workspace_codes, source_codes, versions, analytic_ids)
def test_analytic_round_trip(ws: str, src: str, ver: int, aq: str) -> None:
    raw = f"{ws}/{src}@v{ver}:AQ{aq}"
    if len(raw) > MAX_HANDLE_LENGTH:
        with pytest.raises(MalformedHandleError):
            EvidenceHandle(ws, src, ver, (), aq)
        return
    handle = EvidenceHandle(ws, src, ver, (), aq)
    assert str(handle) == raw
    assert parse_handle(raw) == handle
    assert handle.is_analytic


@settings(max_examples=2000)
@given(st.text(max_size=120))
def test_parsing_is_total_and_canonical(value: str) -> None:
    """Any string either parses to a handle that re-serialises to itself, or is rejected."""
    try:
        handle = parse_handle(value)
    except MalformedHandleError:
        return
    assert str(handle) == value


@settings(max_examples=1000)
@given(structural_handles, st.integers(min_value=0, max_value=200), st.text(min_size=1, max_size=3))
def test_single_mutations_are_never_silently_repaired(
    parts: tuple[str, str, int, tuple[LocatorUnit, ...]], pos: int, insert: str
) -> None:
    original = str(EvidenceHandle(*parts))
    i = pos % (len(original) + 1)
    mutated = original[:i] + insert + original[i:]
    parsed = try_parse_handle(mutated)
    # A mutation either breaks the grammar or produces a *different* valid handle that
    # re-serialises to exactly the mutated text; it never parses back to the original.
    if parsed is not None:
        assert str(parsed) == mutated
        assert str(parsed) != original


@pytest.mark.parametrize(
    "value",
    [
        "",
        "northstar/SURVEY@v1:R1",  # lowercase workspace
        "N/SURVEY@v1:R1",  # workspace too short
        "1NORTHSTAR/SURVEY@v1:R1",  # workspace must start with a letter
        "NORTHSTAR/survey@v1:R1",  # lowercase source
        "NORTHSTAR/SURVEY-@v1:R1",  # dangling dash
        "NORTHSTAR/-SURVEY@v1:R1",
        "NORTHSTAR/A-B-C-D-E-F-G@v1:R1",  # 7 source segments
        "NORTHSTAR/ABCDEFGHIJKLM@v1:R1",  # 13-char segment
        "NORTHSTAR/SURVEY@v0:R1",  # version 0
        "NORTHSTAR/SURVEY@v01:R1",  # leading zero
        "NORTHSTAR/SURVEY@v10000:R1",  # version too large
        "NORTHSTAR/SURVEY@V1:R1",  # uppercase V
        "NORTHSTAR/SURVEY@1:R1",  # missing v
        "NORTHSTAR/SURVEY@v1:",  # empty locator
        "NORTHSTAR/SURVEY@v1:R0",  # index 0
        "NORTHSTAR/SURVEY@v1:R01",  # leading zero index
        "NORTHSTAR/SURVEY@v1:R12345678",  # index too long
        "NORTHSTAR/SURVEY@v1:X1",  # unknown kind
        "NORTHSTAR/SURVEY@v1:R1.",  # trailing dot
        "NORTHSTAR/SURVEY@v1:P1.B2.S3.Q4.R5",  # 5 units
        "NORTHSTAR/SURVEY@v1:AQ3F9A0C21B7D",  # 11 hex
        "NORTHSTAR/SURVEY@v1:AQ3f9a0c21b7d4",  # lowercase hex
        "NORTHSTAR/SURVEY@v1:AQ3F9A0C21B7D4.R1",  # AQ cannot have units
        " NORTHSTAR/SURVEY@v1:R1",  # whitespace is never trimmed
        "NORTHSTAR/SURVEY@v1:R1 ",
        "NORTHSTAR/SURVEY@v1:R1\n",
        "[NORTHSTAR/SURVEY@v1:R1]",  # rendered form needs parse_rendered_handle
        "NORTHSTAR/SURVEY@v1:R1<script>",
        "NORTHSTAR/SURVEY@v1:R1](http://evil)",
        "NORTHSTAR\\SURVEY@v1:R1",
        "NORTHSTAR/SURVEY@v1:R\uff11",  # full-width digit one
        "A" * 200,
    ],
)
def test_malformed_handles_are_rejected(value: str) -> None:
    with pytest.raises(MalformedHandleError):
        parse_handle(value)
    assert try_parse_handle(value) is None


@pytest.mark.parametrize("value", [None, 123, b"NORTHSTAR/SURVEY@v1:R1", ["x"]])
def test_non_strings_are_rejected(value: object) -> None:
    with pytest.raises(MalformedHandleError):
        parse_handle(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "label"),
    [
        ("NORTHSTAR/SURVEY-2026@v1:R185", "Row 185"),
        ("NORTHSTAR/BRAND-STRATEGY@v1:P4.B2", "Page 4, Block 2"),
        ("NORTHSTAR/INTERVIEWS@v1:S3.Q7", "Section 3, Q&A 7"),
        ("NORTHSTAR/Q3-REVIEW@v1:SL6.N1", "Slide 6, Notes 1"),
        ("NORTHSTAR/PRODUCT-PERF@v2:SH2.T1", "Sheet 2, Table 1"),
    ],
)
def test_canonical_examples_parse_with_labels(value: str, label: str) -> None:
    handle = parse_handle(value)
    assert str(handle) == value
    assert handle.locator_label() == label


def test_sheet_names_in_labels() -> None:
    handle = parse_handle("NORTHSTAR/PRODUCT-PERF@v1:SH2.R12")
    assert handle.locator_label({2: "Returns"}) == "Sheet 'Returns', Row 12"


def test_builder_and_source_ref() -> None:
    handle = build_handle("NORTHSTAR", "SURVEY-2026", 1, (LocatorKind.ROW, 185))
    assert str(handle) == "NORTHSTAR/SURVEY-2026@v1:R185"
    assert handle.source_ref == "NORTHSTAR/SURVEY-2026@v1"
    assert str(handle.with_version(2)) == "NORTHSTAR/SURVEY-2026@v2:R185"


def test_structural_xor_analytic() -> None:
    with pytest.raises(MalformedHandleError):
        EvidenceHandle("NORTHSTAR", "X", 1)  # neither
    with pytest.raises(MalformedHandleError):
        EvidenceHandle("NORTHSTAR", "X", 1, (LocatorUnit(LocatorKind.ROW, 1),), "0123456789AB")


def test_workspace_prefix_check() -> None:
    handle = parse_handle("SOUTHPEAK/SURVEY@v1:R2")
    require_workspace(handle, "SOUTHPEAK")
    with pytest.raises(ForeignWorkspaceHandleError):
        require_workspace(handle, "NORTHSTAR")


def test_alphabet_is_render_safe() -> None:
    allowed = set(ALNUM + "v/@:.-")
    handle = parse_handle("NORTHSTAR/A-B@v12:SH3.R40")
    assert set(str(handle)) <= allowed
