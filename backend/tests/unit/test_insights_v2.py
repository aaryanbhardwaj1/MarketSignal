"""Curated brief schema v2 (claim types, kinds, statuses, risks, related links, analysis
summaries): load-time validation rules, the analysis summary number check and the ``used_by``
reverse index. A small synthetic v2 fixture; no database."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from marketsignal.insights.fixture import (
    FIXTURE_DIR,
    Fixture,
    FixtureError,
    check_claim,
    parse_fixture,
)
from marketsignal.insights.service import used_by_index
from marketsignal.insights.summary import check_summary

V1_PATH = FIXTURE_DIR / "NORTHSTAR.v1.json"
FIT = "Fit inconsistency is the top frustration for young shoppers in this study."
PROJ = "Personalised units will stay below 5% of volume through 2028."


def _ev(loc: str, quote: str, role: str = "support", **extra: Any) -> dict[str, Any]:
    return {"handle": f"ACME/MEMO@v1:{loc}", "quote": quote, "role": role, **extra}


def _analysis(aid: str) -> dict[str, Any]:
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
        "parts": [
            {
                "spec": {
                    "dataset": "SURV:1",
                    "metrics": [{"fn": "mean", "column": "score"}],
                    "group_by": ["segment"],
                }
            }
        ],
        "expected": [
            {"group": {"segment": "A"}, "value": 2.0},
            {"group": {"segment": "B"}, "value": 5},
        ],
        "business_area": "Customer satisfaction",
        "summary": "Segment B scores 5.00 against 2.00 for segment A across 3 rows.",
        "interpretation": {"text": "B is happier.", "claim_type": "inference"},
    }


def _metric(aid: str = "score-a") -> dict[str, Any]:
    return {"label": "Mean A", "pick": {"analysis_id": aid, "group": {"segment": "A"}}}


def v2_raw() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "fixture_version": "ACME.v2",
        "workspace": "ACME",
        "label": "Curated analyst brief",
        "corpus": {"MEMO": {"version": 1}, "SURV": {"version": 1}},
        "analyses": [_analysis("score-a"), _analysis("score-b")],
        "signals": [
            {
                "id": "fit",
                "category": "Customer friction",
                "title": "Fit",
                "statement": "Fit inconsistency leads.",
                "evidence": [_ev("P1.B1", FIT)],
                "metrics": [_metric()],
                "kind": "optimization",
                "status": "strong_evidence",
                "claim_type": "observed",
                "implication": {"text": "Fixing fit may cut returns.", "claim_type": "inference"},
                "gaps": ["No cost data."],
                "related": {"analyses": ["score-a"], "opportunities": ["O1"], "signals": []},
            },
            {
                "id": "outlook",
                "category": "Future outlook",
                "title": "Personalisation stays niche",
                "statement": "Personalisation stays below 5% of units.",
                "evidence": [_ev("P2.B1", PROJ, states_projection=True)],
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
                "status": "supported",
                "status_rationale": "Consistent signal.",
                "thesis": "A fit guarantee may help.",
                "evidence": [_ev("P1.B1", FIT), _ev("P3.B1", FIT, "contradict")],
                "metrics": [_metric("score-b")],
                "gaps": [],
                "next_step": "Model the cost.",
                "thesis_claim_type": "hypothesis",
                "why_it_matters": {"text": "Returns are costly.", "claim_type": "inference"},
                "risks": [
                    {
                        "text": "Guarantees invite abuse.",
                        "claim_type": "inference",
                        "evidence": [_ev("P4.B1", FIT)],
                    }
                ],
                "next_investigation": "What would a guarantee cost per order?",
                "related": {"analyses": ["score-b"], "signals": ["fit"]},
            }
        ],
    }


def _set(raw: dict[str, Any], path: list[Any], value: Any) -> dict[str, Any]:
    out = copy.deepcopy(raw)
    node: Any = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


def _drop(raw: dict[str, Any], path: list[Any]) -> dict[str, Any]:
    out = copy.deepcopy(raw)
    node: Any = out
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return out


def test_synthetic_v2_fixture_validates() -> None:
    fixture = parse_fixture(v2_raw())
    assert fixture.schema_version == 2
    fit, outlook = fixture.signals
    assert fit.kind == "optimization"
    assert fit.status == "strong_evidence"
    assert fit.claim_type == "observed"
    assert fit.implication is not None
    assert fit.implication.claim_type == "inference"
    assert fit.related.opportunities == ["O1"]
    assert outlook.related.analyses == []
    assert outlook.evidence[0].states_projection is True
    opp = fixture.opportunities[0]
    assert opp.risks[0].evidence[0].handle == "ACME/MEMO@v1:P4.B1"
    assert opp.next_investigation
    assert fixture.analyses[0].business_area == "Customer satisfaction"
    # risk evidence is part of every handle check
    assert "ACME/MEMO@v1:P4.B1" in [e.handle for e in fixture.all_evidence()]


def test_v1_file_still_loads_with_v2_fields_defaulted() -> None:
    fixture = parse_fixture(json.loads(V1_PATH.read_text(encoding="utf-8")))
    assert fixture.schema_version == 1
    for s in fixture.signals:
        assert (s.kind, s.status, s.claim_type, s.implication) == (None, None, None, None)
        assert s.gaps == []
        assert s.related.analyses == s.related.opportunities == s.related.signals == []
    for o in fixture.opportunities:
        assert (o.thesis_claim_type, o.why_it_matters, o.next_investigation) == (None, None, None)
        assert o.risks == []
    for a in fixture.analyses:
        assert (a.business_area, a.summary, a.interpretation) == (None, None, None)
    assert all(not e.states_projection for e in fixture.all_evidence())


@pytest.mark.parametrize(
    "path",
    [
        ["signals", 0, "kind"],
        ["signals", 0, "status"],
        ["signals", 0, "claim_type"],
        ["signals", 0, "implication"],
        ["signals", 0, "related"],
        ["opportunities", 0, "thesis_claim_type"],
        ["opportunities", 0, "why_it_matters"],
        ["opportunities", 0, "risks"],
        ["opportunities", 0, "next_investigation"],
        ["opportunities", 0, "related"],
        ["analyses", 0, "business_area"],
        ["analyses", 0, "summary"],
    ],
)
def test_v2_requires_its_fields(path: list[Any]) -> None:
    with pytest.raises(FixtureError):
        parse_fixture(_drop(v2_raw(), path))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["schema_version"], 3),
        (["signals", 0, "kind"], "strategic_opportunity"),
        (["signals", 0, "status"], "supported"),
        (["signals", 0, "claim_type"], "fact"),
        (["signals", 0, "implication", "claim_type"], "certain"),
        (["opportunities", 0, "status"], "strong_evidence"),
        (["analyses", 0, "business_area"], "Marketing"),
        (["signals", 0, "related", "extra"], []),
        (["opportunities", 0, "risks", 0, "evidence"], []),
        (["opportunities", 0, "risks", 0, "score"], 3),
    ],
)
def test_v2_enums_and_shapes_fail_closed(path: list[Any], value: Any) -> None:
    with pytest.raises(FixtureError):
        parse_fixture(_set(v2_raw(), path, value))


def test_rule1_observed_needs_a_support_ref() -> None:
    raw = _set(v2_raw(), ["signals", 0, "evidence", 0, "role"], "contradict")
    with pytest.raises(FixtureError, match="observed"):
        parse_fixture(raw)
    raw = _set(v2_raw(), ["opportunities", 0, "risks", 0, "claim_type"], "observed")
    parse_fixture(raw)  # the risk's own support ref satisfies it
    raw = _set(raw, ["opportunities", 0, "risks", 0, "evidence", 0, "role"], "contradict")
    with pytest.raises(FixtureError, match="observed"):
        parse_fixture(raw)


def test_rule2_derived_needs_a_metric() -> None:
    raw = _set(v2_raw(), ["signals", 0, "claim_type"], "derived")
    parse_fixture(raw)
    with pytest.raises(FixtureError, match="derived"):
        parse_fixture(_set(raw, ["signals", 0, "metrics"], []))
    # a risk has no metrics of its own, so it can never borrow its opportunity's as "derived"
    raw = _set(v2_raw(), ["opportunities", 0, "risks", 0, "claim_type"], "derived")
    with pytest.raises(FixtureError, match=r"risk 1.*derived"):
        parse_fixture(raw)


def test_rule3_interpretive_claims_need_evidence_or_a_metric() -> None:
    for claim in ("inference", "hypothesis"):
        check_claim("x", claim, [], 1)  # a metric is enough
        with pytest.raises(ValueError, match=claim):
            check_claim("x", claim, [], 0)


def test_rule4_forecast_needs_a_cited_projection() -> None:
    raw = _set(v2_raw(), ["signals", 1, "evidence", 0, "states_projection"], False)
    with pytest.raises(FixtureError, match="forecast"):
        parse_fixture(raw)
    raw = _set(v2_raw(), ["signals", 0, "implication", "claim_type"], "forecast")
    with pytest.raises(FixtureError, match="forecast"):
        parse_fixture(raw)
    raw = _set(v2_raw(), ["opportunities", 0, "risks", 0, "claim_type"], "forecast")
    with pytest.raises(FixtureError, match="forecast"):
        parse_fixture(raw)
    ok = _set(raw, ["opportunities", 0, "risks", 0, "evidence", 0, "states_projection"], True)
    parse_fixture(ok)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["signals", 0, "related", "analyses"], ["nope"]),
        (["signals", 0, "related", "opportunities"], ["O9"]),
        (["signals", 1, "related", "signals"], ["ghost"]),
        (["opportunities", 0, "related", "signals"], ["ghost"]),
        (["opportunities", 0, "related", "analyses"], ["nope"]),
    ],
)
def test_rule5_related_ids_must_exist(path: list[Any], value: Any) -> None:
    with pytest.raises(FixtureError, match="related"):
        parse_fixture(_set(v2_raw(), path, value))


@pytest.mark.parametrize(
    "handle",
    [
        "OTHER/MEMO@v1:P4.B1",  # outside the workspace
        "ACME/MEMO@v2:P4.B1",  # version not pinned
        "ACME/NOTPINNED@v1:P4.B1",
        "not a handle",
    ],
)
def test_rule6_risk_evidence_gets_the_handle_checks(handle: str) -> None:
    raw = _set(v2_raw(), ["opportunities", 0, "risks", 0, "evidence", 0, "handle"], handle)
    with pytest.raises(FixtureError):
        parse_fixture(raw)


def test_banned_handles_are_rejected_in_risks() -> None:
    raw = json.loads(json.dumps(v2_raw()).replace("ACME", "NORTHSTAR"))
    raw["corpus"]["REVIEWS"] = {"version": 1}
    banned = "NORTHSTAR/REVIEWS@v1:R578"
    with pytest.raises(FixtureError, match="banned"):
        parse_fixture(_set(raw, ["opportunities", 0, "risks", 0, "evidence", 0, "handle"], banned))


def test_interpretation_must_be_an_inference() -> None:
    raw = _set(v2_raw(), ["analyses", 0, "interpretation", "claim_type"], "observed")
    with pytest.raises(FixtureError, match="interpretation"):
        parse_fixture(raw)
    parse_fixture(_set(v2_raw(), ["analyses", 0, "interpretation"], None))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["signals", 0, "claim_type"], "forecast"),
        (["signals", 0, "related"], {}),
        (["opportunities", 0, "risks"], []),
        (["analyses", 0, "summary"], "An unchecked takeaway."),
    ],
)
def test_v1_file_cannot_carry_v2_fields(path: list[Any], value: Any) -> None:
    """The claim rules are v2 only, so a v1 file may not smuggle unchecked claims in."""
    raw = json.loads(V1_PATH.read_text(encoding="utf-8"))
    with pytest.raises(FixtureError, match="schema_version 1"):
        parse_fixture(_set(raw, path, value))


# ── analysis summary number check ───────────────────────────────────────────────────────────


def _payload(status: str = "computed") -> dict[str, Any]:
    ok = status == "computed"
    return {
        "status": status,
        "denominator": {"label": "rows", "value": 1240} if ok else None,
        "rows": [
            {"group": {"c": "A"}, "value": 27.0, "display": "27.0%", "denominator": 500},
            {"group": {"c": "B"}, "value": 2146098, "display": "$2,146,098"},
            {"group": {"c": "C"}, "value": -3.2, "display": "-3.2%"},
        ]
        if ok
        else [],
    }


@pytest.mark.parametrize(
    "summary",
    [
        "Fit leads at 27% of respondents.",
        "Fit leads at 27.0% of 1,240 rows.",
        "Sales reached $2,146,098 in Q3 FY27.",
        "Of 500 Gen Z respondents, 27 percent named fit.",
        "Satisfaction fell 3.2 points.",
        "Fit is the clear leader.",
    ],
)
def test_summary_numbers_that_match_are_verified(summary: str) -> None:
    assert check_summary(summary, _payload()) == (summary, "verified")


@pytest.mark.parametrize(
    "summary",
    [
        "Fit leads at 28% of respondents.",
        "Sales reached $2,146,099.",
        "Fit leads at 27% across 1,241 rows.",
        "Two thirds, or 66.7%, agree.",
    ],
)
def test_summary_with_any_unmatched_number_is_withheld(summary: str) -> None:
    assert check_summary(summary, _payload()) == (None, "unverified")


def test_summary_absent_and_uncomputed() -> None:
    assert check_summary(None, _payload()) == (None, "absent")
    assert check_summary("", _payload()) == (None, "absent")
    for status in ("mismatch", "unavailable"):
        assert check_summary("Fit is the leader.", _payload(status)) == (None, "unverified")


# ── used_by reverse index ───────────────────────────────────────────────────────────────────


def test_used_by_index_combines_metric_picks_and_related_links() -> None:
    fixture: Fixture = parse_fixture(v2_raw())
    index = used_by_index(fixture)
    assert index["score-a"] == {"signals": ["fit"], "opportunities": []}
    assert index["score-b"] == {"signals": [], "opportunities": ["O1"]}


def test_used_by_index_on_v1_reads_metric_picks() -> None:
    fixture = parse_fixture(json.loads(V1_PATH.read_text(encoding="utf-8")))
    index = used_by_index(fixture)
    assert set(index) == {a.id for a in fixture.analyses}
    assert "fit-friction" in index["pain-points-by-cohort"]["signals"]


# ── the committed v2 brief ──────────────────────────────────────────────────────────────────

V2_PATH = FIXTURE_DIR / "NORTHSTAR.v2.json"


def test_committed_v2_brief_is_the_newest_and_validates() -> None:
    from marketsignal.insights.fixture import load_fixture, newest_fixture_path

    assert newest_fixture_path("NORTHSTAR") == V2_PATH
    fixture = load_fixture("NORTHSTAR")
    assert fixture is not None
    assert fixture.schema_version == 2
    assert fixture.label == "Curated analyst brief"
    assert all(a.summary and a.business_area for a in fixture.analyses)
    assert {s.kind for s in fixture.signals} == {
        "emerging_signal",
        "risk_blocker",
        "competitor_finding",
        "optimization",
        "future_outlook",
    }
    forecasts = [s for s in fixture.signals if s.claim_type == "forecast"]
    assert all(any(e.states_projection for e in s.evidence) for s in forecasts)


def test_committed_v2_brief_never_cites_planted_or_superseded_text() -> None:
    raw_text = V2_PATH.read_text(encoding="utf-8")
    assert "GENZ-TRENDS@v1" not in raw_text
    assert "NORTHSTAR/KINETIC-WEB@" not in raw_text
    assert "NORTHSTAR/REVIEWS@v1:R578" not in raw_text
    raw = json.loads(raw_text)
    for item in [*raw["signals"], *raw["opportunities"]]:
        assert not {"score", "rank", "priority", "confidence"} & set(item)
