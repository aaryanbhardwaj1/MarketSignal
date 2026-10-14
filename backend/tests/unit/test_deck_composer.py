"""Deck composition rules over a synthetic, response-shaped brief: unverified items excluded,
stale references never cited, interpretive claims labelled, empty slides omitted, long sections
split onto continuation slides, no handles or ids in visible text, and citations numbered
consistently between bullets, notes and the appendix."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from marketsignal.decks.composer import MAX_BULLETS, UnknownItemsError, compose
from marketsignal.decks.models import DeckRequest

WS = {"code": "ACME", "name": "Acme Footwear"}
AT = "2026-10-14T09:30:00+00:00"


def ref(
    handle: str,
    quote: str,
    role: str = "support",
    integrity: str = "verified",
    title: str = "Customer survey",
) -> dict[str, Any]:
    return {
        "handle": handle,
        "integrity": integrity,
        "role": role,
        "quote": quote if integrity == "verified" else None,
        "char_start": 0 if integrity == "verified" else None,
        "char_end": 10 if integrity == "verified" else None,
        "child_id": None,
        "locator_label": "Page 2",
        "note": None,
        "source": {
            "code": handle.split("/")[1].split("@")[0],
            "title": title,
            "source_type": "pdf",
            "source_class": "internal",
            "version": 1,
        },
    }


def metric(analysis_id: str, label: str, value: float | None) -> dict[str, Any]:
    return {
        "analysis_id": analysis_id,
        "label": label,
        "value": value,
        "display": None if value is None else f"{value:.1f}%",
        "unit": "percent",
        "denominator_label": "Gen Z respondents",
        "derived": None,
    }


def signal(
    sid: str,
    kind: str = "emerging_signal",
    *,
    claim_type: str = "observed",
    integrity: str = "verified",
    evidence: list[dict[str, Any]] | None = None,
    metrics: list[dict[str, Any]] | None = None,
    implication: dict[str, Any] | None = None,
    status: str | None = "strong_evidence",
) -> dict[str, Any]:
    ev = evidence if evidence is not None else [ref(f"ACME/SRC-{sid}@v1:P1", f"Quote {sid}.")]
    return {
        "id": sid,
        "category": "Customer",
        "title": f"Title {sid}",
        "statement": f"Statement {sid}.",
        "integrity": integrity,
        "evidence": ev,
        "metrics": metrics or [],
        "caveats": [],
        "kind": kind,
        "status": status,
        "claim_type": claim_type,
        "implication": implication,
        "gaps": [],
        "related": {"analyses": [], "opportunities": [], "signals": []},
        "support_count": 1,
        "contradiction_count": 0,
    }


def opportunity(
    oid: str,
    *,
    integrity: str = "verified",
    supporting: list[dict[str, Any]] | None = None,
    contradicting: list[dict[str, Any]] | None = None,
    risks: list[dict[str, Any]] | None = None,
    metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sup = supporting if supporting is not None else [ref(f"ACME/OPP-{oid}@v1:P1", f"Opp {oid}.")]
    con = contradicting or []
    return {
        "id": oid,
        "title": f"Opportunity {oid}",
        "status": "mixed_evidence",
        "status_rationale": "Support and a contradiction.",
        "thesis": f"Thesis {oid}.",
        "supporting": sup,
        "contradicting": con,
        "metrics": metrics or [],
        "gaps": [],
        "next_step": f"Next step {oid}.",
        "caveats": [],
        "integrity": integrity,
        "thesis_claim_type": "hypothesis",
        "why_it_matters": {"text": f"Why {oid}.", "claim_type": "inference"},
        "risks": risks or [],
        "next_investigation": f"Question {oid}?",
        "related": {"analyses": [], "opportunities": [], "signals": []},
        "support_count": sum(r["integrity"] == "verified" for r in sup),
        "contradiction_count": sum(r["integrity"] == "verified" for r in con),
    }


def analysis(
    aid: str, n_rows: int = 3, *, presentation: str = "bar", status: str = "computed"
) -> dict[str, Any]:
    rows = [
        {"group": {"pain_point": f"pain_{i}"}, "value": 10.0 + i, "display": f"{10 + i}.0%"}
        for i in range(n_rows)
    ]
    return {
        "id": aid,
        "title": f"Analysis {aid}",
        "question": "What?",
        "category": "customer",
        "status": status,
        "op": "aggregate",
        "unit": "percent",
        "presentation": presentation,
        "denominator": {"label": "Gen Z respondents", "value": 400},
        "filters": [],
        "group_by": ["pain_point"],
        "value": None,
        "display": None,
        "rows": rows if status == "computed" else [],
        "provenance": {
            "dataset": "SURVEY:1",
            "source_code": "SURVEY",
            "source_title": "Gen Z survey",
            "version": 1,
            "table": "t",
            "rows_matched": 400,
            "computed_at": AT,
        },
        "caveats": [],
        "spec": {},
        "business_area": "Customer friction",
        "summary": "Pain 2 leads at 12.0%." if status == "computed" else None,
        "summary_status": "verified" if status == "computed" else "unverified",
        "interpretation": {"text": "Fit outweighs price.", "claim_type": "inference"},
        "used_by": {"signals": [], "opportunities": []},
    }


def world(
    signals: list[dict[str, Any]] | None = None,
    opportunities: list[dict[str, Any]] | None = None,
    analyses: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    brief = {
        "fixture_version": "ACME.v2",
        "label": "Curated analyst brief",
        "computed_at": AT,
        "corpus_check": {"status": "ok", "drifted_sources": []},
        "signals": signals or [],
        "opportunities": opportunities or [],
    }
    return brief, {"fixture_version": "ACME.v2", "computed_at": AT, "analyses": analyses or []}


def build(brief: dict[str, Any], listing: dict[str, Any], **body: Any) -> dict[str, Any]:
    return compose(brief, listing, DeckRequest(**body), workspace=WS, generated_at=AT)


def visible_strings(deck: dict[str, Any]) -> list[str]:
    """Every string a viewer sees on a slide (speaker notes excluded)."""
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key not in ("type", "kind", "claim_type", "status", "chart"):
                    walk(value)

    for slide in deck["slides"]:
        walk({k: v for k, v in slide.items() if k not in ("notes", "kind")})
    return out


def kinds(deck: dict[str, Any]) -> list[str]:
    return [s["kind"] for s in deck["slides"]]


def bullets(deck: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [
        item
        for s in deck["slides"]
        if s["kind"] == kind
        for b in s["blocks"]
        if b["type"] == "bullets"
        for item in b["items"]
    ]


def test_unverified_items_are_excluded_and_reported() -> None:
    bad = signal(
        "sig-bad",
        integrity="unverified",
        evidence=[ref("ACME/GONE@v1:P1", "Gone.", integrity="withdrawn")],
    )
    brief, listing = world([signal("sig-ok"), bad])
    deck = build(brief, listing, signal_ids=["sig-ok", "sig-bad"])
    assert [e["id"] for e in deck["excluded"]] == ["sig-bad"]
    assert deck["excluded"][0]["reason"]
    text = json.dumps(deck["slides"])
    assert "Statement sig-bad" not in text
    assert "Title sig-bad" not in text
    assert deck["counts"]["items"] == 1


def test_analysis_that_did_not_recompute_is_excluded() -> None:
    brief, listing = world(analyses=[analysis("a-ok"), analysis("a-bad", status="mismatch")])
    deck = build(brief, listing, analysis_ids=["a-ok", "a-bad"])
    assert [e["id"] for e in deck["excluded"]] == ["a-bad"]
    assert "Analysis a-bad" not in json.dumps(deck["slides"])


def test_partial_item_cites_only_verified_references() -> None:
    sig = signal(
        "sig-p",
        integrity="partial",
        evidence=[
            ref("ACME/GOOD@v1:P1", "Good quote."),
            ref("ACME/STALE@v1:P9", "Stale quote.", integrity="stale"),
        ],
        metrics=[metric("a-1", "Share", None)],
    )
    brief, listing = world([sig], analyses=[analysis("a-1")])
    deck = build(brief, listing, signal_ids=["sig-p"])
    blob = json.dumps(deck)
    assert "ACME/STALE" not in blob
    assert "Stale quote" not in blob
    assert [s["handle"] for s in deck["sources"]] == ["ACME/GOOD@v1:P1"]
    assert "quantitative" not in kinds(deck)  # its only metric was withheld


def test_observed_statement_without_verified_support_is_excluded() -> None:
    sig = signal(
        "sig-c",
        integrity="partial",
        evidence=[
            ref("ACME/X@v1:P1", "Contra.", role="contradict"),
            ref("ACME/Y@v1:P1", "Gone.", integrity="stale"),
        ],
    )
    brief, listing = world([sig])
    deck = build(brief, listing, signal_ids=["sig-c"])
    assert [e["id"] for e in deck["excluded"]] == ["sig-c"]


def test_interpretive_claims_are_labelled_and_facts_are_not() -> None:
    outlook = signal(
        "sig-f",
        "future_outlook",
        claim_type="forecast",
        implication={"text": "Plan for it.", "claim_type": "hypothesis"},
    )
    fact = signal("sig-o", implication={"text": "So what.", "claim_type": "inference"})
    brief, listing = world([outlook, fact], [opportunity("O1")])
    deck = build(brief, listing, signal_ids=["sig-f", "sig-o"], opportunity_ids=["O1"])
    by_text = {
        b["text"]: b["label"]
        for kind in ("customer_findings", "market_findings", "opportunity")
        for b in bullets(deck, kind)
    }
    assert by_text["Statement sig-f."] == "Forecast"
    assert by_text["Plan for it."] == "Hypothesis"
    assert by_text["Statement sig-o."] is None
    assert by_text["So what."] == "Inference"
    assert by_text["Thesis O1."] == "Hypothesis"
    assert by_text["Why O1."] == "Inference"


def test_forecast_on_a_partial_item_is_downgraded_to_hypothesis() -> None:
    outlook = signal(
        "sig-f",
        "future_outlook",
        claim_type="forecast",
        integrity="partial",
        evidence=[
            ref("ACME/A@v1:P1", "Context."),
            ref("ACME/B@v1:P1", "Projection.", integrity="stale"),
        ],
    )
    brief, listing = world([outlook])
    deck = build(brief, listing, signal_ids=["sig-f"])
    (item,) = [b for b in bullets(deck, "market_findings") if b["text"] == "Statement sig-f."]
    assert (item["claim_type"], item["label"]) == ("hypothesis", "Hypothesis")


def test_only_analyses_keeps_title_summary_and_appendix() -> None:
    brief, listing = world(analyses=[analysis("a-1")])
    deck = build(brief, listing, analysis_ids=["a-1"])
    assert kinds(deck) == ["title", "summary", "quantitative", "appendix"]
    chart = deck["slides"][2]["blocks"][0]
    assert chart["type"] == "chart"
    assert chart["categories"] == ["Pain 0", "Pain 1", "Pain 2"]
    assert chart["emphasis"] == 2
    assert chart["base"] == "Base: 400 Gen Z respondents"


def test_everything_excluded_still_yields_title_summary_appendix() -> None:
    brief, listing = world([signal("s1", integrity="unverified")])
    deck = build(brief, listing, signal_ids=["s1"])
    assert kinds(deck) == ["title", "summary", "appendix"]
    assert deck["counts"] == {"items": 0, "sources": 0, "slides": 3}


def test_wide_or_table_analyses_render_as_tables() -> None:
    brief, listing = world(
        analyses=[analysis("a-wide", 9), analysis("a-tab", 2, presentation="table")]
    )
    deck = build(brief, listing, analysis_ids=["a-wide", "a-tab"])
    types = [s["blocks"][0]["type"] for s in deck["slides"] if s["kind"] == "quantitative"]
    assert types == ["table", "table"]
    table = next(s for s in deck["slides"] if s["title"] == "Analysis a-wide")["blocks"][0]
    assert table["columns"] == ["Pain point", "Value"]
    assert len(table["rows"]) == 9


def test_metric_callouts_skip_withheld_values() -> None:
    sig = signal(
        "s1",
        integrity="partial",
        metrics=[metric("a-1", "Share named fit", 27.0), metric("a-1", "Withheld", None)],
    )
    brief, listing = world([sig], analyses=[analysis("a-1")])
    deck = build(brief, listing, signal_ids=["s1"])
    (slide,) = [s for s in deck["slides"] if s["kind"] == "quantitative"]
    (block,) = slide["blocks"]
    assert block["type"] == "metrics"
    assert [m["label"] for m in block["items"]] == ["Share named fit"]
    assert block["items"][0]["base"] == "Base: Gen Z respondents"


def test_long_sections_split_onto_continuation_slides() -> None:
    sigs = [
        signal(f"s{i}", implication={"text": f"Imp {i}.", "claim_type": "inference"})
        for i in range(5)
    ]
    brief, listing = world(sigs)
    deck = build(brief, listing, signal_ids=[s["id"] for s in sigs])
    slides = [s for s in deck["slides"] if s["kind"] == "customer_findings"]
    assert len(slides) == 3
    assert slides[0]["title"] == "Key customer findings"
    assert all(s["title"] == "Key customer findings (cont.)" for s in slides[1:])
    for s in slides:
        assert sum(len(b["items"]) for b in s["blocks"]) <= MAX_BULLETS


def test_no_handles_or_ids_in_visible_text() -> None:
    risk = {
        "text": "Risky.",
        "claim_type": "observed",
        "evidence": [ref("ACME/RISK@v1:P3", "Risk quote.")],
        "integrity": "verified",
    }
    sig = signal("sig-zq9", "risk_blocker", metrics=[metric("a-zq8", "Share", 27.0)])
    sig.update(title="Fit", statement="Fit leads.", evidence=[ref("ACME/S@v1:P1", "Fit q.")])
    opp = opportunity("opp-zq7", risks=[risk])
    opp.update(
        title="Fit promise",
        supporting=[ref("ACME/O@v1:P1", "Promise q.")],
        thesis="Promise fit.",
        why_it_matters={"text": "Returns.", "claim_type": "inference"},
        next_step="Model it.",
        next_investigation="Cost?",
    )
    table = analysis("a-zq8")
    table["title"] = "Pain points"
    brief, listing = world([sig], [opp], [table])
    deck = build(
        brief, listing, signal_ids=["sig-zq9"], opportunity_ids=["opp-zq7"], analysis_ids=["a-zq8"]
    )
    for text in visible_strings(deck):
        for needle in ("ACME/", "@v1", "zq9", "zq7", "zq8", "SURVEY:1"):
            assert needle not in text, text
    # the handles are kept for audit in speaker notes and the source list
    assert any(n["handle"] == "ACME/RISK@v1:P3" for s in deck["slides"] for n in s["notes"])


def _cites(slide: dict[str, Any]) -> set[int]:
    found: set[int] = set()
    for block in slide["blocks"]:
        for item in block.get("items", []):
            found.update(item.get("cites", []))
        found.update(block.get("cites", []))
    return found


def test_citations_agree_between_bullets_notes_and_appendix() -> None:
    shared = ref("ACME/SHARED@v1:P1", "Shared quote.")
    risk = {
        "text": "Risky.",
        "claim_type": "observed",
        "evidence": [ref("ACME/RISK@v1:P3", "Risk quote.")],
        "integrity": "verified",
    }
    brief, listing = world(
        [
            signal("s1", evidence=[shared], metrics=[metric("a-1", "Share", 27.0)]),
            signal("s2", "competitor_finding", evidence=[shared, ref("ACME/B@v1:P2", "B.")]),
        ],
        [opportunity("O1", risks=[risk], contradicting=[ref("ACME/C@v1:P1", "C.", "contradict")])],
        [analysis("a-1")],
    )
    deck = build(brief, listing, signal_ids=["s1", "s2"], opportunity_ids=["O1"])
    numbers = [s["n"] for s in deck["sources"]]
    assert numbers == list(range(1, len(numbers) + 1))
    assert deck["counts"]["sources"] == len(numbers)
    by_n = {s["n"]: s for s in deck["sources"]}
    for slide in deck["slides"]:
        if slide["kind"] == "appendix":
            continue
        assert {n["n"] for n in slide["notes"]} == _cites(slide), slide["title"]
        for note in slide["notes"]:
            assert note["handle"] == by_n[note["n"]]["handle"]
    listed = [
        item["n"]
        for s in deck["slides"]
        if s["kind"] == "appendix"
        for b in s["blocks"]
        for item in b["items"]
    ]
    assert listed == numbers
    # the shared passage is numbered once
    assert sum(s["handle"] == "ACME/SHARED@v1:P1" for s in deck["sources"]) == 1


def test_titles_default_and_override() -> None:
    brief, listing = world([signal("s1")])
    deck = build(brief, listing, signal_ids=["s1"])
    assert deck["title"] == "Strategic findings: Acme Footwear"
    assert deck["question"] is None
    title = deck["slides"][0]
    assert title["kind"] == "title"
    assert "Built from 1 verified finding" in title["meta"]
    custom = build(
        brief, listing, signal_ids=["s1"], title="  Gen Z\n growth ", question="Where to grow?"
    )
    assert (custom["title"], custom["question"]) == ("Gen Z growth", "Where to grow?")
    assert custom["slides"][0]["subtitle"] == "Where to grow?"


def test_opportunity_slide_and_next_steps() -> None:
    stale_risk = {
        "text": "Stale risk.",
        "claim_type": "observed",
        "evidence": [ref("ACME/R@v1:P1", "R.", integrity="stale")],
        "integrity": "unverified",
    }
    opp = opportunity(
        "O2",
        contradicting=[ref("ACME/C@v1:P1", "C.", "contradict")],
        risks=[stale_risk],
        metrics=[metric("a-1", "Top frustration", 7.0)],
        integrity="partial",
    )
    brief, listing = world(opportunities=[opp], analyses=[analysis("a-1")])
    deck = build(brief, listing, opportunity_ids=["O2"])
    assert "risks" not in kinds(deck)  # its only risk did not re-verify
    (slide,) = [s for s in deck["slides"] if s["kind"] == "opportunity"]
    assert slide["title"] == "Opportunity O2"
    assert slide["subtitle"] == "Growth opportunity · Mixed evidence"
    texts = [b["text"] for b in slide["blocks"][0]["items"]]
    assert "1 supporting and 1 contradicting passage" in texts
    assert "Top frustration: 7.0%" in texts
    (steps,) = [s for s in deck["slides"] if s["kind"] == "next_steps"]
    assert steps["subtitle"] == "From the analyst brief"
    assert [b["text"] for b in steps["blocks"][0]["items"]] == ["Next step O2.", "Question O2?"]
    summary = deck["slides"][1]["blocks"][0]["items"]
    assert [(i["title"], i["status_label"]) for i in summary] == [
        ("Opportunity O2", "Mixed evidence")
    ]


def test_unknown_ids_are_rejected() -> None:
    brief, listing = world([signal("s1")], analyses=[analysis("a-1")])
    with pytest.raises(UnknownItemsError) as err:
        build(brief, listing, signal_ids=["s1", "nope"], opportunity_ids=["O9"])
    assert err.value.unknown == ["nope", "O9"]


def test_composition_is_deterministic() -> None:
    brief, listing = world([signal("s1"), signal("s2", "competitor_finding")], [opportunity("O1")])
    body = {"signal_ids": ["s2", "s1"], "opportunity_ids": ["O1"]}
    assert build(brief, listing, **body) == build(brief, listing, **body)


def test_request_body_rules() -> None:
    with pytest.raises(ValidationError):
        DeckRequest()
    with pytest.raises(ValidationError):
        DeckRequest.model_validate({"signal_ids": ["s1"], "workspace": "OTHER"})
    with pytest.raises(ValidationError):
        DeckRequest(signal_ids=[f"s{i}" for i in range(31)])
    with pytest.raises(ValidationError):
        DeckRequest(signal_ids=["s1"], title="x" * 121)
    assert DeckRequest(signal_ids=["s1", "s1"]).signal_ids == ["s1"]
