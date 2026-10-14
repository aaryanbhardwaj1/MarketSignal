"""Curated brief schema v2 over harness-uploaded sources, with a synthetic v2 fixture injected
through the router's loader: kinds, statuses, claim types, implications, related links, the
verified support / contradiction counts, opportunity risks re-verified and rolled into item
integrity, a forecast citing a stated projection, and analysis summaries shown only when every
number in them is a computed figure."""

# ruff: noqa: F811
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.api.routers import insights as insights_router
from marketsignal.insights.fixture import Fixture, parse_fixture
from marketsignal.insights.service import clear_cache
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401
from tests.integration.test_insights_api import (
    CSV,
    FIT,
    GONE,
    _brief,
    _handle,
    _result_rows,
    _source_id,
    _upload,
)

pytestmark = pytest.mark.integration

PROJ = "Personalised units will stay below five percent of volume through the next two years."
RISK = "Several shoppers admitted they would order two sizes and return one on purpose."
SPEC = {
    "dataset": "SURV:1",
    "metrics": [{"fn": "mean", "column": "score"}],
    "group_by": ["segment"],
    "order": {"by": "group", "direction": "asc"},
}


def _analysis(
    aid: str, a_value: float, summary: str, interpretation: str = "Segment B is more satisfied."
) -> dict[str, Any]:
    return {
        "id": aid,
        "title": "Score by segment",
        "question": "What is the mean score per segment?",
        "category": "customer",
        "op": "aggregate",
        "dataset": "SURV:1",
        "unit": "score",
        "presentation": "bar",
        "denominator_label": "rows",
        "parts": [{"spec": SPEC}],
        "expected": [
            {"group": {"segment": "A"}, "value": a_value},
            {"group": {"segment": "B"}, "value": 5},
        ],
        "business_area": "Customer satisfaction",
        "summary": summary,
        "interpretation": {"text": interpretation, "claim_type": "inference"},
    }


def _ev(handle: str, quote_: str, role: str = "support", **extra: Any) -> dict[str, Any]:
    return {"handle": handle, "quote": quote_, "role": role, **extra}


def _fixture(ws: str, h: dict[str, str]) -> Fixture:
    pick = {"analysis_id": "score-by-segment", "group": {"segment": "A"}}
    return parse_fixture(
        {
            "schema_version": 2,
            "fixture_version": f"{ws}.v2test",
            "workspace": ws,
            "label": "Curated analyst brief",
            "corpus": {
                "MEMO": {"version": 1},
                "OUTLOOK": {"version": 1},
                "GONE": {"version": 1},
                "RISKS": {"version": 1},
                "SURV": {"version": 1},
            },
            "analyses": [
                _analysis(
                    "score-by-segment",
                    2.0,
                    "Segment B averages 5.00 against 2 for segment A, across 3 rows.",
                ),
                _analysis(
                    "score-invented",
                    2.0,
                    "Segment A averages 2.50.",
                    "Segment A trails by 7 points.",
                ),
                _analysis("score-drifted", 9.0, "Segment B is ahead."),
            ],
            "signals": [
                {
                    "id": "fit",
                    "category": "Customer friction",
                    "title": "Fit",
                    "statement": "Fit inconsistency leads.",
                    "evidence": [_ev(h["fit"], FIT)],
                    "metrics": [{"label": "Mean score, A", "pick": pick}],
                    "kind": "optimization",
                    "status": "strong_evidence",
                    "claim_type": "observed",
                    "implication": {
                        "text": "Fixing fit may cut returns.",
                        "claim_type": "inference",
                    },
                    "gaps": ["No cost data."],
                    "related": {"analyses": ["score-invented"], "opportunities": ["O1"]},
                },
                {
                    "id": "outlook",
                    "category": "Future outlook",
                    "title": "Personalisation stays niche",
                    "statement": "Personalised units stay a small share of volume.",
                    "evidence": [
                        _ev(h["proj"], PROJ, states_projection=True),
                        _ev(h["fit"], FIT),
                    ],
                    "metrics": [{"label": "Mean score, A", "pick": pick}],
                    "kind": "future_outlook",
                    "status": "emerging",
                    "claim_type": "forecast",
                    "implication": {"text": "Do not plan around it.", "claim_type": "hypothesis"},
                    "related": {"signals": ["fit"]},
                },
            ],
            "opportunities": [
                {
                    "id": "O1",
                    "title": "Fit Promise",
                    "status": "mixed_evidence",
                    "status_rationale": "Support and a contradiction.",
                    "thesis": "A fit guarantee may help.",
                    "evidence": [_ev(h["fit"], FIT), _ev(h["gone"], GONE, "contradict")],
                    "metrics": [{"label": "Mean score, A", "pick": pick}],
                    "gaps": [],
                    "next_step": "Model the cost.",
                    "thesis_claim_type": "hypothesis",
                    "why_it_matters": {"text": "Returns are costly.", "claim_type": "inference"},
                    "risks": [
                        {
                            "text": "Guarantees invite bracketing.",
                            "claim_type": "observed",
                            "evidence": [_ev(h["risk"], RISK)],
                        }
                    ],
                    "next_investigation": "What would a guarantee cost per order?",
                    "related": {"signals": ["fit"], "analyses": ["score-by-segment"]},
                }
            ],
        }
    )


@pytest.fixture
async def world(
    harness: Harness, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> tuple[Harness, str]:
    clear_cache()
    ws = await harness.create_workspace()
    await _upload(harness, ws, "memo.md", f"# Notes\n\n{FIT}\n".encode(), "MEMO")
    outlook = f"# Outlook\n\n{PROJ}\n"
    await _upload(harness, ws, "outlook.md", outlook.encode(), "OUTLOOK")
    await _upload(harness, ws, "gone.md", f"# Gone\n\n{GONE}\n".encode(), "GONE")
    await _upload(harness, ws, "risks.md", f"# Risks\n\n{RISK}\n".encode(), "RISKS")
    await _upload(harness, ws, "surv.csv", CSV, "SURV")
    handles = {
        "fit": await _handle(app_engine, ws, FIT),
        "proj": await _handle(app_engine, ws, PROJ),
        "gone": await _handle(app_engine, ws, GONE),
        "risk": await _handle(app_engine, ws, RISK),
    }
    fixture = _fixture(ws, handles)
    monkeypatch.setattr(
        insights_router, "load_fixture", lambda code: fixture if code == ws else None
    )
    return harness, ws


def opp_risk_flags(brief: dict[str, Any]) -> list[bool]:
    return [
        ref["states_projection"]
        for opp in brief["opportunities"]
        for risk in opp["risks"]
        for ref in risk["evidence"]
    ]


async def test_v2_brief_serves_every_new_field(
    world: tuple[Harness, str], app_engine: AsyncEngine
) -> None:
    h, ws = world
    before = await _result_rows(app_engine, ws)
    brief = await _brief(h, ws)
    assert brief["corpus_check"] == {"status": "ok", "drifted_sources": []}
    fit, outlook = brief["signals"]
    assert (fit["kind"], fit["status"], fit["claim_type"]) == (
        "optimization",
        "strong_evidence",
        "observed",
    )
    assert fit["implication"] == {"text": "Fixing fit may cut returns.", "claim_type": "inference"}
    assert fit["gaps"] == ["No cost data."]
    assert fit["related"] == {
        "analyses": ["score-invented"],
        "opportunities": ["O1"],
        "signals": [],
    }
    assert (fit["support_count"], fit["contradiction_count"]) == (1, 0)
    assert fit["integrity"] == "verified"
    assert outlook["claim_type"] == "forecast"
    assert outlook["evidence"][0]["integrity"] == "verified"
    assert outlook["evidence"][0]["quote"] == PROJ
    assert outlook["evidence"][0]["states_projection"] is True
    assert fit["evidence"][0]["states_projection"] is False
    assert opp_risk_flags(brief) == [False]
    assert outlook["integrity"] == "verified"

    (opp,) = brief["opportunities"]
    assert opp["thesis_claim_type"] == "hypothesis"
    assert opp["why_it_matters"] == {"text": "Returns are costly.", "claim_type": "inference"}
    assert opp["next_investigation"] == "What would a guarantee cost per order?"
    assert opp["related"] == {
        "analyses": ["score-by-segment"],
        "opportunities": [],
        "signals": ["fit"],
    }
    assert (opp["support_count"], opp["contradiction_count"]) == (1, 1)
    (risk,) = opp["risks"]
    assert (risk["text"], risk["claim_type"], risk["integrity"]) == (
        "Guarantees invite bracketing.",
        "observed",
        "verified",
    )
    assert risk["evidence"][0]["quote"] == RISK
    assert risk["evidence"][0]["source"]["code"] == "RISKS"
    assert opp["integrity"] == "verified"

    listing = (await h.client.get(f"/api/workspaces/{ws}/analytics/analyses")).json()
    by_id = {a["id"]: a for a in listing["analyses"]}
    ok, invented, drifted = (
        by_id["score-by-segment"],
        by_id["score-invented"],
        by_id["score-drifted"],
    )
    assert ok["status"] == "computed"
    assert ok["business_area"] == "Customer satisfaction"
    assert ok["summary"] == "Segment B averages 5.00 against 2 for segment A, across 3 rows."
    assert ok["summary_status"] == "verified"
    assert ok["interpretation"] == {
        "text": "Segment B is more satisfied.",
        "claim_type": "inference",
    }
    assert ok["interpretation_status"] == "verified"
    assert ok["used_by"] == {"signals": ["fit", "outlook"], "opportunities": ["O1"]}
    # a computed analysis whose summary invents a figure: the summary is withheld
    assert invented["status"] == "computed"
    assert (invented["summary"], invented["summary_status"]) == (None, "unverified")
    # its interpretation invents a figure too, so it is withheld like the summary
    assert (invented["interpretation"], invented["interpretation_status"]) == (None, "unverified")
    assert invented["used_by"] == {"signals": ["fit"], "opportunities": []}
    # an analysis that no longer recomputes never shows its summary
    assert drifted["status"] == "mismatch"
    assert (drifted["summary"], drifted["summary_status"]) == (None, "unverified")
    assert (drifted["interpretation"], drifted["interpretation_status"]) == (None, "unverified")
    assert drifted["used_by"] == {"signals": [], "opportunities": []}
    one = (await h.client.get(f"/api/workspaces/{ws}/analytics/analyses/score-invented")).json()
    assert one["summary_status"] == "unverified"
    assert await _result_rows(app_engine, ws) == before


async def test_stale_risk_quote_and_purged_contradiction_roll_up(
    world: tuple[Harness, str],
) -> None:
    h, ws = world
    await _upload(h, ws, "risks.md", b"# Risks\n\nThe risk register was rewritten.\n", "RISKS")
    purge = await h.client.delete(f"/api/workspaces/{ws}/sources/{await _source_id(h, ws, 'GONE')}")
    assert purge.status_code == 200, purge.text
    brief = await _brief(h, ws)
    (opp,) = brief["opportunities"]
    (risk,) = opp["risks"]
    assert risk["evidence"][0]["integrity"] == "stale"
    assert risk["evidence"][0]["quote"] is None
    assert risk["integrity"] == "unverified"
    # the thesis' own support still verifies, so the item is partial, not unverified
    assert opp["integrity"] == "partial"
    assert (opp["support_count"], opp["contradiction_count"]) == (1, 0)
    assert opp["contradicting"][0]["integrity"] == "withdrawn"
    assert brief["corpus_check"]["status"] == "drift"
    assert {"RISKS", "GONE"} <= set(brief["corpus_check"]["drifted_sources"])
    fit = brief["signals"][0]
    assert fit["integrity"] == "verified"


async def test_forecast_with_an_unverified_projection_is_unverified_at_request_time(
    world: tuple[Harness, str],
) -> None:
    """Load-time checks only see the fixture; the projection must also verify per request."""
    h, ws = world
    brief = await _brief(h, ws)
    outlook = brief["signals"][1]
    assert outlook["integrity"] == "verified"
    assert outlook["metrics"][0]["value"] is not None
    rewritten = b"# Outlook\n\nThe outlook section was withdrawn.\n"
    await _upload(h, ws, "outlook.md", rewritten, "OUTLOOK")
    brief = await _brief(h, ws)
    fit, outlook = brief["signals"]
    proj, fit_ref = outlook["evidence"]
    assert (proj["integrity"], proj["quote"]) == ("stale", None)
    assert fit_ref["integrity"] == "verified"
    # without the rule the remaining verified support would roll up to "partial"
    assert outlook["integrity"] == "unverified"
    assert (outlook["metrics"][0]["value"], outlook["metrics"][0]["display"]) == (None, None)
    assert fit["integrity"] == "verified"
    assert fit["metrics"][0]["value"] is not None
