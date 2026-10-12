# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""``GET /api/workspaces/{ws}/conversations`` (final productization phase): ordering, keyset
cursor, ``q``, the curated ``featured`` list, test-run exclusion, title fallback, isolation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from marketsignal.demo import featured as featured_module
from marketsignal.providers.llm.fake import FakeLLM
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_runs_api import FACT, GOOD, OTHER, _install, _seed, _stream

pytestmark = pytest.mark.integration

REAL_MODEL = "sim-model"  # any synthesis model other than the harness's "fake-llm"
Q_TEST = "Which frustration do Gen Z buyers name most often?"
Q_REAL = "What share of Gen Z buyers name fit as their top frustration?"
Q_OTHER = "How did northeast store traffic change?"


@dataclass
class Seeded:
    ws: str
    test_conv: str
    real_conv: str
    other_conv: str
    titled_conv: str


async def _run(h: Harness, ws: str, question: str, *, model: str) -> str:
    _install(h, FakeLLM([GOOD], model=model, repeat_last=True))
    created = await h.client.post(f"/api/workspaces/{ws}/conversations", json={})
    conversation: str = created.json()["conversation_id"]
    started = await h.client.post(
        f"/api/workspaces/{ws}/conversations/{conversation}/runs",
        json={"question": question, "mode": "standard"},
    )
    assert started.status_code == 202, started.text
    events = await _stream(h, started.json()["stream_url"])
    assert events[-1]["event"] == "done"
    return conversation


async def _seeded(h: Harness) -> Seeded:
    ws = await h.create_workspace()
    await _seed(h, ws, FACT, OTHER)
    test_conv = await _run(h, ws, Q_TEST, model="fake-llm")
    real_conv = await _run(h, ws, Q_REAL, model=REAL_MODEL)
    other_conv = await _run(h, ws, Q_OTHER, model=REAL_MODEL)
    titled = await h.client.post(
        f"/api/workspaces/{ws}/conversations", json={"title": "Pricing review 100%"}
    )
    assert titled.status_code == 201, titled.text
    return Seeded(ws, test_conv, real_conv, other_conv, titled.json()["conversation_id"])


async def _list(h: Harness, ws: str, **params: Any) -> dict[str, Any]:
    response = await h.client.get(f"/api/workspaces/{ws}/conversations", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert set(body) == {"items", "next_cursor"}
    return body


def _ids(body: dict[str, Any]) -> list[str]:
    return [item["conversation_id"] for item in body["items"]]


async def test_list_shape_order_titles_and_test_run_exclusion(harness: Harness) -> None:
    s = await _seeded(harness)
    body = await _list(harness, s.ws)
    ids = _ids(body)
    assert set(ids) == {s.real_conv, s.other_conv, s.titled_conv}  # harness run hidden
    assert body["next_cursor"] is None
    keys = [(i["updated_at"], i["conversation_id"]) for i in body["items"]]
    assert keys == sorted(keys, reverse=True)

    by_id = {i["conversation_id"]: i for i in body["items"]}
    real = by_id[s.real_conv]
    assert real["title"] == Q_REAL
    assert real["title_source"] == "first_question"
    assert real["message_count"] == 2
    assert real["featured"] is False
    last_run = real["last_run"]
    assert set(last_run) == {
        "run_id",
        "mode",
        "status",
        "termination_state",
        "degradation_flags",
        "created_at",
        "finished_at",
    }
    assert last_run["mode"] == "standard"
    assert last_run["status"] == "completed"
    assert isinstance(last_run["degradation_flags"], list)
    titled = by_id[s.titled_conv]
    assert titled["title"] == "Pricing review 100%"
    assert titled["title_source"] == "title"
    assert titled["message_count"] == 0
    assert titled["last_run"] is None

    with_tests = await _list(harness, s.ws, include_test_runs="true")
    assert s.test_conv in _ids(with_tests)
    assert len(_ids(with_tests)) == 4


async def test_cursor_pages_are_stable_and_complete(harness: Harness) -> None:
    s = await _seeded(harness)
    full = _ids(await _list(harness, s.ws, include_test_runs="true"))
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params: dict[str, Any] = {"limit": 1, "include_test_runs": "true"}
        if cursor:
            params["cursor"] = cursor
        page = await _list(harness, s.ws, **params)
        seen += _ids(page)
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == full
    assert len(set(seen)) == len(seen) == 4


async def test_q_filters_on_title_and_first_question(harness: Harness) -> None:
    s = await _seeded(harness)
    assert _ids(await _list(harness, s.ws, q="top frustration")) == [s.real_conv]
    assert _ids(await _list(harness, s.ws, q="pricing")) == [s.titled_conv]
    assert _ids(await _list(harness, s.ws, q="100%")) == [s.titled_conv]
    assert _ids(await _list(harness, s.ws, q="%")) == [s.titled_conv]  # literal, not match-all
    assert _ids(await _list(harness, s.ws, q="_")) == []
    assert _ids(await _list(harness, s.ws, q="frustration")) == [s.real_conv]
    both = await _list(harness, s.ws, q="frustration", include_test_runs="true")
    assert set(_ids(both)) == {s.real_conv, s.test_conv}


async def test_featured_list_follows_curated_order(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await _seeded(harness)
    missing = str(uuid.uuid4())
    curated = tuple(uuid.UUID(c) for c in (s.other_conv, missing, s.titled_conv, s.real_conv))
    monkeypatch.setattr(
        featured_module, "featured_ids", lambda code: curated if code == s.ws else ()
    )
    body = await _list(harness, s.ws, featured="true")
    assert _ids(body) == [s.other_conv, s.titled_conv, s.real_conv]  # missing id dropped
    assert body["next_cursor"] is None
    assert all(i["featured"] for i in body["items"])
    assert _ids(await _list(harness, s.ws, featured="true", limit=2)) == [
        s.other_conv,
        s.titled_conv,
    ]
    flags = {i["conversation_id"]: i["featured"] for i in (await _list(harness, s.ws))["items"]}
    assert flags == {s.real_conv: True, s.other_conv: True, s.titled_conv: True}


async def test_empty_workspace_isolation_and_validation(harness: Harness) -> None:
    s = await _seeded(harness)
    other = await harness.create_workspace()
    assert await _list(harness, other) == {"items": [], "next_cursor": None}
    assert await _list(harness, other, featured="true") == {"items": [], "next_cursor": None}
    missing = await harness.client.get("/api/workspaces/TNOPE000000/conversations")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    # A foreign conversation is invisible: its messages 404 from the other workspace.
    foreign = await harness.client.get(
        f"/api/workspaces/{other}/conversations/{s.real_conv}/messages"
    )
    assert foreign.status_code == 404
    for params in ({"limit": 0}, {"limit": 101}, {"cursor": "not-a-cursor"}):
        bad = await harness.client.get(f"/api/workspaces/{s.ws}/conversations", params=params)
        assert bad.status_code == 422, params
        assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
