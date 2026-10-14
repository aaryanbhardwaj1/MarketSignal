"""Developer server log: ring buffer, sanitizer, structlog capture processor and queries."""

from __future__ import annotations

import logging
import threading
from typing import Any

import pytest

from marketsignal.devtools import server_log
from marketsignal.devtools.server_log import (
    NOISE_CAPACITY,
    HttpInfo,
    LogEntry,
    LogQuery,
    ServerLogBuffer,
    configure_server_log,
    query_logs,
)
from marketsignal.telemetry import server_log_capture
from marketsignal.telemetry.logging import redact_sensitive
from marketsignal.telemetry.server_log_capture import (
    MAX_FIELDS,
    MAX_STRING,
    ServerLogHandler,
    capture_server_log,
    classify_kind,
    entry_from_event,
    sanitize_fields,
)

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJydW4ifQ.c2lnbmF0dXJlLXNpZw"
ANTHROPIC = "sk-ant-api03-AbCdEf0123456789"
DSN = "postgresql+psycopg://ms_app:s3cret@db:5432/marketsignal"


def _entry(event: str = "e", **kw: Any) -> LogEntry:
    base: dict[str, Any] = {"ts": "2026-01-01T00:00:00+00:00", "level": "INFO", "logger": "t"}
    base.update(kw)
    return LogEntry(event=event, kind=base.pop("kind", "app"), **base)


def _http(method: str = "GET", route: str = "/r", path: str = "/r", status: int = 200) -> HttpInfo:
    return HttpInfo(method=method, route=route, path=path, status=status, duration_ms=1.0)


@pytest.fixture
def buffer(monkeypatch: pytest.MonkeyPatch) -> ServerLogBuffer:
    fresh = ServerLogBuffer(capacity=50)
    monkeypatch.setattr(server_log, "_buffer", fresh)
    monkeypatch.setattr(server_log_capture, "_capture_enabled", True)
    return fresh


# ------------------------------------------------------------------------------- buffer


def test_buffer_is_bounded_counts_dropped_and_keeps_seq_monotonic() -> None:
    buf = ServerLogBuffer(capacity=3)
    for i in range(5):
        buf.append(_entry(f"e{i}"))
    entries, dropped, errors = buf.snapshot()
    assert [e.seq for e in entries] == [3, 4, 5]
    assert [e.event for e in entries] == ["e2", "e3", "e4"]
    assert dropped == 2
    assert errors == 0
    assert buf.process_started_at.endswith("+00:00")


def test_noise_entries_never_evict_real_entries() -> None:
    buf = ServerLogBuffer(capacity=3)
    for i in range(3):
        buf.append(_entry(f"real{i}"))
    for i in range(NOISE_CAPACITY + 50):
        buf.append(_entry(f"noise{i}", fields={"noise": True}))
    entries, dropped, _ = buf.snapshot()
    assert [e.event for e in entries if not e.noise] == ["real0", "real1", "real2"]
    assert sum(1 for e in entries if e.noise) == NOISE_CAPACITY
    assert NOISE_CAPACITY <= 200
    assert dropped == 0  # only real entries count as dropped


def test_snapshot_merges_noise_and_real_entries_in_seq_order() -> None:
    buf = ServerLogBuffer(capacity=10)
    for i in range(6):
        buf.append(_entry(f"e{i}", fields={"noise": True} if i % 2 else {}))
    entries, _, _ = buf.snapshot()
    assert [e.seq for e in entries] == [1, 2, 3, 4, 5, 6]
    out = query_logs(buf, LogQuery(include_noise=True, after_seq=2))
    assert [e["seq"] for e in out["entries"]] == [3, 4, 5, 6]
    assert [e["seq"] for e in query_logs(buf, LogQuery())["entries"]] == [5, 3, 1]


def test_server_log_capacity_is_capped() -> None:
    from pydantic import ValidationError

    from marketsignal.config import Settings

    assert Settings(server_log_capacity=10_000).server_log_capacity == 10_000
    with pytest.raises(ValidationError):
        Settings(server_log_capacity=10_001)


def test_buffer_rejects_zero_capacity() -> None:
    with pytest.raises(ValueError, match="capacity"):
        ServerLogBuffer(capacity=0)


def test_buffer_is_thread_safe() -> None:
    buf = ServerLogBuffer(capacity=10_000)

    def work() -> None:
        for _ in range(500):
            buf.append(_entry())

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    entries, dropped, _ = buf.snapshot()
    assert len(entries) == 4000
    assert sorted(e.seq for e in entries) == list(range(1, 4001))
    assert dropped == 0


def test_configure_server_log_resizes_only_when_capacity_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_log, "_buffer", ServerLogBuffer(capacity=7))
    same = configure_server_log(7)
    assert same is server_log.get_server_log()
    bigger = configure_server_log(9)
    assert bigger.capacity == 9
    assert bigger is server_log.get_server_log()
    assert bigger is not same


# ---------------------------------------------------------------------------- sanitizer


def test_sanitizer_drops_content_and_secret_keys() -> None:
    risky = {
        name: "leak"
        for name in (
            "question",
            "query",
            "q",
            "content",
            "text",
            "answer",
            "prompt",
            "passage",
            "quote",
            "args",
            "body",
            "headers",
            "Authorization",
            "cookie",
            "token",
            "key",
            "secret",
            "password",
            "dsn",
            "url",
            "stream_token",
            "api_key",
            "database_url",
            "original_query",
        )
    }
    out = sanitize_fields({**risky, "tool": "search_evidence", "count": 3})
    assert out == {"tool": "search_evidence", "count": 3}


def test_sanitizer_scrubs_credentials_inside_kept_values() -> None:
    out = sanitize_fields(
        {
            "reason": f"Bearer {JWT} failed",
            "detail": f"key {ANTHROPIC}",
            "target": f"connect {DSN}",
            "jwt": JWT,
        }
    )
    rendered = repr(out)
    assert JWT not in rendered
    assert ANTHROPIC not in rendered
    assert "s3cret" not in rendered
    assert "[REDACTED]" in str(out["reason"])


def test_sanitizer_keeps_scalars_only_truncates_and_caps_keys() -> None:
    values: dict[str, Any] = {"nested": {"a": 1}, "items": [1, 2], "long": "x" * 500}
    values.update({f"k{i}": i for i in range(20)})
    out = sanitize_fields(values)
    assert "nested" not in out
    assert "items" not in out
    assert len(str(out["long"])) == MAX_STRING
    assert len(out) == MAX_FIELDS


def test_entry_from_event_lifts_structure_and_http() -> None:
    entry = entry_from_event(
        {
            "event": "http.request",
            "kind": "http",
            "method": "get",
            "route": "/api/workspaces/{ws}/runs/{run_id}",
            "path": "/api/workspaces/W/runs/1?st=abc",
            "status": 404,
            "duration_ms": 1.234,
            "request_id": "rid",
            "workspace": "W",
            "run_id": "1",
            "noise": True,
            "timestamp": "2026-01-01T00:00:00Z",
        },
        logger="marketsignal.telemetry.access_log",
        level="warning",
    )
    assert entry.kind == "http"
    assert entry.level == "WARNING"
    assert entry.http == HttpInfo(
        "GET", "/api/workspaces/{ws}/runs/{run_id}", "/api/workspaces/W/runs/1", 404, 1.2
    )
    assert (entry.request_id, entry.workspace, entry.run_id) == ("rid", "W", "1")
    assert dict(entry.fields) == {"noise": True}
    assert entry.noise


def test_entry_from_event_drops_tracebacks_but_flags_them() -> None:
    entry = entry_from_event(
        {"event": "run_failed", "exception": "Traceback ... secret question text"},
        logger="marketsignal.runs.executor",
        level="error",
    )
    assert entry.kind == "run"
    assert dict(entry.fields) == {"has_exception": True}


@pytest.mark.parametrize(
    ("event", "logger", "explicit", "kind"),
    [
        ("http.request", None, None, "http"),
        ("run.finished", "marketsignal.runs.executor", None, "run"),
        ("verification.attempt", "marketsignal.runs.synthesis", None, "verification"),
        ("tool.call", "marketsignal.tools.governance", None, "tool"),
        ("tool x unavailable", "marketsignal.tools.governance", None, "tool"),
        ("ingestion_failed", "marketsignal.ingestion.pipeline", None, "ingestion"),
        ("analytics_result_invalid", "marketsignal.generation.results", None, "analytics"),
        ("startup_complete", "marketsignal.api.app", None, "app"),
        ("Exception in ASGI application", "uvicorn.error", None, "http"),
        ("whatever", None, "verification", "verification"),
        ("whatever", None, "bogus", "app"),
    ],
)
def test_classify_kind(event: str, logger: str | None, explicit: str | None, kind: str) -> None:
    assert classify_kind(event, logger, explicit) == kind


# ---------------------------------------------------------------------------- processor


class _Named:
    name = "marketsignal.runs.executor"


def test_processor_copies_and_returns_event_unchanged(buffer: ServerLogBuffer) -> None:
    event = {"event": "run.finished", "level": "info", "run_id": "r1", "question": "secret?"}
    before = dict(event)
    out = capture_server_log(_Named(), "info", event)
    assert out is event
    assert event == before
    entries, _, _ = buffer.snapshot()
    assert entries[-1].event == "run.finished"
    assert entries[-1].logger == "marketsignal.runs.executor"
    assert "question" not in entries[-1].fields


def test_processor_is_inert_when_capture_is_disabled(
    buffer: ServerLogBuffer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server_log_capture, "_capture_enabled", False)
    event = {"event": "run.finished", "level": "info"}
    assert capture_server_log(_Named(), "info", event) is event
    assert buffer.snapshot()[0] == []


def test_redact_and_capture_are_fast_on_64kb_strings(buffer: ServerLogBuffer) -> None:
    import time

    for big in ("a" * 65_536, "eyJ" * 21_846, "/" + "a1" * 32_768):
        event: dict[str, Any] = {
            "event": "http.request",
            "kind": "http",
            "method": "GET",
            "path": big,
            "request_id": big,
            "detail": big,
            "level": "info",
        }
        started = time.perf_counter()
        capture_server_log(_Named(), "info", redact_sensitive(None, "info", event))
        sanitize_fields({"detail": big})
        assert time.perf_counter() - started < 0.05
    entries, _, errors = buffer.snapshot()
    assert errors == 0
    assert all(e.http is not None and len(e.http.path) <= MAX_STRING for e in entries)


def test_processor_never_raises(buffer: ServerLogBuffer) -> None:
    class Boom:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    event: dict[str, Any] = {"event": Boom()}
    assert capture_server_log(None, "info", event) is event
    entries, _, errors = buffer.snapshot()
    assert entries == []
    assert errors == 1


def test_stdlib_handler_feeds_the_buffer(buffer: ServerLogBuffer) -> None:
    logger = logging.getLogger("mstest.tools.capture")  # outside the installed handlers
    handler = ServerLogHandler(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        logger.info("ignored below warning")
        logger.warning("tool %s unavailable: %s", "search", f"Bearer {JWT}")
    finally:
        logger.removeHandler(handler)
    entries, _, _ = buffer.snapshot()
    assert len(entries) == 1
    assert entries[0].level == "WARNING"
    assert entries[0].kind == "tool"
    assert JWT not in entries[0].event


# ------------------------------------------------------------------------------ queries


def _filled() -> ServerLogBuffer:
    buf = ServerLogBuffer(capacity=100)
    buf.append(_entry("app.start"))
    buf.append(_entry("http.request", kind="http", http=_http(route="/a", path="/a")))
    buf.append(
        _entry("http.request", kind="http", level="WARNING", http=_http("POST", "/b", "/b", 422))
    )
    buf.append(
        _entry("http.request", kind="http", http=_http(route="/healthz"), fields={"noise": True})
    )
    buf.append(_entry("run.finished", kind="run", level="ERROR", run_id="RUN-42"))
    return buf


def test_query_newest_first_hides_noise_and_counts_levels() -> None:
    out = query_logs(_filled(), LogQuery())
    assert [e["seq"] for e in out["entries"]] == [5, 3, 2, 1]
    assert out["size"] == 5
    assert out["oldest_seq"] == 1
    assert out["latest_seq"] == 5
    assert out["scope"] == "api_process"
    assert out["routes"] == ["/a", "/b", "/healthz"]
    assert out["levels"] == {"DEBUG": 0, "INFO": 2, "WARNING": 1, "ERROR": 1, "CRITICAL": 0}


def test_query_after_seq_is_ascending_and_limited() -> None:
    out = query_logs(_filled(), LogQuery(after_seq=1, include_noise=True, limit=2))
    assert [e["seq"] for e in out["entries"]] == [2, 3]


@pytest.mark.parametrize(
    ("query", "seqs"),
    [
        (LogQuery(level="WARNING"), [5, 3]),
        (LogQuery(kind="run"), [5]),
        (LogQuery(method="POST"), [3]),
        (LogQuery(status_class="4xx"), [3]),
        (LogQuery(route="/a"), [2]),
        (LogQuery(q="run-42"), [5]),
        (LogQuery(q="/B"), [3]),
        (LogQuery(include_noise=True, route="/healthz"), [4]),
        (LogQuery(limit=1), [5]),
    ],
)
def test_query_filters(query: LogQuery, seqs: list[int]) -> None:
    assert [e["seq"] for e in query_logs(_filled(), query)["entries"]] == seqs


def test_query_empty_buffer() -> None:
    out = query_logs(ServerLogBuffer(capacity=5), LogQuery())
    assert out["entries"] == []
    assert out["oldest_seq"] is None
    assert out["latest_seq"] is None
    assert out["dropped"] == 0
