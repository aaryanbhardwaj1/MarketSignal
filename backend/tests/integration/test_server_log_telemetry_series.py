# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""Server log (``GET /api/dev/logs``) and telemetry series (E12) end to end, as ``ms_app``.

The server log must carry the request's own access entry with its route template and without
the query string (stream tokens travel in ``?st=``), run/verification events by id, and never
any question or answer text. The series must be ordered oldest first, exclude test-harness runs
by default and never show another workspace's runs.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import pytest

from marketsignal.providers.llm.fake import FakeLLM
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_runs_api import FACT, GOOD, OTHER, _ask, _install, _seed, _stream

pytestmark = pytest.mark.integration

QUESTION = "What share of Gen Z buyers name fit as their top frustration?"
ANSWER_FRAGMENT = "Fit inconsistency is the top frustration"


async def _get(h: Harness, path: str, **params: Any) -> Any:
    response = await h.client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _run(h: Harness, ws: str) -> tuple[str, str]:
    _, run = await _ask(h, ws, QUESTION, mode="standard")
    await _stream(h, run["stream_url"])
    return str(run["run_id"]), str(run["stream_url"])


async def test_server_log_records_access_and_run_events_without_content(
    harness: Harness,
) -> None:
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    run_id, stream_url = await _run(harness, ws)
    await _get(harness, f"/api/workspaces/{ws}/telemetry/summary", include_test_runs="true")

    template = "/api/workspaces/{ws}/telemetry/summary"
    body = await _get(harness, "/api/dev/logs", route=template, limit=500)
    own = [e for e in body["entries"] if e["workspace"] == ws]
    assert own, body["entries"][:3]
    entry = own[0]
    assert entry["kind"] == "http"
    assert entry["level"] == "INFO"
    assert entry["http"]["route"] == template
    assert entry["http"]["path"] == f"/api/workspaces/{ws}/telemetry/summary"
    assert entry["http"]["status"] == 200
    assert entry["request_id"]
    assert template in body["routes"]

    everything = await _get(harness, "/api/dev/logs", include_noise="true", q=run_id, limit=500)
    events = {e["event"] for e in everything["entries"]}
    assert {"run.started", "run.finished", "verification.attempt"} <= events
    finished = next(e for e in everything["entries"] if e["event"] == "run.finished")
    assert finished["kind"] == "run"
    assert finished["fields"]["status"] == "completed"
    streams = [e for e in everything["entries"] if e["fields"].get("stream") is True]
    assert streams
    assert streams[0]["http"]["path"] == urlsplit(stream_url).path

    full = repr(await _get(harness, "/api/dev/logs", include_noise="true", limit=500))
    token = urlsplit(stream_url).query.split("st=", 1)[1]
    assert token not in full
    assert QUESTION not in full
    assert ANSWER_FRAGMENT not in full
    assert "?" not in "".join(
        e["http"]["path"] for e in everything["entries"] if e["http"] is not None
    )


async def test_series_orders_runs_hides_test_runs_and_isolates_workspaces(
    harness: Harness,
) -> None:
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws, other = await harness.create_workspace(), await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    await _seed(harness, other, FACT, OTHER)
    ids = [(await _run(harness, ws))[0] for _ in range(3)]
    foreign = (await _run(harness, other))[0]
    base = f"/api/workspaces/{ws}/telemetry/series"

    hidden = await _get(harness, base)
    assert hidden["points"] == []
    assert hidden["test_runs_excluded"] == 3

    shown = await _get(harness, base, include_test_runs="true")
    assert [p["id"] for p in shown["points"]] == ids  # oldest first
    assert shown["n"] == 3
    assert shown["truncated"] is False
    assert foreign not in {p["id"] for p in shown["points"]}
    point = shown["points"][0]
    assert set(point["stages"]) == {
        "retrieval",
        "agent",
        "pack",
        "synthesis",
        "verification",
        "first_token",
    }
    assert point["stages"]["agent"] is None  # not recorded: never zero-filled
    assert point["stages"]["retrieval"] is not None
    assert point["mode"] == "standard"
    assert point["status"] == "completed"
    assert point["evidence_count"] >= 1
    assert isinstance(point["degraded"], bool)
    assert "question" not in point

    latest = await _get(harness, base, include_test_runs="true", limit=1)
    assert [p["id"] for p in latest["points"]] == ids[-1:]
    assert latest["truncated"] is True

    theirs = await _get(
        harness, f"/api/workspaces/{other}/telemetry/series", include_test_runs="true"
    )
    assert [p["id"] for p in theirs["points"]] == [foreign]

    summary = await _get(
        harness, f"/api/workspaces/{ws}/telemetry/summary", include_test_runs="true"
    )
    assert summary["rates"]["success"] == 1.0
    assert summary["rates"]["failed"] == 0.0
    assert summary["rates"]["cancelled"] == 0.0
    assert summary["errors"] == []
    assert summary["evidence_pack"]["size"]["n"] == 3
    assert summary["evidence_pack"]["size"]["p50"] >= 1


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 2001}, {"since": "2026-01-01T00:00:00"}, {"mode": "deep"}],
)
async def test_series_validates_params(harness: Harness, params: dict[str, Any]) -> None:
    ws = await harness.create_workspace()
    response = await harness.client.get(f"/api/workspaces/{ws}/telemetry/series", params=params)
    assert response.status_code == 422
