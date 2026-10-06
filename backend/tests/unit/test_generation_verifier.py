"""Answer contract and deterministic verifier: parsing, numbers, leakage, repair, structure."""

from __future__ import annotations

import re
import uuid

import pytest

from marketsignal.generation.contract import (
    ANSWER,
    CONFLICTS,
    FINDINGS,
    GAPS,
    INTERPRETATION,
    UNRECOGNIZED,
    extract_numbers,
    is_faithful,
    number_values,
    parse_sections,
    split_units,
    states_insufficient,
    strip_leaks,
)
from marketsignal.generation.types import CANONICAL_RE, EvidencePack, PackItem
from marketsignal.generation.verifier import (
    ANSWER_MISSING,
    ANSWER_TOO_LONG,
    GAPS_MISSING,
    NO_CITATIONS,
    TOO_MANY_CITATIONS,
    regeneration_feedback,
    verify_answer,
)

H1 = "NORTHSTAR/SURVEY-2026@v1:R185"
H2 = "NORTHSTAR/BRAND-STRATEGY@v1:P4.B2"
H3 = "NORTHSTAR/INTERVIEWS@v1:S3.Q7"
ALIAS_IN_TEXT = re.compile(r"\[E\d+\]")


def _item(rank: int, handle: str, text: str) -> PackItem:
    return PackItem(
        alias=f"E{rank}",
        rank=rank,
        handle=handle,
        parent_id=uuid.UUID(int=rank),
        source_code=handle.split("/")[1].split("@")[0],
        source_title=f"Source {rank}",
        source_class="survey",
        source_type="csv",
        locator_label=f"Row {rank}",
        heading_path=("Root",),
        text=text,
        window=None,
        tokens=len(text.split()),
        content_hash=f"hash{rank}",
        anchor_child_id=uuid.UUID(int=100 + rank),
        anchor_char_start=rank * 10,
        anchor_char_end=rank * 10 + 5,
        fused_rank=rank,
    )


PACK = EvidencePack(
    items=(
        _item(1, H1, "Respondents: 2,960. Price was the top driver for 27% of buyers in 2025."),
        _item(2, H2, "Net revenue | 2025 | 612.0 | margin | 16.8"),
        _item(3, H3, "Interviewees expect churn of 14 to 21 percent by 2027."),
    ),
    tokens=60,
    truncated=False,
)
EMPTY_PACK = EvidencePack(items=(), tokens=0, truncated=False)


def _answer(answer: str, findings: str = "- Price led for 27% of buyers [E1].") -> str:
    return f"### Answer\n{answer}\n\n### Key findings\n{findings}\n"


# --- section parsing -------------------------------------------------------------------------


def test_sections_heading_levels_and_variants() -> None:
    raw = (
        "## Answer\nA.\n### Key Findings\n- f\n#### Conflicting evidence\n- c\n"
        "### Interpretation\ni\n### Gaps and unknowns\ng\n"
    )
    sections = parse_sections(raw)
    assert list(sections) == [ANSWER, FINDINGS, CONFLICTS, INTERPRETATION, GAPS]
    assert sections[FINDINGS] == "- f"
    assert parse_sections("### Gaps & Unknowns:\nx")[GAPS] == "x"
    assert parse_sections("### **gaps &amp; unknowns**\nx")[GAPS] == "x"


def test_sections_unrecognized_preamble_and_unknown_heading() -> None:
    raw = "Sure, here it is.\n### Answer\nA [E1].\n### Sources\nsee docs\n# Answer\n"
    sections = parse_sections(raw)
    assert sections[UNRECOGNIZED] == "Sure, here it is.\n\nsee docs\n# Answer"
    assert sections[ANSWER] == "A [E1]."


def test_sections_repeated_heading_concatenates_and_fences_are_not_headings() -> None:
    raw = "### Answer\nOne.\n```\n### Gaps & unknowns\n```\n### Answer\nTwo."
    sections = parse_sections(raw)
    assert GAPS not in sections
    assert sections[ANSWER].startswith("One.")
    assert sections[ANSWER].endswith("Two.")


def test_sections_heading_level_one_and_five_are_text() -> None:
    assert parse_sections("# Answer\nx\n##### Answer\ny") == {
        UNRECOGNIZED: "# Answer\nx\n##### Answer\ny"
    }


# --- unit segmentation ------------------------------------------------------------------------


def test_split_bullets_one_unit_each_with_continuation() -> None:
    text = "- First. Still first.\n  continued\n* Second\n1. Third\n2) Fourth"
    assert split_units(text) == ["First. Still first. continued", "Second", "Third", "Fourth"]


def test_split_sentences_decimals_and_abbreviations() -> None:
    text = (
        "Margin was 16.8 in 2025, e.g. in Q2 vs. Q1 [E2]. Acme Inc. and Beta Co. grew approx. "
        "half. See No. 3 for detail. The answer is no. Done."
    )
    assert split_units(text) == [
        "Margin was 16.8 in 2025, e.g. in Q2 vs. Q1 [E2].",
        "Acme Inc. and Beta Co. grew approx. half.",
        "See No. 3 for detail.",
        "The answer is no.",
        "Done.",
    ]


def test_split_keeps_citations_on_both_sides_of_punctuation() -> None:
    text = "Price led at 27% [E1]. Revenue was 612.0. [E2] [E1] Churn may rise. [inference] Ok."
    assert split_units(text) == [
        "Price led at 27% [E1].",
        "Revenue was 612.0. [E2] [E1]",
        "Churn may rise. [inference]",
        "Ok.",
    ]


def test_split_respects_markdown_and_citation_internals() -> None:
    text = "**Revenue rose.** Then `a. B` stayed. Ref [[NORTHSTAR/X@v1:P4.B2]] holds. Last"
    assert split_units(text) == [
        "**Revenue rose.**",
        "Then `a. B` stayed.",
        "Ref [[NORTHSTAR/X@v1:P4.B2]] holds.",
        "Last",
    ]


def test_split_no_split_before_lowercase_and_paragraph_breaks() -> None:
    assert split_units("Growth vs. decline. it continued.\n\nNew paragraph") == [
        "Growth vs. decline. it continued.",
        "New paragraph",
    ]


# --- numbers -----------------------------------------------------------------------------------


def _norm(text: str) -> list[tuple[str, float]]:
    return [(m.mantissa_text, m.value) for m in extract_numbers(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("27%", [("27", 27.0)]),
        ("27 percent", [("27", 27.0)]),
        ("27 per cent", [("27", 27.0)]),
        ("$612.0 million", [("612.0", 612.0e6)]),
        ("$612.0M", [("612.0", 612.0e6)]),
        ("€3m and £4bn", [("3", 3e6), ("4", 4e9)]),
        ("USD 40", [("40", 40.0)]),
        ("2,960 respondents", [("2960", 2960.0)]),
        ("12k users, 1.2 billion", [("12", 12e3), ("1.2", 1.2e9)]),
        ("down -3.2%", [("3.2", -3.2)]),
        ("14 to 21", [("14", 14.0), ("21", 21.0)]),
        ("14\u201321", [("14", 14.0), ("21", 21.0)]),
        ("14-21", [("14", 14.0), ("21", 21.0)]),
        ("in 2025", [("2025", 2025.0)]),
    ],
)
def test_number_formats(text: str, expected: list[tuple[str, float]]) -> None:
    assert _norm(text) == expected


def test_number_flags_percent_and_currency() -> None:
    (pct,) = extract_numbers("21 percent")
    (cur,) = extract_numbers("US$5")
    assert pct.percent
    assert pct.currency is None
    assert cur.currency == "US$"
    assert not cur.percent


def test_numbers_glued_identifiers_and_ordinals_ignored() -> None:
    text = "1. Q2 FY26 R0147 NS-KR2 E3 v1 v1.2 3rd 21st COVID-19 SURVEY-2026 [E3] 5"
    assert _norm(text) == [("5", 5.0)]
    assert _norm("- 2) item\n3. other 7") == [("7", 7.0)]


@pytest.mark.parametrize(
    ("claim", "evidence", "ok"),
    [
        ("$612.0 million", "612.0", True),
        ("$612.0 million", "$612.0M", True),
        ("612,000,000", "$612.0M", True),
        ("1.2M", "1,200,000", True),
        ("21%", "21 percent", True),
        ("16.8%", "| 16.8 |", True),
        ("612", "612.0", True),
        ("613", "612.0", False),
        ("19.4%", "21%", False),
        ("2026", "in 2025", False),
    ],
)
def test_faithfulness(claim: str, evidence: str, ok: bool) -> None:
    (mention,) = extract_numbers(claim)
    assert is_faithful(mention, number_values([evidence])) is ok


# --- leakage -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind", "kept"),
    [
        ("See https://example.com/a?b=1 now", "url", "See now"),
        ("Visit www.example.com.", "url", "Visit."),
        ("Chart ![c](http://x/c.png) here", "image", "Chart here"),
        ("Read [the memo](http://x) today", "link", "Read the memo today"),
        ("Text <b>bold</b> end", "html", "Text bold end"),
        ("Id 123e4567-e89b-12d3-a456-426614174000 x", "uuid", "Id x"),
        ("Child #w3 here", "child_id", "Child here"),
        (f"Raw {H1} here", "raw_handle", "Raw here"),
        (f"Raw [{H2}#w4] here", "raw_handle", "Raw here"),
        (f"Forged [[{H1}]] marker", "canonical_marker", "Forged marker"),
        ("A <script>alert(1)</script> B", "html", "A B"),
    ],
)
def test_strip_leaks(text: str, kind: str, kept: str) -> None:
    scan = strip_leaks(text)
    assert kind in scan.removed
    assert scan.text == kept


def test_strip_leaks_no_leak_is_identity_and_alias_link_keeps_brackets() -> None:
    clean = "Price led at 27% [E1].  Two spaces kept."
    assert strip_leaks(clean).text == clean
    assert strip_leaks(clean).removed == ()
    assert strip_leaks("Fact [E3](#src).").text == "Fact [E3]."


# --- verifier: citations -------------------------------------------------------------------------


def test_valid_answer_passes_and_is_canonical() -> None:
    raw = _answer("Price was the top driver for 27% of buyers [E1]. Margin was 16.8% [E2].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.ok
    assert result.report.passed
    assert result.report.structural_failures == []
    assert f"[[{H1}]]" in result.content
    assert f"[[{H2}]]" in result.content
    assert not ALIAS_IN_TEXT.search(result.content)
    assert all(CANONICAL_RE.fullmatch(f"[[{h}]]") for h in (H1, H2))
    assert result.content.startswith("### Answer\n\n")
    assert "### Key findings\n\n- Price led for 27% of buyers" in result.content


def test_unknown_and_malformed_aliases_removed() -> None:
    raw = _answer("Price led at 27% [E1] [E7] [E] [E123] [e3] [ E3 ] [E1, E2].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.report.unknown_aliases == ["E7", "E", "E123", "e3", " E3 ", "E1, E2"]
    assert result.sections[ANSWER] == [f"Price led at 27% [[{H1}]]."]
    assert not ALIAS_IN_TEXT.search(result.content)


def test_alias_outside_pack_does_not_count_as_citation() -> None:
    raw = _answer("Price led at 27% [E9].", findings="- Revenue 612.0 [E12].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.report.unknown_aliases == ["E9", "E12"]
    assert result.sections[ANSWER] == ["Price led at 27% [inference]."]
    assert FINDINGS not in result.sections
    assert NO_CITATIONS in result.report.structural_failures


def test_duplicate_citation_in_unit_collapses() -> None:
    raw = _answer("Price led at 27% [E1] [E1] of buyers [E1].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[ANSWER][0].count(f"[[{H1}]]") == 1
    assert any("duplicate citation E1" in r for r in result.report.repairs)


def test_citation_cards_order_uniqueness_and_anchor_fields() -> None:
    raw = _answer(
        "Margin was 16.8 [E2]. Price led at 27% [E1].",
        findings="- Margin 16.8 [E2].\n- Churn 14 to 21 percent [E3] [E1].",
    )
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert [c["handle"] for c in result.citations] == [H2, H1, H3]
    assert result.report.cited_aliases == ["E2", "E1", "E3"]
    assert result.report.citations == 5
    card = result.citations[0]
    assert card["parent_content_hash"] == "hash2"
    assert card["anchor_child_id"] == str(uuid.UUID(int=102))
    assert (card["char_start"], card["char_end"]) == (20, 25)
    assert all("alias" not in c for c in result.citations)


# --- verifier: numeric and section rules -------------------------------------------------------


def test_numeric_violation_drops_cited_sentence() -> None:
    raw = _answer("Price led at 19.4% [E1]. Revenue was $612.0 million [E2].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[ANSWER] == [f"Revenue was $612.0 million [[{H2}]]."]
    assert result.report.numeric_violations == ["Answer #1: 19.4% not found in cited evidence E1"]


def test_number_must_come_from_the_cited_item_not_the_pack() -> None:
    # Phase 4 (A3): the figure is stated exactly in one other item only, so the citation is
    # re-pointed there instead of dropping a true claim; ambiguous figures are still dropped.
    raw = _answer("Revenue was 612.0 [E2].", findings="- Revenue 612.0 [E1].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[FINDINGS] == [f"Revenue 612.0 [[{H2}]]."]
    assert result.report.repairs == [
        "Key findings #1: re-pointed citation E1 -> E2 (only item with the figures)"
    ]
    assert result.report.numeric_violations == []
    twice = EvidencePack(
        items=(*PACK.items, _item(4, "NORTHSTAR/FINANCE@v1:P1", "Net revenue 612.0")),
        tokens=70,
        truncated=False,
    )
    ambiguous = verify_answer(raw, twice, pack_truncated=False)
    assert FINDINGS not in ambiguous.sections
    assert ambiguous.report.numeric_violations == [
        "Key findings #1: 612.0 not found in cited evidence E1"
    ]


def test_uncited_answer_sentence_tagged_or_dropped() -> None:
    raw = _answer("Price led at 27% [E1]. Buyers favour value at 27%. Churn will hit 40%.")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[ANSWER] == [
        f"Price led at 27% [[{H1}]].",
        "Buyers favour value at 27% [inference].",
    ]
    assert result.report.numeric_violations == []
    assert any("tagged uncited sentence" in r for r in result.report.repairs)
    assert any("dropped uncited sentence" in r for r in result.report.repairs)


def test_inference_sentence_numbers_must_be_in_pack() -> None:
    raw = _answer(
        "Price led [E1]. Churn will reach 40% [inference]. Churn may reach 21% [inference]."
    )
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[ANSWER][1:] == ["Churn may reach 21% [inference]."]
    assert result.report.numeric_violations == ["Answer #2: 40% not found in the evidence pack"]


def test_finding_without_citation_dropped() -> None:
    raw = _answer("Price led [E1].", findings="- Price led for 27% of buyers [E1].\n- Uncited.")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert len(result.sections[FINDINGS]) == 1
    assert "Key findings #2: dropped unit without a valid citation" in result.report.repairs


def test_conflicts_need_citations() -> None:
    raw = (
        _answer("Price led [E1].") + "### Conflicting evidence\n- Interviews disagree [E3].\n- No."
    )
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[CONFLICTS] == [f"Interviews disagree [[{H3}]]."]


def test_interpretation_tagged_and_new_numbers_dropped() -> None:
    raw = _answer("Price led [E1].") + (
        "### Interpretation\nValue messaging should matter more. "
        "Churn near 21% is likely [inference]. Share could reach 35%."
    )
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[INTERPRETATION] == [
        "Value messaging should matter more [inference].",
        "Churn near 21% is likely [inference].",
    ]
    assert result.report.numeric_violations == [
        "Interpretation #3: 35% not found in the evidence pack"
    ]


def test_gaps_aliases_removed_and_numbers_dropped() -> None:
    raw = _answer("Price led [E1].") + (
        "### Gaps & unknowns\n- No regional split is available [E2] [E9].\n- Nothing after 2025."
    )
    result = verify_answer(raw, PACK, pack_truncated=True)
    assert result.sections[GAPS] == ["No regional split is available."]
    assert result.report.unknown_aliases == ["E9"]
    assert result.ok
    assert result.report.cited_aliases == ["E1"]


def test_gaps_required_when_truncated() -> None:
    missing = verify_answer(_answer("Price led [E1]."), PACK, pack_truncated=True)
    assert missing.report.structural_failures == [GAPS_MISSING]
    assert not missing.ok
    assert not missing.report.passed
    only_numbers = _answer("Price led [E1].") + "### Gaps & unknowns\nData after 2025 is missing."
    emptied = verify_answer(only_numbers, PACK, pack_truncated=True)
    assert GAPS_MISSING in emptied.report.structural_failures
    assert verify_answer(_answer("Price led [E1]."), PACK, pack_truncated=False).ok


def test_unrecognized_text_dropped_and_leaks_reported() -> None:
    raw = "Here you go: https://x.io\n" + _answer(
        "Price led at 27% [E1] (see https://evil.example/a). <i>Revenue</i> was 612.0 [E2]."
    )
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert "dropped text outside the answer sections" in result.report.repairs
    assert result.report.leaks_removed == ["url", "url", "html", "html"]
    assert "http" not in result.content
    assert "<" not in result.content
    assert result.ok


# --- verifier: structural failures -------------------------------------------------------------


def test_answer_missing() -> None:
    result = verify_answer("### Key findings\n- Price led at 27% [E1].", PACK, pack_truncated=False)
    assert ANSWER_MISSING in result.report.structural_failures
    emptied = verify_answer(_answer("Churn will hit 40%."), PACK, pack_truncated=False)
    assert ANSWER_MISSING in emptied.report.structural_failures


def test_no_citations_vs_insufficiency_statement() -> None:
    uncited = "### Answer\nBuyers care about value."
    assert (
        NO_CITATIONS
        in verify_answer(uncited, PACK, pack_truncated=False).report.structural_failures
    )
    insufficient = "### Answer\nThe evidence does not contain regional pricing data."
    result = verify_answer(insufficient, PACK, pack_truncated=False)
    assert result.ok
    # Phase 4 (A5): an evidence-gap statement is not an inference, so it stays untagged.
    assert result.sections[ANSWER] == ["The evidence does not contain regional pricing data."]
    assert result.report.gap_statements == ["Answer #1"]
    assert verify_answer(uncited, EMPTY_PACK, pack_truncated=False).ok


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("There is insufficient evidence to answer.", True),
        ("No relevant data was found.", True),
        ("The sources do not address churn.", True),
        ("This cannot be determined from the pack.", True),
        ("Evidence is limited but points to price.", False),
        ("Buyers have no loyalty.", False),
    ],
)
def test_insufficiency_regex_is_conservative(text: str, expected: bool) -> None:
    assert states_insufficient(text) is expected


def test_too_many_citations() -> None:
    findings = "\n".join(f"- Point {n} led [E1] [E2] [E3]." for n in "ABCDEFG")
    result = verify_answer(_answer("Price led [E1].", findings), PACK, pack_truncated=False)
    assert result.report.citations > 20
    assert TOO_MANY_CITATIONS in result.report.structural_failures


def test_answer_too_long_counts_before_repair() -> None:
    answer = "A [E1]. B [E1]. C [E1]. D [E1]. Churn will hit 40%."
    result = verify_answer(_answer(answer), PACK, pack_truncated=False)
    assert len(result.sections[ANSWER]) == 4
    assert ANSWER_TOO_LONG in result.report.structural_failures


# --- determinism and feedback ------------------------------------------------------------------


def test_deterministic() -> None:
    raw = "Intro\n" + _answer("Price led at 27% [E1] [E7]. Churn grows.") + "### Gaps & unknowns\nx"
    first = verify_answer(raw, PACK, pack_truncated=True)
    second = verify_answer(raw, PACK, pack_truncated=True)
    assert first == second
    assert first.report.as_dict() == second.report.as_dict()


def test_regeneration_feedback() -> None:
    raw = "### Answer\nPrice led at 19.4% [E1] [E8]."
    report = verify_answer(raw, PACK, pack_truncated=True).report
    feedback = regeneration_feedback(report)
    assert "'### Answer' section is missing" in feedback
    assert "Gaps & unknowns" in feedback
    assert "19.4% not found in cited evidence E1" in feedback
    assert "E8" in feedback
    assert feedback.count("\n- ") >= 3
    ok_report = verify_answer(_answer("Price led [E1]."), PACK, pack_truncated=False).report
    assert regeneration_feedback(ok_report) == ""
