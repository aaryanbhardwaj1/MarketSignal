"""Build eval/datasets/research-dev-p5 (Phase 5, A3: research synthesis completeness, dev only).

A small dev set for measuring whether the research summary hand-off (``agent/summary.py``) makes
synthesis state more of the gold values the agent gathered. Two parts:

* seven FRESH multi-dimension questions (2-3 numeric gold facts each, all Northstar), written
  for this set; gold values come from ``seed_data/fact_ledger.json``; gold handles are the
  anchor parents in ``build_research_v0.ANCHORS`` plus any alternates research-v0 *dev* items
  already list for the same fact (no test item is read for handles);
* five research-v0 DEV items copied verbatim (ids kept): the dev items where Phase 4 research
  stated only part of the gold (answer completeness < 1 in
  ``eval/baselines/phase4/research-v0-dev-live``).

No research-v0 test item is used. Leakage guard: normalised-token Jaccard of each fresh question
against every research-v0 question must stay below 0.6 (same rule as research-v0).

    python3 scripts/build_research_dev_p5.py           # write items.json
    python3 scripts/build_research_dev_p5.py --check   # rebuild in memory, diff vs the file
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "datasets" / "research-dev-p5" / "items.json"
RESEARCH_V0 = ROOT / "eval" / "datasets" / "research-v0" / "items.json"
LEDGER = ROOT / "seed_data" / "fact_ledger.json"
JACCARD_REJECT = 0.6

COPIED_DEV_IDS = ("R-IT-05", "R-CI-02", "R-CF-01", "R-CF-05", "R-RF-03")

# (id, category, question, fact_ids). All expect a full answer; router expectation research.
FRESH: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "P5-01",
        "multi_metric_internal",
        "For Northstar's Gen Z plan, give the FY28 target Gen Z share of revenue, finance's "
        "FY26 Gen Z revenue growth estimate, and the FY26 latest-estimate net revenue.",
        ("NS-003", "NS-128", "NS-125"),
    ),
    (
        "P5-02",
        "multi_metric_market",
        "How large is the 2026 US Gen Z athletic footwear market, what share of Gen Z athletic "
        "spend went through marketplaces and social commerce in 2026, and what share of Gen Z "
        "footwear purchases do social commerce platforms account for?",
        ("NS-129", "NS-108", "NS-035"),
    ),
    (
        "P5-03",
        "multi_metric_survey",
        "In the willingness-to-pay study, how many people were surveyed, what share of Gen Z "
        "would pay a 15% premium for personalized fit, and what share would accept a 25% premium?",
        ("NS-044", "NS-041", "NS-042"),
    ),
    (
        "P5-04",
        "stated_vs_revealed",
        "Compare stated and revealed demand for personalization: the share of Gen Z willing to "
        "pay a 15% premium in the study versus the pilot's premium-tier uptake, plus the "
        "click-through lift from custom colorway emails.",
        ("NS-041", "NS-051", "NS-084"),
    ),
    (
        "P5-05",
        "product_quality",
        "What is the Knit Runner 2's return rate, and how many knit upper wear support tickets "
        "were logged in Q3 2026?",
        ("NS-120", "NS-012"),
    ),
    (
        "P5-06",
        "plan_and_growth",
        "What Gen Z marketing budget does the FY27 memo propose, how fast did Social Shop sales "
        "grow quarter over quarter in Q2 FY26, and what was Gen Z NPS in Q2 FY26?",
        ("NS-100", "NS-085", "NS-086"),
    ),
    (
        "P5-07",
        "scale_comparison",
        "How does Vantage Athletic's FY2025 net revenue compare with Northstar's FY26 "
        "latest-estimate net revenue and the size of the 2026 US Gen Z athletic footwear market?",
        ("NS-090", "NS-125", "NS-129"),
    ),
)


def _research_v0_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_research_v0", ROOT / "scripts" / "build_research_v0.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _gold_fact(
    fact: dict[str, Any], anchor: str, alternates: set[str], classes: dict[Any, str]
) -> dict[str, Any]:
    return {
        "fact_id": fact["fact_id"],
        "handles": sorted({anchor, *alternates}),
        "anchor_handle": anchor,
        "value": fact["value"],
        "unit": fact["unit"],
        "source_code": fact["source_code"],
        "source_class": classes[(fact["workspace_code"], fact["source_code"])],
    }


def build() -> dict[str, Any]:
    v0 = _research_v0_module()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    facts = {f["fact_id"]: f for f in ledger["facts"]}
    research = json.loads(RESEARCH_V0.read_text(encoding="utf-8"))["items"]
    dev = [i for i in research if i["split"] == "dev"]
    alternates: dict[str, set[str]] = {}
    for item in dev:
        for fact in item["gold_facts"]:
            alternates.setdefault(fact["fact_id"], set()).update(fact["handles"])
    classes = v0.source_classes()
    v0_tokens = [(i["id"], v0.tokens(i["question"], content=False)) for i in research]

    items: list[dict[str, Any]] = []
    for item_id, category, question, fact_ids in FRESH:
        gold = [
            _gold_fact(facts[f], v0.ANCHORS[f], alternates.get(f, set()), classes) for f in fact_ids
        ]
        mine = v0.tokens(question, content=False)
        nearest, score = max(((i, v0.jaccard(mine, t)) for i, t in v0_tokens), key=lambda x: x[1])
        if score >= JACCARD_REJECT:
            raise SystemExit(f"{item_id}: Jaccard {score:.2f} with {nearest}")
        items.append(
            {
                "id": item_id,
                "workspace": "NORTHSTAR",
                "category": category,
                "question": question,
                "expect": "answer",
                "gold_facts": gold,
                "source_classes": [],
                "canary": None,
                "provenance": "hand_written:research-dev-p5",
                "origin_split": None,
                "router_expectation": "research",
                "gold_source_classes": sorted({g["source_class"] for g in gold}),
                "leakage": {"max_jaccard_research_v0": round(score, 3), "nearest": nearest},
                "split": "dev",
            }
        )
    by_id = {i["id"]: i for i in dev}
    items.extend(
        by_id[i] | {"provenance_note": "copied from research-v0 dev"} for i in COPIED_DEV_IDS
    )
    return {
        "dataset_version": "research-dev-p5",
        "description": (
            "Phase 5 A3 dev set (research synthesis completeness): 7 fresh multi-dimension "
            "Northstar questions plus 5 research-v0 dev items that Phase 4 research answered "
            "incompletely. Dev only: never a test or holdout set. Built by "
            "scripts/build_research_dev_p5.py."
        ),
        "manifest": {
            "counts": {"items": len(items), "fresh": len(FRESH), "copied_dev": len(COPIED_DEV_IDS)},
            "gold_facts": sum(len(i["gold_facts"]) for i in items),
            "copied_dev_ids": list(COPIED_DEV_IDS),
        },
        "items": items,
    }


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="diff a rebuild against the file")
    args = parser.parse_args()
    text = render(build())
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("research-dev-p5: up to date" if same else "research-dev-p5: STALE", file=sys.stderr)
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
