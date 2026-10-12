# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""``GET …/runs/{run_id}/verification`` (final productization phase): per-attempt summaries
that never include the rejected model spans; a foreign or unknown run is 404."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.providers.llm.fake import FakeLLM
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_runs_api import FACT, GOOD, _ask, _install, _scoped, _seed, _stream

pytestmark = pytest.mark.integration

SPAN_CANARY = "REJECTED-SPAN-CANARY-5521 a dropped model sentence"


async def _completed_run(h: Harness, ws: str) -> str:
    _install(h, FakeLLM([GOOD], repeat_last=True))
    await _seed(h, ws, FACT)
    _, run = await _ask(h, ws, "fit inconsistency share", mode="standard")
    events = await _stream(h, run["stream_url"])
    assert events[-1]["event"] == "done"
    run_id: str = run["run_id"]
    return run_id


async def _insert_attempt(engine: AsyncEngine, ws: str, run_id: str, attempt: int) -> None:
    report: dict[str, Any] = {
        "passed": False,
        "citations": 3,
        "repairs": ["alias", "numeric"],
        "failure_categories": ["numbers_in_gaps"],
        "result_ids": ["11111111-1111-1111-1111-111111111111"],
        "rejected": [
            {
                "span": SPAN_CANARY,
                "index": 1,
                "reason": "numbers_in_gaps",
                "aliases": ["E2"],
                "section": "Gaps & unknowns",
            }
        ],
    }
    async with engine.connect() as conn:
        await _scoped(conn, ws)
        await conn.execute(
            text(
                "INSERT INTO verification_attempts (workspace_id, query_run_id, attempt, "
                "disposition, report) VALUES (current_setting('app.workspace_id')::uuid, :r, "
                ":a, 'regenerate', CAST(:rep AS jsonb))"
            ),
            {"r": run_id, "a": attempt, "rep": json.dumps(report)},
        )
        await conn.commit()


async def test_verification_summary_without_rejected_spans(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    ws = await harness.create_workspace()
    run_id = await _completed_run(harness, ws)
    url = f"/api/workspaces/{ws}/runs/{run_id}/verification"
    first = await harness.client.get(url)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["run_id"] == run_id
    assert body["attempts"], "the scripted run verified at least one attempt"
    assert body["final_disposition"] == body["attempts"][-1]["disposition"]
    assert body["attempts"][0]["disposition"] in ("accepted", "repaired")

    await _insert_attempt(app_engine, ws, run_id, attempt=2)
    response = await harness.client.get(url)
    assert response.status_code == 200, response.text
    assert SPAN_CANARY not in response.text
    assert "span" not in response.text
    last = response.json()["attempts"][-1]
    assert last == {
        "attempt": 2,
        "disposition": "regenerate",
        "passed": False,
        "citations": 3,
        "failure_categories": ["numbers_in_gaps"],
        "repairs_n": 2,
        "rejected": [
            {"reason": "numbers_in_gaps", "section": "Gaps & unknowns", "aliases": ["E2"]}
        ],
        "result_ids": ["11111111-1111-1111-1111-111111111111"],
    }
    assert response.json()["final_disposition"] == "regenerate"


async def test_foreign_and_unknown_runs_are_404(harness: Harness) -> None:
    ws = await harness.create_workspace()
    other = await harness.create_workspace()
    run_id = await _completed_run(harness, ws)
    for code, rid in ((other, run_id), (ws, str(uuid.uuid4()))):
        response = await harness.client.get(f"/api/workspaces/{code}/runs/{rid}/verification")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


async def test_run_without_attempts_has_no_disposition(harness: Harness) -> None:
    """A run whose synthesis never verified (provider down) has an empty summary."""
    from marketsignal.providers.llm.base import LLMUnavailableError
    from marketsignal.providers.llm.fake import ScriptedResponse

    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _install(harness, FakeLLM([ScriptedResponse(error=LLMUnavailableError("down"))]))
    _, run = await _ask(harness, ws, "fit inconsistency share", mode="standard")
    await _stream(harness, run["stream_url"])
    response = await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}/verification")
    assert response.status_code == 200, response.text
    assert response.json() == {"run_id": run["run_id"], "final_disposition": None, "attempts": []}
