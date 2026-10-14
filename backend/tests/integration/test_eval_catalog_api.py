"""Evaluation catalog API (E11): dev-only, read-only, closed run-id set.

No database or model is needed: the endpoints serve the precomputed catalog. The app is built
with an unreachable database (as in tests/unit/test_app.py) and the LLM disabled.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from marketsignal.api.app import create_app
from marketsignal.config import Settings

pytestmark = pytest.mark.integration

UNREACHABLE_DB = "postgresql+psycopg://ms_app:x@127.0.0.1:1/marketsignal"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "env": "test",
        "database_url": SecretStr(UNREACHABLE_DB),
        "redis_url": None,
        "log_json": False,
        "llm_enabled": False,
        "stream_token_secret": SecretStr("integration-stream-token-secret-0123456789"),
        "mcp_token_key": SecretStr("integration-mcp-capability-key-0123456789ab"),
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(_settings())) as c:
        yield c


def test_catalog_is_served_with_etag(client: TestClient) -> None:
    res = client.get("/api/dev/eval/catalog")
    assert res.status_code == 200
    body = res.json()
    assert body["schema_version"] == 1
    assert len(body["failure_runs"]) == 7
    etag = res.headers["etag"]
    again = client.get("/api/dev/eval/catalog", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_items_page_and_bucket_filter(client: TestClient) -> None:
    res = client.get("/api/dev/eval/runs/p3-grounded-live/items", params={"limit": 10})
    assert res.status_code == 200
    page = res.json()
    assert page["run_id"] == "p3-grounded-live"
    assert page["total"] == 76
    assert len(page["items"]) == 10
    assert page["items"][0]["phase"] == "grounded"
    fp = client.get(
        "/api/dev/eval/runs/p3-grounded-live/items",
        params={"bucket": "verifier_false_positive", "limit": 50},
    ).json()
    assert fp["total"] == len(fp["items"]) > 0
    assert all(
        i["failure"]["final_classification"] == "verifier_false_positive" for i in fp["items"]
    )


def test_ragas_section_and_items_by_configuration(client: TestClient) -> None:
    ragas = client.get("/api/dev/eval/catalog").json()["ragas"]
    assert [r["id"] for r in ragas["runs"]] == ["ragas-p3-live-v0", "ragas-p4-research-test"]
    res = client.get(
        "/api/dev/eval/runs/ragas-p4-research-test/items",
        params={"bucket": "research", "limit": 50},
    )
    assert res.status_code == 200
    page = res.json()
    assert page["run_id"] == "ragas-p4-research-test"
    assert page["total"] == 30
    assert {i["phase"] for i in page["items"]} == {"ragas"}
    assert {i["configuration"] for i in page["items"]} == {"research"}


def test_limit_above_fifty_is_a_validation_error(client: TestClient) -> None:
    res = client.get("/api/dev/eval/runs/p2-test-c3/items", params={"limit": 51})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("run_id", ["nope", "%2E%2E", "P3-GROUNDED-LIVE", "p2-test-c3.json"])
def test_unknown_or_traversal_run_id_is_404(client: TestClient, run_id: str) -> None:
    res = client.get(f"/api/dev/eval/runs/{run_id}/items")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "EVAL_RUN_NOT_FOUND"


@pytest.mark.parametrize("path", ["..", "..%2Fcatalog.v1", "..%2F..%2Fsettings", "a%2Fb"])
def test_encoded_separators_never_reach_a_file(client: TestClient, path: str) -> None:
    """Dot segments are normalised and a decoded slash no longer matches the route: a 404,
    never file content."""
    res = client.get(f"/api/dev/eval/runs/{path}/items")
    assert res.status_code == 404
    assert res.json()["error"]["code"] in {"EVAL_RUN_NOT_FOUND", "NOT_FOUND"}


def test_router_absent_in_prod() -> None:
    settings = _settings(
        env="prod",
        stream_token_secret=SecretStr("prod-stream-token-secret-0123456789abcdef"),
        mcp_token_key=SecretStr("prod-mcp-capability-key-0123456789abcdef"),
    )
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/dev/eval/catalog").status_code == 404
        assert c.get("/api/dev/eval/runs/p2-test-c3/items").status_code == 404


def test_router_absent_when_dev_endpoints_disabled() -> None:
    with TestClient(create_app(_settings(dev_endpoints_enabled=False))) as c:
        assert c.get("/api/dev/eval/catalog").status_code == 404
