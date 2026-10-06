# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""A6: every verified synthesis attempt is persisted to ``verification_attempts``."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.providers.llm.fake import FakeLLM
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_runs_api import FACT, GOOD, _ask, _install, _scoped, _seed, _stream

pytestmark = pytest.mark.integration

# Fails verification: the only Answer sentence states a figure no evidence supports.
BAD = "### Answer\nFit inconsistency frustrates 61 percent of Gen Z buyers [E1].\n"


async def _attempts(engine: AsyncEngine, ws: str, run_id: str) -> list[tuple[int, str, dict]]:
    async with engine.begin() as conn:
        await _scoped(conn, ws)
        rows = await conn.execute(
            text(
                "SELECT attempt, disposition, report::text FROM verification_attempts "
                "WHERE query_run_id = CAST(:r AS uuid) ORDER BY attempt"
            ),
            {"r": run_id},
        )
        return [(a, d, json.loads(r)) for a, d, r in rows.all()]


async def test_run_persists_one_row_per_verified_attempt(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    _install(harness, FakeLLM([BAD, GOOD]))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "What share of Gen Z buyers name fit as a frustration?")
    events = await _stream(harness, run["stream_url"])
    final = next(e for e in events if e["event"] == "final")["data"]
    assert final["verification"]["passed"] is True
    assert "rejected" not in final["verification"]  # dropped drafts stay out of the UI payload

    rows = await _attempts(app_engine, ws, run["run_id"])
    assert [(a, d) for a, d, _ in rows] == [(1, "regenerate"), (2, "accepted")]
    first = rows[0][2]
    assert first["regeneration_requested"] is True
    assert "answer_missing" in first["failure_categories"]
    assert first["rejected"][0]["aliases"] == ["E1"]
    assert first["rejected"][0]["reason"] == "numbers_not_in_cited_evidence"
    assert first["evidence_checked"] == ["E1"]
    assert first["evidence_handles"][0].startswith(f"{ws}/")
    assert rows[1][2]["regeneration_requested"] is False


async def test_two_failures_record_fallback(harness: Harness, app_engine: AsyncEngine) -> None:
    _install(harness, FakeLLM([BAD, BAD]))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "What share of Gen Z buyers name fit as a frustration?")
    await _stream(harness, run["stream_url"])
    rows = await _attempts(app_engine, ws, run["run_id"])
    assert [(a, d) for a, d, _ in rows] == [(1, "regenerate"), (2, "fallback")]
