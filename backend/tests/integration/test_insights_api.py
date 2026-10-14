"""Curated analyst brief API (plan §5.4) over harness-uploaded sources, with a synthetic
mini-fixture injected through the router's loader: verified, stale and withdrawn evidence,
computed / mismatch / unavailable analyses, no analytics rows written, workspace isolation."""

# ruff: noqa: F811
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.api.routers import insights as insights_router
from marketsignal.insights.fixture import Fixture, parse_fixture
from marketsignal.insights.service import clear_cache
from tests.fixtures.factories import make_csv
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401

pytestmark = pytest.mark.integration

FIT = "Fit inconsistency is the top frustration for young shoppers in this study."
GONE = "Delivery speed complaints doubled in the third quarter of the year."
CSV = make_csv([["segment", "score"], ["A", 1], ["A", 3], ["B", 5]])


async def _upload(h: Harness, ws: str, name: str, body: bytes, code: str) -> None:
    response = await h.upload(ws, name, body, source_code=code)
    assert response.status_code in (200, 202), response.text
    await h.drain()


async def _scoped(conn: Any, ws: str) -> None:
    await conn.execute(
        text(
            "SELECT set_config('app.workspace_id', "
            "(SELECT id::text FROM workspaces WHERE code = :c), true)"
        ),
        {"c": ws},
    )


async def _handle(engine: AsyncEngine, ws: str, needle: str) -> str:
    async with engine.begin() as conn:
        await _scoped(conn, ws)
        rows = (await conn.execute(text("SELECT handle, text FROM parent_chunks"))).all()
    hits = [h for h, t in rows if needle in re.sub(r"\s+", " ", t)]
    assert len(hits) == 1, rows
    return str(hits[0])


async def _result_rows(engine: AsyncEngine, ws: str) -> int:
    async with engine.begin() as conn:
        await _scoped(conn, ws)
        return int(
            (await conn.execute(text("SELECT count(*) FROM analytics_results"))).scalar_one()
        )


def _fixture(ws: str, fit_handle: str, gone_handle: str) -> Fixture:
    spec = {
        "dataset": "SURV:1",
        "metrics": [{"fn": "mean", "column": "score"}],
        "group_by": ["segment"],
        "order": {"by": "group", "direction": "asc"},
    }

    def analysis(aid: str, a_value: float) -> dict[str, Any]:
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
            "parts": [{"spec": spec}],
            "expected": [
                {"group": {"segment": "A"}, "value": a_value},
                {"group": {"segment": "B"}, "value": 5},
            ],
        }

    def ev(handle: str, quote_: str, role: str = "support") -> dict[str, Any]:
        return {"handle": handle, "quote": quote_, "role": role}

    return parse_fixture(
        {
            "schema_version": 1,
            "fixture_version": f"{ws}.test",
            "workspace": ws,
            "label": "Curated analyst brief",
            "corpus": {"MEMO": {"version": 1}, "GONE": {"version": 1}, "SURV": {"version": 1}},
            "analyses": [analysis("score-by-segment", 2.0), analysis("score-drifted", 9.0)],
            "signals": [
                {
                    "id": "fit",
                    "category": "Customer friction",
                    "title": "Fit",
                    "statement": "Fit inconsistency leads.",
                    "evidence": [ev(fit_handle, FIT)],
                    "metrics": [
                        {
                            "label": "Mean score, A",
                            "pick": {"analysis_id": "score-by-segment", "group": {"segment": "A"}},
                        }
                    ],
                },
                {
                    "id": "delivery",
                    "category": "Service",
                    "title": "Delivery",
                    "statement": "Delivery complaints rose.",
                    "evidence": [ev(gone_handle, GONE)],
                    "metrics": [
                        {
                            "label": "Drifted",
                            "pick": {"analysis_id": "score-drifted", "group": {"segment": "A"}},
                        }
                    ],
                },
            ],
            "opportunities": [
                {
                    "id": "O1",
                    "title": "Fit Promise",
                    "status": "supported",
                    "status_rationale": "Consistent signal.",
                    "thesis": "A fit guarantee may help.",
                    "evidence": [ev(fit_handle, FIT), ev(gone_handle, GONE, "contradict")],
                    "gaps": ["No cost model."],
                    "next_step": "Model the cost.",
                }
            ],
        }
    )


@pytest.fixture
async def world(
    harness: Harness, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> tuple[Harness, str, str, Fixture]:
    clear_cache()
    ws, other = await harness.create_workspace(), await harness.create_workspace()
    await _upload(harness, ws, "memo.md", f"# Notes\n\n{FIT}\n\nA closing line.\n".encode(), "MEMO")
    await _upload(harness, ws, "gone.md", f"# Gone\n\n{GONE}\n".encode(), "GONE")
    await _upload(harness, ws, "surv.csv", CSV, "SURV")
    fixture = _fixture(ws, await _handle(app_engine, ws, FIT), await _handle(app_engine, ws, GONE))
    monkeypatch.setattr(
        insights_router, "load_fixture", lambda code: fixture if code == ws else None
    )
    return harness, ws, other, fixture


async def _brief(h: Harness, ws: str) -> dict[str, Any]:
    response = await h.client.get(f"/api/workspaces/{ws}/insights")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _source_id(h: Harness, ws: str, code: str) -> str:
    sources = (await h.client.get(f"/api/workspaces/{ws}/sources")).json()
    return str(next(s["source_id"] for s in sources if s["source_code"] == code))


async def test_verified_brief_maps_quotes_and_recomputes_without_writing(
    world: tuple[Harness, str, str, Fixture], app_engine: AsyncEngine
) -> None:
    h, ws, _other, _fx = world
    before = await _result_rows(app_engine, ws)
    brief = await _brief(h, ws)
    assert brief["fixture_version"] == f"{ws}.test"
    assert brief["label"] == "Curated analyst brief"
    assert brief["corpus_check"] == {"status": "ok", "drifted_sources": []}
    fit = brief["signals"][0]
    assert fit["integrity"] == "verified"
    ref = fit["evidence"][0]
    assert ref["integrity"] == "verified"
    assert ref["quote"] == FIT
    assert ref["child_id"]
    assert ref["source"]["code"] == "MEMO"
    assert ref["source"]["version"] == 1
    passage = (await h.client.get(f"/api/workspaces/{ws}/evidence/{quote(ref['handle'])}")).json()
    assert passage["text"][ref["char_start"] : ref["char_end"]] == FIT
    assert fit["metrics"][0] | {"analysis_id": "score-by-segment"} == {
        "analysis_id": "score-by-segment",
        "label": "Mean score, A",
        "value": 2.0,
        "display": "2.00",
        "unit": "score",
        "denominator_label": "rows",
        "derived": None,
    }
    # mismatch: the drifted analysis withholds every number, so its item is only partial
    delivery = brief["signals"][1]
    assert delivery["metrics"][0]["value"] is None
    assert delivery["metrics"][0]["display"] is None
    assert delivery["integrity"] == "partial"
    opp = brief["opportunities"][0]
    assert [e["role"] for e in opp["supporting"]] == ["support"]
    assert [e["role"] for e in opp["contradicting"]] == ["contradict"]
    assert opp["integrity"] == "verified"
    # schema v2 additions are always present; a v1 fixture serves their defaults
    assert {k: fit[k] for k in ("kind", "status", "claim_type", "implication", "gaps")} == {
        "kind": None,
        "status": None,
        "claim_type": None,
        "implication": None,
        "gaps": [],
    }
    assert fit["related"] == {"analyses": [], "opportunities": [], "signals": []}
    assert (fit["support_count"], fit["contradiction_count"]) == (1, 0)
    assert ref["states_projection"] is False
    assert {k: opp[k] for k in ("thesis_claim_type", "why_it_matters", "next_investigation")} == {
        "thesis_claim_type": None,
        "why_it_matters": None,
        "next_investigation": None,
    }
    assert opp["risks"] == []
    assert (opp["support_count"], opp["contradiction_count"]) == (1, 1)

    listing = (await h.client.get(f"/api/workspaces/{ws}/analytics/analyses")).json()
    by_id = {a["id"]: a for a in listing["analyses"]}
    ok, bad = by_id["score-by-segment"], by_id["score-drifted"]
    assert ok["status"] == "computed"
    assert [(r["group"], r["value"]) for r in ok["rows"]] == [
        ({"segment": "A"}, 2.0),
        ({"segment": "B"}, 5.0),
    ]
    assert ok["denominator"] == {"label": "rows", "value": 3}
    assert ok["provenance"]["source_code"] == "SURV"
    assert ok["provenance"]["rows_matched"] == 3
    assert (ok["business_area"], ok["summary"], ok["interpretation"]) == (None, None, None)
    assert ok["summary_status"] == "absent"
    assert ok["used_by"] == {"signals": ["fit"], "opportunities": []}
    assert bad["used_by"] == {"signals": ["delivery"], "opportunities": []}
    assert bad["status"] == "mismatch"
    assert bad["rows"] == []
    assert bad["value"] is None
    assert bad["denominator"] is None
    assert bad["provenance"]["rows_matched"] is None
    one = await h.client.get(f"/api/workspaces/{ws}/analytics/analyses/score-by-segment")
    assert one.status_code == 200
    assert one.json()["id"] == "score-by-segment"
    missing = await h.client.get(f"/api/workspaces/{ws}/analytics/analyses/nope")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
    assert await _result_rows(app_engine, ws) == before


async def test_other_workspace_gets_an_empty_brief(
    world: tuple[Harness, str, str, Fixture],
) -> None:
    h, _ws, other, _fx = world
    brief = await _brief(h, other)
    assert brief["fixture_version"] is None
    assert brief["signals"] == []
    assert brief["opportunities"] == []
    listing = (await h.client.get(f"/api/workspaces/{other}/analytics/analyses")).json()
    assert listing["fixture_version"] is None
    assert listing["analyses"] == []
    gone = await h.client.get(f"/api/workspaces/{other}/analytics/analyses/score-by-segment")
    assert gone.status_code == 404
    unknown = await h.client.get("/api/workspaces/NOPE0000/insights")
    assert unknown.status_code == 404


async def test_superseded_and_purged_evidence_is_stale_or_withdrawn(
    world: tuple[Harness, str, str, Fixture],
) -> None:
    h, ws, _other, _fx = world
    await _upload(h, ws, "memo.md", b"# Notes\n\nThe notes were rewritten entirely.\n", "MEMO")
    purge = await h.client.delete(f"/api/workspaces/{ws}/sources/{await _source_id(h, ws, 'GONE')}")
    assert purge.status_code == 200, purge.text
    brief = await _brief(h, ws)
    fit, delivery = brief["signals"]
    stale = fit["evidence"][0]
    assert stale["integrity"] == "stale"
    assert stale["quote"] is None
    assert stale["char_start"] is None
    assert stale["child_id"] is None
    assert fit["integrity"] == "unverified"
    withdrawn = delivery["evidence"][0]
    assert withdrawn["integrity"] == "withdrawn"
    assert withdrawn["quote"] is None
    assert withdrawn["source"]["code"] == "GONE"
    assert stale["states_projection"] is withdrawn["states_projection"] is False
    assert delivery["integrity"] == "unverified"
    assert brief["corpus_check"]["status"] == "drift"
    assert {"MEMO", "GONE"} <= set(brief["corpus_check"]["drifted_sources"])


async def test_purged_dataset_makes_analyses_unavailable(
    world: tuple[Harness, str, str, Fixture],
) -> None:
    h, ws, _other, _fx = world
    purge = await h.client.delete(f"/api/workspaces/{ws}/sources/{await _source_id(h, ws, 'SURV')}")
    assert purge.status_code == 200, purge.text
    listing = (await h.client.get(f"/api/workspaces/{ws}/analytics/analyses")).json()
    assert {a["status"] for a in listing["analyses"]} == {"unavailable"}
    assert all(a["rows"] == [] and a["value"] is None for a in listing["analyses"])
    brief = await _brief(h, ws)
    assert brief["signals"][0]["metrics"][0]["value"] is None
    assert brief["signals"][0]["integrity"] == "partial"
