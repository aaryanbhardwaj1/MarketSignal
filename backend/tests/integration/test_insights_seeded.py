"""The committed NORTHSTAR curated brief, end to end, against a fresh copy of the seed corpus.

Uploads the 24 NORTHSTAR seed files (manifest ``upload_order``, so GENZ-TRENDS 2026 becomes v2)
into a new test workspace through the real upload API, rewrites the newest committed fixture's
handles to that workspace and serves it: every quoted passage (risks included) must verify,
every analysis must recompute, every item must roll up to ``verified``, every v2 analysis
summary must pass the number check, and nothing may be written to ``analytics_results``. It
follows whichever fixture version is newest, so a new ``NORTHSTAR.v<N>.json`` is checked here
before it can reach the demo."""

# ruff: noqa: F811
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.api.routers import insights as insights_router
from marketsignal.insights.fixture import newest_fixture_path, parse_fixture
from marketsignal.insights.service import clear_cache
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401
from tests.integration.test_insights_api import _brief, _result_rows

pytestmark = pytest.mark.integration

SEED = Path(__file__).resolve().parents[3] / "seed_data" / "generated"
WORKSPACE = "NORTHSTAR"


async def _seed(h: Harness, ws: str) -> None:
    manifest = json.loads((SEED / "manifest.json").read_text(encoding="utf-8"))
    uploads = [u for u in manifest["uploads"] if u["workspace_code"] == WORKSPACE]
    assert len(uploads) == 24
    for item in sorted(uploads, key=lambda u: u["upload_order"]):
        path = SEED / item["filename"]
        response = await h.upload(
            ws,
            path.name,
            path.read_bytes(),
            source_class=item["source_class"],
            confidentiality=item["confidentiality"],
            title=item["title"],
            source_code=item["source_code"],
        )
        assert response.status_code in (200, 202), response.text
    await h.drain()


def _refs(item: dict[str, Any]) -> list[dict[str, Any]]:
    refs = item.get("evidence") or [*item["supporting"], *item["contradicting"]]
    return [*refs, *(r for risk in item.get("risks", []) for r in risk["evidence"])]


async def test_newest_northstar_fixture_verifies_on_a_fresh_seed(
    harness: Harness, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = newest_fixture_path(WORKSPACE)
    assert path is not None
    clear_cache()
    ws = await harness.create_workspace()
    await _seed(harness, ws)
    raw = json.loads(path.read_text(encoding="utf-8").replace(f"{WORKSPACE}/", f"{ws}/"))
    fixture = parse_fixture({**raw, "workspace": ws})
    monkeypatch.setattr(
        insights_router, "load_fixture", lambda code: fixture if code == ws else None
    )
    before = await _result_rows(app_engine, ws)

    brief = await _brief(harness, ws)
    assert brief["fixture_version"] == fixture.fixture_version
    assert brief["corpus_check"] == {"status": "ok", "drifted_sources": []}
    items = [*brief["signals"], *brief["opportunities"]]
    assert len(items) == len(fixture.signals) + len(fixture.opportunities)
    failures = [
        f"{item['id']}: {ref['integrity']} {ref['handle']}"
        for item in items
        for ref in _refs(item)
        if ref["integrity"] != "verified"
    ]
    failures += [
        f"{item['id']}: metric withheld {m['label']}"
        for item in items
        for m in item["metrics"]
        if m["value"] is None
    ]
    failures += [f"{i['id']}: {i['integrity']}" for i in items if i["integrity"] != "verified"]

    listing = (await harness.client.get(f"/api/workspaces/{ws}/analytics/analyses")).json()
    analyses = listing["analyses"]
    assert [a["id"] for a in analyses] == [a.id for a in fixture.analyses]
    failures += [f"{a['id']}: {a['status']}" for a in analyses if a["status"] != "computed"]
    if fixture.schema_version >= 2:
        failures += [
            f"{a['id']}: summary {a['summary_status']}"
            for a in analyses
            if a["summary_status"] != "verified"
        ]
    assert not failures, "\n".join(failures)
    assert await _result_rows(app_engine, ws) == before
