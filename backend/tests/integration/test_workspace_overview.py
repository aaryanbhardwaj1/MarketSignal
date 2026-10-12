# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""``GET /api/workspaces/{ws}`` overview fields (final productization phase): sources by type
and class, datasets, analytics results, conversations and run counts (test-harness runs
excluded) and the latest readiness."""

from __future__ import annotations

import pytest

from marketsignal.providers.llm.fake import FakeLLM
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_runs_api import FACT, GOOD, _ask, _install, _seed, _stream

pytestmark = pytest.mark.integration

CSV = b"segment,nps_score\nGen Z,9\nMillennial,6\n"


async def _run(h: Harness, ws: str, *, model: str) -> None:
    _install(h, FakeLLM([GOOD], model=model, repeat_last=True))
    _, run = await _ask(h, ws, "fit inconsistency share", mode="standard")
    events = await _stream(h, run["stream_url"])
    assert events[-1]["event"] == "done"


async def test_overview_fields(harness: Harness) -> None:
    ws = await harness.create_workspace()
    empty = (await harness.client.get(f"/api/workspaces/{ws}")).json()
    assert empty["runs"] == {
        "total": 0,
        "by_mode": {},
        "by_termination_state": {},
        "last_run_at": None,
    }
    assert empty["last_ready_at"] is None
    assert empty["dataset_count"] == empty["conversation_count"] == 0

    await _seed(harness, ws, FACT)
    upload = await harness.upload(ws, "survey.csv", CSV, source_code="SURVEY-T")
    assert upload.status_code in (200, 202), upload.text
    await harness.drain()
    await _run(harness, ws, model="fake-llm")  # harness run: excluded
    await _run(harness, ws, model="sim-model")

    body = (await harness.client.get(f"/api/workspaces/{ws}")).json()
    for key in ("id", "code", "corpus_version", "sources_by_status", "parent_count"):
        assert key in body  # the existing detail is kept
    assert sum(body["sources_by_type"].values()) == 2
    assert sum(body["sources_by_class"].values()) == 2
    assert body["dataset_count"] == 1
    assert body["analytics_result_count"] == 0
    assert body["conversation_count"] == 1
    runs = body["runs"]
    assert runs["total"] == 1
    assert runs["by_mode"] == {"standard": 1}
    assert sum(runs["by_termination_state"].values()) == 1
    assert runs["last_run_at"] is not None
    assert body["last_ready_at"] is not None
