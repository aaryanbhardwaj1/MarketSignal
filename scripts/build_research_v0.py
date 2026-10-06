"""Build eval/datasets/research-v0 (Phase 4 research-mode evaluation: standard vs research agent).

Deterministic and reproducible. Every item is hand written for this dataset (no question is
copied from retrieval-v0 or grounded-v0); facts come from the fixed synthetic corpus and its
fact ledger, so every gold fact names its ledger ``fact_id``.

Gold handles per fact = the parent that holds the planted anchor (located in the seeded DB with
``evaluation.gold.locate`` and cross-checked against retrieval-v0 ``frozen.json``) plus reviewed
alternates: retrieval-v0's dual-judged ``also_satisfied_by`` and the restatements listed in
``ALTERNATES`` below (single-reviewer, each with a probe string that must still occur in the
parent). Coverage in the grounded harness is any-of per fact, so missing restatements would
under-credit; extra non-stating parents would over-credit - hence the probes.

Split: union-find over items sharing a fact, a ledger-related fact (contradiction, superseded,
distractor pairs) or an anchor parent; whole groups go to dev (~40%) or test (~60%) by a greedy,
category-stratified pass in an order fixed by sha256(seed:group). Leakage: normalized-token
Jaccard (all tokens, and content tokens without stopwords) against every retrieval-v0 and
grounded-v0 question; any item above 0.6 fails the build.

    python3 scripts/build_research_v0.py                    # build items.json + README.md
    python3 scripts/build_research_v0.py --check            # rebuild in memory, diff vs files
    uv --directory backend run python ../scripts/build_research_v0.py --verify-db
                                                            # anchors/handles against the DB
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "eval" / "datasets" / "research-v0"
ITEMS_OUT = OUT_DIR / "items.json"
README_OUT = OUT_DIR / "README.md"
LEDGER = ROOT / "seed_data" / "fact_ledger.json"
MANIFEST = ROOT / "seed_data" / "generated" / "manifest.json"
RETRIEVAL_V0 = ROOT / "eval" / "datasets" / "retrieval-v0" / "frozen.json"
GROUNDED_V0 = ROOT / "eval" / "datasets" / "grounded-v0" / "items.json"

DATASET_VERSION = "research-v0"
SPLIT_SEED = "research-v0"
DEV_FRACTION = 0.40
JACCARD_REJECT = 0.60

# Parent holding each used fact's planted anchor (gold.locate against the seeded DB; checked
# against frozen.json where the fact is there, and re-located by --verify-db).
ANCHORS: dict[str, str] = {
    "NS-001": "NORTHSTAR/BRAND-STRATEGY@v1:P1.B2",
    "NS-002": "NORTHSTAR/BRAND-STRATEGY@v1:P1.B2",
    "NS-003": "NORTHSTAR/BRAND-STRATEGY@v1:P1.B2",
    "NS-004": "NORTHSTAR/BRAND-STRATEGY@v1:P4.B2",
    "NS-005": "NORTHSTAR/BRAND-STRATEGY@v1:P1.B2",
    "NS-006": "NORTHSTAR/BRAND-STRATEGY@v1:P3.B1",
    "NS-007": "NORTHSTAR/BRAND-STRATEGY@v1:P3.B2",
    "NS-D10": "NORTHSTAR/BRAND-STRATEGY@v1:P4.B2",
    "NS-010": "NORTHSTAR/SUPPORT-THEMES@v1:P2.B1",
    "NS-011": "NORTHSTAR/SUPPORT-THEMES@v1:P2.B3",
    "NS-012": "NORTHSTAR/SUPPORT-THEMES@v1:P2.B2",
    "NS-020": "NORTHSTAR/KINETIC-AR@v1:P2.B2",
    "NS-021": "NORTHSTAR/KINETIC-AR@v1:P3.B1",
    "NS-022": "NORTHSTAR/KINETIC-AR@v1:P2.B2",
    "NS-023": "NORTHSTAR/KINETIC-AR@v1:P2.B4",
    "NS-D09": "NORTHSTAR/KINETIC-AR@v1:P2.B2",
    "NS-035": "NORTHSTAR/GENZ-TRENDS@v2:P2.B2",
    "NS-036": "NORTHSTAR/GENZ-TRENDS@v2:P2.B3",
    "NS-039": "NORTHSTAR/GENZ-TRENDS@v2:P3.B4",
    "NS-040": "NORTHSTAR/GENZ-TRENDS@v2:P4.B1",
    "NS-041": "NORTHSTAR/WTP-STUDY@v1:P2.B2",
    "NS-042": "NORTHSTAR/WTP-STUDY@v1:P2.B2",
    "NS-044": "NORTHSTAR/WTP-STUDY@v1:P1.B3",
    "NS-D01": "NORTHSTAR/WTP-STUDY@v1:P2.B3",
    "NS-050": "NORTHSTAR/PERSO-PILOT@v1:S1.B4",
    "NS-051": "NORTHSTAR/PERSO-PILOT@v1:S1.B5",
    "NS-052": "NORTHSTAR/PERSO-PILOT@v1:S1.B6",
    "NS-054": "NORTHSTAR/PERSO-PILOT@v1:S1.B7",
    "NS-D03": "NORTHSTAR/PERSO-PILOT@v1:S1.B4",
    "NS-060": "NORTHSTAR/INTERVIEWS@v1:S5.Q1",
    "NS-061": "NORTHSTAR/INTERVIEWS@v1:S9.Q1",
    "NS-062": "NORTHSTAR/INTERVIEWS@v1:S7.Q1",
    "NS-063": "NORTHSTAR/INTERVIEWS@v1:S11.Q1",
    "NS-064": "NORTHSTAR/INTERVIEWS@v1:S13.Q1",
    "NS-065": "NORTHSTAR/INTERVIEWS@v1:S4.Q2",
    "NS-066": "NORTHSTAR/INTERVIEWS@v1:S14.Q1",
    "NS-070": "NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B1",
    "NS-071": "NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B6",
    "NS-072": "NORTHSTAR/GENZ-FOCUS-GROUP@v1:S3.B6",
    "NS-080": "NORTHSTAR/Q3-REVIEW@v1:SL3",
    "NS-081": "NORTHSTAR/Q3-REVIEW@v1:SL10.N1",
    "NS-082": "NORTHSTAR/Q3-REVIEW@v1:SL8.N1",
    "NS-083": "NORTHSTAR/Q3-REVIEW@v1:SL14.N1",
    "NS-084": "NORTHSTAR/Q3-REVIEW@v1:SL12",
    "NS-085": "NORTHSTAR/Q3-REVIEW@v1:SL5",
    "NS-086": "NORTHSTAR/Q3-REVIEW@v1:SL3",
    "NS-090": "NORTHSTAR/VANTAGE-DECK@v1:SL3",
    "NS-091": "NORTHSTAR/VANTAGE-DECK@v1:SL8.N1",
    "NS-092": "NORTHSTAR/VANTAGE-DECK@v1:SL5",
    "NS-093": "NORTHSTAR/PACE-DECK@v1:SL4",
    "NS-095": "NORTHSTAR/PACE-DECK@v1:SL7",
    "NS-100": "NORTHSTAR/FY27-MEMO@v1:S1.B7",
    "NS-101": "NORTHSTAR/FY27-MEMO@v1:S1.B6",
    "NS-102": "NORTHSTAR/FY27-MEMO@v1:S1.B6",
    "NS-D04": "NORTHSTAR/FY27-MEMO@v1:S1.B4",
    "NS-103": "NORTHSTAR/VANTAGE-WEB@v1:S1.B3",
    "NS-104": "NORTHSTAR/VANTAGE-WEB@v1:S1.B4",
    "NS-105": "NORTHSTAR/KINETIC-WEB@v1:S1.B5",
    "NS-106": "NORTHSTAR/KINETIC-WEB@v1:S1.B6",
    "NS-107": "NORTHSTAR/PACE-WEB@v1:S1.B5",
    "NS-108": "NORTHSTAR/CHANNEL-SHIFT@v1:S1.B2",
    "NS-110": "NORTHSTAR/ANALYST-CALL@v1:S1.B1",
    "NS-111": "NORTHSTAR/ANALYST-CALL@v1:S1.B1",
    "NS-112": "NORTHSTAR/ANALYST-CALL@v1:S1.B2",
    "NS-120": "NORTHSTAR/PRODUCT-PERF@v1:SH2.R2",
    "NS-D05": "NORTHSTAR/PRODUCT-PERF@v1:SH2.R3",
    "NS-121": "NORTHSTAR/PRODUCT-PERF@v1:SH2.R14",
    "NS-123": "NORTHSTAR/PRODUCT-PERF@v1:SH3.R11",
    "NS-124": "NORTHSTAR/PRODUCT-PERF@v1:SH3.R35",
    "NS-125": "NORTHSTAR/FIN-SUMMARY-FY26@v1:SH1.R2",
    "NS-D06": "NORTHSTAR/FIN-SUMMARY-FY26@v1:SH1.R2",
    "NS-126": "NORTHSTAR/FIN-SUMMARY-FY26@v1:SH1.R5",
    "NS-127": "NORTHSTAR/FIN-SUMMARY-FY26@v1:SH2.R2",
    "NS-128": "NORTHSTAR/FIN-SUMMARY-FY26@v1:SH2.R2",
    "NS-129": "NORTHSTAR/CATEGORY-SIZING@v1:SH1.R5",
    "NS-D07": "NORTHSTAR/CATEGORY-SIZING@v1:SH1.R23",
    "NS-130": "NORTHSTAR/CATEGORY-SIZING@v1:SH1.R17",
    "NS-D08": "NORTHSTAR/CHANNEL-PERF@v1:R117",
    "NS-141": "NORTHSTAR/CHANNEL-PERF@v1:R114",
    "NS-144": "NORTHSTAR/SURVEY-2026@v1:R389",
    "NS-145": "NORTHSTAR/SURVEY-2026@v1:R522",
    "NS-148": "NORTHSTAR/REVIEWS@v1:R656",
    "NS-149": "NORTHSTAR/REVIEWS@v1:R234",
    "SP-C01": "SOUTHPEAK/BRAND-STRATEGY@v1:P4.B4",
    "SP-C03": "SOUTHPEAK/INTERVIEWS@v1:S6.Q1",
    "SP-C04": "SOUTHPEAK/BOARD-DECK@v1:SL6.N1",
}

# Reviewed restatements beyond retrieval-v0's also_satisfied_by: (handle, probe). A parent is
# listed only if a reader of it alone would give the same value for the same entity, metric and
# period. The probe must occur in the parent (whitespace-normalised) - checked by --verify-db.
ALTERNATES: dict[str, tuple[tuple[str, str], ...]] = {
    "NS-003": (
        ("NORTHSTAR/BRAND-STRATEGY@v1:P7.B2", "against the 30% target for FY28"),
        ("NORTHSTAR/FY27-MEMO@v1:S1.B2", "30% by the end of FY28"),
    ),
    "NS-006": (("NORTHSTAR/Q3-REVIEW@v1:SL7", "Campus Competitors | 24%"),),
    "NS-010": (("NORTHSTAR/SUPPORT-THEMES@v1:P1.B3", "Sizing and fit | 31% | 22%"),),
    "NS-020": (
        ("NORTHSTAR/BRAND-STRATEGY@v1:P5.B3", "by 64% to $148 million in fiscal 2025"),
        ("NORTHSTAR/Q3-REVIEW@v1:SL13", "$148 million revenue in fiscal 2025, up 64%"),
        ("NORTHSTAR/KINETIC-AR@v1:P2.B3", "Net revenue | $90M | $148M"),
    ),
    "NS-021": (
        ("NORTHSTAR/BRAND-STRATEGY@v1:P5.B3", "claims a return rate of 6%"),
        ("NORTHSTAR/KINETIC-AR@v1:P2.B3", "return rate on customized midsoles | n/a | 6%"),
        ("NORTHSTAR/ANALYST-CALL@v1:S1.B1", "publishes a return rate of 6%"),
    ),
    "NS-022": (
        ("NORTHSTAR/BRAND-STRATEGY@v1:P5.B3", "gross margin of 38%"),
        ("NORTHSTAR/KINETIC-AR@v1:P2.B3", "Gross margin | n/a | 38%"),
    ),
    "NS-023": (
        ("NORTHSTAR/KINETIC-AR@v1:P2.B3", "Repeat customer share | n/a | 31%"),
        ("NORTHSTAR/ANALYST-CALL@v1:S1.B1", "repeat purchase share of about 31%"),
    ),
    "NS-041": (("NORTHSTAR/WTP-STUDY@v1:P3.B3", "15% | 38% | 29%"),),
    "NS-042": (("NORTHSTAR/WTP-STUDY@v1:P3.B3", "25% | 12% | 8%"),),
    "NS-D01": (("NORTHSTAR/WTP-STUDY@v1:P3.B3", "15% | 38% | 29%"),),
    "NS-050": (
        ("NORTHSTAR/FY27-MEMO@v1:S1.B3", "18% against 24%"),
        ("NORTHSTAR/PERSO-PILOT@v1:S1.B12", "90 day repeat purchase | 18% | 24% control"),
    ),
    "NS-051": (("NORTHSTAR/PERSO-PILOT@v1:S1.B12", "Premium tier uptake | 9%"),),
    "NS-065": (("NORTHSTAR/PERSO-PILOT@v1:S1.B8", "wants everyday trainers in two days"),),
    "NS-071": (("NORTHSTAR/PERSO-PILOT@v1:S1.B8", "ranked personalization behind fit guarantees"),),
    "NS-072": (("NORTHSTAR/PERSO-PILOT@v1:S1.B8", "strongest reaction as a status signal"),),
    "NS-081": (("NORTHSTAR/PERSO-PILOT@v1:S1.B12", "week six early read of 27% repeat purchase"),),
    "NS-090": (("NORTHSTAR/BRAND-STRATEGY@v1:P5.B2", "about $4.2 billion"),),
    "NS-092": (
        ("NORTHSTAR/BRAND-STRATEGY@v1:P5.B2", "sells for around $165"),
        ("NORTHSTAR/Q3-REVIEW@v1:SL13", "average selling price around $165"),
    ),
    "NS-093": (("NORTHSTAR/BRAND-STRATEGY@v1:P5.B4", "44% of its active customer file"),),
    "NS-095": (
        ("NORTHSTAR/BRAND-STRATEGY@v1:P5.B4", "doors from 640 to 1,100"),
        ("NORTHSTAR/Q3-REVIEW@v1:SL13", "doors up from 640 to 1,100"),
    ),
    "NS-105": (
        ("NORTHSTAR/Q3-REVIEW@v1:SL13", "14 to 21 day delivery"),
        ("NORTHSTAR/KINETIC-AR@v1:P3.B4", "delivery in 14 to 21 days"),
    ),
    "NS-106": (
        ("NORTHSTAR/BRAND-STRATEGY@v1:P5.B3", "custom runner at $210"),
        ("NORTHSTAR/Q3-REVIEW@v1:SL13", "custom runner at $210"),
        ("NORTHSTAR/ANALYST-CALL@v1:S1.B1", "custom runner, at around $210"),
    ),
    "NS-126": (
        ("NORTHSTAR/BRAND-STRATEGY@v1:P1.B2", "gross margin is tracking at 47.2%"),
        ("NORTHSTAR/BRAND-STRATEGY@v1:P2.B1", "Gross margin of 47.2%"),
        ("NORTHSTAR/Q3-REVIEW@v1:SL3", "$612.0 million with gross margin of 47.2%"),
    ),
    "NS-128": (
        ("NORTHSTAR/BRAND-STRATEGY@v1:P2.B1", "an increase of 13.8%"),
        ("NORTHSTAR/Q3-REVIEW@v1:SL3", "projected to grow 13.8% in FY26"),
    ),
    "NS-D03": (("NORTHSTAR/PERSO-PILOT@v1:S1.B12", "60 day repeat purchase | 14%"),),
    "NS-D06": (
        ("NORTHSTAR/BRAND-STRATEGY@v1:P1.B2", "$571.0 million in FY25"),
        ("NORTHSTAR/BRAND-STRATEGY@v1:P1.B3", "FY25 net revenue closed at $571.0 million"),
    ),
    "NS-D09": (("NORTHSTAR/KINETIC-AR@v1:P2.B3", "Net revenue | $90M"),),
}

# Per-item handle overrides: (item_id, fact_id) -> handles, when the question asks for a part of
# the fact that only some of its parents state.
HANDLE_OVERRIDES: dict[tuple[str, str], tuple[str, ...]] = {
    # Rescan fee ($35) is only on the Kinetic Lab page; the restatements give only the $210 price.
    ("R-SC-11", "NS-106"): ("NORTHSTAR/KINETIC-WEB@v1:S1.B6",),
}

NS, SP = "NORTHSTAR", "SOUTHPEAK"
R, S = "research", "standard"

# (id, workspace, category, question, expect, fact_ids, router_expectation, notes)
# fmt: off
Spec = tuple[str, str, str, str, str, tuple[str, ...], str, str]

MULTI_CLASS: list[Spec] = [
    (
        "R-MC-01", NS, "multi_class",
        "How far behind its rivals is Northstar with Gen Z? Give Northstar's aided awareness "
        "among Gen Z, Vantage Athletic's FY2025 revenue scale, and the share of Pace & Co.'s "
        "active customers who are Gen Z.",
        "answer", ("NS-002", "NS-090", "NS-093"), R,
        "Internal brand strategy + two competitor decks; three separate entities, so one fused "
        "query rarely surfaces all three parents (the brand-strategy competitor summaries help).",
    ),
    (
        "R-MC-02", NS, "multi_class",
        "Quantify Northstar's fit problem from three angles: the share of under-28 support "
        "contacts in Q3 about sizing and fit, the share of Gen Z survey respondents who call fit "
        "inconsistency their top frustration, and the share of Switchback Trail's Q3 2026 "
        "returns put down to running small.",
        "answer", ("NS-010", "NS-004", "NS-124"), R,
        "Customer support report + internal strategy prose + an internal returns spreadsheet "
        "row; the row only matches on its record text, so a sub-query per angle is needed.",
    ),
    (
        "R-MC-03", NS, "multi_class",
        "Size up the social-commerce opportunity: what share of Gen Z athletic footwear purchases "
        "now happen on social platforms according to the latest trend panel, how fast did "
        "Northstar's Social Shop grow quarter over quarter in Q2 FY26, and how big is the FY27 "
        "Gen Z marketing budget the strategy team proposes?",
        "answer", ("NS-035", "NS-085", "NS-100"), R,
        "Market report (2026 edition, superseding 2025) + Q3 deck + FY27 memo. The superseded "
        "2025 figure is inactive, so a single search tends to return only the social-commerce "
        "material.",
    ),
    (
        "R-MC-04", NS, "multi_class",
        "The panel analyst argues that an exchange promise would help Northstar more than a "
        "longer refund window. How much more often do Gen Z shoppers return athletic apparel "
        "than shoppers over 35 according to the panel, and what exchange guarantee does the FY27 "
        "memo propose, and for when?",
        "answer", ("NS-111", "NS-101"), R,
        "Customer-class analyst notes + internal FY27 memo; the two halves share almost no "
        "vocabulary ('return at 1.5 times' vs 'Fit Promise, free exchange guarantee').",
    ),
    (
        "R-MC-05", NS, "multi_class",
        "Put Northstar's numbers in market context: its FY26 latest-estimate net revenue, the "
        "growth expected from Gen Z revenue in FY26, and the size of the 2026 US Gen Z athletic "
        "footwear market.",
        "answer", ("NS-125", "NS-128", "NS-129"), R,
        "Financial workbook rows + market sizing row (a millennial row NS-D07 is a near "
        "distractor); spreadsheets need targeted lookups.",
    ),
    (
        "R-MC-06", NS, "multi_class",
        "How much do young shoppers care about fast delivery, and is Northstar's personalization "
        "offer creating delivery friction? Give the trend panel's share of Gen Z rating "
        "three-day delivery essential and how much more likely personalized orders were to "
        "trigger order-status tickets.",
        "answer", ("NS-039", "NS-011"), R,
        "Market trend report + customer support report; the support fact is phrased as "
        "'where is my order ticket', not 'delivery friction'.",
    ),
]

IDENTIFIER_THEN_SEMANTIC: list[Spec] = [
    (
        "R-IT-01", NS, "identifier_then_semantic",
        "What did survey respondent R0521 complain about, and how many Knit Runner 2 returns in "
        "Q3 2026 were logged for that same kind of failure?",
        "answer", ("NS-145", "NS-123"), R,
        "Exact respondent id first (keyword lane), then a semantic hop from 'knit split' to the "
        "returns row whose reason is 'Durability - upper wear'.",
    ),
    (
        "R-IT-02", NS, "identifier_then_semantic",
        "Review RV-00233 is a five-star review. Which product is it for, and how many units of "
        "that product has Northstar sold so far in FY26?",
        "answer", ("NS-149", "NS-121"), R,
        "The product (Studio Contour Legging) is only known after the review is opened; the "
        "unit count needs a second lookup on the SKU sheet.",
    ),
    (
        "R-IT-03", NS, "identifier_then_semantic",
        "What did the customer who wrote review RV-00655 complain about, and what did the "
        "personalization pilot find about average lead time and its effect on reordering?",
        "answer", ("NS-148", "NS-054"), R,
        "Review id lookup, then the pilot results document; the pilot wording ('lead time', "
        "'reason not to order again') differs from the review ('took 13 days').",
    ),
    (
        "R-IT-04", NS, "identifier_then_semantic",
        "What average order value does record CP-2026-09-APP-GENZ show, and how does it compare "
        "with the average order value of Northstar's largest Gen Z segment, and how large is "
        "that segment?",
        "answer", ("NS-141", "NS-007"), R,
        "Channel CSV row by record id, then the segment narrative ($94, Studio Social).",
    ),
    (
        "R-IT-05", NS, "identifier_then_semantic",
        "Survey respondent R0388 named a premium they would accept. What was it and what "
        "condition did they attach, and how does stated acceptance in the external "
        "willingness-to-pay study change at a 25% premium?",
        "answer", ("NS-144", "NS-042"), R,
        "Respondent id lookup, then the WTP study (prose or the acceptance-by-premium table).",
    ),
    (
        "R-IT-06", NS, "identifier_then_semantic",
        "SKU NS-KR2: what is its FY26 return rate, and what were customers contacting support "
        "about for that shoe in Q3, and in what volume?",
        "answer", ("NS-120", "NS-012"), R,
        "SKU row (NS-KR1 row is a near distractor), then the support themes report, which names "
        "the product (Knit Runner 2) rather than the SKU code.",
    ),
]

CUSTOMER_COMPETITOR: list[Spec] = [
    (
        "R-CC-01", NS, "customer_competitor",
        "An interviewee put a number on how much extra they would pay for a shoe built from a "
        "scan of their foot. How does that compare with what Kinetic Lab charges for its custom "
        "runner?",
        "answer", ("NS-061", "NS-106"), R,
        "Interview quote + competitor price (also restated in strategy summaries).",
    ),
    (
        "R-CC-02", NS, "customer_competitor",
        "One interviewee wants everyday trainers delivered within two days. How far is the "
        "leading made-to-order competitor from meeting that expectation?",
        "answer", ("NS-065", "NS-105"), R,
        "The competitor is not named; the agent must resolve 'made-to-order competitor' to "
        "Kinetic Lab and then find its 14 to 21 day window.",
    ),
    (
        "R-CC-03", NS, "customer_competitor",
        "One interviewee says their last three pairs came from a run club group chat rather "
        "than ads. How does Vantage Athletic's stated mission and homepage emphasis compare with "
        "that discovery route?",
        "answer", ("NS-064", "NS-103"), R,
        "Interview quote + competitor web positioning page; no shared vocabulary.",
    ),
    (
        "R-CC-04", NS, "customer_competitor",
        "How common was cart abandonment over mismatched size charts among the Gen Z "
        "focus-group participants, and how widely has Vantage rolled out in-store gait scanning "
        "as its answer to fit?",
        "answer", ("NS-070", "NS-091"), R,
        "Focus group note + competitor investor-deck speaker notes.",
    ),
    (
        "R-CC-05", NS, "customer_competitor",
        "What kind of personalization got the Gen Z focus-group participants most excited, and "
        "how does Vantage Athletic's personalization offer compare with that?",
        "answer", ("NS-072", "NS-104"), R,
        "Focus group (status-signal framing) + competitor web page (12 preset colorways).",
    ),
]

CUSTOMER_INTERNAL: list[Spec] = [
    (
        "R-CI-01", NS, "customer_internal",
        "An interviewee's Knit Runners frayed after about two months of walking to class. What "
        "did Northstar estimate that durability issue cost in Q2 returns and replacements?",
        "answer", ("NS-062", "NS-082"), R,
        "Interview quote + Q3 review speaker notes.",
    ),
    (
        "R-CI-02", NS, "customer_internal",
        "What made a shopper who loved the custom colorway tool give up on ordering, and what "
        "did Northstar leadership decide about personalization at the Q3 strategy review?",
        "answer", ("NS-066", "NS-083"), R,
        "Interview quote + leadership decision in deck speaker notes.",
    ),
    (
        "R-CI-03", NS, "customer_internal",
        "One interviewee wears different sizes across Northstar's joggers, hoodies and shoe "
        "lines. What remedy does next year's plan propose for that, and in which quarter would "
        "it launch?",
        "answer", ("NS-060", "NS-101"), R,
        "Interview quote + FY27 memo recommendation (Fit Promise, Q1 FY27).",
    ),
    (
        "R-CI-04", NS, "customer_internal",
        "What does the external panel analyst expect personalization's share of US athletic "
        "footwear units to be through 2028, and is the FY27 memo's stance on personalization "
        "consistent with that view?",
        "answer", ("NS-112", "NS-102"), R,
        "Analyst call notes (customer class) + FY27 memo recommendation.",
    ),
    (
        "R-CI-05", NS, "customer_internal",
        "Customers say they discover shoes through run clubs and group chats rather than ads. "
        "How large is the proposed FY27 Gen Z marketing budget, and how much of it would move "
        "toward creator and community programmes?",
        "answer", ("NS-064", "NS-100"), R,
        "Interview quote + FY27 memo budget ($24M, 40% to creator and community).",
    ),
]

CONFLICT_SEARCH: list[Spec] = [
    (
        "R-CF-01", NS, "conflict_search",
        "Northstar is sizing a paid fit-personalization tier at a 15% markup. What uptake should "
        "it plan for: the stated acceptance in the external study, or the take-up actually "
        "observed when pilot shoppers were offered that tier?",
        "conflict", ("NS-041", "NS-051"), R,
        "Ledger contradiction C1 (stated 38% vs revealed 9%). A first search on the external "
        "study surfaces only the stated side; the pilot side needs a second search.",
    ),
    (
        "R-CF-02", NS, "conflict_search",
        "The Q3 strategy review slides cite an encouraging early repeat-purchase number for "
        "personalized buyers. Does the pilot's final readout confirm it?",
        "conflict", ("NS-081", "NS-050"), R,
        "Ledger contradiction C2 (week-six 27% vs final 90-day 18% below 24% control); the "
        "question anchors on the deck, the final readout lives in the pilot report.",
    ),
    (
        "R-CF-03", NS, "conflict_search",
        "The board tracks Gen Z share of revenue against a 30% FY28 target. What is the FY25 "
        "starting point, and do the brand team and finance agree on it?",
        "conflict", ("NS-001", "NS-127", "NS-003"), R,
        "Ledger contradiction C3 (21% loyalty definition vs 19.4% finance definition). The "
        "finance side is a spreadsheet row that prose-oriented queries miss.",
    ),
    (
        "R-CF-04", NS, "conflict_search",
        "Kinetic Lab's annual report touts a low return rate on customized midsoles. Is there "
        "independent evidence on that figure, and how does either number compare with returns "
        "on Northstar's own personalized pilot items?",
        "conflict", ("NS-021", "NS-110", "NS-052"), R,
        "Ledger contradiction C4 (claimed 6% vs analyst ~15% with remakes) plus the pilot's 11% "
        "vs 16%; three documents, two of which use different vocabulary for returns.",
    ),
    (
        "R-CF-05", NS, "conflict_search",
        "Should Northstar lead its Gen Z messaging with personalization? Check what framing "
        "excited the focus group most, and where personalization landed when participants "
        "allocated a fixed budget of points across benefits.",
        "conflict", ("NS-072", "NS-071"), R,
        "Ledger contradiction C5 (status-signal excitement vs ranked behind fit guarantee, "
        "delivery, materials). Both sides share one parent, so a careful single pass can find "
        "both; the conflict still has to be surfaced.",
    ),
]

FIRST_PASS_INSUFFICIENT: list[Spec] = [
    (
        "R-FP-01", NS, "first_pass_insufficient",
        "How quickly is Pace & Co. expanding its physical presence through partner retailers, "
        "and how affordable is its range overall?",
        "answer", ("NS-095", "NS-107"), R,
        "Why the first pass misses: the deck states expansion as 'store in store doors' and the "
        "affordability fact sits in the returns paragraph of the Pace web page ('70% of its "
        "range is priced under $50'); a single expansion-focused query rarely retrieves the "
        "returns paragraph.",
    ),
    (
        "R-FP-02", NS, "first_pass_insufficient",
        "How healthy is the made-to-order shoe start-up commercially: how fast are its sales "
        "growing, how profitable is it, and how loyal are its customers?",
        "answer", ("NS-020", "NS-022", "NS-023"), R,
        "Why the first pass misses: the company is unnamed (Kinetic Lab must be resolved "
        "first), and 'loyal' maps to 'order a second pair within twelve months', a different "
        "annual-report paragraph from revenue and margin.",
    ),
    (
        "R-FP-03", NS, "first_pass_insufficient",
        "How big is the US custom-sneaker market among young consumers in 2026, and what is the "
        "most recent estimate of the whole Gen Z athletic apparel market?",
        "answer", ("NS-130", "NS-036"), R,
        "Why the first pass misses: 'custom sneaker' must map to the sizing row 'Personalized "
        "athletic footwear' (US-GENZ-PFW-2026), which prose queries about personalization "
        "outrank; the apparel figure is a 2026 restatement ('we restate the 2025 ... market').",
    ),
    (
        "R-FP-04", NS, "first_pass_insufficient",
        "How many people did the external willingness-to-pay study survey, and how did the "
        "older millennial respondents compare on paying a 15% premium for fit-personalized "
        "shoes?",
        "answer", ("NS-044", "NS-D01"), R,
        "Why the first pass misses: a premium-focused query returns the results section; the "
        "sample size is in the methods paragraph ('surveyed 2,400 US consumers'), which shares "
        "no premium vocabulary.",
    ),
    (
        "R-FP-05", NS, "first_pass_insufficient",
        "How much of Gen Z athletic spending now flows through third-party platforms instead of "
        "brand-owned sites, and how far do young shoppers trust fellow customers over "
        "advertising?",
        "answer", ("NS-108", "NS-040"), R,
        "Why the first pass misses: 'third-party platforms' is stated as 'marketplace and "
        "social commerce' (channel note), and trust is phrased as 'peer reviews and creator try "
        "on videos' in a different report.",
    ),
    (
        "R-FP-06", SP, "first_pass_insufficient",
        "Which Southpeak product drew a comfort complaint in the customer interviews, and what "
        "sales goal is set for the jacket meant to showcase the brand refresh?",
        "answer", ("SP-C03", "SP-C01"), R,
        "Why the first pass misses: Southpeak's comfort and fit vocabulary is dominated by boot "
        "sizing material; the pack complaint is phrased 'straps dug into my shoulders', and the "
        "jacket goal names the Ridgeline shell, not 'showcase jacket'.",
    ),
]

REFORMULATION: list[Spec] = [
    (
        "R-RF-01", NS, "reformulation",
        "What CTR uplift did bespoke-colour email creative achieve against business-as-usual "
        "sends?",
        "answer", ("NS-084",), S,
        "Jargon/synonyms: 'bespoke-colour' = custom colorway, 'business-as-usual sends' = "
        "standard creative. Single fact: research helps only if the first pass misses.",
    ),
    (
        "R-RF-02", NS, "reformulation",
        "What GM% does the FY26 LE carry, and what was the Q2 top line?",
        "answer", ("NS-126", "NS-080"), R,
        "Finance shorthand: GM% = gross margin, LE = latest estimate, top line = net revenue.",
    ),
    (
        "R-RF-03", NS, "reformulation",
        "Which shopper personas does Northstar's Gen Z segmentation define?",
        "answer", ("NS-006",), S,
        "'Personas' = segments.",
    ),
    (
        "R-RF-04", NS, "reformulation",
        "What does a Vantage performance running shoe typically go for at the till these days?",
        "answer", ("NS-092",), S,
        "Colloquial price wording vs 'average selling price' / 'ASP'.",
    ),
    (
        "R-RF-05", NS, "reformulation",
        "How do younger shoppers react to eco-friendly marketing that lacks specifics, according "
        "to the one-on-one conversations?",
        "answer", ("NS-063",), S,
        "'Eco-friendly marketing' = green claims; 'one-on-one conversations' = interviews.",
    ),
    (
        "R-RF-06", NS, "reformulation",
        "What was Northstar's company-wide promoter score across all age groups in Q2?",
        "answer", ("NS-D04",), S,
        "'Promoter score' = NPS; the Gen Z NPS (22) is a near distractor for the all-customer "
        "figure (31).",
    ),
]

INSUFFICIENT_STOP: list[Spec] = [
    (
        "R-IS-01", NS, "insufficient_stop",
        "How many patents does Kinetic Lab hold on its phone foot-scanning technology?",
        "insufficient", (), S,
        "No patent or IP information exists in the corpus; the scan process is described, which "
        "invites over-searching. Correct behaviour: stop and state insufficiency.",
    ),
    (
        "R-IS-02", NS, "insufficient_stop",
        "What greenhouse-gas emissions per pair does Northstar report for its running footwear, "
        "and how does that compare with Vantage Athletic's racers?",
        "insufficient", (), R,
        "No emissions data anywhere (sustainability content is about claims and transparency). "
        "Comparison phrasing may route to research; the agent should stop rather than loop.",
    ),
    (
        "R-IS-03", NS, "insufficient_stop",
        "What inventory turnover did Northstar achieve in FY26, and which distribution centres "
        "hold the most stock?",
        "insufficient", (), R,
        "Neither inventory turnover nor distribution centres appear in the corpus.",
    ),
    (
        "R-IS-04", NS, "insufficient_stop",
        "How much debt does Northstar carry on its balance sheet?",
        "insufficient", (), S,
        "The financial summary covers P&L lines and segment revenue only; no balance sheet.",
    ),
    (
        "R-IS-05", SP, "insufficient_stop",
        "What royalty does Southpeak pay to license the waterproof membrane in its shell "
        "jackets?",
        "insufficient", (), S,
        "Shell jackets (Ridgeline) exist in the Southpeak corpus, membranes and licensing do "
        "not: an adjacent-topic trap.",
    ),
    (
        "R-IS-06", NS, "insufficient_stop",
        "How did Northstar's share price react after the Q3 strategy review?",
        "insufficient", (), S,
        "The Q3 review exists but no share-price data does; the agent should not substitute "
        "revenue or NPS figures.",
    ),
]

SIMPLE_CONTROL: list[Spec] = [
    (
        "R-SC-01", NS, "simple_control",
        "How much revenue did Northstar actually book for the FY25 year, per the financial "
        "summary?",
        "answer", ("NS-D06",), S, "Single financial row / strategy sentence.",
    ),
    (
        "R-SC-02", NS, "simple_control",
        "What net revenue did Kinetic Lab book in fiscal 2024?",
        "answer", ("NS-D09",), S, "Single annual-report sentence or table.",
    ),
    (
        "R-SC-03", NS, "simple_control",
        "What value does the category sizing workbook put on the 2026 US athletic footwear "
        "market for millennials?",
        "answer", ("NS-D07",), S, "Single sizing row (Gen Z row is the near distractor).",
    ),
    (
        "R-SC-04", NS, "simple_control",
        "What conversion rate did millennial shoppers have on the Social Shop in September "
        "2026?",
        "answer", ("NS-D08",), S, "Single channel CSV row.",
    ),
    (
        "R-SC-05", NS, "simple_control",
        "What is the FY26 return rate of the original Knit Runner, SKU NS-KR1?",
        "answer", ("NS-D05",), S, "Single SKU row by exact code.",
    ),
    (
        "R-SC-06", NS, "simple_control",
        "What was repeat purchase among personalized buyers at the pilot's 60 day checkpoint?",
        "answer", ("NS-D03",), S, "Single pilot sentence or results table.",
    ),
    (
        "R-SC-07", NS, "simple_control",
        "Among survey respondents aged 28 and older, where does fit inconsistency rank as a "
        "frustration, and at what share?",
        "answer", ("NS-D10",), S, "Single strategy sentence.",
    ),
    (
        "R-SC-08", NS, "simple_control",
        "What brand position does Northstar's 2026 brand strategy want to own with active Gen Z "
        "consumers?",
        "answer", ("NS-005",), S, "Single strategy sentence.",
    ),
    (
        "R-SC-09", SP, "simple_control",
        "How many members did Southpeak's Basecamp Rewards programme have at the close of the "
        "quarter?",
        "answer", ("SP-C04",), S, "Single board-deck speaker note.",
    ),
    (
        "R-SC-10", NS, "simple_control",
        "What net revenue did Vantage Athletic report for FY2025?",
        "answer", ("NS-090",), S, "Single investor-deck slide.",
    ),
    (
        "R-SC-11", NS, "simple_control",
        "What does Kinetic Lab charge for its custom runner, and for a rescan fitting?",
        "answer", ("NS-106",), S, "Single web-page sentence (only the anchor states the fee).",
    ),
    (
        "R-SC-12", NS, "simple_control",
        "How long is the free returns window at Pace & Co., and what share of its range is "
        "priced under $50?",
        "answer", ("NS-107",), S, "Single web-page sentence.",
    ),
]

# fmt: on

ALL_SPECS = (
    MULTI_CLASS
    + IDENTIFIER_THEN_SEMANTIC
    + CUSTOMER_COMPETITOR
    + CUSTOMER_INTERNAL
    + CONFLICT_SEARCH
    + FIRST_PASS_INSUFFICIENT
    + REFORMULATION
    + INSUFFICIENT_STOP
    + SIMPLE_CONTROL
)

PROVENANCE = {
    "conflict_search": "hand_written:ledger-contradiction",
    "insufficient_stop": "hand_written:topic-not-in-corpus",
}

_STOPWORDS_TEXT = (
    "a an and are as at be by did do does for from had has have how in is it its of on or "
    "our s so than that the their there these this to was were what when where which who why "
    "with would you your i me my we us they them"
)
STOPWORDS = frozenset(_STOPWORDS_TEXT.split())
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")


def tokens(text: str, *, content: bool) -> frozenset[str]:
    toks = _TOKEN.findall(text.lower().replace("'", ""))
    return frozenset(t for t in toks if not (content and t in STOPWORDS))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def corpus_sha256() -> str:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = sorted(
        (u["workspace_code"], u["source_code"], int(u["version"]), u["filename"], u["sha256"])
        for u in manifest["uploads"]
    )
    return sha256_bytes(canonical_json(entries).encode())


def source_classes() -> dict[tuple[str, str], str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {(u["workspace_code"], u["source_code"]): u["source_class"] for u in manifest["uploads"]}


def related_pairs(ledger: dict[str, Any]) -> list[tuple[str, str]]:
    pairs = [(c["a"], c["b"]) for c in ledger["contradictions"]]
    pairs += [(s["old"], s["new"]) for s in ledger["superseded"]]
    pairs += [(d["fact_id"], d["distractor_of"]) for d in ledger["distractors"]]
    return pairs


def frozen_handles() -> dict[str, tuple[list[str], list[str]]]:
    """fact_id -> (satisfied_by, also_satisfied_by) from retrieval-v0 frozen gold."""
    out: dict[str, tuple[list[str], list[str]]] = {}
    for item in json.loads(RETRIEVAL_V0.read_text())["items"]:
        for rf in item["required_facts"]:
            out[rf["fact_id"]] = (list(rf["satisfied_by"]), list(rf.get("also_satisfied_by", [])))
    return out


def fact_handles(fact_id: str, frozen: dict[str, tuple[list[str], list[str]]]) -> list[str]:
    anchor = ANCHORS[fact_id]
    handles = [anchor]
    if fact_id in frozen:
        sat, also = frozen[fact_id]
        if sat != [anchor]:
            raise SystemExit(f"{fact_id}: anchor {anchor} != frozen satisfied_by {sat}")
        handles += also
    handles += [h for h, _ in ALTERNATES.get(fact_id, ())]
    return list(dict.fromkeys(handles))


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def assign_splits(items: list[dict[str, Any]], pairs: list[tuple[str, str]]) -> None:
    uf = _UnionFind()
    for a, b in pairs:
        uf.union(f"fact:{a}", f"fact:{b}")
    for item in items:
        node = f"item:{item['id']}"
        uf.find(node)
        for fact in item["gold_facts"]:
            uf.union(node, f"fact:{fact['fact_id']}")
            uf.union(node, f"parent:{fact['anchor_handle']}")
    members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        members[uf.find(f"item:{item['id']}")].append(item)
    groups = {f"G-{min(i['id'] for i in m)}": m for m in members.values()}
    order = sorted(
        groups,
        key=lambda g: (-len(groups[g]), sha256_bytes(f"{SPLIT_SEED}:{g}".encode())),
    )
    totals = Counter(i["category"] for i in items)
    dev: Counter[str] = Counter()

    def cost(counts: Counter[str]) -> float:
        per_cat = sum((counts[c] - DEV_FRACTION * n) ** 2 for c, n in totals.items())
        overall = (sum(counts.values()) - DEV_FRACTION * len(items)) ** 2
        return per_cat + overall

    cats = {name: Counter(i["category"] for i in groups[name]) for name in order}
    in_dev: dict[str, bool] = {}
    for name in order:  # greedy pass, then deterministic hill-climb (single-group flips)
        in_dev[name] = cost(dev + cats[name]) < cost(dev)
        if in_dev[name]:
            dev += cats[name]
    improved = True
    while improved:
        improved = False
        for name in order:
            flipped = dev - cats[name] if in_dev[name] else dev + cats[name]
            if cost(flipped) < cost(dev) - 1e-9:
                dev, in_dev[name], improved = flipped, not in_dev[name], True
    for name in order:
        for item in groups[name]:
            item["group"] = name
            item["split"] = "dev" if in_dev[name] else "test"


def build() -> tuple[dict[str, Any], str]:
    ledger = json.loads(LEDGER.read_text())
    facts = {f["fact_id"]: f for f in ledger["facts"]}
    classes = source_classes()
    frozen = frozen_handles()
    retrieval = json.loads(RETRIEVAL_V0.read_text())["items"]
    grounded = json.loads(GROUNDED_V0.read_text())["items"]
    references = [(i["id"], i["question"], i["split"]) for i in retrieval]
    references += [(i["id"], i["question"], "grounded") for i in grounded]
    contradiction_pairs = {frozenset((c["a"], c["b"])): c["id"] for c in ledger["contradictions"]}
    items: list[dict[str, Any]] = []
    for item_id, ws, category, question, expect, fact_ids, router, notes in ALL_SPECS:
        gold = []
        for fid in fact_ids:
            fact = facts[fid]
            if fact["workspace_code"] != ws:
                raise SystemExit(f"{item_id}: {fid} is not in {ws}")
            handles = list(HANDLE_OVERRIDES.get((item_id, fid), fact_handles(fid, frozen)))
            gold.append(
                {
                    "fact_id": fid,
                    "handles": handles,
                    "anchor_handle": ANCHORS[fid],
                    "value": fact["value"],
                    "unit": fact["unit"],
                    "source_code": fact["source_code"],
                    "source_class": classes[(ws, fact["source_code"])],
                }
            )
        items.append(
            {
                "id": item_id,
                "workspace": ws,
                "category": category,
                "question": question,
                "expect": expect,
                "gold_facts": gold,
                "source_classes": [],
                "canary": None,
                "provenance": PROVENANCE.get(category, "hand_written:research-v0"),
                "origin_split": None,
                "router_expectation": router,
                "notes": notes,
                "gold_source_classes": sorted({g["source_class"] for g in gold}),
                "ledger_contradictions": sorted(
                    contradiction_pairs[frozenset((a, b))]
                    for i, a in enumerate(fact_ids)
                    for b in fact_ids[i + 1 :]
                    if frozenset((a, b)) in contradiction_pairs
                ),
            }
        )
    for item in items:
        best = {"all": (0.0, "", ""), "content": (0.0, "", "")}
        for mode in best:
            q = tokens(item["question"], content=mode == "content")
            for ref_id, ref_q, ref_split in references:
                score = jaccard(q, tokens(ref_q, content=mode == "content"))
                if score > best[mode][0]:
                    best[mode] = (score, ref_id, ref_split)
        item["leakage"] = {
            "max_jaccard_all_tokens": round(best["all"][0], 3),
            "nearest_all_tokens": f"{best['all'][1]} ({best['all'][2]})",
            "max_jaccard_content_tokens": round(best["content"][0], 3),
            "nearest_content_tokens": f"{best['content'][1]} ({best['content'][2]})",
        }
    assign_splits(items, related_pairs(ledger))
    problems = validate(items, facts, references)
    if problems:
        raise SystemExit("validation failed:\n  " + "\n  ".join(problems))
    doc = {
        "dataset_version": DATASET_VERSION,
        "description": (
            "Phase 4 research-mode evaluation: hand-written items comparing the standard "
            "single-pass path with the bounded research agent. Grounded-eval compatible schema "
            "plus router_expectation, notes, split and leakage diagnostics."
        ),
        "manifest": {
            "ledger_sha256": sha256_bytes(LEDGER.read_bytes()),
            "corpus_sha256": corpus_sha256(),
            "retrieval_v0_items_sha256": json.loads(RETRIEVAL_V0.read_text())["manifest"][
                "items_sha256"
            ],
            "grounded_v0_sha256": sha256_bytes(GROUNDED_V0.read_bytes()),
            "split_seed": SPLIT_SEED,
            "dev_fraction_target": DEV_FRACTION,
            "jaccard_reject_threshold": JACCARD_REJECT,
            "counts": summary_counts(items),
        },
        "items": items,
    }
    return doc, render_readme(doc, references)


def summary_counts(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"dev": 0, "test": 0})
    for item in items:
        by_cat[item["category"]][item["split"]] += 1
    return {
        "items": len(items),
        "dev": sum(1 for i in items if i["split"] == "dev"),
        "test": sum(1 for i in items if i["split"] == "test"),
        "groups": len({i["group"] for i in items}),
        "by_category": {k: by_cat[k] for k in sorted(by_cat)},
        "router_expectation": dict(sorted(Counter(i["router_expectation"] for i in items).items())),
        "expect": dict(sorted(Counter(i["expect"] for i in items).items())),
    }


def validate(
    items: list[dict[str, Any]],
    facts: dict[str, Any],
    references: list[tuple[str, str, str]],
) -> list[str]:
    problems: list[str] = []
    ids = [i["id"] for i in items]
    if len(ids) != len(set(ids)):
        problems.append("duplicate item ids")
    norm_q = [" ".join(sorted(tokens(i["question"], content=False))) for i in items]
    if len(norm_q) != len(set(norm_q)):
        problems.append("duplicate questions")
    ref_texts = {q.strip().lower() for _, q, _ in references}
    fact_split: dict[str, set[str]] = defaultdict(set)
    for item in items:
        iid, ws, cat = item["id"], item["workspace"], item["category"]
        prefix = {
            "multi_class": "MC",
            "identifier_then_semantic": "IT",
            "customer_competitor": "CC",
            "customer_internal": "CI",
            "conflict_search": "CF",
            "first_pass_insufficient": "FP",
            "reformulation": "RF",
            "insufficient_stop": "IS",
            "simple_control": "SC",
        }[cat]
        if not re.fullmatch(rf"R-{prefix}-\d\d", iid):
            problems.append(f"{iid}: id does not match category {cat}")
        if item["question"].strip().lower() in ref_texts:
            problems.append(f"{iid}: question copied from retrieval-v0/grounded-v0")
        lk = item["leakage"]
        if max(lk["max_jaccard_all_tokens"], lk["max_jaccard_content_tokens"]) > JACCARD_REJECT:
            problems.append(f"{iid}: leakage Jaccard above {JACCARD_REJECT}: {lk}")
        if item["router_expectation"] not in ("research", "standard"):
            problems.append(f"{iid}: bad router_expectation")
        gold = item["gold_facts"]
        fids = [g["fact_id"] for g in gold]
        if len(fids) != len(set(fids)):
            problems.append(f"{iid}: duplicate gold fact")
        for g in gold:
            fact_split[g["fact_id"]].add(item["split"])
            overridden = (iid, g["fact_id"]) in HANDLE_OVERRIDES
            if not g["handles"] or (g["anchor_handle"] not in g["handles"] and not overridden):
                problems.append(f"{iid}/{g['fact_id']}: anchor missing from handles")
            if len(g["handles"]) != len(set(g["handles"])):
                problems.append(f"{iid}/{g['fact_id']}: duplicate handles")
            for h in g["handles"]:
                if not h.startswith(f"{ws}/") or not re.fullmatch(
                    r"[A-Z0-9-]+/[A-Z0-9-]+@v\d+:[A-Z0-9.]+", h
                ):
                    problems.append(f"{iid}/{g['fact_id']}: bad or foreign handle {h}")
            fact = facts[g["fact_id"]]
            if fact["category"] == "injection":
                problems.append(f"{iid}: uses injection-carrier fact {g['fact_id']}")
            if fact.get("superseded_by"):
                problems.append(f"{iid}: uses superseded fact {g['fact_id']}")
        classes = set(item["gold_source_classes"])
        if item["expect"] == "insufficient":
            if gold:
                problems.append(f"{iid}: insufficient item with gold facts")
        elif not gold:
            problems.append(f"{iid}: answerable item without gold")
        if cat == "multi_class" and len(classes) < 2:
            problems.append(f"{iid}: multi_class needs >= 2 source classes")
        if cat == "customer_competitor" and not {"customer", "competitor"} <= classes:
            problems.append(f"{iid}: needs customer + competitor evidence")
        if cat == "customer_internal" and not (
            "customer" in classes and classes & {"internal", "financial"}
        ):
            problems.append(f"{iid}: needs customer + internal evidence")
        if cat == "conflict_search" and (
            item["expect"] != "conflict" or not item["ledger_contradictions"]
        ):
            problems.append(f"{iid}: conflict item must contain a ledger contradiction pair")
        if cat == "simple_control" and (len(gold) != 1 or item["router_expectation"] != "standard"):
            problems.append(f"{iid}: simple control must be one fact, routed standard")
    for fid, splits in fact_split.items():
        if len(splits) > 1:
            problems.append(f"{fid}: fact appears in both dev and test")
    return problems


def render_readme(doc: dict[str, Any], references: list[tuple[str, str, str]]) -> str:
    items = doc["items"]
    counts = doc["manifest"]["counts"]
    split_of = {i["id"]: i["split"] for i in items}
    alt_cross = sorted(
        {
            h
            for i in items
            for g in i["gold_facts"]
            for h in g["handles"]
            if any(
                h in g2["handles"] and split_of[j["id"]] != i["split"]
                for j in items
                for g2 in j["gold_facts"]
            )
        }
    )
    lines = [
        "# research-v0",
        "",
        "Phase 4 research-mode evaluation set: compares the standard single-pass path with the "
        "bounded research agent (plan §19, ADR-0007, ADR-0015). Built by "
        "`scripts/build_research_v0.py` (deterministic; `--check` diffs a rebuild against these "
        "files, `--verify-db` checks every handle against the seeded database). Do not edit "
        "`items.json` by hand.",
        "",
        "All data is fictional (synthetic seed corpus). Questions and ids are new; facts come "
        "from `seed_data/fact_ledger.json` and every gold fact names its ledger `fact_id`.",
        "",
        "## Schema",
        "",
        "Compatible with the grounded-eval harness (`id, workspace, category, question, expect, "
        "gold_facts[{fact_id, handles, value, unit}], source_classes, canary, provenance, "
        "origin_split`). Extra fields: `router_expectation` (`research` | `standard`: what a "
        "reasonable router should pick from the question alone), `notes` (why multi-step search "
        "should or should not help; for `first_pass_insufficient` why the obvious first query "
        "misses part of the gold), `split`, `group`, `gold_source_classes`, "
        "`ledger_contradictions`, `leakage`, and per gold fact `anchor_handle`, `source_code`, "
        "`source_class`. `source_classes` is always `[]` (no filters). `handles` is any-of per "
        "fact; every listed fact is required.",
        "",
        "## Gold",
        "",
        "- `anchor_handle`: the active parent containing the fact's planted anchor, located with "
        "`evaluation.gold.locate` in the seeded DB; equal to retrieval-v0 `satisfied_by` for "
        "every fact that retrieval-v0 also uses.",
        "- Alternates: retrieval-v0's dual-judged `also_satisfied_by`, plus restatements "
        "reviewed for this set (`ALTERNATES` in the builder, single reviewer, each with a probe "
        "string that must still occur in the parent). Candidates were found by value and "
        "surface-form search over all active parents; candidates that state only part of a fact "
        "or a different period/definition were rejected (e.g. 'a little under 20%' for NS-127, "
        "NPS mentions without the Q2 period).",
        "- Per-item override: `R-SC-11` also asks for the rescan fee, which only the Kinetic "
        "Lab page states, so its gold is the anchor alone.",
        "- The grounded harness checks each numeric ledger `value` appears in the answer, so "
        "every question asks for the ledger value of each of its facts.",
        "- No superseded, injection-carrier or canary-output facts are used.",
        "",
        "## Categories and split",
        "",
        "| category | dev | test | total |",
        "|---|---|---|---|",
    ]
    for cat, c in counts["by_category"].items():
        lines.append(f"| {cat} | {c['dev']} | {c['test']} | {c['dev'] + c['test']} |")
    lines += [
        f"| **all** | {counts['dev']} | {counts['test']} | {counts['items']} |",
        "",
        f"Router expectation: {counts['router_expectation']}. Expect: {counts['expect']}.",
        "",
        f"Split: {counts['groups']} leakage groups. Items are union-found when they share a gold "
        "fact, a ledger-related fact (contradiction, superseded and distractor pairs) or an "
        "anchor parent; whole groups are assigned by a greedy pass (largest first, ties by "
        f"sha256(`{SPLIT_SEED}`:group)) followed by deterministic single-group flips that "
        f"reduce the squared deviation from {DEV_FRACTION:.0%} dev per category and overall. "
        "No fact appears in both splits (validated). Alternate (restatement) parents are not "
        "used for grouping - summary documents restate many facts and would collapse the set "
        f"into one group; {len(alt_cross)} alternate parents are shared across splits: "
        + (", ".join(f"`{h}`" for h in alt_cross) or "none")
        + ".",
        "",
        "## Provenance",
        "",
        "Hand written for this dataset (`hand_written:research-v0`, "
        "`hand_written:ledger-contradiction` for conflict items, "
        "`hand_written:topic-not-in-corpus` for insufficient items). Insufficient topics were "
        "checked absent by keyword search over every active parent in the workspace (patents, "
        "emissions, inventory turnover, distribution centres, debt, licensing/membranes, share "
        "price).",
        "",
        "## Leakage checks",
        "",
        f"Each question is compared with all {len(references)} retrieval-v0 (dev and test) and "
        "grounded-v0 questions using normalized-token Jaccard: lowercase alphanumeric tokens "
        "(ids such as `rv-00412` kept whole), once with all tokens and once without stopwords. "
        f"The build fails if either exceeds {JACCARD_REJECT}. Exact-text copies are also "
        "rejected, and duplicate questions within the set fail validation. verifier-v1 is built "
        "concurrently and is not compared; this set contains no verifier-style (citation "
        "perturbation or adversarial) items.",
        "",
        "Nearest reference shown with its origin (`dev`/`test` = retrieval-v0 split, "
        "`grounded` = grounded-v0).",
        "",
        "| item | split | max J (all) | nearest | max J (content) | nearest |",
        "|---|---|---|---|---|---|",
    ]
    for i in items:
        lk = i["leakage"]
        lines.append(
            f"| {i['id']} | {i['split']} | {lk['max_jaccard_all_tokens']:.3f} | "
            f"{lk['nearest_all_tokens']} | {lk['max_jaccard_content_tokens']:.3f} | "
            f"{lk['nearest_content_tokens']} |"
        )
    worst = max(
        items,
        key=lambda i: max(
            i["leakage"]["max_jaccard_all_tokens"], i["leakage"]["max_jaccard_content_tokens"]
        ),
    )
    strict = [r for r in references if r[2] in ("test", "grounded")]
    strict_max = max(
        (jaccard(tokens(i["question"], content=c), tokens(q, content=c)), i["id"], rid)
        for i in items
        for rid, q, _ in strict
        for c in (False, True)
    )
    lines += [
        "",
        f"Highest similarity to a retrieval-v0 test or grounded-v0 question: {strict_max[1]} vs "
        f"{strict_max[2]} ({strict_max[0]:.3f}).",
        "",
        f"Highest similarity overall: {worst['id']} "
        f"({max(worst['leakage']['max_jaccard_all_tokens'], worst['leakage']['max_jaccard_content_tokens']):.3f}).",  # noqa: E501
        "",
        "## Caveats",
        "",
        "- Facts overlap with retrieval-v0/grounded-v0 by construction (same fixed corpus); "
        "only questions are new. Several multi-part items reuse a fact that a retrieval-v0 "
        "test item asks about in a single-fact form.",
        "- Alternates added here are single-reviewer; retrieval-v0's were dual-judged.",
        "- `router_expectation` is judged from the question text alone; reformulation items "
        "that look like single lookups are labelled `standard` even though research may "
        "recover a missed first pass.",
        "",
    ]
    return "\n".join(lines)


async def verify_db(doc: dict[str, Any]) -> list[str]:
    """Re-locate anchors and resolve every handle in its own workspace scope (backend venv)."""
    from marketsignal.config import Settings
    from marketsignal.db.engine import create_engine, create_session_factory
    from marketsignal.db.session import scoped_session
    from marketsignal.evaluation.gold import load_workspace, locate, norm, parent_contains_anchor
    from marketsignal.evidence.resolver import resolve_evidence

    ledger = json.loads(LEDGER.read_text())
    facts = {f["fact_id"]: f for f in ledger["facts"]}
    probes = {(fid, h): p for fid, alts in ALTERNATES.items() for h, p in alts}
    problems: list[str] = []
    engine = create_engine(Settings())
    try:
        factory = create_session_factory(engine)
        workspaces = {c: await load_workspace(factory, c) for c in ("NORTHSTAR", "SOUTHPEAK")}
        for fid, anchor in ANCHORS.items():
            fact = facts[fid]
            located = locate(fact, workspaces[fact["workspace_code"]])
            if located != [anchor]:
                problems.append(f"{fid}: anchor located at {located}, expected {anchor}")
        checked = 0
        for item in doc["items"]:
            ws = workspaces[item["workspace"]]
            for g in item["gold_facts"]:
                for h in g["handles"]:
                    checked += 1
                    if h not in ws.parents:
                        problems.append(f"{item['id']}: {h} is not an active parent")
                        continue
                    async with scoped_session(factory, ws.scope) as session:
                        try:
                            body = (await resolve_evidence(session, ws.scope, h)).as_dict()
                        except Exception as exc:  # every failure is a finding
                            problems.append(f"{item['id']}: {h} does not resolve ({exc!r})")
                            continue
                    text_ = norm(body["text"])
                    if h == g["anchor_handle"]:
                        if not parent_contains_anchor(facts[g["fact_id"]], body["text"]):
                            problems.append(f"{item['id']}: {h} lacks the anchor")
                    else:
                        probe = probes.get((g["fact_id"], h))
                        if probe is not None and norm(probe) not in text_:
                            problems.append(f"{item['id']}: {h} lacks probe {probe!r}")
        print(f"verified {checked} gold handle references, {len(ANCHORS)} anchors")
    finally:
        await engine.dispose()
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="diff a rebuild against files")
    parser.add_argument("--verify-db", action="store_true", help="verify handles against DB")
    args = parser.parse_args()
    doc, readme = build()
    payload = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if args.verify_db:
        import asyncio

        problems = asyncio.run(verify_db(doc))
        if problems:
            print("DB verification failed:\n  " + "\n  ".join(problems))
            return 1
        print("DB verification ok")
        return 0
    if args.check:
        same = ITEMS_OUT.read_text() == payload and README_OUT.read_text() == readme
        print("up to date" if same else "OUT OF DATE: re-run scripts/build_research_v0.py")
        return 0 if same else 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ITEMS_OUT.write_text(payload)
    README_OUT.write_text(readme)
    print(json.dumps(doc["manifest"]["counts"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
