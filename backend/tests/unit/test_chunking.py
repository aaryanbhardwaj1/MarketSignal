"""Child derivation and the D1 span contract."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from marketsignal.domain.enums import ChildKind
from marketsignal.evidence.handles import LocatorKind
from marketsignal.ingestion.chunking import ChildContractError, build_children, check_child_contract
from marketsignal.ingestion.models import ChildDraft, ParentDraft, ParentKind, RowChildSpec
from marketsignal.ingestion.structure import Unit, group_units
from marketsignal.ingestion.tokenizer import RegexTokenizer

TOK = RegexTokenizer()


def narrative(text: str) -> ParentDraft:
    return ParentDraft(
        ((LocatorKind.PAGE, 1), (LocatorKind.BLOCK, 1)), ParentKind.NARRATIVE, text, ("H",)
    )


def test_short_parent_yields_one_window_covering_the_text() -> None:
    (child,) = build_children([narrative("  Fit is inconsistent.  ")], TOK, 192, 32)
    assert child.kind is ChildKind.WINDOW
    assert (child.char_start, child.char_end) == (2, 22)
    assert child.text == "Fit is inconsistent."
    assert child.heading_text == "H"


def test_windows_overlap_and_stride() -> None:
    text = " ".join(f"w{i}" for i in range(100))
    children = build_children([narrative(text)], TOK, 40, 10)
    assert [c.token_count for c in children] == [40, 40, 40]  # ends at 40, 70, 100
    assert children[1].text.startswith("w30 ")  # stride = 40 - 10
    assert children[-1].text.endswith("w99")


@settings(max_examples=300)
@given(
    st.text(alphabet=st.sampled_from("ab cd.\n,!"), min_size=1, max_size=600),
    st.integers(min_value=2, max_value=60),
    st.data(),
)
def test_windows_cover_every_token_and_honour_the_contract(
    text: str, size: int, data: st.DataObject
) -> None:
    overlap = data.draw(st.integers(min_value=0, max_value=size - 1))
    parent = narrative(text)
    children = build_children([parent], TOK, size, overlap)
    spans = TOK.spans(text)
    if len(spans) == 0:
        assert children == []
        return
    covered = {
        i for c in children for i, s in enumerate(spans.starts) if c.char_start <= s < c.char_end
    }
    assert covered == set(range(len(spans)))
    for child in children:
        assert text[child.char_start : child.char_end] == child.text
        assert child.token_count <= size


def test_row_child_span_points_at_verbatim_cell() -> None:
    text = "id: R1; verbatim: Too slow."
    start = text.index("Too")
    parent = ParentDraft(
        ((LocatorKind.ROW, 2),),
        ParentKind.ROW,
        text,
        ("Survey",),
        row_child=RowChildSpec("Survey | verbatim: Too slow.", start, len(text)),
    )
    numeric = ParentDraft(
        ((LocatorKind.ROW, 3),), ParentKind.ROW, "id: R2; nps: 9", ("Survey",), index_children=False
    )
    children = build_children([parent, numeric], TOK, 192, 32)
    (child,) = children
    assert child.kind is ChildKind.ROW
    assert child.parent_ordinal == 0
    assert text[child.char_start : child.char_end] == "Too slow."


def test_summary_child_covers_whole_parent() -> None:
    parent = ParentDraft(
        ((LocatorKind.TABLE, 1),), ParentKind.TABLE_SUMMARY, "Table 'x': 2 rows.", ("x",)
    )
    (child,) = build_children([parent], TOK, 192, 32)
    assert child.kind is ChildKind.SUMMARY
    assert (child.char_start, child.char_end) == (
        0,
        len(parent.text),
    )


def test_contract_violations_are_detected() -> None:
    parent = narrative("abc def")
    bad = ChildDraft(0, 0, ChildKind.WINDOW, "xyz", 0, 3, 1)
    with pytest.raises(ChildContractError):
        check_child_contract([parent], [bad])
    with pytest.raises(ChildContractError):
        check_child_contract([parent], [ChildDraft(0, 0, ChildKind.WINDOW, "abc", 0, 99, 1)])


def test_overlap_must_be_smaller_than_window() -> None:
    with pytest.raises(ValueError, match="overlap"):
        build_children([narrative("a b")], TOK, 10, 10)


def test_changing_child_policy_never_changes_parents() -> None:
    parents = [narrative(" ".join(f"t{i}" for i in range(300)))]
    snapshot = list(parents)
    a = build_children(parents, TOK, 192, 32)
    b = build_children(parents, TOK, 64, 8)
    assert parents == snapshot
    assert len(a) != len(b)


def test_group_units_caps_blocks_and_tags_split_lists() -> None:
    units = [Unit("intro " * 5)] + [Unit(f"item {i} " * 4, list_run=1) for i in range(10)]
    blocks = group_units(units, TOK, 30, "P1")
    assert all(TOK.count(b.text) <= 30 for b in blocks)
    split = [b for b in blocks if b.list_group_id]
    assert len(split) >= 2
    assert len({b.list_group_id for b in split}) == 1


def test_group_units_splits_oversize_paragraphs_at_sentences() -> None:
    sentence = "This sentence has exactly eight tokens in it. "
    blocks = group_units([Unit(sentence * 10)], TOK, 20, "")
    assert len(blocks) > 1
    assert all(TOK.count(b.text) <= 20 for b in blocks)
