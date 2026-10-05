from marketsignal.telemetry.logging import redact_sensitive


def _redact(**event: object) -> dict[str, object]:
    return dict(redact_sensitive(None, "info", dict(event)))


def test_sensitive_keys_are_redacted_case_insensitively() -> None:
    out = _redact(Authorization="Bearer abc", password="hunter2", event="x")
    assert out["Authorization"] == "[REDACTED]"
    assert out["password"] == "[REDACTED]"
    assert out["event"] == "x"


def test_dsn_credentials_are_scrubbed_from_strings() -> None:
    out = _redact(event="connect failed postgresql+psycopg://ms_app:s3cret@db:5432/marketsignal")
    assert "s3cret" not in str(out["event"])
    assert "postgresql+psycopg://[REDACTED]@db:5432/marketsignal" in str(out["event"])


def test_stream_token_query_parameter_is_scrubbed() -> None:
    out = _redact(event="GET /api/workspaces/w/runs/r/events?st=eyJhbGciOi.payload.sig&x=1")
    assert "eyJhbGciOi" not in str(out["event"])
    assert "?st=[REDACTED]&x=1" in str(out["event"])


def test_nested_structures_are_scrubbed() -> None:
    out = _redact(headers={"cookie": "session=1", "accept": "text/event-stream"})
    assert out["headers"] == {"cookie": "[REDACTED]", "accept": "text/event-stream"}
