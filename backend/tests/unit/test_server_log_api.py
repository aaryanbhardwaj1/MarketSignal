"""``GET /api/dev/logs`` through the real app (no database needed): access events, noise,
validation and dev-only mounting."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from marketsignal.api.app import create_app
from marketsignal.devtools import server_log
from marketsignal.devtools.server_log import ServerLogBuffer
from marketsignal.telemetry.access_log import safe_text
from tests.unit.test_app import _settings


@pytest.fixture(autouse=True)
def fresh_buffer(monkeypatch: pytest.MonkeyPatch) -> ServerLogBuffer:
    buffer = ServerLogBuffer(capacity=2000)  # the default: create_app keeps it
    monkeypatch.setattr(server_log, "_buffer", buffer)
    return buffer


def _logs(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/dev/logs", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _http(entries: list[dict[str, Any]], path: str) -> list[dict[str, Any]]:
    return [e for e in entries if e["http"] and e["http"]["path"] == path]


def test_access_entry_has_route_template_and_no_query_string() -> None:
    with TestClient(create_app(_settings())) as client:
        missing = client.get("/api/dev/does-not-exist?st=secret-token&x=1")
        assert missing.status_code == 404
        client.get("/healthz?probe=1", headers={"x-request-id": "rid-health"})
        body = _logs(client)

    assert body["scope"] == "api_process"
    assert body["capacity"] == 2000
    assert body["process_started_at"]
    [miss] = _http(body["entries"], "/api/dev/does-not-exist")
    assert miss["kind"] == "http"
    assert miss["level"] == "WARNING"
    assert miss["event"] == "http.request"
    assert miss["http"]["status"] == 404
    assert miss["http"]["method"] == "GET"
    assert miss["http"]["duration_ms"] >= 0
    assert miss["request_id"]
    assert "secret-token" not in repr(body)
    # health checks are noise: hidden by default, shown with include_noise
    assert _http(body["entries"], "/healthz") == []


def test_noise_is_shown_on_request_with_route_template() -> None:
    with TestClient(create_app(_settings())) as client:
        client.get("/healthz?probe=1", headers={"x-request-id": "rid-health"})
        body = _logs(client, include_noise="true")
    [health] = _http(body["entries"], "/healthz")
    assert health["http"]["route"] == "/healthz"
    assert health["request_id"] == "rid-health"
    assert health["fields"]["noise"] is True
    assert "/healthz" in body["routes"]


def test_logs_endpoint_marks_itself_as_noise_and_supports_after_seq() -> None:
    with TestClient(create_app(_settings())) as client:
        first = _logs(client, include_noise="true")
        second = _logs(client, include_noise="true", after_seq=first["latest_seq"] or 0)
    own = [e for e in second["entries"] if e["http"] and e["http"]["route"] == "/api/dev/logs"]
    assert own
    assert all(e["fields"]["noise"] is True for e in own)
    seqs = [e["seq"] for e in second["entries"]]
    assert seqs == sorted(seqs)


@pytest.mark.parametrize(
    "params",
    [
        {"level": "LOUD"},
        {"kind": "nope"},
        {"status_class": "6xx"},
        {"method": "G3T"},
        {"limit": 0},
        {"limit": 501},
        {"after_seq": -1},
        {"q": "x" * 201},
    ],
)
def test_bad_params_are_422(params: dict[str, Any]) -> None:
    with TestClient(create_app(_settings())) as client:
        response = client.get("/api/dev/logs", params=params)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides", [{"env": "prod"}, {"dev_endpoints_enabled": False}], ids=["prod", "disabled"]
)
def test_not_mounted_outside_dev(overrides: dict[str, Any]) -> None:
    with TestClient(create_app(_settings(**overrides))) as client:
        assert client.get("/api/dev/logs").status_code == 404
        series = client.get("/api/workspaces/NORTHSTAR/telemetry/series")
        assert series.status_code == 404


@pytest.mark.parametrize(
    "overrides", [{"env": "prod"}, {"dev_endpoints_enabled": False}], ids=["prod", "disabled"]
)
def test_nothing_is_captured_outside_dev(
    overrides: dict[str, Any], fresh_buffer: ServerLogBuffer
) -> None:
    with TestClient(create_app(_settings(**overrides))) as client:
        client.get("/healthz")
        client.get("/api/dev/does-not-exist")
        import logging

        logging.getLogger("marketsignal.test").warning("stdlib warning")
    assert fresh_buffer.snapshot()[0] == []


def test_long_paths_are_truncated_and_flagged() -> None:
    with TestClient(create_app(_settings())) as client:
        client.get("/api/dev/" + "a" * 60_000)  # the HTTP client caps URLs at 64 KiB
        body = _logs(client)
    [entry] = [e for e in body["entries"] if e["http"] and e["http"]["status"] == 404]
    assert len(entry["http"]["path"]) <= 200
    assert entry["fields"]["path_truncated"] is True


def test_control_characters_in_paths_are_replaced() -> None:
    assert safe_text("/x\ny\x1bz\x7fw\tv") == ("/x?y?z?w?v", False)
    assert safe_text("/" + "a" * 600) == ("/" + "a" * 511, True)
    with TestClient(create_app(_settings())) as client:
        client.get("/api/dev/x%0Ay%1Bz%7Fw")
        body = _logs(client)
    [entry] = [e for e in body["entries"] if e["http"] and e["http"]["status"] == 404]
    # the server log also cuts at "?" (query-string guard), so only the clean prefix remains
    assert entry["http"]["path"] == "/api/dev/x"
    assert "path_truncated" not in entry["fields"]


@pytest.mark.parametrize("supplied", ["x" * 65, "a b", "<script>", "rid/../1", ""])
def test_access_log_uses_the_same_replaced_request_id(supplied: str) -> None:
    with TestClient(create_app(_settings())) as client:
        response = client.get("/api/dev/missing", headers={"x-request-id": supplied})
        body = _logs(client)
    echoed = response.headers["x-request-id"]
    assert echoed != supplied
    assert len(echoed) == 32
    [entry] = _http(body["entries"], "/api/dev/missing")
    assert entry["request_id"] == echoed
