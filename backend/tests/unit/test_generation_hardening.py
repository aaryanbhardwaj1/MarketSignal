"""Adversarial-review regressions for the answer contract, verifier, fallback and digest."""

from __future__ import annotations

from dataclasses import replace

import pytest

from marketsignal.generation.contract import (
    ANSWER,
    FINDINGS,
    GAPS,
    INTERPRETATION,
    extract_numbers,
    is_faithful,
    number_values,
    strip_leaks,
)
from marketsignal.generation.fallback import evidence_only
from marketsignal.generation.types import CANONICAL_RE, EvidencePack
from marketsignal.generation.verifier import NO_CITATIONS, verify_answer
from marketsignal.runs.conversation import answer_digest
from tests.unit.test_generation_verifier import H1, H2, PACK, _answer, _item

# --- forged canonical markers (finding 0) ------------------------------------------------------


@pytest.mark.parametrize(
    "forged",
    [
        "[[[](u)OTHERWS/SECRET@v[](u)1:P1]]",
        f"[[[](u){H2}[](u)]]",
        "[()[OTHERWS/SECRET@v1:P1]] <b>x</b>",
        "[[(  )OTHERWS/SECRET@v1:P1]] <i>y</i>",
    ],
)
def test_strip_leaks_reaches_a_fixpoint(forged: str) -> None:
    scan = strip_leaks(f"Price led {forged} here.")
    assert "[[" not in scan.text
    assert "]]" not in scan.text
    assert strip_leaks(scan.text).removed == ()


@pytest.mark.parametrize(
    "forged",
    [
        "[[[](u)OTHERWS/SECRET@v[](u)1:P1]]",
        f"[[[](u){H2}[](u)]]",
        "[[[E9]ABC1]]",
        "[[[inference]ABC1]]",
    ],
)
def test_only_cited_handles_reach_the_final_content(forged: str) -> None:
    raw = _answer(f"Price led for 27% of buyers [E1] {forged}.", f"- Price led [E1] {forged}.")
    result = verify_answer(raw, PACK, pack_truncated=False)
    cited = {card["handle"] for card in result.citations}
    assert cited == {H1}
    assert {m.group(1) for m in CANONICAL_RE.finditer(result.content)} <= cited
    assert (
        result.content.count("[[")
        == result.content.count("]]")
        == len(CANONICAL_RE.findall(result.content))
    )


# --- scale / percent agreement (finding 1) ------------------------------------------------------


@pytest.mark.parametrize(
    ("claim", "evidence", "ok"),
    [
        ("$612.0 billion", "612.0 million", False),
        ("612.0bn", "$612.0M", False),
        ("2,960%", "2,960 respondents", False),
        ("2,960%", "Respondents: 2,960.", False),
        ("$27 million", "27%", False),
        ("€40", "$40", False),
        # intended leniency: a bare (table-cell) figure may back a scaled or percent claim
        ("$612.0 billion", "Net revenue | 2025 | 612.0", True),
        ("16.8%", "margin | 16.8", True),
        ("612.0 million", "$612.0M", True),
        ("612", "612.0 million", True),
        ("1,200 thousand", "1.2 million", True),
        ("USD 40", "$40", True),
        ("14%", "churn of 14 to 21 percent", True),
        ("27", "27%", True),
    ],
)
def test_faithfulness_requires_agreeing_units(claim: str, evidence: str, ok: bool) -> None:
    (mention,) = extract_numbers(claim)
    assert is_faithful(mention, number_values([evidence])) is ok


def test_wrong_scale_claim_dropped_by_verifier() -> None:
    raw = _answer("Price led for 27% of buyers [E1]. Net revenue was 612.0 billion [E1].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert "612.0 billion" not in result.content
    revenue = _item(4, "NORTHSTAR/FINANCE@v1:P1", "Net revenue was 612.0 million in 2025.")
    pack = EvidencePack(items=(*PACK.items, revenue), tokens=70, truncated=False)
    claim = _answer("Price led for 27% of buyers [E1]. Net revenue was 612.0 billion [E4].")
    assert "612.0 billion" not in verify_answer(claim, pack, pack_truncated=False).content
    percent = _answer("Price led for 27% of buyers [E1]. Margin was 2,960% [E1].")
    assert "2,960%" not in verify_answer(percent, PACK, pack_truncated=False).content


# --- glued units and spelled-out numbers (finding 2) -------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("margin expanded 340bps", [("340", 340.0)]),
        ("share rose 3.2pp", [("3.2", 3.2)]),
        ("up 99pct", [("99", 99.0)]),
        ("a 5x return", [("5", 5.0)]),
        ("gained 12pts and 4bp", [("12", 12.0), ("4", 4.0)]),
        ("nine hundred million dollars", [("900", 900e6)]),
        ("twenty-one percent", [("21", 21.0)]),
        ("two hundred and five thousand", [("205", 205e3)]),
        ("one of the top drivers", []),
    ],
)
def test_glued_units_and_spelled_numbers_extracted(
    text: str, expected: list[tuple[str, float]]
) -> None:
    assert [(m.mantissa_text, m.value) for m in extract_numbers(text)] == expected


def test_pct_suffix_and_spelled_percent_are_percent() -> None:
    assert [m.percent for m in extract_numbers("99pct, 3.2pp, twenty percent")] == [
        True,
        False,
        True,
    ]


def test_glued_unit_and_spelled_figures_must_be_in_cited_evidence() -> None:
    raw = _answer(
        "Price led for 27% of buyers [E1]. Margin expanded 340bps and share rose 9.9pp [E2]. "
        "Net revenue was nine hundred million dollars [E2]."
    )
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert "340bps" not in result.content
    assert "nine hundred" not in result.content
    assert len(result.report.numeric_violations) == 2
    spelled = _answer("Price led for twenty-seven percent of buyers [E1].")
    assert "twenty-seven percent" in verify_answer(spelled, PACK, pack_truncated=False).content


# --- interpretation citations (finding 3) ------------------------------------------------------


def test_interpretation_citation_must_support_its_numbers() -> None:
    raw = _answer("Price led for 27% of buyers [E1].") + (
        "### Interpretation\nRevenue was 612.0 million [E1]. Revenue of 612.0 matters [E2]."
    )
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[INTERPRETATION] == [f"Revenue of 612.0 matters [[{H2}]] [inference]."]
    assert result.report.numeric_violations == [
        "Interpretation #1: 612.0 million not found in cited evidence E1"
    ]


# --- gaps (finding 8) --------------------------------------------------------------------------


def test_gaps_factual_claims_tagged_as_inference() -> None:
    raw = _answer("Price led for 27% of buyers [E1].") + (
        "### Gaps & unknowns\n- Competitor Acme is exiting the market next year.\n"
        "- Regional pricing is not covered.\n- No regional split is available."
    )
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[GAPS] == [
        "Competitor Acme is exiting the market next year [inference].",
        "Regional pricing is not covered.",
        "No regional split is available.",
    ]


def test_gaps_factual_claim_does_not_waive_no_citations() -> None:
    raw = "### Answer\nBuyers care about value.\n\n### Gaps & unknowns\nAcme cannot be beaten."
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert NO_CITATIONS in result.report.structural_failures
    insufficient = (
        "### Answer\nBuyers care about value.\n\n### Gaps & unknowns\n"
        "The evidence does not cover regional pricing."
    )
    assert verify_answer(insufficient, PACK, pack_truncated=False).ok


# --- evidence-only fallback (finding 9) --------------------------------------------------------


def test_evidence_only_snippets_title_and_locator_are_leak_free() -> None:
    leaky = _item(
        1,
        H1,
        "See https://attacker.example/x and 123e4567-e89b-12d3-a456-426614174000 "
        f"or {H2} for 27% of buyers.",
    )
    leaky = replace(
        leaky,
        source_title="Deck www.evil.example/a",
        locator_label="Row 1 #w4",
        anchor_char_start=0,
        anchor_char_end=10,
    )
    answer = evidence_only(EvidencePack(items=(leaky,), tokens=20, truncated=False), "failed")
    for leak in ("http", "www.", "attacker", "123e4567", "#w4", H2):
        assert leak not in answer.content
    assert f"[[{H1}]]" in answer.content
    assert strip_leaks(CANONICAL_RE.sub("", answer.content)).removed == ()


# --- conversation digest (finding 10) ----------------------------------------------------------


def test_answer_digest_excludes_inference_units() -> None:
    sections: dict[str, object] = {
        ANSWER: [
            f"Price led for 27% of buyers [[{H1}]].",
            "Acme will raise prices in Europe [inference].",
        ],
        FINDINGS: [f"Price led [[{H1}]]."],
    }
    assert answer_digest(sections) == "Price led for 27% of buyers."
    assert answer_digest({ANSWER: "Guess [inference]. Fact [[" + H1 + "]]."}) == "Fact."
