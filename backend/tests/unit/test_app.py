from fastapi.testclient import TestClient
from pydantic import SecretStr

from marketsignal.api.app import create_app
from marketsignal.config import Settings

# Port 1 on localhost refuses connections immediately: no services needed for these tests.
UNREACHABLE_DB = "postgresql+psycopg://ms_app:x@127.0.0.1:1/marketsignal"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "env": "test",
        "database_url": SecretStr(UNREACHABLE_DB),
        "redis_url": None,
        "log_json": False,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_healthz_is_dependency_free() -> None:
    with TestClient(create_app(_settings())) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_readyz_reports_not_ready_when_database_unreachable() -> None:
    with TestClient(create_app(_settings())) as client:
        response = client.get("/readyz")
    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "not_ready"
    assert body["checks"]["database"]["status"] == "failed"
    assert body["checks"]["redis"]["status"] == "degraded"


def test_readyz_hides_error_details_in_prod() -> None:
    with TestClient(create_app(_settings(env="prod"))) as client:
        body = client.get("/readyz").json()
    assert all("detail" not in check for check in body["checks"].values())


def test_request_id_is_propagated() -> None:
    with TestClient(create_app(_settings())) as client:
        response = client.get("/healthz", headers={"x-request-id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"


def test_metrics_requires_token_when_configured() -> None:
    app = create_app(_settings(metrics_token=SecretStr("t0ken")))
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 401
        ok = client.get("/metrics", headers={"authorization": "Bearer t0ken"})
    assert ok.status_code == 200


def test_docs_disabled_in_prod() -> None:
    with TestClient(create_app(_settings(env="prod"))) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
