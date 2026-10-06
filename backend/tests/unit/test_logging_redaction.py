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
