"""Phase 5 A1: deterministic citation budget for list-style (enumeration) answers.

Fresh dev examples: scripted enumeration answers over synthetic packs (not grounded-v0). Each
case is the kind of over-citation seen in Phase 4 (every bullet cites several items, the
Answer repeats the Key-findings citations) and must now verify under the cap without
weakening support: every remaining claim keeps >= 1 supporting citation.
"""

from __future__ import annotations

import uuid

from marketsignal.generation.citation_budget import MIN_FINDINGS
from marketsignal.generation.contract import ANSWER, CONFLICTS, FINDINGS
from marketsignal.generation.prompts import SYSTEM_PROMPT
from marketsignal.generation.types import EvidencePack, PackItem
from marketsignal.generation.verifier import (
    TOO_MANY_CITATIONS,
    regeneration_feedback,
    verify_answer,
)

CHANNELS = (
    ("Marketplace", "31%"),
    ("Own web store", "24%"),
    ("Wholesale", "18%"),
    ("Retail stores", "12%"),
    ("Outlet", "6%"),
    ("Social commerce", "4%"),
    ("Catalogue", "3%"),
    ("Pop-up", "2%"),
)


def _item(rank: int, text: str, *, handle: str | None = None) -> PackItem:
    return PackItem(
        alias=f"E{rank}",
        rank=rank,
        handle=handle or f"WS/SRC{rank}@v1:P{rank}",
        parent_id=uuid.UUID(int=rank),
        source_code=f"SRC{rank}",
        source_title="Channel Review",
        source_class="internal",
        source_type="text",
        locator_label=f"Page {rank}",
        heading_path=(),
        text=text,
        window=None,
        tokens=len(text.split()),
        content_hash=f"h{rank}",
        anchor_child_id=uuid.UUID(int=100 + rank),
        anchor_char_start=0,
        anchor_char_end=5,
        fused_rank=rank,
    )


def _channel_pack() -> EvidencePack:
    items = [
        _item(n, f"{name} accounted for {share} of FY2026 orders.")
        for n, (name, share) in enumerate(CHANNELS, start=1)
    ]
    items.append(_item(9, "Channel mix summary: eight channels were active in FY2026."))
    return EvidencePack(items=tuple(items), tokens=100, truncated=False)


def _enumeration_answer(per_bullet_extra: int = 2) -> str:
    """Each bullet cites its own item plus ``per_bullet_extra`` neighbours and the summary;
    the Answer cites the summary and the top items again."""
    answer = (
        "Eight channels were active in FY2026 [E9] [E1] [E2] [E3]. "
        "Marketplace was the largest at 31% [E1] [E9]."
    )
    bullets = []
    for n, (name, share) in enumerate(CHANNELS, start=1):
        extras = [f"[E{(n + k - 1) % 8 + 1}]" for k in range(1, per_bullet_extra + 1)]
        bullets.append(f"- {name} accounted for {share} of orders [E{n}] {' '.join(extras)} [E9].")
    return f"### Answer\n{answer}\n\n### Key findings\n" + "\n".join(bullets) + "\n"


def _supported_everywhere(result_sections: dict[str, list[str]]) -> bool:
    return all("[[" in unit for key in (ANSWER, FINDINGS) for unit in result_sections.get(key, []))


def test_enumeration_answer_over_the_cap_is_fitted_and_keeps_unique_evidence() -> None:
    pack = _channel_pack()
    result = verify_answer(_enumeration_answer(), pack, pack_truncated=False)
    budget = result.report.citation_budget
    assert budget["before"] > 20 >= result.report.citations
    assert result.ok, result.report.structural_failures
    assert TOO_MANY_CITATIONS not in result.report.structural_failures
    # Every channel bullet survives and keeps its own item (unique evidence preserved).
    assert len(result.sections[FINDINGS]) == len(CHANNELS)
    for n, bullet in enumerate(result.sections[FINDINGS], start=1):
        assert f"[[WS/SRC{n}@v1:P{n}]]" in bullet
    assert _supported_everywhere(result.sections)
    assert not result.report.numeric_violations
    assert all("citation cap 20" in r for r in result.report.repairs if "removed" in r)


def test_feedback_names_count_and_over_cited_aliases() -> None:
    pack = _channel_pack()
    result = verify_answer(_enumeration_answer(), pack, pack_truncated=False, max_citations=4)
    assert TOO_MANY_CITATIONS in result.report.structural_failures
    feedback = regeneration_feedback(result.report)
    assert f"uses {result.report.citation_budget['before']} citation markers" in feedback
    assert "the limit is 4" in feedback
    assert "Over-cited: E9 (" in feedback
    assert "at most once per bullet" in feedback
    assert "for enumerations cite each item once" in feedback


def test_exactly_at_the_cap_is_untouched() -> None:
    pack = _channel_pack()
    raw = _enumeration_answer(per_bullet_extra=0)  # 6 + 8 * 2 = 22 markers
    full = verify_answer(raw, pack, pack_truncated=False, max_citations=22)
    assert full.ok
    assert full.report.citations == 22
    assert full.report.citation_budget == {}
    assert not any("citation cap" in r for r in full.report.repairs)


def test_one_over_the_cap_removes_exactly_one_marker() -> None:
    pack = _channel_pack()
    raw = _enumeration_answer(per_bullet_extra=0)
    result = verify_answer(raw, pack, pack_truncated=False, max_citations=21)
    assert result.ok
    assert result.report.citations == 21
    assert sum("citation cap 21" in r for r in result.report.repairs) == 1


def test_citations_needed_for_figures_are_never_removed() -> None:
    pack = EvidencePack(
        items=(
            _item(1, "Marketplace accounted for 31% of orders."),
            _item(2, "Wholesale accounted for 18% of orders."),
        ),
        tokens=10,
        truncated=False,
    )
    bullet = "- Marketplace took 31% and wholesale 18% [E1] [E2]."
    raw = "### Answer\nMarketplace led with 31% [E1].\n\n### Key findings\n" + bullet + "\n"
    result = verify_answer(raw, pack, pack_truncated=False, max_citations=2)
    # Removing either citation would leave a figure unsupported: stays over, fails.
    assert result.report.citations == 3
    assert TOO_MANY_CITATIONS in result.report.structural_failures
    assert "[[WS/SRC1@v1:P1]]" in result.sections[FINDINGS][0]
    assert "[[WS/SRC2@v1:P2]]" in result.sections[FINDINGS][0]


def test_answer_reuses_key_findings_citations_instead_of_repeating() -> None:
    pack = _channel_pack()
    raw = (
        "### Answer\nMarketplace and the web store lead [E1] [E2].\n\n### Key findings\n"
        "- Marketplace accounted for 31% of orders [E1].\n"
        "- Own web store accounted for 24% of orders [E2].\n"
    )
    result = verify_answer(raw, pack, pack_truncated=False, max_citations=3)
    assert result.ok
    assert result.sections[ANSWER][0].count("[[") == 1  # kept its first citation
    assert any("already cited in Key findings" in r for r in result.report.repairs)


def test_same_parent_cited_twice_in_one_unit_is_collapsed() -> None:
    handle = "WS/SRC1@v1:P1"
    pack = EvidencePack(
        items=(
            _item(1, "Marketplace accounted for 31% of orders.", handle=handle),
            _item(2, "Marketplace accounted for 31% of orders.", handle=handle),
        ),
        tokens=10,
        truncated=False,
    )
    raw = "### Answer\nMarketplace led with 31% [E1] [E2].\n"
    result = verify_answer(raw, pack, pack_truncated=False, max_citations=1)
    assert result.ok
    assert any("same source as another citation" in r for r in result.report.repairs)


def test_conflict_bullets_keep_both_sides() -> None:
    pack = _channel_pack()
    raw = (
        "### Answer\nMarketplace led [E1] [E9].\n\n"
        "### Conflicting evidence\n- Marketplace is put at 31% [E1] [E9].\n"
    )
    result = verify_answer(raw, pack, pack_truncated=False, max_citations=3)
    assert result.ok
    assert result.sections[CONFLICTS][0].count("[[") == 2
    assert result.sections[ANSWER][0].count("[[") == 1


def test_trailing_findings_dropped_only_beyond_minimum_and_reported() -> None:
    pack = _channel_pack()
    bullets = "\n".join(
        f"- {name} accounted for {share} of orders [E{n}]."
        for n, (name, share) in enumerate(CHANNELS, start=1)
    )
    raw = f"### Answer\nEight channels were active [E9].\n\n### Key findings\n{bullets}\n"
    result = verify_answer(raw, pack, pack_truncated=False, max_citations=5)
    assert result.ok
    assert len(result.sections[FINDINGS]) == 4 >= MIN_FINDINGS
    assert sum("dropped a trailing Key findings bullet" in r for r in result.report.repairs) == 4
    tight = verify_answer(raw, pack, pack_truncated=False, max_citations=3)
    assert len(tight.sections[FINDINGS]) == MIN_FINDINGS
    assert TOO_MANY_CITATIONS in tight.report.structural_failures


def test_duplicate_bullets_are_dropped_before_unique_ones() -> None:
    pack = _channel_pack()
    repeated = "\n".join("- Marketplace accounted for 31% of orders [E1]." for _ in range(4))
    raw = f"### Answer\nMarketplace led with 31% [E1].\n\n### Key findings\n{repeated}\n"
    result = verify_answer(raw, pack, pack_truncated=False, max_citations=2)
    assert result.ok
    assert len(result.sections[FINDINGS]) == 1


def test_budget_is_deterministic() -> None:
    pack = _channel_pack()
    first = verify_answer(_enumeration_answer(), pack, pack_truncated=False)
    second = verify_answer(_enumeration_answer(), pack, pack_truncated=False)
    assert first.content == second.content
    assert first.report.repairs == second.report.repairs


def test_system_prompt_states_per_bullet_citation_rule() -> None:
    assert "Cite each source at" in SYSTEM_PROMPT
    assert "most once per bullet" in SYSTEM_PROMPT
    assert "For enumerations and lists, cite each item once" in SYSTEM_PROMPT
