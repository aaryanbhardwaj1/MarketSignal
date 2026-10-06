"""Phase 4 verifier precision (A1-A5, A7): fewer false positives, same false-negative guards."""

from __future__ import annotations

import uuid
from html import escape

import pytest

from marketsignal.db.scope import WorkspaceScope
from marketsignal.generation.contract import (
    ANSWER,
    FINDINGS,
    INTERPRETATION,
    extract_numbers,
    states_insufficient,
)
from marketsignal.generation.prompts import (
    SYSTEM_PROMPT,
    build_system_prompt,
    render_user_turn,
    visible_metadata,
)
from marketsignal.generation.types import EvidencePack, PackItem
from marketsignal.generation.verifier import (
    TOO_MANY_CITATIONS,
    detect_conflicts,
    regeneration_feedback,
    verify_answer,
)


def _item(
    rank: int,
    text: str,
    *,
    title: str = "Field Notes",
    locator: str = "Page 1",
    heading: tuple[str, ...] = (),
) -> PackItem:
    return PackItem(
        alias=f"E{rank}",
        rank=rank,
        handle=f"WS/SRC{rank}@v1:P{rank}",
        parent_id=uuid.UUID(int=rank),
        source_code=f"SRC{rank}",
        source_title=title,
        source_class="survey",
        source_type="text",
        locator_label=locator,
        heading_path=heading,
        text=text,
        window=None,
        tokens=len(text.split()),
        content_hash=f"h{rank}",
        anchor_child_id=uuid.UUID(int=100 + rank),
        anchor_char_start=0,
        anchor_char_end=5,
        fused_rank=rank,
    )


def _pack(*items: PackItem, truncated: bool = False) -> EvidencePack:
    return EvidencePack(items=items, tokens=10, truncated=truncated)


def _ans(answer: str, findings: str = "") -> str:
    body = f"### Answer\n{answer}\n"
    return body + (f"\n### Key findings\n{findings}\n" if findings else "")


PACK = _pack(
    _item(1, "Loyalty members rated delivery 4.2 out of 5; 38% cited late parcels.",
          title="Customer Pulse 2025", locator="Slide 7", heading=("Q3 2025 Review", "Delivery")),
    _item(2, "Region | Revenue ($m)\nEMEA | 612.0\nAPAC | 233.5", title="Finance Pack",
          locator="Table 4"),
    _item(3, "Store count reached 1,840 after 112 openings.", locator="Page 9"),
)  # fmt: skip


# --- A1: temporal values ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "temporal"),
    [
        ("in 2025", True),
        ("the 2026 edition", True),
        ("Q3 2025 results", True),
        ("March 2024", True),
        ("between 2023 and 2025", True),
        ("Brand Strategy 2026", True),
        ("2,025 units", False),
        ("2025 respondents", False),
        ("sold 1990 widgets", False),
    ],
)
def test_year_shaped_numbers_are_temporal_only_in_date_context(text: str, temporal: bool) -> None:
    mentions = [m for m in extract_numbers(text) if m.mantissa >= 1000]
    assert mentions
    assert all(m.temporal is temporal for m in mentions)


def test_iso_date_year_is_temporal_and_day_month_stay_checked() -> None:
    # Review R2: day/month digits are never masked; an exact copy of the date still matches.
    mentions = extract_numbers("Updated 2025-03-14 with 38% coverage")
    assert [(m.mantissa_text, m.temporal) for m in mentions] == [
        ("2025", True),
        ("03", False),
        ("14", False),
        ("38", False),
    ]


def test_year_from_sibling_item_or_question_is_accepted() -> None:
    raw = _ans("Late parcels drove complaints for 38% of members in 2025 [E1].")
    assert verify_answer(raw, PACK, pack_truncated=False).ok
    # Review R3: a cited unit's year must be in the cited item (text or visible metadata);
    # the question and other items only back years in uncited/[inference] units.
    q3 = _ans("In Q3 2026, 38% of members cited late parcels [E1].")
    cited = verify_answer(q3, PACK, pack_truncated=False, question="What happened in Q3 2026?")
    assert not cited.ok
    guess = _ans("Delivery rated 4.2 [E1]. Parcels may slow again in 2026 [inference].")
    tagged = verify_answer(guess, PACK, pack_truncated=False, question="Outlook for 2026?")
    assert tagged.sections[ANSWER][1] == "Parcels may slow again in 2026 [inference]."
    assert len(verify_answer(guess, PACK, pack_truncated=False).sections[ANSWER]) == 1


def test_genuine_year_shaped_quantity_still_checked() -> None:
    raw = _ans("The chain reached 2025 stores [E3].")
    assert not verify_answer(raw, PACK, pack_truncated=False).ok


# --- A2: visible metadata ----------------------------------------------------------------------


def test_visible_metadata_is_exactly_what_render_pack_shows() -> None:
    item = PACK.items[0]
    assert visible_metadata(item) == ("Customer Pulse 2025", "Slide 7", "Q3 2025 Review > Delivery")
    turn = render_user_turn("q", PACK)
    for value in visible_metadata(item):
        assert escape(value, quote=True) in turn


def test_metadata_number_supports_only_same_form_claims() -> None:
    slide = _ans("Slide 7 reports a 4.2 delivery rating [E1].")
    assert verify_answer(slide, PACK, pack_truncated=False).ok
    pct = _ans("Delivery scored 7% [E1].")  # "Slide 7" must not back a percent claim
    assert not verify_answer(pct, PACK, pack_truncated=False).ok


def test_hidden_metadata_never_supports() -> None:
    raw = _ans("The source has 4 hash fields [E3].")  # content_hash/rank are never shown
    assert not verify_answer(raw, PACK, pack_truncated=False).ok


# --- A3: clause repair, re-pointing, dangling references ----------------------------------------


def test_unsupported_clause_removed_supported_clause_kept() -> None:
    raw = _ans("Members rated delivery 4.2; returns rose 19% [E1].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.ok
    assert result.sections[ANSWER] == ["Members rated delivery 4.2 [[WS/SRC1@v1:P1]]."]
    assert any("clause" in r for r in result.report.repairs)


@pytest.mark.parametrize("sep", [", while", ", whereas", ", but", ", and"])
def test_conjunction_clause_removed(sep: str) -> None:
    raw = _ans(f"EMEA revenue was $612.0 million{sep} APAC grew 41% [E2].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[ANSWER] == ["EMEA revenue was $612.0 million [[WS/SRC2@v1:P2]]."]


def test_parenthetical_with_unsupported_figure_removed() -> None:
    raw = _ans("Store count reached 1,840 (up 9% on the prior year) [E3].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[ANSWER] == ["Store count reached 1,840 [[WS/SRC3@v1:P3]]."]


def test_unsafe_split_drops_the_whole_unit() -> None:
    raw = _ans("Price, range, and speed drove 44% of visits [E1].")
    assert not verify_answer(raw, PACK, pack_truncated=False).ok


def test_citation_repointed_only_to_the_single_item_with_the_exact_figure() -> None:
    raw = _ans("EMEA revenue was 612.0 [E1].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[ANSWER] == ["EMEA revenue was 612.0 [[WS/SRC2@v1:P2]]."]
    twice = _pack(*PACK.items, _item(4, "EMEA revenue (restated): 612.0"))
    assert not verify_answer(raw, twice, pack_truncated=False).ok  # ambiguous: no guessing
    # Review R4: the target must also name the claim's subject; plain percents never move.
    other = _pack(_item(1, "Acme churn was 9%."), _item(2, "Beta revenue was $612.0 million."))
    for claim in ("Acme revenue was $612.0 million [E1].", "Acme churn was 12% [E1]."):
        assert not verify_answer(_ans(claim), other, pack_truncated=False).ok


def test_dangling_reference_after_dropped_unit_is_dropped() -> None:
    raw = _ans("Members rated delivery 4.2 [E1]. Returns rose 19% [E1]. This drove churn [E1].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[ANSWER] == ["Members rated delivery 4.2 [[WS/SRC1@v1:P1]]."]
    assert any("refers back" in r for r in result.report.repairs)


# --- false-negative guards stay intact --------------------------------------------------------


@pytest.mark.parametrize(
    "claim",
    [
        "EMEA revenue was $612.0 billion [E4].",
        "EMEA revenue was €612.0 million [E4].",
        "EMEA revenue was 612.0% of plan [E4].",
        "EMEA revenue was $640.0 million [E4].",
        "EMEA and APAC revenue totalled 845.5 [E2].",
        "Revenue grew 2.4% in 2031 [E2].",
    ],
)
def test_magnitude_currency_percent_and_computed_values_still_rejected(claim: str) -> None:
    pack = _pack(*PACK.items, _item(4, "EMEA net revenue was $612.0 million."))
    assert not verify_answer(_ans(claim), pack, pack_truncated=False).ok


# --- A4: citation cap ---------------------------------------------------------------------------


@pytest.mark.parametrize(("count", "ok"), [(7, True), (8, True), (9, False)])
def test_configurable_citation_cap(count: int, ok: bool) -> None:
    # Single-citation answer + conflict bullets: nothing the citation budget may remove.
    pack = _pack(*(_item(n, f"Fact {n} holds.") for n in range(1, count + 1)))
    sides = "\n".join(f"- Fact {n} holds [E{n}]." for n in range(2, count + 1))
    raw = f"### Answer\nFact 1 holds [E1].\n\n### Conflicting evidence\n{sides}\n"
    result = verify_answer(raw, pack, pack_truncated=False, max_citations=8)
    assert result.ok is ok
    if not ok:
        assert TOO_MANY_CITATIONS in result.report.structural_failures
        assert "at most 8" in regeneration_feedback(result.report)


def test_cap_is_stated_in_the_system_prompt() -> None:
    assert "at most 20 [E#] citation markers" in SYSTEM_PROMPT
    assert "at most 12 [E#] citation markers" in build_system_prompt(12)


# --- A5: evidence gaps are not inferences -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "The available evidence does not establish which rival cut prices.",
        "The sources do not identify the competitor.",
        "None of the sources give a regional split.",
        "Regional churn is not broken down in the evidence.",
        "The evidence does not specify the sample size.",
    ],
)
def test_broadened_insufficiency_patterns(text: str) -> None:
    assert states_insufficient(text)


def test_gap_statement_in_answer_is_not_tagged_inference() -> None:
    raw = _ans(
        "Members rated delivery 4.2 [E1]. The evidence does not identify which carrier was late."
    )
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[ANSWER][1] == "The evidence does not identify which carrier was late."
    assert result.sections["answer_unknowns"] == [result.sections[ANSWER][1]]
    assert result.report.gap_statements == ["Answer #2"]
    claimy = _ans("The sources do not name a carrier, so delivery is likely outsourced.")
    tagged = verify_answer(claimy, PACK, pack_truncated=False)
    assert tagged.sections[ANSWER][0].endswith("[inference].")


# --- A6: structured attempt report ----------------------------------------------------------------


def test_attempt_report_records_rejections_and_evidence_checked() -> None:
    raw = _ans("Members rated delivery 4.2 [E1]. Returns rose 19% [E1] [E7].")
    report = verify_answer(raw, PACK, pack_truncated=False).report
    assert report.evidence_checked == ["E1"]
    assert report.rejected == [
        {
            "section": "Answer",
            "index": 2,
            "aliases": ["E1"],
            "reason": "numbers_not_in_cited_evidence",
            "span": "Returns rose 19% [E1].",
        }
    ]
    assert set(report.failure_categories) == {"numbers_not_in_cited_evidence", "unknown_alias"}
    assert "rejected" not in report.as_dict()  # dropped drafts stay out of the final payload
    assert report.attempt_record()["rejected"] == report.rejected


# --- A7: conflict signal -------------------------------------------------------------------------


def test_conflict_signal_and_prompt_note() -> None:
    a = _item(1, "Net revenue: 612.0")
    b = _item(2, "Net revenue (restated): 598.4")
    c = _item(3, "Gross margin: 41.0")
    signals = detect_conflicts(_pack(a, b, c))
    assert signals == ["E1 and E2 state different values for 'net revenue'"]
    assert detect_conflicts(_pack(a, c)) == []
    turn = render_user_turn("q", _pack(a, b), notes=signals)
    assert "Conflicting evidence" in turn
    assert "different values for" in turn
    assert verify_answer(_ans("Net revenue was 612.0 [E1]."), _pack(a, b), pack_truncated=False).ok


def test_interpretation_gap_rules_unchanged() -> None:
    raw = _ans("Members rated delivery 4.2 [E1].") + "\n### Interpretation\nCarriers matter.\n"
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[INTERPRETATION] == ["Carriers matter [inference]."]
    assert FINDINGS not in result.sections


def test_dataset_row_labels_state_scale_currency_and_percent() -> None:
    row = _pack(_item(1, "region: EMEA; revenue_musd: 612.0; yoy_growth_pct: 12.3"))
    for claim, ok in [
        ("EMEA revenue was USD 612.0 million [E1].", True),
        ("EMEA revenue was 612.0 [E1].", True),
        ("EMEA growth was 12.3% [E1].", True),
        ("EMEA revenue was USD 612.0 billion [E1].", False),
        ("EMEA revenue was EUR 612.0 million [E1].", False),
        ("EMEA growth was USD 12.3 million [E1].", False),
    ]:
        assert verify_answer(_ans(claim), row, pack_truncated=False).ok is ok, claim


def test_fiscal_labels_must_name_a_visible_year() -> None:
    fy = _pack(_item(1, "Online share of sales: 28% in FY2026.", locator="Slide 14"))
    assert verify_answer(_ans("Online share was 28% in FY2026 [E1]."), fy, pack_truncated=False).ok
    assert verify_answer(_ans("Online share was 28% in FY26 [E1]."), fy, pack_truncated=False).ok
    wrong = _ans("Online share was 28% in FY2025 [E1].")
    assert not verify_answer(wrong, fy, pack_truncated=False).ok


def test_trailing_computed_appositive_removed() -> None:
    raw = _ans("Store count reached 1,840, a gain of 9.4% [E3].")
    result = verify_answer(raw, PACK, pack_truncated=False)
    assert result.sections[ANSWER] == ["Store count reached 1,840 [[WS/SRC3@v1:P3]]."]


# --- adversarial review probes (R1-R6): never accept what the Phase 3 verifier rejected -------
# Each probe: (id, pack items [text, title?, locator?, heading?], question, answer, Phase 3
# content). Every unit the current verifier keeps WITHOUT an [inference] tag must also have been
# kept, verbatim, by the Phase 3 verifier; stricter outcomes (dropped or tagged) are allowed.
_PROBES: list[tuple[str, list[list[object]], str, str, str]] = [
    (
        "A1-by-year-from-question",
        [["Store count rose by 112 in 2024."]],
        "Did store count rise by 2000?",
        "Store count rose by 2000 [E1].",
        "",
    ),
    (
        "A1-by-year-from-other-item",
        [["Store count rose by 112 in 2024."], ["The chain was founded in 1950."]],
        "",
        "Store count rose by 1950 [E1].",
        "",
    ),
    (
        "A1-vs-quantity",
        [["Store count reached 1,840 after 112 openings."], ["Founded 1990."]],
        "",
        "Store count reached 1,840 vs 1990 a year earlier [E1].",
        "",
    ),
    (
        "A1-sales-after",
        [["The chain sold 112 cars in 2024."], ["Report 2019."]],
        "",
        "The chain booked 2019 sales [E1].",
        "",
    ),
    (
        "A1-wrong-period",
        [["Revenue was $612.0 million in 2024."], ["Revenue was $580.0 million in 2023."]],
        "",
        "Revenue was $612.0 million in 2023 [E1].",
        "",
    ),
    (
        "A1-wrong-period-question",
        [["Revenue was $612.0 million in 2024."]],
        "What was revenue in 2019?",
        "Revenue was $612.0 million in 2019 [E1].",
        "",
    ),
    (
        "A1-year-plain-qty",
        [["Revenue grew 12%."], ["Data from 2025."]],
        "",
        "Revenue was 2025 [E1].",
        "",
    ),
    (
        "A1-range-prop",
        [["Revenue grew 12% in 2025."], ["Outlook to 2030."]],
        "",
        "In 2025, 2030 were opened [E1].",
        "",
    ),
    (
        "A1-from-to",
        [["Headcount fell from 2,100 to 1,950."], ["Founded 1950. Plan 2100."]],
        "",
        "Headcount fell from 2100 to 1950 [E1].",
        "### Answer\n\nHeadcount fell from 2100 to 1950 [[WS/SRC1@v1:P1]].",
    ),
    (
        "A1-headcount-from",
        [["Headcount was 1,200."], ["Since 2010 the firm grew."]],
        "",
        "Headcount rose from 2010 [E1].",
        "",
    ),
    (
        "MASK-may",
        [["Store count reached 1,840 after 112 openings."]],
        "",
        "Up to 45 may close next year [E1].",
        "",
    ),
    (
        "MASK-march",
        [["Store count reached 1,840 after 112 openings."]],
        "",
        "Since March 40 stores have closed [E1].",
        "",
    ),
    (
        "MASK-dec",
        [["Store count reached 1,840 after 112 openings."]],
        "",
        "Store count reached 1,840 and 12 dec stores closed [E1].",
        "",
    ),
    (
        "MASK-decimal-may",
        [["Prices rose to $1 per unit."]],
        "",
        "Prices of $1.5 may rise further [E1].",
        "",
    ),
    (
        "MASK-uncited",
        [["Store count reached 1,840 after 112 openings."]],
        "",
        "Store count reached 1,840 [E1]. About 45 may close soon.",
        "### Answer\n\nStore count reached 1,840 [[WS/SRC1@v1:P1]].",
    ),
    (
        "MASK-findings",
        [["Store count reached 1,840 after 112 openings."]],
        "",
        "Store count reached 1,840 [E1].\n\n### Key findings\n- In May 38 stores closed [E1]",
        "### Answer\n\nStore count reached 1,840 [[WS/SRC1@v1:P1]].",
    ),
    ("MASK-iso", [["Range 2000 to 2010."]], "", "Prices ranged 2000-12-15 [E1].", ""),
    (
        "A2-slide-smuggle",
        [["Loyalty members rated delivery 4.2 out of 5.", "Customer Pulse", "Slide 12"]],
        "",
        "As Slide 12 shows, 12 stores closed [E1].",
        "",
    ),
    (
        "A2-slide-substring",
        [["Loyalty members rated delivery 4.2 out of 5.", "Customer Pulse", "Slide 1"]],
        "",
        "Slide 12 shows 1 store closed [E1].",
        "",
    ),
    (
        "A2-title-top50",
        [["Brand X grew 3%.", "Top 50 Brands Report", "Page 2"]],
        "",
        "In the Top 50 Brands Report, 50 brands lost share [E1].",
        "",
    ),
    (
        "A2-title-top50-pct",
        [["Brand X grew 3%.", "Top 50 Brands Report", "Page 2"]],
        "",
        "Top 50 brands lost 50% share [E1].",
        "",
    ),
    (
        "A2-heading-number",
        [["Delivery ratings improved.", "Pulse", "Page 3", ["Section 40 Closures"]]],
        "",
        "Section 40 says 40 stores closed [E1].",
        "",
    ),
    (
        "A2-other-item-meta-uncited",
        [["Delivery improved."], ["Nothing here.", "Pulse", "Table 300"]],
        "",
        "Delivery improved [E1]. Table 300 implies 300 closures [inference].",
        "### Answer\n\nDelivery improved [[WS/SRC1@v1:P1]].",
    ),
    (
        "A3-repoint-pct",
        [["Acme churn was 9%."], ["12% of Beta stores are in EMEA."]],
        "",
        "Acme churn was 12% [E1].",
        "",
    ),
    (
        "A3-repoint-company",
        [
            ["Acme revenue was $580.0 million in 2024."],
            ["Beta revenue was $612.0 million in 2024."],
        ],
        "",
        "Acme revenue was $612.0 million [E1].",
        "",
    ),
    (
        "A3-repoint-year-evidence",
        [["Acme revenue grew."], ["The survey ran in 2024."]],
        "",
        "Acme revenue was 2024 [E1].",
        "",
    ),
    (
        "A3-repoint-multi-cite",
        [["Acme churn was 9%."], ["12% of Beta stores are in EMEA."]],
        "",
        "Acme churn was 12% [E1] [E1].",
        "",
    ),
    (
        "A3-clause-negation",
        [["Revenue rose 12% in 2024."]],
        "",
        "Revenue rose 12%, but not in 2019 [E1].",
        "",
    ),
    (
        "A3-clause-false",
        [["Store count reached 1,840 after 112 openings."]],
        "",
        "It is false that store count reached 1,840; the true figure is 2,500 [E1].",
        "",
    ),
    (
        "A3-clause-only-if",
        [["Store count could reach 1,840 if 500 stores reopen."]],
        "",
        "Store count reached 1,840 (only if 900 stores reopen) [E1].",
        "",
    ),
    (
        "A3-paren-alias-reassembly",
        [["Revenue was $612.0 million."], ["Unrelated note."]],
        "",
        "Revenue was $612.0 million [E1] [E(999)2].",
        "",
    ),
    (
        "A3-paren-alias-oob",
        [["Revenue was $612.0 million."], ["Unrelated note."]],
        "",
        "Revenue was $612.0 million [E1] [E(999)42].",
        "",
    ),
    (
        "A3-paren-alias-inference",
        [["Revenue was $612.0 million."], ["Unrelated note."]],
        "",
        "Revenue was $612.0 million [E1]. [inference] The brand is collapsing [E(777)2].",
        "### Answer\n\nRevenue was $612.0 million [[WS/SRC1@v1:P1]] [inference].",
    ),
    (
        "A3-paren-canon",
        [["Revenue was $612.0 million."]],
        "",
        "Revenue was $612.0 million [E1] [(999)[WS/EVIL@v1:X](999)].",
        "",
    ),
    (
        "A5-hidden-claim-q",
        [["Revenue rose 12% in 2024."]],
        "Why did revenue fall 40% in 2024?",
        "Revenue fell 40% and the documents do not explain why.",
        "",
    ),
    (
        "A5-hidden-claim-pack",
        [["Store count reached 1,840 after 112 openings."]],
        "",
        "Store count fell to 112 and no source explains why.",
        "### Answer\n\nStore count fell to 112 and no source explains why [inference].",
    ),
    (
        "A5-hidden-noconcl",
        [["Store count reached 1,840 after 112 openings."]],
        "",
        "Store count reached 1,840 [E1]. The CEO was fired for fraud, and the evidence does not say when.",  # noqa: E501 - probe data
        "### Answer\n\nStore count reached 1,840 [[WS/SRC1@v1:P1]]. The CEO was fired for fraud, and the evidence does not say when [inference].",  # noqa: E501 - probe data
    ),
    (
        "A5-gap-in-interp",
        [["Store count reached 1,840 after 112 openings."]],
        "Did 40% of stores close?",
        "Store count reached 1,840 [E1]. 40% of stores closed; the evidence does not state where.",
        "### Answer\n\nStore count reached 1,840 [[WS/SRC1@v1:P1]].",
    ),
    (
        "MASK-percent-word",
        [["38% cited late parcels."]],
        "",
        "In March 40 percent of shoppers churned [E1].",
        "",
    ),
    (
        "MASK-million",
        [["38% cited late parcels."]],
        "",
        "In May 12 million shoppers left [E1].",
        "",
    ),
    (
        "MASK-decimal-precision",
        [["Revenue was $612 million."]],
        "",
        "Revenue of $612.25 may be restated [E1].",
        "",
    ),
    (
        "REASM-findings",
        [["Revenue was $612.0 million."], ["Unrelated note."]],
        "",
        "Revenue was $612.0 million [E1].\n\n### Key findings\n- Margins are collapsing [E1] [E(5)2]",  # noqa: E501 - probe data
        "### Answer\n\nRevenue was $612.0 million [[WS/SRC1@v1:P1]].",
    ),
    (
        "REASM-interp-uncited",
        [["Revenue was $612.0 million."], ["Unrelated note."]],
        "",
        "Revenue was $612.0 million [E1].\n\n### Interpretation\n[inference] The brand is collapsing [E(777)2].",  # noqa: E501 - probe data
        "### Answer\n\nRevenue was $612.0 million [[WS/SRC1@v1:P1]].",
    ),
    (
        "REASM-answer-uncited-inferred",
        [["Revenue was $612.0 million."], ["Unrelated note."]],
        "",
        "[inference] The brand is collapsing [E(777)2]. Revenue was $612.0 million [E1].",
        "### Answer\n\nRevenue was $612.0 million [[WS/SRC1@v1:P1]].",
    ),
    (
        "HOLD-forged-canonical",
        [["Revenue was $612.0 million."]],
        "",
        "Revenue was $612.0 million [[WS/SRC9@v1:P9]] [E1].",
        "### Answer\n\nRevenue was $612.0 million [[WS/SRC1@v1:P1]].",
    ),
    (
        "HOLD-magnitude",
        [["Revenue was $612.0 million."]],
        "",
        "Revenue was $612.0 billion [E1].",
        "",
    ),
    (
        "HOLD-currency",
        [["Revenue was $612.0 million."]],
        "",
        "Revenue was €612.0 million [E1].",
        "",
    ),
    ("HOLD-pct-vs-pp", [["Share rose 12%."]], "", "Share rose 12 bps [E1].", ""),
    (
        "HOLD-2025units",
        [["Shipments reached 2025."]],
        "",
        "Shipments reached 2,026 units [E1].",
        "",
    ),
    (
        "HOLD-year-qty-not-visible",
        [["Store count rose by 112 in 2024."]],
        "",
        "Store count rose by 1990 [E1].",
        "",
    ),
    (
        "HOLD-repoint-ambiguous",
        [["Acme churn was 9%."], ["12% in EMEA."], ["12% in APAC."]],
        "",
        "Acme churn was 12% [E1].",
        "",
    ),
    (
        "HOLD-repoint-small",
        [["Acme has 9 stores."], ["Beta has 12 stores."]],
        "",
        "Acme has 12 stores [E1].",
        "",
    ),
    (
        "HOLD-fiscal",
        [["Revenue was $612.0 million in FY2024."]],
        "",
        "Revenue was $612.0 million in FY2023 [E1].",
        "### Answer\n\nRevenue was $612.0 million in FY2023 [[WS/SRC1@v1:P1]].",
    ),
    (
        "HOLD-gap-numbers-not-in-q",
        [["Revenue rose 12%."]],
        "",
        "Revenue fell 40% and the documents do not explain why.",
        "",
    ),
    (
        "HOLD-backref",
        [["Revenue rose 12%."]],
        "",
        "Revenue fell 40% [E1]. This drove layoffs [E1].",
        "### Answer\n\nThis drove layoffs [[WS/SRC1@v1:P1]].",
    ),
]


def _probe_pack(items: list[list[object]]) -> EvidencePack:
    built = []
    for rank, spec in enumerate(items, start=1):
        text, *rest = spec
        title = str(rest[0]) if rest else "Field Notes"
        locator = str(rest[1]) if len(rest) > 1 else "Page 1"
        heading = tuple(str(h) for h in rest[2]) if len(rest) > 2 else ()  # type: ignore[attr-defined]
        built.append(_item(rank, str(text), title=title, locator=locator, heading=heading))
    return _pack(*built)


@pytest.mark.parametrize(
    ("probe_id", "items", "question", "answer", "phase3"), _PROBES, ids=[p[0] for p in _PROBES]
)
def test_review_probe_never_accepts_more_than_phase3(
    probe_id: str, items: list[list[object]], question: str, answer: str, phase3: str
) -> None:
    result = verify_answer(
        f"### Answer\n{answer}\n", _probe_pack(items), pack_truncated=False, question=question
    )
    for key, units in result.sections.items():
        if key == "answer_unknowns":
            continue
        for unit in units:
            assert "[inference]" in unit or unit in phase3, (probe_id, unit)


def test_verifier_exception_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review R1(c): an unexpected verifier error is a failed verification, not a crash."""
    from marketsignal.config import Settings
    from marketsignal.runs import synthesis
    from marketsignal.runs.state import RunRequest

    def boom(*_: object, **__: object) -> None:
        raise KeyError("E42")

    monkeypatch.setattr(synthesis, "verify_answer", boom)
    scope = WorkspaceScope(workspace_id=uuid.UUID(int=1), workspace_code="WS")
    req = RunRequest(uuid.UUID(int=2), scope, uuid.UUID(int=3), "q", "consultant")
    verified = synthesis._verify_safely(req, Settings(), "### Answer\nx [E1].", PACK)
    assert not verified.ok
    assert verified.report.structural_failures == ["verifier_error"]
    assert "could not be checked" in regeneration_feedback(verified.report)
