import pytest

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


def test_uvicorn_access_filter_scrubs_stream_token_in_args() -> None:
    import logging

    from marketsignal.telemetry.logging import UvicornAccessScrubFilter

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", "/api/workspaces/w/runs/r/events?st=eyJhbG.pay.sig&x=1", "1.1", 200),
        None,
    )
    assert UvicornAccessScrubFilter().filter(record) is True
    rendered = record.getMessage()
    assert "eyJhbG" not in rendered
    assert "?st=[REDACTED]&x=1" in rendered
    assert isinstance(record.args, tuple)
    assert record.args[-1] == 200  # non-strings untouched


def test_uvicorn_access_filter_scrubs_plain_message() -> None:
    import logging

    from marketsignal.telemetry.logging import UvicornAccessScrubFilter

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, "GET /e?token=abc.def.ghi", None, None
    )
    UvicornAccessScrubFilter().filter(record)
    assert "abc.def.ghi" not in record.getMessage()


def test_configure_logging_installs_access_filter_once() -> None:
    import logging

    from marketsignal.telemetry.logging import UvicornAccessScrubFilter, configure_logging

    logger = logging.getLogger("uvicorn.access")
    before = list(logger.filters)
    try:
        configure_logging("INFO", True)
        configure_logging("INFO", True)
        installed = [f for f in logger.filters if isinstance(f, UvicornAccessScrubFilter)]
        assert len(installed) == 1
    finally:
        logger.filters[:] = before


def test_provider_keys_bearer_values_and_jwts_are_scrubbed_from_strings() -> None:
    from marketsignal.telemetry.logging import _scrub_string

    fake_key = "sk-ant-" + "api03-" + "x" * 40  # synthetic; never a real credential
    jwt = "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiJydW4ifQ." + "c2lnbmF0dXJl"
    text = f"failed with key {fake_key}; Authorization: Bearer abc.def; stream {jwt}"
    out = _scrub_string(text)
    assert "sk-ant-" not in out
    assert "abc.def" not in out
    assert jwt not in out


def test_rendered_tracebacks_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    import structlog

    from marketsignal.telemetry.logging import configure_logging

    fake_key = "sk-ant-" + "api03-" + "y" * 40  # synthetic; never a real credential
    configure_logging("INFO", True)  # binds the print logger to the captured stdout
    try:
        raise RuntimeError(f"upstream said {fake_key}")
    except RuntimeError:
        structlog.get_logger("t").exception("llm_failed")
    out = capsys.readouterr().out
    assert "llm_failed" in out
    assert "RuntimeError" in out
    assert "sk-ant-" not in out


def test_http_client_loggers_are_pinned_above_debug() -> None:
    import logging

    from marketsignal.telemetry.logging import configure_logging

    logging.getLogger().setLevel(logging.DEBUG)
    configure_logging("DEBUG", True)
    # The MCP SDK calls basicConfig(level=INFO) when a server is built; the pin must hold.
    logging.basicConfig(level=logging.INFO)
    # anthropic 1.x uses httpx2/httpcore2 (live research smoke showed their INFO lines).
    for name in ("httpx", "httpcore", "httpx2", "httpcore2", "httpcore2.http11", "anthropic"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
    logging.getLogger().setLevel(logging.WARNING)
    configure_logging("INFO", True)
