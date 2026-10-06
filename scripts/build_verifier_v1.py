"""Build eval/datasets/verifier-v1 (synthetic citation-verifier evaluation set).

Every evidence text, question and answer below is hand-written and fictional (no real
organisations, no corpus content). Gold labels encode the *semantic* truth of each claim under
the policy recorded in the generated README, not the behaviour of any verifier implementation.

Cases are grouped into families (one evidence pack + 2-4 answer variants). Families, never
cases, are split ~60/40 into dev/holdout with a fixed seed. Output is byte-deterministic.

    python3 scripts/build_verifier_v1.py
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "eval" / "datasets" / "verifier-v1"
VERSION = "verifier-v1"
SEED = 20261006
DEV_FRACTION = 0.6
DEFAULT_CAP = 20
MAX_ANSWER_SENTENCES = 4
MIN_KEY_LEN = 10

TYPES = (
    "years_dates",
    "edition_labels",
    "percentages",
    "quantities",
    "million_billion",
    "row_labels",
    "titles",
    "table_headers",
    "section_headings",
    "slide_titles",
    "multi_clause",
    "computed_values",
    "unsupported_calculation",
    "valid_unit_conversion",
    "invalid_unit_conversion",
    "conflicting_evidence",
    "insufficiency",
    "citation_cap",
    "fabricated_citation",
    "foreign_handle",
    "currency_mismatch",
    "uncited_claim",
    "dangling_reference",
    "back_reference",
    "quantity_as_year_shape",
    "leak",
)
S, U, M = "supported", "unsupported", "miscited"
LABELS = (S, U, M)
FAILURES = (
    "answer_missing",
    "answer_too_long",
    "no_citations",
    "too_many_citations",
    "gaps_missing",
)
SOURCE_CLASSES = (
    "survey",
    "finance",
    "interview",
    "competitor",
    "strategy",
    "market_report",
    "deck",
)
ALIAS_RE = re.compile(r"\[(E\d{1,2})\]")
SECTION_RE = re.compile(r"^### (.+)$", re.MULTILINE)
PARAGRAPH_SECTIONS = ("Answer", "Interpretation")
GAPS = "Gaps & unknowns"

Json = dict[str, Any]


# --------------------------------------------------------------------------- builders


def ev(alias: str, title: str, cls: str, loc: str, heading: tuple[str, ...], text: str) -> Json:
    return {
        "alias": alias,
        "source_title": title,
        "source_class": cls,
        "locator_label": loc,
        "heading_path": list(heading),
        "text": text,
    }


def u(key: str, label: str, typ: str, note: str, correct: str | None = None) -> Json:
    unit: Json = {"key": key, "label": label, "type": typ, "note": note}
    if correct is not None:
        unit["correct_alias"] = correct
    return unit


def md(
    answer: list[str],
    findings: list[str] | None = None,
    conflicts: list[str] | None = None,
    interp: list[str] | None = None,
    gaps: list[str] | None = None,
) -> str:
    """Render a model-style answer with the contract's level-3 headings."""
    blocks = [f"### Answer\n{' '.join(answer)}"]
    for heading, items in (("Key findings", findings), ("Conflicting evidence", conflicts)):
        if items:
            blocks.append(f"### {heading}\n" + "\n".join(f"- {b}" for b in items))
    if interp:
        blocks.append("### Interpretation\n" + " ".join(interp))
    if gaps:
        blocks.append(f"### {GAPS}\n" + "\n".join(f"- {b}" for b in gaps))
    return "\n\n".join(blocks) + "\n"


def case(
    suffix: str,
    question: str,
    answer: str,
    units: list[Json],
    *,
    failures: tuple[str, ...] = (),
    truncated: bool = False,
    cap: int = DEFAULT_CAP,
    retry: str | None = None,
    extra_types: tuple[str, ...] = (),
) -> Json:
    return {
        "suffix": suffix,
        "case_types": sorted({x["type"] for x in units} | set(extra_types)),
        "question": question,
        "pack_truncated": truncated,
        "max_citations": cap,
        "answer": answer,
        "retry_answer": retry,
        "units": units,
        "expected": {"ok": not failures, "structural_failures": list(failures)},
    }


def family(fid: str, scenario: str, pack: list[Json], conflict: bool, cases: list[Json]) -> Json:
    built = []
    for c in cases:
        body = {k: v for k, v in c.items() if k != "suffix"}
        body["case_id"] = f"{fid}-{c['suffix']}"
        body["pack"] = pack
        body["expected"] = {**c["expected"], "conflict_present": conflict}
        built.append(body)
    return {"family_id": fid, "scenario": scenario, "cases": built}


# --------------------------------------------------------------------------- families


def f01() -> Json:
    pack = [
        ev(
            "E1",
            "Halcyon Foods FY2025 Annual Report",
            "finance",
            "Page 14",
            ("Financial Review", "Revenue by Region"),
            "Revenue by region (EUR million)\nRegion | FY2024 | FY2025\nEMEA | 412.6 | 448.1\n"
            "Americas | 297.3 | 301.9\nAPAC | 118.4 | 139.0",
        ),
        ev(
            "E2",
            "Halcyon Foods FY2025 Annual Report",
            "finance",
            "Page 15",
            ("Financial Review", "Outlook"),
            "Management expects APAC to remain the fastest-growing region in FY2026, supported "
            "by two new co-packing partners in Vietnam.",
        ),
    ]
    q = "How did Halcyon Foods' regional revenue change between FY2024 and FY2025?"
    a = case(
        "a",
        q,
        md(
            [
                "Halcyon Foods' EMEA revenue rose from EUR 412.6 million in FY2024 to EUR 448.1 "
                "million in FY2025 [E1].",
                "APAC grew from EUR 118.4 million to EUR 139.0 million over the same period [E1].",
            ],
            ["Americas revenue moved from EUR 297.3 million to EUR 301.9 million [E1]."],
        ),
        [
            u(
                "EMEA revenue rose from EUR 412.6 million in FY2024",
                S,
                "table_headers",
                "EMEA row under the FY2024 and FY2025 column headers",
            ),
            u("APAC grew from EUR 118.4 million to EUR 139.0 million", S, "row_labels", "APAC row"),
            u("Americas revenue moved from EUR 297.3 million", S, "row_labels", "Americas row"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "The Revenue by Region table shows EMEA revenue reached EUR 448.1 million in "
                "FY2025 "
                "[E1].",
                "APAC revenue grew 17.4% year on year to EUR 139.0 million [E1].",
            ],
            ["Americas revenue was EUR 301.9 million in FY2023 [E1]."],
        ),
        [
            u(
                "Revenue by Region table shows EMEA revenue",
                S,
                "section_headings",
                "E1 heading; EMEA FY2025 cell",
            ),
            u(
                "APAC revenue grew 17.4% year on year",
                U,
                "computed_values",
                "17.4% = 139.0/118.4 - 1; arithmetically right but not stated",
            ),
            u(
                "Americas revenue was EUR 301.9 million in FY2023",
                U,
                "years_dates",
                "301.9 is FY2025; FY2023 appears nowhere in pack or question",
            ),
        ],
    )
    return family(
        "F01",
        "Finance table flattened as text: revenue by region and fiscal year",
        pack,
        False,
        [a, b],
    )


def f02() -> Json:
    title = "Brightwater Outfitters Customer Pulse Survey 2026"
    pack = [
        ev(
            "E1",
            title,
            "survey",
            "Q7",
            ("Purchase Drivers",),
            "Q7. Which factor most influenced your last jacket purchase? (n=1,240)\n"
            "Durability: 38%\nPrice: 27%\nBrand reputation: 19%\nSustainability claims: 11%\n"
            "Other: 5%",
        ),
        ev(
            "E2",
            title,
            "survey",
            "Q12",
            ("Sustainability",),
            "Q12. Willing to pay more for recycled materials, as a proportion of all "
            "respondents (n=1,240): 0.42. Proportion among respondents aged 18-29: 0.57.",
        ),
        ev(
            "E3",
            title,
            "survey",
            "Methodology",
            ("Methodology",),
            "Fieldwork ran 3-21 March 2026 online across the UK and Ireland. Results are "
            "unweighted.",
        ),
    ]
    q = (
        "What drives Brightwater Outfitters customers' jacket purchases, and how much does "
        "sustainability matter?"
    )
    a = case(
        "a",
        q,
        md(
            [
                "Durability was the most cited purchase driver at 38%, ahead of price at 27% [E1].",
                "Overall, 42% of respondents said they would pay more for recycled materials [E2].",
            ],
            ["Among 18-29 year olds the figure was 57% [E2]."],
        ),
        [
            u(
                "most cited purchase driver at 38%",
                S,
                "percentages",
                "Q7 durability 38%, price 27%",
            ),
            u(
                "42% of respondents said they would pay more",
                S,
                "valid_unit_conversion",
                "0.42 is explicitly a proportion of respondents",
            ),
            u(
                "Among 18-29 year olds the figure was 57%",
                S,
                "valid_unit_conversion",
                "0.57 explicitly a proportion",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Sustainability claims were the deciding factor for 11% of the 1,240 respondents "
                "[E1].",
                "Overall, 0.42% of customers would pay a premium for recycled materials [E2].",
            ],
            ["The question was asked in the April 2026 wave [E3]."],
        ),
        [
            u("deciding factor for 11% of the 1,240 respondents", S, "percentages", "Q7 row"),
            u(
                "0.42% of customers would pay a premium",
                U,
                "invalid_unit_conversion",
                "proportion 0.42 is 42%, not 0.42%",
            ),
            u(
                "asked in the April 2026 wave",
                U,
                "years_dates",
                "fieldwork was March 2026; April 2026 appears nowhere",
            ),
        ],
    )
    return family(
        "F02", "Survey question tables and proportions stated as decimals", pack, False, [a, b]
    )


def f03() -> Json:
    title = "Corvane Telecom Q2 2026 Results"
    pack = [
        ev(
            "E1",
            title,
            "finance",
            "Page 3",
            ("Operating Highlights",),
            "Mobile subscribers reached 12.4 million at 30 June 2026, up from 11.8 million a "
            "year earlier. Fixed broadband connections were 2.06 million.",
        ),
        ev(
            "E2",
            title,
            "finance",
            "Page 7",
            ("Financial Summary",),
            "Group revenue for the half year was GBP 1,215 million. Capital expenditure was "
            "GBP 284 million.",
        ),
    ]
    q = "How large is Corvane Telecom's customer base and revenue?"
    a = case(
        "a",
        q,
        md(
            [
                "Corvane had 12.4 million mobile subscribers at 30 June 2026 [E1].",
                "Half-year group revenue was GBP 1.215 billion [E2].",
            ],
            ["Fixed broadband connections stood at 2.6 million [E1]."],
        ),
        [
            u("Corvane had 12.4 million mobile subscribers", S, "quantities", "E1"),
            u(
                "Half-year group revenue was GBP 1.215 billion",
                S,
                "valid_unit_conversion",
                "GBP 1,215 million = GBP 1.215 billion",
            ),
            u("Fixed broadband connections stood at 2.6 million", U, "quantities", "E1 says 2.06"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Corvane serves more than twelve million mobile subscribers [E1].",
                "Half-year revenue was USD 1,215 million [E2].",
            ],
            ["Capital expenditure was GBP 2.84 billion [E2]."],
        ),
        [
            u(
                "serves more than twelve million mobile subscribers",
                S,
                "quantities",
                "spelled-out lower bound; 12.4 million is more than twelve million",
            ),
            u("Half-year revenue was USD 1,215 million", U, "currency_mismatch", "evidence is GBP"),
            u(
                "Capital expenditure was GBP 2.84 billion",
                U,
                "invalid_unit_conversion",
                "GBP 284 million is GBP 0.284 billion",
            ),
        ],
    )
    return family(
        "F03", "Telecom results pages: subscribers, revenue and capex", pack, False, [a, b]
    )


def f04() -> Json:
    pack = [
        ev(
            "E1",
            "Northgate Cycling Market Report 2025 edition",
            "market_report",
            "Page 22",
            ("Competitive Landscape", "Market Share"),
            "Meridian Bikes held an estimated 14.2% share of the UK e-bike market in 2024.",
        ),
        ev(
            "E2",
            "Northgate Cycling Market Report 2026 edition",
            "market_report",
            "Page 19",
            ("Competitive Landscape", "Market Share"),
            "Restated: Meridian Bikes' 2024 UK e-bike share is revised to 12.9% following a "
            "correction to importer data; earlier editions overstated the figure. Meridian's "
            "2025 share was 13.6%.",
        ),
    ]
    q = "What is Meridian Bikes' share of the UK e-bike market?"
    a = case(
        "a",
        q,
        md(
            [
                "Meridian Bikes held 13.6% of the UK e-bike market in 2025 [E2].",
                "Its 2024 share was restated to 12.9% in the 2026 edition [E2].",
            ],
            ["The 2026 edition attributes the restatement to a change in survey method [E2]."],
            conflicts=[
                "The 2025 edition reported a 14.2% share for 2024 [E1], later revised down [E2]."
            ],
        ),
        [
            u("held 13.6% of the UK e-bike market in 2025", S, "percentages", "E2"),
            u(
                "restated to 12.9% in the 2026 edition",
                S,
                "edition_labels",
                "edition label from E2 source title",
            ),
            u(
                "attributes the restatement to a change in survey method",
                U,
                "conflicting_evidence",
                "E2 cites corrected importer data",
            ),
            u("reported a 14.2% share for 2024", S, "edition_labels", "E1 is the 2025 edition"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Meridian Bikes held 14.2% of the UK e-bike market in 2024 according to the 2025 "
                "edition [E1].",
                "Its share then moved to 13.6% in 2025, a gain of 0.7 points [E2].",
            ],
            ["The 2026 edition estimates Meridian's 2025 share at 13.6% [E1]."],
        ),
        [
            u(
                "held 14.2% of the UK e-bike market in 2024",
                S,
                "conflicting_evidence",
                "backed by E1 text and correctly attributed; superseded but not misquoted",
            ),
            u("Its share then moved to 13.6% in 2025", S, "multi_clause", "E2"),
            u("a gain of 0.7 points", U, "multi_clause", "13.6 - 12.9 computed, not stated"),
            u(
                "estimates Meridian's 2025 share at 13.6%",
                M,
                "edition_labels",
                "13.6% and the 2026 edition label belong to E2",
                "E2",
            ),
        ],
    )
    c = case(
        "c",
        q,
        md(
            [
                "Meridian's share was 13.6% in 2025 according to the 2027 edition [E2].",
                "[inference] The downward restatement suggests importer data for the category is "
                "still being corrected.",
            ],
            ["Meridian's 2024 share was revised to 12.9% [E2]."],
        ),
        [
            u(
                "13.6% in 2025 according to the 2027 edition",
                U,
                "edition_labels",
                "no 2027 edition anywhere in pack or question",
            ),
            u(
                "suggests importer data for the category is still being corrected",
                S,
                "uncited_claim",
                "tagged inference, no new numbers",
            ),
            u("2024 share was revised to 12.9%", S, "conflicting_evidence", "E2"),
        ],
    )
    return family(
        "F04",
        "Market share restated between report editions (genuine conflict)",
        pack,
        True,
        [a, b, c],
    )


def f05() -> Json:
    title = "Aldermoor Coffee Investor Factsheet"
    pack = [
        ev(
            "E1",
            title,
            "finance",
            "Page 2",
            ("Estate", "Company-operated"),
            "Company-operated stores: 312 at 31 December 2025.",
        ),
        ev(
            "E2",
            title,
            "finance",
            "Page 2",
            ("Estate", "Franchise"),
            "Franchised stores: 129 at 31 December 2025. Total estate (company-operated plus "
            "franchised): 441.",
        ),
        ev(
            "E3",
            "Aldermoor Coffee Expansion Plan 2026",
            "strategy",
            "Page 5",
            ("Openings",),
            "Target: 35 new company-operated openings in 2026.",
        ),
    ]
    q = "How many stores does Aldermoor Coffee operate?"
    a = case(
        "a",
        q,
        md(
            [
                "Aldermoor had 441 stores at the end of 2025, of which 312 were company-operated "
                "[E1][E2].",
                "It targets 35 openings in 2026, lifting company-operated stores by 11% [E3].",
            ]
        ),
        [
            u("had 441 stores at the end of 2025", S, "multi_clause", "E2 total estate"),
            u("of which 312 were company-operated", S, "multi_clause", "E1"),
            u(
                "lifting company-operated stores by 11%",
                U,
                "computed_values",
                "35/312 computed; one claim with the openings target",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Aldermoor operated 312 company-run stores at 31 December 2025 [E1].",
                "It will reach 476 stores by the end of 2026 [E3].",
            ],
            ["Franchised stores totalled 129 [E2]."],
            conflicts=[
                "Store counts of 312 and 441 both appear in the factsheet for 31 December "
                "2025 [E1][E2]."
            ],
        ),
        [
            u("operated 312 company-run stores", S, "quantities", "E1"),
            u(
                "will reach 476 stores by the end of 2026",
                U,
                "unsupported_calculation",
                "441 + 35 assumes no closures or franchise change; not stated",
            ),
            u("Franchised stores totalled 129", S, "quantities", "E2"),
            u(
                "Store counts of 312 and 441 both appear",
                S,
                "conflicting_evidence",
                "accurate, but the figures measure different things: a false conflict",
            ),
        ],
    )
    return family(
        "F05",
        "Store counts by ownership type; similar-looking numbers, no conflict",
        pack,
        False,
        [a, b],
    )


def f06() -> Json:
    pack = [
        ev(
            "E1",
            "Brightwater Outfitters Inventory Ledger",
            "finance",
            "Row 44",
            ("Inventory", "Outerwear"),
            "sku_family: Storm Shell; units_on_hand: 2025; reorder_point: 1990; warehouse: Leeds",
        ),
        ev(
            "E2",
            "Interview: Brightwater Supplier Account Manager",
            "interview",
            "Q4",
            ("Lead Times",),
            "Lead time for Storm Shell fabric is currently eleven weeks, up from eight weeks "
            "last season.",
        ),
    ]
    q = "What is Brightwater's current stock position on the Storm Shell line?"
    a = case(
        "a",
        q,
        md(
            [
                "The Leeds warehouse holds 2025 units of Storm Shell [E1].",
                "The line's reorder point is 1990 units [E1].",
            ],
            ["Fabric lead time is eleven weeks, up from eight [E2]."],
        ),
        [
            u(
                "Leeds warehouse holds 2025 units of Storm Shell",
                S,
                "quantity_as_year_shape",
                "units_on_hand: 2025",
            ),
            u("reorder point is 1990 units", S, "quantity_as_year_shape", "reorder_point: 1990"),
            u("Fabric lead time is eleven weeks, up from eight", S, "quantities", "E2"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Storm Shell stock was last counted in 2025 at the Leeds warehouse [E1].",
                "Units on hand stand at 2,025, above the reorder point [E1].",
            ],
            ["Lead times have lengthened by three weeks [E2]."],
        ),
        [
            u(
                "stock was last counted in 2025",
                U,
                "quantity_as_year_shape",
                "2025 is a unit count, not a count date",
            ),
            u("Units on hand stand at 2,025", S, "row_labels", "units_on_hand field"),
            u("lengthened by three weeks", U, "computed_values", "11 - 8 not stated"),
        ],
    )
    c = case(
        "c",
        q,
        md(
            [
                "The Leeds warehouse stocks the Storm Shell line [E1].",
                "Units on hand are 2025 [E1].",
                "The reorder point is set at 1990 [E1].",
                "Storm Shell fabric lead time is eleven weeks [E2].",
                "Last season it was eight weeks [E2].",
            ]
        ),
        [
            u("Leeds warehouse stocks the Storm Shell line", S, "row_labels", "E1"),
            u("Units on hand are 2025", S, "quantity_as_year_shape", "E1"),
            u("reorder point is set at 1990", S, "quantity_as_year_shape", "E1"),
            u("fabric lead time is eleven weeks", S, "quantities", "E2"),
            u("Last season it was eight weeks", S, "quantities", "E2"),
        ],
    )
    c["expected"] = {"ok": False, "structural_failures": ["answer_too_long"]}
    return family("F06", "Dataset row whose quantities look like years", pack, False, [a, b, c])


def f07() -> Json:
    deck = "Corvane Q3 2026 Board Review"
    pack = [
        ev(
            "E1",
            deck,
            "deck",
            "Slide 7",
            (deck, "Pricing"),
            "Proposed price rise of 4.5% on legacy mobile plans from January 2027. Expected "
            "churn uplift: 0.3 percentage points.",
        ),
        ev(
            "E2",
            deck,
            "deck",
            "Slide 9",
            (deck, "Network"),
            "5G population coverage reached 78% in September 2026; target 90% by end-2027.",
        ),
    ]
    q = "What pricing and network items did the Corvane board review in Q3 2026?"
    a = case(
        "a",
        q,
        md(
            [
                "The Pricing slide proposes a 4.5% rise on legacy mobile plans from January 2027 "
                "[E1].",
                "The Network slide reports 5G population coverage of 78% in September 2026 [E2].",
            ],
            ["Management expects a churn uplift of 0.3 percentage points [E1]."],
        ),
        [
            u("Pricing slide proposes a 4.5% rise", S, "slide_titles", "heading Pricing, Slide 7"),
            u("Network slide reports 5G population coverage of 78%", S, "slide_titles", "E2"),
            u("churn uplift of 0.3 percentage points", S, "percentages", "E1"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Slide 8 of the Board Review covers the proposed 4.5% price rise [E1].",
                "The Network slide puts 5G coverage at 78% [E1].",
            ],
            ["Churn is expected to rise by 0.3% [E1]."],
        ),
        [
            u(
                "Slide 8 of the Board Review covers",
                U,
                "slide_titles",
                "the price rise is on Slide 7; Slide 8 is not in the pack",
            ),
            u("Network slide puts 5G coverage at 78%", M, "slide_titles", "78% only in E2", "E2"),
            u(
                "Churn is expected to rise by 0.3%",
                U,
                "percentages",
                "evidence says percentage points, not percent",
            ),
        ],
        failures=("answer_missing",),
    )
    c = case(
        "c",
        q,
        md(
            [
                "The Q2 2026 Board Review's Pricing slide proposes a 4.5% increase [E1].",
                "[inference] The board appears to be weighing price-led revenue against a modest "
                "churn risk.",
            ],
            ["Coverage must rise 12 points to hit the 90% target [E2]."],
        ),
        [
            u(
                "Q2 2026 Board Review's Pricing slide",
                U,
                "slide_titles",
                "deck is Q3 2026; Q2 2026 appears nowhere",
            ),
            u(
                "weighing price-led revenue against a modest churn risk",
                S,
                "uncited_claim",
                "inference, no numbers",
            ),
            u("Coverage must rise 12 points", U, "computed_values", "90 - 78 not stated"),
        ],
        failures=("no_citations",),
        retry=md(
            [
                "The Q2 2026 board deck proposes a 4.5% price increase [E1].",
                "[inference] Coverage still has some way to go.",
            ],
            ["Coverage needs another 12 points [E2]."],
        ),
    )
    return family(
        "F07", "Board slide deck with slide locators and section titles", pack, False, [a, b, c]
    )


def f08() -> Json:
    title = "Interview: Head of Procurement, Halcyon Foods"
    pack = [
        ev(
            "E1",
            title,
            "interview",
            "Q3",
            ("Supplier Consolidation",),
            "We cut our packaging suppliers from 23 to 9 over eighteen months, mainly to get "
            "volume discounts.",
        ),
        ev(
            "E2",
            title,
            "interview",
            "Q5",
            ("Risks",),
            "The concern is single-sourcing. If one of those nine has a strike, we have maybe "
            "three weeks of buffer stock.",
        ),
    ]
    q = "How has Halcyon Foods changed its packaging supply base?"
    a = case(
        "a",
        q,
        md(
            [
                "Halcyon cut its packaging suppliers from 23 to 9 over eighteen months [E1].",
                "The head of procurement flagged single-sourcing as the main risk, with about four "
                "weeks of buffer stock [E2].",
            ],
            ["Under Supplier Consolidation, volume discounts are given as the main motive [E1]."],
        ),
        [
            u("cut its packaging suppliers from 23 to 9", S, "quantities", "E1"),
            u(
                "head of procurement flagged single-sourcing",
                U,
                "quantities",
                "role is right but E2 says three weeks of buffer stock, not four",
            ),
            u(
                "volume discounts are given as the main motive",
                S,
                "section_headings",
                "heading Supplier Consolidation",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Halcyon reduced its packaging supplier count by 61% [E1].",
                "In the Risks section, the interviewee says buffer stock covers roughly three "
                "weeks "
                "[E2].",
            ],
            ["The CFO said consolidation saved EUR 2.3 million a year [E1]."],
        ),
        [
            u(
                "reduced its packaging supplier count by 61%",
                U,
                "computed_values",
                "14/23 = 60.9%, not stated",
            ),
            u("In the Risks section, the interviewee says", S, "section_headings", "E2 heading"),
            u(
                "The CFO said consolidation saved EUR 2.3 million",
                U,
                "titles",
                "interviewee is head of procurement; no savings figure in pack",
            ),
        ],
    )
    q2 = "How much has Halcyon Foods saved from packaging supplier consolidation?"
    c = case(
        "c",
        q2,
        md(
            [
                "The available evidence does not give a savings figure for Halcyon's supplier "
                "consolidation.",
                "The interview says only that consolidation was pursued mainly for volume "
                "discounts "
                "[E1].",
            ],
            gaps=[
                "The interview does not report the value of the discounts; procurement cost "
                "data would close this gap."
            ],
        ),
        [
            u("does not give a savings figure", S, "insufficiency", "true insufficiency"),
            u("pursued mainly for volume discounts", S, "insufficiency", "E1"),
            u("does not report the value of the discounts", S, "insufficiency", "true gap"),
        ],
    )
    return family(
        "F08",
        "Interview transcript with question locators and section headings",
        pack,
        False,
        [a, b, c],
    )


def f09() -> Json:
    title = "Corvane Regional KPI Extract"
    pack = [
        ev(
            "E1",
            title,
            "finance",
            "Row 12",
            ("KPI Extract", "Regions"),
            "region: EMEA; revenue_musd: 612.0; yoy_growth_pct: 12.3; arpu_usd: 18.40",
        ),
        ev(
            "E2",
            title,
            "finance",
            "Row 13",
            ("KPI Extract", "Regions"),
            "region: LATAM; revenue_musd: 204.5; yoy_growth_pct: 21.7; arpu_usd: 9.10",
        ),
    ]
    q = "Compare Corvane's EMEA and LATAM performance."
    a = case(
        "a",
        q,
        md(
            [
                "EMEA revenue was USD 612.0 million [E1].",
                "LATAM grew faster at 21.7% on revenue of USD 204.5 million [E2].",
            ],
            ["ARPU was USD 18.40 in EMEA and USD 9.10 in LATAM [E1][E2]."],
        ),
        [
            u("EMEA revenue was USD 612.0 million", S, "row_labels", "revenue_musd field"),
            u("LATAM grew faster at 21.7%", S, "row_labels", "21.7 > 12.3"),
            u("ARPU was USD 18.40 in EMEA", S, "row_labels", "arpu_usd fields"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "EMEA revenue was USD 612.0 billion [E1].",
                "LATAM revenue growth was USD 21.7 million [E2].",
            ],
            [
                "Combined EMEA and LATAM revenue was USD 816.5 million [E1][E2].",
                "EMEA ARPU is three times LATAM ARPU [E1][E2].",
            ],
        ),
        [
            u("EMEA revenue was USD 612.0 billion", U, "million_billion", "field is musd"),
            u(
                "LATAM revenue growth was USD 21.7 million",
                U,
                "percentages",
                "21.7 is yoy_growth_pct, a percent, not an amount",
            ),
            u(
                "Combined EMEA and LATAM revenue was USD 816.5 million",
                U,
                "computed_values",
                "sum not stated",
            ),
            u(
                "EMEA ARPU is three times LATAM ARPU",
                U,
                "unsupported_calculation",
                "18.40/9.10 is about 2, and no ratio is stated",
            ),
        ],
        retry=None,
        failures=("answer_missing",),
    )
    return family("F09", "Dataset rows with field-name labels", pack, False, [a, b])


def f10() -> Json:
    pack = [
        ev(
            "E1",
            "Brightwater Outfitters FY2025 Trading Update",
            "finance",
            "Page 1",
            ("Headline Results",),
            "FY2025 revenue: GBP 184.2 million (unaudited).",
        ),
        ev(
            "E2",
            "Brightwater Outfitters FY2025 Annual Report",
            "finance",
            "Page 31",
            ("Notes", "Note 4 Revenue"),
            "Audited FY2025 revenue was GBP 181.7 million. This supersedes the unaudited GBP "
            "184.2 million in the trading update, after reclassifying gift-card breakage.",
        ),
    ]
    q = "What was Brightwater Outfitters' FY2025 revenue?"
    a = case(
        "a",
        q,
        md(
            [
                "Brightwater's audited FY2025 revenue was GBP 181.7 million [E2].",
                "This supersedes the unaudited GBP 184.2 million reported in the trading update "
                "[E2].",
            ],
            conflicts=["The unaudited trading update reported GBP 184.2 million [E1]."],
        ),
        [
            u("audited FY2025 revenue was GBP 181.7 million", S, "conflicting_evidence", "E2"),
            u(
                "This supersedes the unaudited GBP 184.2 million",
                S,
                "dangling_reference",
                "antecedent supported; E2 states the supersession",
            ),
            u(
                "unaudited trading update reported GBP 184.2 million",
                S,
                "conflicting_evidence",
                "E1",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Brightwater's FY2025 revenue was GBP 184.2 million, up 6% on FY2024 [E1].",
                "This growth was driven by gift-card breakage [E2].",
            ],
            ["Audited revenue was GBP 2.5 million lower than the trading update figure [E1][E2]."],
        ),
        [
            u(
                "FY2025 revenue was GBP 184.2 million",
                S,
                "multi_clause",
                "backed by E1 (superseded but correctly cited)",
            ),
            u("up 6% on FY2024", U, "multi_clause", "no growth rate; FY2024 absent from pack"),
            u(
                "This growth was driven by gift-card breakage",
                U,
                "dangling_reference",
                "antecedent claim unsupported; breakage was a reclassification",
            ),
            u(
                "GBP 2.5 million lower than the trading update",
                U,
                "computed_values",
                "184.2 - 181.7 not stated",
            ),
        ],
    )
    return family("F10", "Unaudited figure superseded by audited annual report", pack, True, [a, b])


def f11() -> Json:
    title = "Pellucid Skincare Channel Review 2026"
    pack = [
        ev(
            "E1",
            title,
            "strategy",
            "Page 4",
            ("Channels", "Direct-to-consumer"),
            "Direct-to-consumer sales were 41% of net revenue in H1 2026.",
        ),
        ev(
            "E2",
            title,
            "strategy",
            "Page 5",
            ("Channels", "Pharmacy"),
            "Pharmacy chains contributed 33% of net revenue in H1 2026.",
        ),
        ev(
            "E3",
            title,
            "strategy",
            "Page 6",
            ("Channels", "Marketplaces"),
            "Online marketplaces contributed 19% of net revenue in H1 2026.",
        ),
        ev(
            "E4",
            title,
            "strategy",
            "Page 7",
            ("Channels", "Other"),
            "Salons and duty-free contributed the remaining 7% of net revenue.",
        ),
    ]
    q = "What is Pellucid Skincare's channel mix?"
    answer = [
        "Direct-to-consumer was Pellucid's largest channel at 41% of net revenue in H1 2026 [E1].",
        "Pharmacy chains were second at 33% [E2].",
    ]
    findings = [
        "Shares were DTC 41%, pharmacy 33%, marketplaces 19% and salons and duty-free "
        "7% [E1][E2][E3][E4].",
        "Marketplaces were the third-largest channel at 19% [E3].",
    ]
    base = [
        u("largest channel at 41% of net revenue", S, "citation_cap", "E1"),
        u("Pharmacy chains were second at 33%", S, "citation_cap", "E2"),
        u("Shares were DTC 41%, pharmacy 33%", S, "citation_cap", "all four items"),
        u("third-largest channel at 19%", S, "citation_cap", "E3"),
    ]
    a = case("a", q, md(answer, findings), base, cap=8)
    extra = "Pharmacy and salons contributed 33% and 7% respectively [E2][E4]."
    c = case(
        "c",
        q,
        md(answer, [*findings, extra]),
        [*base, u("Pharmacy and salons contributed 33% and 7%", S, "citation_cap", "E2, E4")],
        cap=8,
        failures=("too_many_citations",),
        retry=md(
            answer, [*findings, extra, "Salons and duty-free were the smallest channel [E4]."]
        ),
    )
    return family(
        "F11", "Channel mix across four pages; citation count 7 vs 9 at cap 8", pack, False, [a, c]
    )


def f12() -> Json:
    title = "Quillon Pricing Benchmark 2026"
    pack = [
        ev(
            "E1",
            title,
            "competitor",
            "Row 3",
            ("Benchmark", "Quillon"),
            "vendor: Quillon; tier: Starter; price_per_seat_usd: 12; annual_discount_pct: 15",
        ),
        ev(
            "E2",
            title,
            "competitor",
            "Row 4",
            ("Benchmark", "Quillon"),
            "vendor: Quillon; tier: Business; price_per_seat_usd: 29; annual_discount_pct: 20",
        ),
        ev(
            "E3",
            title,
            "competitor",
            "Row 7",
            ("Benchmark", "Fennick"),
            "vendor: Fennick; tier: Business; price_per_seat_usd: 32; annual_discount_pct: 10",
        ),
    ]
    q = "How does Quillon's pricing compare with Fennick's?"
    answer = [
        "Quillon's Business tier costs USD 29 per seat versus Fennick's USD 32 [E2][E3].",
        "Quillon also offers a Starter tier at USD 12 per seat [E1].",
    ]
    findings = [
        "Annual discounts are 15% for Quillon Starter, 20% for Quillon Business and 10% "
        "for Fennick Business [E1][E2][E3].",
        "Both vendors sell a Business tier priced per seat [E2][E3].",
    ]
    base = [
        u(
            "Business tier costs USD 29 per seat versus Fennick's USD 32",
            S,
            "citation_cap",
            "E2, E3",
        ),
        u("Starter tier at USD 12 per seat", S, "row_labels", "price_per_seat_usd"),
        u(
            "Annual discounts are 15% for Quillon Starter",
            S,
            "row_labels",
            "annual_discount_pct fields",
        ),
        u("Both vendors sell a Business tier", S, "citation_cap", "E2, E3"),
    ]
    a = case("a", q, md(answer, findings), base, cap=8)
    extra = (
        "Fennick Business lists at USD 32 per seat with a 10% annual discount, against USD "
        "29 and 20% at Quillon [E3][E2]."
    )
    b = case(
        "b",
        q,
        md(answer, [*findings, extra]),
        [*base, u("Fennick Business lists at USD 32 per seat", S, "citation_cap", "E3, E2")],
        cap=8,
        failures=("too_many_citations",),
        retry=md(answer, [findings[0], extra]),
    )
    return family(
        "F12",
        "Competitor pricing rows; citation count exactly 8 vs 10 at cap 8",
        pack,
        False,
        [a, b],
    )


def f13() -> Json:
    pack = [
        ev(
            "E1",
            "Tessaly Pet Care Owner Survey 2026",
            "survey",
            "Q9",
            ("Subscriptions",),
            "34% of dog owners currently use a pet-food subscription; 22% of cat owners do "
            "(n=1,506).",
        ),
        ev(
            "E2",
            "Interview: Tessaly Pet Care Head of Growth",
            "interview",
            "Q2",
            ("Retention",),
            "Subscribers who skip two deliveries in a row usually cancel within a month, so we "
            "now send a pause offer after the first skip.",
        ),
    ]
    q = "How widely are pet-food subscriptions used, and what drives cancellations?"
    a = case(
        "a",
        q,
        md(
            [
                "34% of dog owners and 22% of cat owners use a pet-food subscription [E1].",
                "Cancellations typically follow two consecutive skipped deliveries [E2].",
            ],
            ["Subscription use is higher among dog owners than cat owners."],
        ),
        [
            u("34% of dog owners and 22% of cat owners", S, "percentages", "E1"),
            u("follow two consecutive skipped deliveries", S, "quantities", "E2"),
            u(
                "higher among dog owners than cat owners",
                U,
                "uncited_claim",
                "Key findings bullet with no citation",
            ),
        ],
    )
    c = case(
        "c",
        q,
        md(
            [
                "Subscription use is more common among dog owners than cat owners.",
                "Monthly churn among subscribers is 6% [E2].",
            ],
            ["41% of subscribers skip at least one delivery a year [E3]."],
        ),
        [
            u(
                "more common among dog owners than cat owners",
                S,
                "uncited_claim",
                "uncited Answer sentence restating pack facts without numbers",
            ),
            u("Monthly churn among subscribers is 6%", U, "percentages", "no churn rate in pack"),
            u(
                "41% of subscribers skip at least one delivery",
                U,
                "fabricated_citation",
                "E3 not in pack; figure absent",
            ),
        ],
        failures=("no_citations",),
        retry=md(
            [
                "Dog owners use subscriptions more than cat owners.",
                "About 6% of subscribers cancel each month [E2].",
            ]
        ),
    )
    return family(
        "F13", "Survey plus interview; uncited claims and an uncitable answer", pack, False, [a, c]
    )


def f14() -> Json:
    pack = [
        ev(
            "E1",
            "Corvane Competitor Tracker",
            "competitor",
            "Page 2",
            ("Pricing Moves",),
            "A rival operator cut its SIM-only 30GB plan to GBP 10 per month in August 2026. "
            "Corvane's equivalent plan remains GBP 12.",
        ),
        ev(
            "E2",
            "Corvane Churn Dashboard",
            "finance",
            "Page 1",
            ("Monthly Churn",),
            "Postpaid churn was 1.1% in August 2026 versus 0.9% in July 2026.",
        ),
    ]
    q = "Which competitor cut prices, and how much churn did the cut cause at Corvane?"
    a = case(
        "a",
        q,
        md(
            [
                "The evidence does not name the operator that cut its SIM-only 30GB plan to GBP 10 "
                "per month [E1].",
                "Postpaid churn rose to 1.1% in August 2026 from 0.9% in July [E2].",
            ],
            gaps=[
                "Churn is not broken down by reason, so the effect of the price cut cannot be "
                "isolated."
            ],
        ),
        [
            u("does not name the operator that cut", S, "insufficiency", "true"),
            u("Postpaid churn rose to 1.1% in August 2026", S, "percentages", "E2"),
            u("Churn is not broken down by reason", S, "insufficiency", "true gap"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Fennick Mobile cut its SIM-only 30GB plan to GBP 10 per month [E1].",
                "The cut raised Corvane's postpaid churn by 0.2 percentage points [E2].",
            ],
            ["Corvane's equivalent plan still costs GBP 12 [E1]."],
        ),
        [
            u(
                "Fennick Mobile cut its SIM-only 30GB plan",
                U,
                "insufficiency",
                "the evidence does not name the rival",
            ),
            u(
                "raised Corvane's postpaid churn by 0.2 percentage points",
                U,
                "computed_values",
                "difference and causation not stated",
            ),
            u("equivalent plan still costs GBP 12", S, "quantities", "E1"),
        ],
        failures=("answer_missing",),
        retry=md(
            [
                "Fennick Mobile's price cut pushed Corvane's churn up to 1.1% [E1][E2].",
                "The cut accounts for the 0.2 point rise [E2].",
            ]
        ),
    )
    return family(
        "F14",
        "Competitor move without a named rival; causal question unanswerable",
        pack,
        False,
        [a, b],
    )


def f15() -> Json:
    pack = [
        ev(
            "E1",
            "Ostrava Glassworks Export Price List 2026",
            "finance",
            "Page 2",
            ("Export Prices", "Tableware"),
            "Tumbler set (6 pieces): EUR 48.00 ex-works. Carafe, 1.2 litre: EUR 36.50 ex-works.",
        ),
        ev(
            "E2",
            "Interview: Ostrava Glassworks Export Director",
            "interview",
            "Q6",
            ("US Distribution",),
            "Our US distributor sells the tumbler set at USD 89 retail.",
        ),
    ]
    q = "What are Ostrava Glassworks' export and US retail prices for tableware?"
    a = case(
        "a",
        q,
        md(
            [
                "The six-piece tumbler set lists at EUR 48.00 ex-works [E1].",
                "The US distributor retails it at USD 89 [E2].",
            ],
            ["The 1.2 litre carafe (1,200 ml) is EUR 36.50 ex-works [E1]."],
        ),
        [
            u(
                "six-piece tumbler set lists at EUR 48.00",
                S,
                "currency_mismatch",
                "currency matches evidence",
            ),
            u("US distributor retails it at USD 89", S, "currency_mismatch", "E2 in USD"),
            u(
                "carafe (1,200 ml) is EUR 36.50 ex-works",
                S,
                "valid_unit_conversion",
                "1.2 litre = 1,200 ml",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            ["The tumbler set lists at USD 48.00 ex-works [E1].", "US retail is USD 89 [E2]."],
            [
                "The US retail markup on the tumbler set is about 85% [E1][E2].",
                "The carafe holds 12 litres [E1].",
            ],
        ),
        [
            u("tumbler set lists at USD 48.00 ex-works", U, "currency_mismatch", "evidence is EUR"),
            u("US retail is USD 89", S, "quantities", "E2"),
            u(
                "US retail markup on the tumbler set is about 85%",
                U,
                "unsupported_calculation",
                "cross-currency ratio, not stated",
            ),
            u("The carafe holds 12 litres", U, "invalid_unit_conversion", "1.2 litre"),
        ],
    )
    return family("F15", "Price list in EUR and distributor price in USD", pack, False, [a, b])


def f16() -> Json:
    pack = [
        ev(
            "E1",
            "Larkspur Grocery Market Report 2026",
            "market_report",
            "Page 11",
            ("Online Grocery",),
            "Online grocery penetration reached 13.8% of UK grocery sales in 2025.",
        ),
        ev(
            "E2",
            "Larkspur Shopper Survey 2026",
            "survey",
            "Q4",
            ("Online Habits",),
            "52% of respondents bought groceries online at least once in the past month (n=2,010).",
        ),
    ]
    q = "How large is online grocery in the UK?"
    a = case(
        "a",
        q,
        md(
            [
                "Online grocery accounted for 13.8% of UK grocery sales in 2025 [E1].",
                "Under Online Habits, 52% of shoppers bought groceries online in the past month "
                "[E2].",
            ],
            ["Online penetration stood at 13.8% in 2025 [E2]."],
        ),
        [
            u("accounted for 13.8% of UK grocery sales", S, "percentages", "E1"),
            u("Under Online Habits, 52% of shoppers", S, "section_headings", "E2 heading and text"),
            u(
                "Online penetration stood at 13.8% in 2025",
                M,
                "back_reference",
                "figure cited correctly to E1 above, restated citing E2",
                "E1",
            ),
        ],
    )
    c = case(
        "c",
        q,
        md(
            [
                "The shopper survey sampled 2,010 respondents [E2].",
                "Online grocery penetration reached 13.8% in 2025 [E1].",
            ],
            ["The survey was fielded in 2010 [E2]."],
        ),
        [
            u("survey sampled 2,010 respondents", S, "quantity_as_year_shape", "n=2,010"),
            u("penetration reached 13.8% in 2025", S, "percentages", "E1"),
            u(
                "The survey was fielded in 2010",
                U,
                "quantity_as_year_shape",
                "2,010 is the sample size; 2010 appears nowhere as a year",
            ),
        ],
    )
    return family("F16", "Market report share plus survey incidence", pack, False, [a, c])


def f17() -> Json:
    title = "Vantor Paints Category Review 2026 edition"
    pack = [
        ev(
            "E1",
            title,
            "market_report",
            "Page 6",
            ("Market Structure", "Share by Brand"),
            "Brand | Volume share 2025 (%) | Value share 2025 (%)\nVantor | 18.0 | 22.5\n"
            "Crestline | 24.3 | 21.0\nPrivate label | 30.1 | 19.4",
        ),
        ev(
            "E2",
            title,
            "market_report",
            "Page 7",
            ("Market Structure", "Price Positioning"),
            "Vantor's average price per litre was 26% above the category average in 2025.",
        ),
    ]
    q = "What is Vantor's position in the UK paint market?"
    a = case(
        "a",
        q,
        md(
            [
                "Vantor held a 22.5% value share in 2025 [E1].",
                "Its average price per litre was 26% above the category average in 2024 [E2].",
            ],
            ["Private label led on volume with 30.1% [E1]."],
        ),
        [
            u("Vantor held a 22.5% value share in 2025", S, "table_headers", "Value share column"),
            u(
                "26% above the category average in 2024",
                U,
                "years_dates",
                "E2 is 2025; 2024 appears nowhere in this pack or question",
            ),
            u("Private label led on volume with 30.1%", S, "row_labels", "Private label row"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Vantor led the market with an 18.0% value share in 2025 [E1].",
                "Under Price Positioning, Vantor is priced 26% above the category average per "
                "litre "
                "[E2].",
            ],
            ["Crestline's value share was 24.3% [E1]."],
        ),
        [
            u(
                "led the market with an 18.0% value share",
                U,
                "table_headers",
                "18.0 is Vantor's volume share; value share is 22.5",
            ),
            u("Under Price Positioning, Vantor is priced", S, "section_headings", "E2 heading"),
            u(
                "Crestline's value share was 24.3%",
                U,
                "table_headers",
                "24.3 is Crestline's volume share",
            ),
        ],
    )
    return family("F17", "Brand share table with volume and value columns", pack, False, [a, b])


def f18() -> Json:
    pack = [
        ev(
            "E1",
            "Interview: Brightwater Store Manager, Manchester",
            "interview",
            "Q2",
            ("Footfall",),
            "Weekend footfall is down about a fifth since the tram works started in May 2026.",
        ),
        ev(
            "E2",
            "Brightwater Footfall Counter Export",
            "finance",
            "Row 5",
            ("Footfall", "Manchester"),
            "store: Manchester; week: 2026-W30; visits: 8,412; visits_prior_year: 10,377",
        ),
    ]
    q = "How has footfall changed at Brightwater's Manchester store?"
    a = case(
        "a",
        q,
        md(
            [
                "The store manager reports weekend footfall down about a fifth since the tram "
                "works "
                "began in May 2026 [E1].",
                "In week 2026-W30 the store recorded <b>8,412 visits</b> against 10,377 a year "
                "earlier [E2].",
            ],
            ["Visits fell 18.9% year on year in week 2026-W30 [E2]."],
        ),
        [
            u("down about a fifth since the tram works began in May 2026", S, "years_dates", "E1"),
            u(
                "against 10,377 a year earlier",
                S,
                "leak",
                "HTML tags in the sentence; figures match visits and visits_prior_year",
            ),
            u(
                "Visits fell 18.9% year on year",
                U,
                "computed_values",
                "1 - 8,412/10,377 computed, not stated",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Footfall is down about a fifth according to the store manager "
                "(https://intranet.brightwater.example/footfall) [E1].",
                "The counter logged 8,412 visits in week 2026-W30 [E2].",
            ],
            ["Footfall fell by 1,965 visits in July 2026 [E2]."],
        ),
        [
            u(
                "down about a fifth according to the store manager",
                S,
                "leak",
                "URL in sentence; claim backed by E1",
            ),
            u("logged 8,412 visits in week 2026-W30", S, "years_dates", "ISO week in E2"),
            u(
                "fell by 1,965 visits in July 2026",
                U,
                "computed_values",
                "difference not stated; July 2026 not in pack",
            ),
        ],
    )
    return family(
        "F18",
        "Manager interview plus footfall counter row; HTML and URL leaks",
        pack,
        False,
        [a, b],
    )


def f19() -> Json:
    pack = [
        ev(
            "E1",
            "Rowan & Finch Tea Strategy Memo 2026",
            "strategy",
            "Page 3",
            ("Priorities", "Premiumisation"),
            "We will reduce the number of SKUs from 140 to 95 by Q2 2027 and shift marketing "
            "spend toward loose-leaf ranges.",
        ),
        ev(
            "E2",
            "Rowan & Finch Tea Category Data",
            "market_report",
            "Page 2",
            ("Loose Leaf",),
            "Loose-leaf tea value sales grew 7.2% in 2025 while teabag value sales fell 1.8%.",
        ),
    ]
    q = "What is Rowan & Finch's strategy, and does it fit category trends?"
    a = case(
        "a",
        q,
        md(
            [
                "Rowan & Finch plans to cut its range from 140 to 95 SKUs by Q2 2027 [E1].",
                "[inference] The shift toward loose leaf fits the segment's stronger value growth.",
            ],
            ["Loose-leaf value sales grew 7.2% in 2025 [E2]."],
            interp=[
                "[inference] Range cuts may free around 30% of shelf space for loose-leaf lines."
            ],
        ),
        [
            u("cut its range from 140 to 95 SKUs by Q2 2027", S, "years_dates", "E1"),
            u(
                "fits the segment's stronger value growth",
                S,
                "uncited_claim",
                "inference, no numbers",
            ),
            u("Loose-leaf value sales grew 7.2% in 2025", S, "percentages", "E2"),
            u(
                "may free around 30% of shelf space",
                U,
                "unsupported_calculation",
                "inference introduces a number",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Rowan & Finch will remove 45 SKUs by Q2 2027 [E1].",
                "[inference] The plan should lift loose-leaf share by roughly 5 points.",
            ],
            ["Loose-leaf grew 7.2% by value in 2025 [E2]."],
        ),
        [
            u("will remove 45 SKUs by Q2 2027", U, "computed_values", "140 - 95 not stated"),
            u(
                "lift loose-leaf share by roughly 5 points",
                U,
                "unsupported_calculation",
                "inference introduces a number with no basis",
            ),
            u("Loose-leaf grew 7.2% by value in 2025", S, "percentages", "E2"),
        ],
        failures=("answer_missing",),
        retry=md(
            [
                "Rowan & Finch is dropping 45 SKUs [E1].",
                "[inference] Loose leaf could reach a 5 point higher share.",
            ],
            ["Teabags fell 1.8% [E2]."],
        ),
    )
    return family(
        "F19",
        "Strategy memo plus category data; inference with and without numbers",
        pack,
        False,
        [a, b],
    )


def f20() -> Json:
    deck = "Halcyon Foods Strategy Day 2026"
    pack = [
        ev(
            "E1",
            deck,
            "deck",
            "Slide 4",
            ("Strategy Day 2026", "Chilled Division"),
            "Chilled division operating margin: 12.0% in FY2025.",
        ),
        ev(
            "E2",
            deck,
            "deck",
            "Slide 5",
            ("Strategy Day 2026", "Ambient Division"),
            "Ambient division operating margin: 12.4% in FY2025; target 14% by FY2028.",
        ),
    ]
    q = "What are Halcyon Foods' divisional operating margins?"
    a = case(
        "a",
        q,
        md(
            [
                "The Chilled Division slide shows a 12.0% operating margin in FY2025 [E1].",
                "The Ambient division earned 12.4% and targets 14% by FY2027 [E2].",
            ],
            ["Each division is presented on its own slide in the Strategy Day 2026 deck [E1][E2]."],
        ),
        [
            u("Chilled Division slide shows a 12.0% operating margin", S, "slide_titles", "E1"),
            u("Ambient division earned 12.4%", S, "multi_clause", "E2"),
            u("targets 14% by FY2027", U, "multi_clause", "target year is FY2028; FY2027 absent"),
            u(
                "presented on its own slide in the Strategy Day 2026 deck",
                S,
                "titles",
                "source titles and locators",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Halcyon's group operating margin was 12.0% in FY2025 [E1].",
                "The Ambient division targets a 14% margin by FY2028 [E2].",
            ],
            ["Ambient division operating margin data sit on Slide 5 [E2]."],
            conflicts=[
                "Slide 4 reports a 12.0% margin while Slide 5 reports 12.4% for FY2025 [E1][E2]."
            ],
        ),
        [
            u(
                "group operating margin was 12.0%",
                U,
                "slide_titles",
                "12.0% is the Chilled division slide, not group",
            ),
            u("targets a 14% margin by FY2028", S, "years_dates", "E2"),
            u("operating margin data sit on Slide 5", S, "slide_titles", "E2 locator"),
            u(
                "Slide 4 reports a 12.0% margin while Slide 5",
                S,
                "conflicting_evidence",
                "accurate, but two divisions are not a conflict",
            ),
        ],
    )
    return family(
        "F20",
        "Two deck slides with near-identical divisional margins, no conflict",
        pack,
        False,
        [a, b],
    )


def f21() -> Json:
    pack = [
        ev(
            "E1",
            "Kestrel Air Traffic Statistics September 2026",
            "finance",
            "Page 1",
            ("Passengers",),
            "Passengers carried in September 2026: 486,000, up 6.1% year on year. Load factor: "
            "81.4%.",
        ),
        ev(
            "E2",
            "Kestrel Air Network Plan Winter 2026",
            "strategy",
            "Page 3",
            ("New Routes",),
            "Three new routes from Bristol start in November 2026: Bergen, Turin and Porto.",
        ),
    ]
    q = "How is Kestrel Air's traffic trending, and which routes are being added?"
    a = case(
        "a",
        q,
        md(
            [
                "Kestrel Air carried 486,000 passengers in September 2026 [E1].",
                "Three new Bristol routes start in November 2026 [E2].",
            ],
            ["Load factor was 81.4% [E1] (source table: KESTREL/STATS@v1:P1)."],
        ),
        [
            u("carried 486,000 passengers in September 2026", S, "quantities", "E1"),
            u("Three new Bristol routes start in November 2026", S, "years_dates", "E2"),
            u(
                "Load factor was 81.4%",
                S,
                "foreign_handle",
                "raw internal handle in text; claim backed by E1",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Kestrel carried 486 million passengers in September 2026 [E1].",
                "New routes will serve Bergen, Turin and Porto [E2].",
            ],
            [
                "On-time performance was 88% [E5].",
                "Load factor reached 81.4% [[KESTREL/STATS@v1:P1]].",
            ],
        ),
        [
            u("carried 486 million passengers", U, "million_billion", "486,000, not million"),
            u(
                "New routes will serve Bergen, Turin and Porto",
                S,
                "section_headings",
                "New Routes section of E2",
            ),
            u("On-time performance was 88%", U, "fabricated_citation", "E5 not in pack; absent"),
            u(
                "Load factor reached 81.4%",
                U,
                "foreign_handle",
                "after marker removal the bullet carries a figure and no valid citation",
            ),
        ],
    )
    c = case(
        "c",
        q,
        md(
            [
                "Passenger numbers rose 6.1% to 486,000 [E3].",
                "The winter network plan adds Bergen, Turin and Porto from Bristol [E2].",
            ],
            ["Load factor was 81.4% in September 2026 [E1]."],
        ),
        [
            u(
                "Passenger numbers rose 6.1% to 486,000",
                M,
                "fabricated_citation",
                "E3 not in pack; both figures are in exactly one pack item",
                "E1",
            ),
            u(
                "winter network plan adds Bergen, Turin and Porto",
                S,
                "titles",
                "Winter from E2 source title",
            ),
            u("Load factor was 81.4% in September 2026", S, "percentages", "E1"),
        ],
    )
    d = case(
        "d",
        q,
        md(
            [
                "Kestrel Air carried 486,000 passengers in September 2026, up 6.1% year on year "
                "[E1].",
                "Three routes from Bristol launch in November 2026 [E2].",
            ],
            [
                "Load factor reached 81.4% [E1].",
                "The new destinations are Bergen, Turin and Porto [E2].",
            ],
        ),
        [
            u("carried 486,000 passengers in September 2026, up 6.1%", S, "citation_cap", "E1"),
            u("Three routes from Bristol launch in November 2026", S, "citation_cap", "E2"),
            u("Load factor reached 81.4%", S, "citation_cap", "E1"),
            u("new destinations are Bergen, Turin and Porto", S, "citation_cap", "E2"),
        ],
        cap=3,
        failures=("too_many_citations",),
        retry=md(
            [
                "Kestrel carried 486,000 passengers in September 2026 [E1].",
                "Load factor was 81.4% [E1].",
            ],
            ["Bergen, Turin and Porto open in November 2026 [E2].", "Traffic was up 6.1% [E1]."],
        ),
    )
    return family(
        "F21",
        "Airline traffic page and network plan; handles, invented aliases, cap",
        pack,
        False,
        [a, b, c, d],
    )


def f22() -> Json:
    pack = [
        ev(
            "E1",
            "Sablewood Homes Trading Statement",
            "finance",
            "Page 1",
            ("Completions",),
            "Completions in the six months to 30 June 2026 were 1,912 homes, compared with "
            "1,744 in the prior-year period. Average selling price was GBP 342,000.",
        ),
        ev(
            "E2",
            "Sablewood Homes Land Bank Note",
            "strategy",
            "Page 2",
            ("Planning",),
            "Planning consent for the Ashby Fields site (420 plots) was granted on 2026-08-14.",
        ),
    ]
    q = "How many homes did Sablewood complete in H1 2026, and what is in the pipeline?"
    a = case(
        "a",
        q,
        md(
            [
                "Sablewood completed 1,912 homes in the six months to 30 June 2026 [E1].",
                "Ashby Fields received planning consent for 420 plots on 14 August 2026 [E2].",
            ],
            ["Prior-year H1 completions totalled 1,744 homes [E1]."],
        ),
        [
            u("completed 1,912 homes in the six months", S, "quantity_as_year_shape", "E1"),
            u("420 plots on 14 August 2026", S, "years_dates", "ISO date 2026-08-14 restated"),
            u("Prior-year H1 completions totalled 1,744 homes", S, "quantity_as_year_shape", "E1"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Completions rose 9.6% to 1,912 homes in H1 2026 [E1].",
                "Consent for Ashby Fields was granted in September 2026 [E2].",
            ],
            ["Average selling price was GBP 342 million [E1]."],
        ),
        [
            u(
                "Completions rose 9.6% to 1,912 homes",
                U,
                "computed_values",
                "1,912/1,744 - 1 computed, not stated",
            ),
            u("granted in September 2026", U, "years_dates", "consent was 2026-08-14"),
            u("Average selling price was GBP 342 million", U, "million_billion", "GBP 342,000"),
        ],
        failures=("answer_missing",),
        retry=md(
            [
                "Completions grew by 168 homes to 1,912 [E1].",
                "Ashby Fields was approved in September 2026 [E2].",
            ]
        ),
    )
    return family(
        "F22", "Housebuilder completions with year-like counts and an ISO date", pack, False, [a, b]
    )


def f23() -> Json:
    pack = [
        ev(
            "E1",
            "Marlowe Dental Patient Survey 2026",
            "survey",
            "Q3",
            ("Booking",),
            "61% of patients booked their last appointment online (n=860).",
        ),
        ev(
            "E2",
            "Marlowe Dental Operations Review",
            "strategy",
            "Page 8",
            ("No-shows",),
            "No-show rates fell from 9% to 6% after SMS reminders were introduced in January 2026.",
        ),
    ]
    q = "How do Marlowe Dental patients book, and what reduced no-shows?"
    a = case(
        "a",
        q,
        md(
            [
                "61% of patients booked their last appointment online [E1].",
                "No-show rates fell from 9% to 6% after SMS reminders were introduced in January "
                "2026 [E2].",
                "[inference] This suggests reminders are an effective lever.",
            ]
        ),
        [
            u("61% of patients booked their last appointment online", S, "percentages", "E1"),
            u("SMS reminders were introduced in January 2026", S, "years_dates", "E2"),
            u(
                "This suggests reminders are an effective lever",
                S,
                "dangling_reference",
                "antecedent supported; inference adds no numbers",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "61% of patients book online [E1], and online booking cut no-shows by a third "
                "[E2].",
                "This reduction saved Marlowe GBP 1.4 million [E2].",
            ],
            ["No-shows fell to 6% [E2]."],
        ),
        [
            u("61% of patients book online", S, "multi_clause", "E1"),
            u(
                "online booking cut no-shows by a third",
                U,
                "multi_clause",
                "E2 credits SMS reminders; one third is computed",
            ),
            u(
                "This reduction saved Marlowe GBP 1.4 million",
                U,
                "dangling_reference",
                "antecedent unsupported; figure absent",
            ),
            u("No-shows fell to 6%", S, "percentages", "E2"),
        ],
    )
    c = case(
        "c",
        q,
        md(
            [
                "Most patients book online [E1].",
                "The survey sample was 860 patients [E1].",
                "No-shows fell from 9% to 6% [E2].",
                "SMS reminders drove the fall [E2].",
                "Online booking also reduced no-shows by 3 points [E1].",
            ]
        ),
        [
            u("Most patients book online", S, "percentages", "61% is a majority"),
            u("survey sample was 860 patients", S, "quantities", "n=860"),
            u("No-shows fell from 9% to 6%", S, "percentages", "E2"),
            u("SMS reminders drove the fall", S, "titles", "E2 text"),
            u(
                "Online booking also reduced no-shows by 3 points",
                U,
                "computed_values",
                "E1 says nothing about no-shows; 9 - 6 computed",
            ),
        ],
        failures=("answer_too_long",),
        retry=md(
            [
                "61% book online [E1].",
                "The sample was 860 [E1].",
                "No-shows fell to 6% [E2].",
                "Reminders started in January 2026 [E2].",
                "Online booking helped too [E1].",
            ]
        ),
    )
    return family(
        "F23",
        "Survey and operations review; This-sentences after good and bad claims",
        pack,
        False,
        [a, b, c],
    )


def f24() -> Json:
    pack = [
        ev(
            "E1",
            "Orchard Lane Cider Distributor Survey 2026",
            "survey",
            "Q5",
            ("Stock Availability",),
            "On-shelf availability across surveyed pubs: 92%.",
        ),
        ev(
            "E2",
            "Interview: Orchard Lane Regional Sales Lead",
            "interview",
            "Q8",
            ("Stock Availability",),
            "Honestly our on-shelf availability in pubs is nearer 80% this summer; the 92% "
            "survey number only counts managed estates.",
        ),
    ]
    q = "What is Orchard Lane's on-shelf availability in pubs?"
    a = case(
        "a",
        q,
        md(
            [
                "The distributor survey puts on-shelf availability across surveyed pubs at 92% "
                "[E1].",
                "The regional sales lead estimates it is nearer 80% this summer [E2].",
            ],
            conflicts=["Survey: 92% availability [E1]; sales lead: nearer 80% [E2]."],
        ),
        [
            u("availability across surveyed pubs at 92%", S, "conflicting_evidence", "E1"),
            u(
                "regional sales lead estimates it is nearer 80%",
                S,
                "titles",
                "role from E2 source title",
            ),
            u("Survey: 92% availability", S, "conflicting_evidence", "both sides cited"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Orchard Lane's pub availability is 92% [E1].",
                "This is consistent with the sales lead's view [E2].",
            ],
            ["Availability in managed estates is 80% [E2]."],
        ),
        [
            u(
                "pub availability is 92%",
                S,
                "conflicting_evidence",
                "backed by E1 text; omits the disagreement",
            ),
            u(
                "This is consistent with the sales lead's view",
                U,
                "dangling_reference",
                "E2 contradicts the survey figure",
            ),
            u(
                "Availability in managed estates is 80%",
                U,
                "conflicting_evidence",
                "E2: 92% counts managed estates; 80% is the overall estimate",
            ),
        ],
    )
    return family(
        "F24", "Survey figure disputed by an interviewee (genuine conflict)", pack, True, [a, b]
    )


def f25() -> Json:
    title = "Fenwright Insurance Claims Report H1 2026"
    pack = [
        ev(
            "E1",
            title,
            "finance",
            "Page 12",
            ("Motor", "Claims Frequency"),
            "Motor claims frequency was 7.8 per 100 policies in H1 2026.",
        ),
        ev(
            "E2",
            title,
            "finance",
            "Page 15",
            ("Home", "Escape of Water"),
            "Escape-of-water claims accounted for 38% of home claim costs.",
        ),
    ]
    q = "What does Fenwright's claims report say about motor and home claims?"
    a = case(
        "a",
        q,
        md(
            [
                "According to page 12 of the Claims Report H1 2026, motor claims frequency was 7.8 "
                "per 100 policies [E1].",
                "In the Home section, escape-of-water claims made up 38% of home claim costs [E2].",
            ],
            ["Motor frequency is reported under Claims Frequency [E1]."],
        ),
        [
            u(
                "According to page 12 of the Claims Report H1 2026",
                S,
                "titles",
                "locator and source title of E1",
            ),
            u("In the Home section, escape-of-water claims", S, "section_headings", "E2"),
            u("reported under Claims Frequency", S, "section_headings", "E1 heading"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Page 14 of the Claims Report shows motor frequency at 7.8 per 100 policies [E1].",
                "Escape-of-water claims were 38% of all home claims [E2].",
            ],
            ["Motor claims frequency was 7.8% [E1]."],
        ),
        [
            u("Page 14 of the Claims Report shows", U, "titles", "E1 is Page 12"),
            u(
                "Escape-of-water claims were 38% of all home claims",
                U,
                "percentages",
                "38% is of claim costs, not claim count",
            ),
            u(
                "Motor claims frequency was 7.8%",
                U,
                "invalid_unit_conversion",
                "a rate per 100 policies is not stated as a share",
            ),
        ],
        failures=("answer_missing",),
        retry=md(
            [
                "Page 14 puts motor frequency at 7.8% [E1].",
                "Water claims were 38% of home claims [E2].",
            ]
        ),
    )
    return family(
        "F25", "Insurance report with page locators and nested headings", pack, False, [a, b]
    )


def f26() -> Json:
    pack = [
        ev(
            "E1",
            "Halden Cosmetics Market Sizing",
            "market_report",
            "Page 3",
            ("Market Size",),
            "The UK prestige fragrance market was worth GBP 1.1 billion in 2025.",
        ),
        ev(
            "E2",
            "Halden Cosmetics Consumer Panel",
            "survey",
            "Q2",
            ("Purchase Channels",),
            "Department stores remain the top purchase channel for prestige fragrance.",
        ),
    ]
    q = "What is Halden's share of the UK prestige fragrance market, by channel?"
    a = case(
        "a",
        q,
        md(
            [
                "None of the sources give Halden's share of the UK prestige fragrance market.",
                "The market itself was worth GBP 1.1 billion in 2025 [E1].",
            ],
            gaps=[
                "Halden's sales are not broken down by channel; retailer sell-out data would "
                "close this gap."
            ],
        ),
        [
            u("None of the sources give Halden's share", S, "insufficiency", "true"),
            u("market itself was worth GBP 1.1 billion", S, "million_billion", "E1"),
            u("not broken down by channel", S, "insufficiency", "true gap"),
        ],
        truncated=True,
    )
    b = case(
        "b",
        q,
        md(
            [
                "Halden's market share is not reported in the evidence.",
                "The UK prestige fragrance market was worth GBP 1.1 billion in 2025 [E1].",
            ],
            ["Department stores account for 45% of prestige fragrance sales [E2]."],
        ),
        [
            u("market share is not reported in the evidence", S, "insufficiency", "true"),
            u("prestige fragrance market was worth GBP 1.1 billion", S, "million_billion", "E1"),
            u("Department stores account for 45%", U, "percentages", "no share in E2"),
        ],
        truncated=True,
        failures=("gaps_missing",),
        retry=md(
            [
                "The evidence does not report Halden's share.",
                "The market was GBP 1.1 billion in 2025 [E1].",
            ],
            ["Department stores lead [E2]."],
        ),
    )
    c = case(
        "c",
        q,
        md(
            [
                "The evidence does not establish Halden's market share.",
                "The market was worth GBP 1,100 million in 2025 [E1].",
            ],
            gaps=["Halden's share is likely below 10%, but no source confirms it."],
        ),
        [
            u("does not establish Halden's market share", S, "insufficiency", "true"),
            u("worth GBP 1,100 million in 2025", S, "valid_unit_conversion", "GBP 1.1 billion"),
            u("share is likely below 10%", U, "insufficiency", "number in Gaps with no basis"),
        ],
        truncated=True,
    )
    return family(
        "F26", "Truncated pack: market size known, company share unknown", pack, False, [a, b, c]
    )


def f27() -> Json:
    title = "Northmere Water Performance Dataset"
    pack = [
        ev(
            "E1",
            title,
            "finance",
            "Row 21",
            ("Leakage", "2025-26"),
            "zone: North; leakage_ml_per_day: 48.6; target_ml_per_day: 45.0",
        ),
        ev(
            "E2",
            title,
            "finance",
            "Row 22",
            ("Leakage", "2025-26"),
            "zone: South; leakage_ml_per_day: 39.2; target_ml_per_day: 41.0",
        ),
    ]
    q = "Is Northmere Water meeting its leakage targets?"
    a = case(
        "a",
        q,
        md(
            [
                "The North zone is above target, at 48.6 Ml per day against a 45.0 target [E1].",
                "The South zone is 10% below its 41.0 target at 39.2 Ml per day [E2].",
            ],
            gaps=[
                "The extract does not cover all zones, so company-wide performance is not "
                "established."
            ],
        ),
        [
            u("North zone is above target, at 48.6 Ml per day", S, "row_labels", "E1"),
            u(
                "South zone is 10% below its 41.0 target",
                U,
                "unsupported_calculation",
                "39.2 is about 4.4% below 41.0, and no gap is stated",
            ),
            u("does not cover all zones", S, "insufficiency", "truncated pack"),
        ],
        truncated=True,
    )
    b = case(
        "b",
        q,
        md(
            [
                "Northmere leaks 87.8 Ml per day across both zones [E1][E2].",
                "The South zone beat its leakage target [E2].",
            ],
            ["North exceeds its target by 3.6 Ml per day [E1]."],
        ),
        [
            u("leaks 87.8 Ml per day across both zones", U, "computed_values", "sum not stated"),
            u("South zone beat its leakage target", S, "row_labels", "39.2 < 41.0"),
            u("exceeds its target by 3.6 Ml per day", U, "computed_values", "difference"),
        ],
        truncated=True,
        failures=("gaps_missing",),
    )
    c = case(
        "c",
        q,
        md(
            [
                "North zone leakage was 48.6 megalitres per day in 2025-26 [E1].",
                "South zone leakage was 39.2 litres per day [E2].",
            ],
            gaps=["The dataset does not report leakage for other zones."],
        ),
        [
            u(
                "leakage was 48.6 megalitres per day in 2025-26",
                S,
                "valid_unit_conversion",
                "ml_per_day field read as megalitres (Ml), heading 2025-26",
            ),
            u(
                "leakage was 39.2 litres per day",
                U,
                "invalid_unit_conversion",
                "megalitres, not litres",
            ),
            u("does not report leakage for other zones", S, "insufficiency", "truncated pack"),
        ],
        truncated=True,
    )
    return family(
        "F27", "Truncated utility dataset rows; Gaps section required", pack, False, [a, b, c]
    )


def f28() -> Json:
    title = "Quarry Lane Gyms Membership Report"
    pack = [
        ev(
            "E1",
            title,
            "finance",
            "Page 2",
            ("Members", "December 2025"),
            "Members at 31 December 2025: 214,000.",
        ),
        ev(
            "E2",
            title,
            "finance",
            "Page 3",
            ("Members", "June 2026"),
            "Members at 30 June 2026: 241,000. Net joiners in H1 2026: 27,000.",
        ),
    ]
    q = "How has Quarry Lane Gyms' membership changed?"
    a = case(
        "a",
        q,
        md(
            [
                "Quarry Lane had 214,000 members at 31 December 2025 [E1].",
                "Membership reached 241,000 by 30 June 2026 [E2].",
            ],
            ["Membership grew 12.6% in six months [E1][E2]."],
        ),
        [
            u("had 214,000 members at 31 December 2025", S, "quantities", "E1"),
            u("Membership reached 241,000 by 30 June 2026", S, "quantities", "E2"),
            u("Membership grew 12.6% in six months", U, "computed_values", "not stated"),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Membership was 241,000 at 30 June 2026 [E2].",
                "The December 2025 figure was 241,000 [E1].",
            ],
            ["Net joiners totalled 27,000 in H1 2026 [E2]."],
            conflicts=[
                "The report gives 214,000 members on page 2 but 241,000 on page 3 [E1][E2]."
            ],
        ),
        [
            u("Membership was 241,000 at 30 June 2026", S, "quantities", "E2"),
            u(
                "The December 2025 figure was 241,000",
                U,
                "quantities",
                "E1 gives 214,000 (transposed); E2's 241,000 is a June figure, so not miscited",
            ),
            u("Net joiners totalled 27,000 in H1 2026", S, "quantities", "E2"),
            u(
                "gives 214,000 members on page 2 but 241,000 on page 3",
                S,
                "conflicting_evidence",
                "accurate but different dates: a false conflict",
            ),
        ],
    )
    return family(
        "F28",
        "Membership at two dates with digit-swapped numbers, no conflict",
        pack,
        False,
        [a, b],
    )


def f29() -> Json:
    pack = [
        ev(
            "E1",
            "Pinecrest Outdoor Retail Index, 2026 edition",
            "market_report",
            "Page 4",
            ("Segments", "Sales by Segment"),
            "Segment | 2025 sales (GBP m) | Growth vs 2024 (%)\nFootwear | 640 | 4.1\n"
            "Apparel | 1,120 | 2.7\nEquipment | 395 | -1.3",
        ),
        ev(
            "E2",
            "Pinecrest Outdoor Retail Index, 2025 edition",
            "market_report",
            "Page 4",
            ("Segments", "Sales by Segment"),
            "Segment | 2024 sales (GBP m)\nFootwear | 615\nApparel | 1,090\nEquipment | 400",
        ),
    ]
    q = "How large are the UK outdoor retail segments?"
    a = case(
        "a",
        q,
        md(
            [
                "The 2026 edition puts 2025 footwear sales at GBP 640 million [E1].",
                "Apparel made up about two thirds of segment sales at GBP 1,120 million [E1].",
            ],
            ["The 2025 edition recorded apparel sales of GBP 1,090 million for 2024 [E2]."],
        ),
        [
            u(
                "2026 edition puts 2025 footwear sales at GBP 640 million",
                S,
                "edition_labels",
                "E1 title; GBP m column",
            ),
            u(
                "about two thirds of segment sales",
                U,
                "unsupported_calculation",
                "1,120 of 2,155 is about 52%; no share stated",
            ),
            u(
                "2025 edition recorded apparel sales of GBP 1,090 million",
                S,
                "edition_labels",
                "E2",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Apparel sales were GBP 1.12 billion in 2025 [E1].",
                "The 2024 edition reported footwear sales of GBP 615 million [E2].",
            ],
            ["Equipment sales were GBP 395 billion [E1].", "Apparel sales grew 2.7% [E2]."],
        ),
        [
            u(
                "Apparel sales were GBP 1.12 billion in 2025",
                S,
                "valid_unit_conversion",
                "GBP 1,120 m",
            ),
            u(
                "2024 edition reported footwear sales",
                U,
                "edition_labels",
                "615 is in the 2025 edition; no 2024 edition exists in pack",
            ),
            u("Equipment sales were GBP 395 billion", U, "million_billion", "GBP m"),
            u(
                "Apparel sales grew 2.7%",
                M,
                "table_headers",
                "2.7 is only in E1's growth column",
                "E1",
            ),
        ],
    )
    c = case(
        "c",
        q,
        md(
            [
                "Footwear sales reached EUR 640 million in 2025 [E1].",
                "Apparel sales were GBP 1,090 million in 2024 according to the 2025 edition [E2].",
            ],
            ["Equipment was the only segment to decline, by 1.3% [E1]."],
        ),
        [
            u("Footwear sales reached EUR 640 million", U, "currency_mismatch", "GBP m"),
            u("GBP 1,090 million in 2024 according to the 2025 edition", S, "edition_labels", "E2"),
            u("only segment to decline, by 1.3%", S, "table_headers", "Growth vs 2024 column"),
        ],
    )
    d = case(
        "d",
        q,
        md(
            [
                "Footwear sales were GBP 640 million in 2025 [E1].",
                "Apparel sales were GBP 1,120 million [E1].",
            ],
            [
                "Equipment sales fell 1.3% [E1].",
                "In 2024 apparel sales were GBP 1,090 million [E2].",
            ],
        ),
        [
            u("Footwear sales were GBP 640 million in 2025", S, "citation_cap", "E1"),
            u("Apparel sales were GBP 1,120 million", S, "citation_cap", "E1"),
            u("Equipment sales fell 1.3%", S, "citation_cap", "E1"),
            u("In 2024 apparel sales were GBP 1,090 million", S, "citation_cap", "E2"),
        ],
        cap=4,
    )
    return family(
        "F29",
        "Two editions of an index with different year columns, no conflict",
        pack,
        False,
        [a, b, c, d],
    )


def f30() -> Json:
    deck = "Brightwater Outfitters Investor Day 2026"
    pack = [
        ev(
            "E1",
            deck,
            "deck",
            "Slide 12",
            ("Investor Day 2026", "Store Roll-out"),
            "Plan: 18 new stores in FY2027, of which 6 in Scotland.",
        ),
        ev(
            "E2",
            deck,
            "deck",
            "Slide 14",
            ("Investor Day 2026", "Digital"),
            "Online share of sales: 28% in FY2026; ambition 35% by FY2029.",
        ),
    ]
    q = "What growth plans did Brightwater set out at its Investor Day?"
    a = case(
        "a",
        q,
        md(
            [
                "The Store Roll-out slide plans 18 new stores in FY2027 [E1].",
                "The Digital slide targets an online share of sales of 35% by FY2029 [E2].",
            ],
            ['Online share of sales was 28% in FY2025 [E2] <img src="chart.png">.'],
        ),
        [
            u("Store Roll-out slide plans 18 new stores in FY2027", S, "slide_titles", "E1"),
            u("Digital slide targets an online share of sales of 35%", S, "slide_titles", "E2"),
            u(
                "Online share of sales was 28% in FY2025",
                U,
                "leak",
                "img tag; E2 says FY2026 and FY2025 is absent",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Slide 13 sets out plans for 18 new stores [E1].",
                "Online share was 28% in FY2026 [[BRIGHTWATER/INVDAY@v1:S14]] [E2].",
            ],
            ["12 of the new stores will be in England [E1]."],
        ),
        [
            u("Slide 13 sets out plans for 18 new stores", U, "slide_titles", "E1 is Slide 12"),
            u(
                "Online share was 28% in FY2026",
                S,
                "foreign_handle",
                "foreign marker plus a valid alias; claim backed by E2",
            ),
            u(
                "12 of the new stores will be in England",
                U,
                "unsupported_calculation",
                "18 - 6 and the England attribution are not stated",
            ),
        ],
    )
    c = case(
        "c",
        q,
        md(
            [
                "Brightwater plans 18 new stores in FY2027 [E1].",
                "Online share should rise 7 points by FY2029 [E2].",
            ],
            ["Six new stores are planned for Scotland [E2]."],
        ),
        [
            u("plans 18 new stores in FY2027", S, "quantities", "E1"),
            u("Online share should rise 7 points", U, "computed_values", "35 - 28 not stated"),
            u(
                "Six new stores are planned for Scotland",
                M,
                "quantities",
                "spelled-out 6, only in E1",
                "E1",
            ),
        ],
    )
    return family(
        "F30",
        "Investor day slide deck with HTML, handles and slide numbers",
        pack,
        False,
        [a, b, c],
    )


def f31() -> Json:
    report = "Lumen Grove Market Report 2026"
    pack = [
        ev(
            "E1",
            "Lumen Grove Installer Survey 2026",
            "survey",
            "Q3",
            ("Lead Sources",),
            "Referrals generated 44% of installer leads; online ads 31%; trade shows 9%.",
        ),
        ev(
            "E2",
            report,
            "market_report",
            "Page 10",
            ("Installations",),
            "Residential solar installations reached 186,000 in 2025, up from 152,000 in 2024.",
        ),
        ev(
            "E3",
            report,
            "market_report",
            "Page 12",
            ("Pricing",),
            "Average installed price for a 4 kW system fell to GBP 6,200 in 2025.",
        ),
    ]
    q = "What does the UK residential solar installer market look like?"
    a = case(
        "a",
        q,
        md(
            [
                "Residential solar installations reached 186,000 in 2025 [E2].",
                "Installations grew 22.4% year on year [E2].",
            ],
            ["A 4 kW system cost GBP 6,200 on average in 2025 [E3]."],
        ),
        [
            u("installations reached 186,000 in 2025", S, "quantities", "E2"),
            u(
                "Installations grew 22.4% year on year",
                U,
                "computed_values",
                "186,000/152,000 - 1 computed, not stated",
            ),
            u("A 4 kW system cost GBP 6,200", S, "quantities", "E3"),
        ],
    )
    c = case(
        "c",
        q,
        md(
            [
                "Installations reached 186,000 in 2025 [E2].",
                "Referrals generated 44% of installer leads [E1].",
            ],
            [
                "The 186,000 installations in 2025 coincided with a fall in system prices [E3].",
                "Installers earned about GBP 1.15 billion from residential systems in 2025.",
            ],
        ),
        [
            u("Installations reached 186,000 in 2025", S, "quantities", "E2"),
            u("Referrals generated 44% of installer leads", S, "percentages", "E1"),
            u(
                "coincided with a fall in system prices",
                M,
                "back_reference",
                "186,000 cited to E2 above, restated citing E3",
                "E2",
            ),
            u(
                "earned about GBP 1.15 billion",
                U,
                "uncited_claim",
                "uncited bullet; 186,000 x 6,200 computed",
            ),
        ],
    )
    return family(
        "F31", "Solar market survey and report; growth rate and back-reference", pack, False, [a, c]
    )


def f32() -> Json:
    pack = [
        ev(
            "E1",
            "Ardent Bank SME Lending Factbook",
            "finance",
            "Page 4",
            ("Lending Volumes",),
            "Gross SME lending in 2025: GBP 3.4 billion, of which 22% was green finance.",
        ),
        ev(
            "E2",
            "Ardent Bank SME Customer Interviews",
            "interview",
            "Q11",
            ("Approval Times",),
            "A typical SME loan now takes nine working days from application to decision, down "
            "from fourteen.",
        ),
    ]
    q = "How much does Ardent Bank lend to SMEs, and how fast are decisions?"
    a = case(
        "a",
        q,
        md(
            [
                "Ardent Bank's gross SME lending was GBP 3.4 billion in 2025 [E1].",
                "Loan decisions now take about nine working days [E2].",
            ],
            ["Green finance made up 22% of 2025 SME lending, roughly GBP 0.5 billion [E1]."],
        ),
        [
            u("gross SME lending was GBP 3.4 billion", S, "million_billion", "E1"),
            u("Loan decisions now take about nine working days", S, "quantities", "E2"),
            u("Green finance made up 22%", S, "multi_clause", "E1"),
            u(
                "roughly GBP 0.5 billion",
                U,
                "unsupported_calculation",
                "22% of 3.4bn is about 0.75bn; not stated",
            ),
        ],
    )
    b = case(
        "b",
        q,
        md(
            [
                "Ardent lent GBP 3.4 billion to SMEs in 2025 [E1].",
                "Green finance lending totalled GBP 748 million [E1].",
            ],
            ["SME lending reached GBP 3.4 billion [E2]."],
        ),
        [
            u("Ardent lent GBP 3.4 billion to SMEs", S, "million_billion", "E1"),
            u(
                "Green finance lending totalled GBP 748 million",
                U,
                "computed_values",
                "22% x 3.4bn computed, not stated",
            ),
            u(
                "SME lending reached GBP 3.4 billion",
                M,
                "back_reference",
                "cited to E1 above, restated citing E2",
                "E1",
            ),
        ],
    )
    c = case(
        "c",
        q,
        md(
            [
                'SME loans take nine working days to decide, <a href="https://ardent.example/sme">'
                "per customer interviews</a> [E2].",
                "Lending was GBP 3.4 billion in 2025 [[ARDENT/FACTBOOK@v3:P4]].",
            ],
            ["22% of SME lending was green finance [E1].", "Approval rates were 64% [E3]."],
        ),
        [
            u("SME loans take nine working days to decide", S, "leak", "anchor tag; E2"),
            u(
                "Lending was GBP 3.4 billion in 2025",
                U,
                "foreign_handle",
                "after marker removal the sentence has a figure and no valid citation",
            ),
            u("22% of SME lending was green finance", S, "percentages", "E1"),
            u("Approval rates were 64%", U, "fabricated_citation", "E3 not in pack; absent"),
        ],
    )
    return family(
        "F32",
        "Bank factbook and interviews; leaks, handles and back-references",
        pack,
        False,
        [a, b, c],
    )


FAMILY_BUILDERS = (
    f01,
    f02,
    f03,
    f04,
    f05,
    f06,
    f07,
    f08,
    f09,
    f10,
    f11,
    f12,
    f13,
    f14,
    f15,
    f16,
    f17,
    f18,
    f19,
    f20,
    f21,
    f22,
    f23,
    f24,
    f25,
    f26,
    f27,
    f28,
    f29,
    f30,
    f31,
    f32,
)


# --------------------------------------------------------------------------- validation


def segments(answer: str) -> list[tuple[str, str]]:
    """(section, segment) pairs: sentences for paragraph sections, lines for bullet ones."""
    out: list[tuple[str, str]] = []
    parts = SECTION_RE.split(answer)
    for heading, body in zip(parts[1::2], parts[2::2], strict=True):
        text = body.strip()
        if heading in PARAGRAPH_SECTIONS:
            pieces = re.split(r"(?<=\.)\s+", text)
        else:
            pieces = [line.removeprefix("- ") for line in text.splitlines()]
        out.extend((heading, p) for p in pieces if p.strip())
    return out


def derived_failures(c: Json) -> list[str]:
    """Structural failures implied by the gold units (cross-check for hand-set expectations)."""
    answer = c["answer"]
    by_key = {x["key"]: x for x in c["units"]}
    segs = segments(answer)
    kept = [
        (sec, seg) for sec, seg in segs if any(k in seg and by_key[k]["label"] == S for k in by_key)
    ]
    failures = []
    answer_kept = [seg for sec, seg in kept if sec == "Answer"]
    if not answer_kept:
        failures.append("answer_missing")
    if sum(1 for sec, _ in segs if sec == "Answer") > MAX_ANSWER_SENTENCES:
        failures.append("answer_too_long")
    insufficient = any(
        x["label"] == S
        and x["type"] == "insufficiency"
        and any(x["key"] in seg for seg in answer_kept)
        for x in c["units"]
    )
    has_cite = any(ALIAS_RE.search(seg) for _, seg in kept)
    if answer_kept and not has_cite and not insufficient:
        failures.append("no_citations")
    if len(ALIAS_RE.findall(answer)) > c["max_citations"]:
        failures.append("too_many_citations")
    if c["pack_truncated"] and f"### {GAPS}" not in answer:
        failures.append("gaps_missing")
    return failures


def validate_case(c: Json) -> None:
    cid = c["case_id"]
    answer = c["answer"]
    aliases = {item["alias"] for item in c["pack"]}
    assert re.fullmatch(r"F\d{2}-[a-d]", cid), cid
    for item in c["pack"]:
        assert item["source_class"] in SOURCE_CLASSES, (cid, item["source_class"])
    types = {x["type"] for x in c["units"]}
    for x in c["units"]:
        key = x["key"]
        assert len(key) >= MIN_KEY_LEN, (cid, key)
        assert "[" not in key, (cid, key)
        assert "]" not in key, (cid, key)
        assert answer.count(key) == 1, (cid, key, answer.count(key))
        assert x["label"] in LABELS, (cid, x)
        assert x["type"] in TYPES, (cid, x)
        if x["label"] == M:
            assert x.get("correct_alias") in aliases, (cid, key)
        else:
            assert "correct_alias" not in x, (cid, key)
    cited = set(ALIAS_RE.findall(answer))
    if cited - aliases:
        assert "fabricated_citation" in types, (cid, cited - aliases)
    for sec, seg in segments(answer):
        assert any(x["key"] in seg for x in c["units"]), (cid, sec, seg)
    exp = c["expected"]
    assert set(exp["structural_failures"]) <= set(FAILURES), cid
    assert exp["ok"] == (not exp["structural_failures"]), cid
    assert sorted(exp["structural_failures"]) == sorted(derived_failures(c)), (
        cid,
        exp["structural_failures"],
        derived_failures(c),
    )
    if c["retry_answer"] is not None:
        assert not exp["ok"], (cid, "retry only simulates a second failing draft")


def validate(families: list[Json]) -> None:
    ids = [f["family_id"] for f in families]
    assert len(ids) == len(set(ids)), "duplicate family id"
    for f in families:
        assert 2 <= len(f["cases"]) <= 4, f["family_id"]
        for c in f["cases"]:
            assert c["case_id"].startswith(f["family_id"] + "-")
            validate_case(c)


# --------------------------------------------------------------------------- output


def split(families: list[Json]) -> tuple[list[Json], list[Json]]:
    ids = sorted(f["family_id"] for f in families)
    random.Random(SEED).shuffle(ids)  # noqa: S311 - reproducible split, not crypto
    n_dev = round(len(ids) * DEV_FRACTION)
    dev_ids = set(ids[:n_dev])
    dev = [f for f in families if f["family_id"] in dev_ids]
    holdout = [f for f in families if f["family_id"] not in dev_ids]
    return dev, holdout


def dump(obj: Json) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def stats(families: list[Json]) -> Json:
    cases = [c for f in families for c in f["cases"]]
    units = [x for c in cases for x in c["units"]]
    return {
        "families": len(families),
        "cases": len(cases),
        "units": len(units),
        "labels": Counter(x["label"] for x in units),
        "types": Counter(x["type"] for x in units),
        "ok_false": sum(1 for c in cases if not c["expected"]["ok"]),
        "conflict_cases": sum(1 for c in cases if c["expected"]["conflict_present"]),
        "failures": Counter(fl for c in cases for fl in c["expected"]["structural_failures"]),
    }


def readme(dev: list[Json], holdout: list[Json], holdout_sha: str) -> str:
    sd, sh = stats(dev), stats(holdout)
    type_rows = "\n".join(f"| `{t}` | {sd['types'][t]} | {sh['types'][t]} |" for t in TYPES)
    label_rows = "\n".join(f"| {lb} | {sd['labels'][lb]} | {sh['labels'][lb]} |" for lb in LABELS)
    fail_rows = "\n".join(
        f"| `{fl}` | {sd['failures'][fl]} | {sh['failures'][fl]} |" for fl in FAILURES
    )
    return f"""# verifier-v1: synthetic citation-verifier evaluation set

Generated by `scripts/build_verifier_v1.py` (do not edit the JSON by hand; edit the script and
re-run). Every pack, question and answer is hand-written and fictional. Nothing is derived from
the corpus, the fact ledger or any recorded baseline run.

## Purpose

Measure a deterministic citation verifier claim by claim: does it keep supported claims, drop
unsupported or miscited ones, flag conflicts only when they are real, and make the right
accept/regenerate decision on the whole answer. Gold labels encode the semantic truth of each
claim under the policy below, not the behaviour of any implementation.

## Split and usage

Cases are grouped into families (one evidence scenario plus 2-4 answer variants). Families,
never cases, are split {round(DEV_FRACTION * 100)}/{round((1 - DEV_FRACTION) * 100)} by shuffling
the sorted family ids with `random.Random({SEED})`.

- **dev** ({sd["families"]} families): {", ".join(f["family_id"] for f in dev)}
- **holdout** ({sh["families"]} families): {", ".join(f["family_id"] for f in holdout)}

**Holdout is used once, for the final measurement only.** Do not inspect its cases while
tuning. `holdout.json` SHA-256: `{holdout_sha}`

## Counts

| | dev | holdout |
|---|---|---|
| families | {sd["families"]} | {sh["families"]} |
| cases | {sd["cases"]} | {sh["cases"]} |
| units | {sd["units"]} | {sh["units"]} |
| cases expected `ok: false` | {sd["ok_false"]} | {sh["ok_false"]} |
| cases with `conflict_present` | {sd["conflict_cases"]} | {sh["conflict_cases"]} |

| label | dev | holdout |
|---|---|---|
{label_rows}

| structural failure | dev | holdout |
|---|---|---|
{fail_rows}

| unit type | dev | holdout |
|---|---|---|
{type_rows}

## Schema

`dev.json` / `holdout.json`:
`{{"version", "split", "seed", "families": [{{"family_id", "scenario", "cases": [CASE]}}]}}`

CASE fields:

- `case_id` (`F01-a`), `case_types` (sorted unit types, plus extras), `question`
- `pack_truncated`: when true, the contract requires a `### {GAPS}` section
- `max_citations`: citation cap (20 unless the case tests the cap)
- `pack`: `alias`, `source_title`, `source_class`, `locator_label`, `heading_path`, `text`
  (what `render_pack` shows the model)
- `answer`: raw model-style markdown; `retry_answer`: null, or a second draft that also fails
  (simulates fallback after a rejected regeneration)
- `units`: `key` (a substring of exactly one claim span, occurring exactly once in `answer`,
  no brackets), `label` (`supported` / `unsupported` / `miscited`), `type`, `note`, and
  `correct_alias` for miscited units. Multi-clause sentences have one unit per clause. Every
  content sentence or bullet carries at least one unit; headings do not.
- `expected`: `ok`, `structural_failures`, `conflict_present`

## Gold labelling policy

**supported**: backed by the text of the cited item(s), or by metadata visibly rendered for a
cited item (`source_title`, `locator_label`, `heading_path`). Temporal qualifiers (years,
quarters, FY labels, month-year, ISO dates or weeks, edition labels) are supported when they
appear anywhere in the visible pack or the question. Valid unit conversions of a cited figure
(million to billion, litre to ml, spelled-out to digits, a decimal shown as a percent only when
the evidence calls it a share or proportion). True insufficiency statements. `[inference]`
sentences with no new numbers. Uncited Answer sentences that restate pack facts without numbers.

**unsupported**: figure absent from the cited evidence; wrong scale; percent versus absolute or
percent versus percentage points; currency mismatch; computed values (sums, differences,
growth rates, ratios, shares of totals) even when arithmetically right; invalid conversions;
fabricated aliases on claims whose content is not in the pack; years, dates or edition labels
appearing nowhere in pack or question; wrong locators (slide or page numbers) or wrong roles;
uncited Key findings bullets; uncited Answer sentences carrying numbers (including a sentence
whose only marker is a foreign `[[...]]` handle); `This`/`These` sentences whose antecedent is
unsupported (`dangling_reference`).

**miscited**: the claim's figure is stated exactly in exactly one other pack item
(`correct_alias`) but the answer cites a different item, or an alias that is not in the pack.

## Structural expectations

`ok` is true when, after removing every unit not labelled supported (clause-level), the Answer
section still holds a supported sentence, there is at least one citation left or an explicit
insufficiency statement in Answer, the raw answer has at most `max_citations` `[E#]`
occurrences, the Answer has at most {MAX_ANSWER_SENTENCES} sentences, and a Gaps section exists
when `pack_truncated`. Failure names: {", ".join(f"`{fl}`" for fl in FAILURES)}. In every
citation-cap case all units are supported, so the raw and post-removal citation counts agree.
`conflict_present` is true only when two items genuinely disagree on the same metric or one
explicitly supersedes or restates another; three families contain similar-looking numbers with
no conflict, to measure false conflict triggers.
"""


def main() -> None:
    families = [build() for build in FAMILY_BUILDERS]
    validate(families)
    dev, holdout = split(families)
    for fid_set in (dev, holdout):
        assert fid_set, "empty split"
    payloads = {
        "dev": {"version": VERSION, "split": "dev", "seed": SEED, "families": dev},
        "holdout": {"version": VERSION, "split": "holdout", "seed": SEED, "families": holdout},
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    blobs = {name: dump(p) for name, p in payloads.items()}
    for name, blob in blobs.items():
        (OUT_DIR / f"{name}.json").write_bytes(blob)
    holdout_sha = hashlib.sha256(blobs["holdout"]).hexdigest()
    (OUT_DIR / "README.md").write_text(readme(dev, holdout, holdout_sha), encoding="utf-8")
    for name, fams in (("dev", dev), ("holdout", holdout)):
        st = stats(fams)
        print(
            name,
            st["families"],
            "families",
            st["cases"],
            "cases",
            st["units"],
            "units",
            dict(st["labels"]),
        )
        missing = [t for t in TYPES if not st["types"][t]]
        if missing:
            print(f"  WARNING {name} lacks unit types: {missing}")
    print("holdout sha256", holdout_sha)


if __name__ == "__main__":
    main()
