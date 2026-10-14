"""Copy structured log events into the developer server log (``devtools.server_log``).

Two entry points feed the same sanitizer:

* :func:`capture_server_log` - a structlog processor placed after ``redact_sensitive`` and
  before the renderer. It never raises and returns the event unchanged (stdout output is
  untouched); an internal failure only bumps the buffer's ``capture_errors`` counter.
* :class:`ServerLogHandler` - a stdlib ``logging.Handler`` for WARNING+ records of the stdlib
  loggers (uvicorn/fastapi errors, the tool governor, the MCP client).

The sanitizer keeps ids, enums, counts and durations: it drops every key that could carry user
content or credentials (questions, queries, answers, passages, prompts, tool arguments, bodies,
headers, tokens, keys, DSNs/URLs), tracebacks and every non-scalar value; it truncates strings,
caps the number of keys and runs the shared credential scrubber over everything that is kept.
Strings are cut to :data:`SCRUB_WINDOW` characters *before* scrubbing, so the work per value is
bounded however long the input is (paths and request ids come straight from the client).

Capture is off until :func:`set_capture_enabled` turns it on (``configure_logging`` does, only
when the developer endpoints are mounted). The processor checks the flag on every event because
structlog caches each logger's processor chain on first use.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

from marketsignal.devtools.server_log import (
    KINDS,
    LEVELS,
    HttpInfo,
    LogEntry,
    Scalar,
    get_server_log,
    utc_now_iso,
)
from marketsignal.telemetry.logging import _REDACTED as REDACTED
from marketsignal.telemetry.logging import _SENSITIVE_KEYS as SENSITIVE_KEYS
from marketsignal.telemetry.logging import _scrub_string as scrub_string

MAX_STRING = 200
# Strings are cut to this many characters before the credential scrubber runs.
SCRUB_WINDOW = 512
MAX_FIELDS = 12
# Exact keys whose values may carry user content, model output or secrets.
_DROP_KEYS = frozenset(
    {
        "question",
        "query",
        "original_query",
        "q",
        "content",
        "text",
        "answer",
        "prompt",
        "system",
        "messages",
        "passage",
        "quote",
        "snippet",
        "args",
        "arguments",
        "input",
        "body",
        "payload",
        "headers",
        "authorization",
        "cookie",
        "set-cookie",
        "token",
        "key",
        "secret",
        "password",
        "dsn",
        "url",
        "uri",
        "reasoning",
        "thinking",
        "feedback",
        "draft",
        "exception",
        "exc_info",
        "stack",
        "stack_info",
    }
)
# Substrings that mark a key as credential-bearing (``stream_token``, ``api_key``, ``db_url``...).
_DROP_KEY_PARTS = ("secret", "password", "passwd", "authorization", "cookie", "api_key", "dsn")
_DROP_KEY_SUFFIXES = ("_token", "_key", "_url", "_uri", "_query", "_text", "_prompt")
# Keys lifted out of the event into first-class entry fields.
_STRUCTURAL = frozenset(
    {"event", "level", "timestamp", "logger", "kind", "request_id", "run_id", "workspace"}
)
_HTTP_KEYS = ("method", "route", "path", "status", "duration_ms")
_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL", "EXCEPTION": "ERROR"}
# (event prefix, kind) checked first; then (logger-name fragment, kind).
_EVENT_KINDS = (
    ("http.", "http"),
    ("verif", "verification"),
    ("run", "run"),
    ("llm_", "run"),
    ("tool", "tool"),
    ("ingest", "ingestion"),
    ("analytics", "analytics"),
)
_LOGGER_KINDS = (
    (".runs.", "run"),
    (".agent.", "run"),
    (".tools.", "tool"),
    (".mcp.", "tool"),
    (".ingestion.", "ingestion"),
    (".worker.", "ingestion"),
    (".analytics.", "analytics"),
    ("uvicorn", "http"),
)


def _drop_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in _DROP_KEYS
        or any(part in lowered for part in _DROP_KEY_PARTS)
        or lowered.endswith(_DROP_KEY_SUFFIXES)
    )


_capture_enabled = False


def set_capture_enabled(enabled: bool) -> None:
    global _capture_enabled
    _capture_enabled = enabled


def _short(value: str) -> str:
    cleaned = scrub_string(value[:SCRUB_WINDOW])
    return cleaned if len(cleaned) <= MAX_STRING else cleaned[: MAX_STRING - 1] + "…"


def _scalar(value: Any) -> tuple[bool, Scalar]:
    if value is None or isinstance(value, bool | int | float):
        return True, value
    if isinstance(value, str):
        return True, _short(value)
    return False, None


def sanitize_fields(values: Mapping[str, Any]) -> dict[str, Scalar]:
    """At most :data:`MAX_FIELDS` scalar, scrubbed, truncated values with safe keys."""
    out: dict[str, Scalar] = {}
    for key, value in values.items():
        if len(out) >= MAX_FIELDS:
            break
        name = str(key)
        if name in _STRUCTURAL or _drop_key(name):
            continue
        ok, scalar = (True, REDACTED) if name.lower() in SENSITIVE_KEYS else _scalar(value)
        if ok:
            out[name[:64]] = scalar
    return out


def normalize_level(level: Any) -> str:
    name = str(level or "INFO").upper()
    name = _LEVEL_ALIASES.get(name, name)
    return name if name in LEVELS else "INFO"


def classify_kind(event: str, logger: str | None, explicit: Any = None) -> str:
    if isinstance(explicit, str) and explicit in KINDS:
        return explicit
    lowered = event.lower()
    for prefix, kind in _EVENT_KINDS:
        if lowered.startswith(prefix):
            return kind
    name = f".{logger}." if logger else ""
    for fragment, kind in _LOGGER_KINDS:
        if fragment in name:
            return kind
    return "app"


def _opt_str(value: Any) -> str | None:
    return None if value is None else _short(str(value))


def _http_info(event_dict: Mapping[str, Any]) -> HttpInfo | None:
    method = event_dict.get("method")
    if not isinstance(method, str) or "path" not in event_dict:
        return None
    status = event_dict.get("status")
    duration = event_dict.get("duration_ms")
    return HttpInfo(
        method=_short(method.upper()),
        route=_opt_str(event_dict.get("route")),
        path=_short(str(event_dict.get("path") or "").split("?", 1)[0]),
        status=status if isinstance(status, int) and not isinstance(status, bool) else None,
        duration_ms=round(float(duration), 1) if isinstance(duration, int | float) else None,
    )


def entry_from_event(event_dict: Mapping[str, Any], *, logger: str | None, level: Any) -> LogEntry:
    """A sanitized :class:`LogEntry` from a structlog event dict (pure; may raise)."""
    event = _short(str(event_dict.get("event", "")))
    kind = classify_kind(event, logger, event_dict.get("kind"))
    http = _http_info(event_dict) if kind == "http" else None
    rest = {k: v for k, v in event_dict.items() if http is None or k not in _HTTP_KEYS}
    if event_dict.get("exception") or event_dict.get("exc_info"):
        rest["has_exception"] = True
    return LogEntry(
        ts=str(event_dict.get("timestamp") or utc_now_iso()),
        level=normalize_level(level),
        logger=_opt_str(logger),
        event=event,
        kind=kind,
        request_id=_opt_str(event_dict.get("request_id")),
        run_id=_opt_str(event_dict.get("run_id")),
        workspace=_opt_str(event_dict.get("workspace")),
        http=http,
        fields=sanitize_fields(rest),
    )


def capture_server_log(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: copy the event into the server log; never raises, never mutates."""
    if not _capture_enabled:
        return event_dict
    buffer = get_server_log()
    try:
        name = getattr(logger, "name", None)
        level = event_dict.get("level", method_name)
        buffer.append(entry_from_event(event_dict, logger=name, level=level))
    except Exception:
        buffer.note_capture_error()
    return event_dict


class ServerLogHandler(logging.Handler):
    """Feeds stdlib log records (message only; never ``exc_info`` text) into the server log."""

    def emit(self, record: logging.LogRecord) -> None:
        buffer = get_server_log()
        try:
            context = structlog.contextvars.get_contextvars()
            event = {
                "event": record.getMessage(),
                "request_id": context.get("request_id"),
                "run_id": context.get("run_id"),
            }
            if record.exc_info:
                event["exc_info"] = True
            buffer.append(entry_from_event(event, logger=record.name, level=record.levelname))
        except Exception:
            buffer.note_capture_error()


# Stdlib loggers whose WARNING+ records are copied (uvicorn.access is replaced by http.request).
STDLIB_CAPTURE_LOGGERS = ("uvicorn.error", "fastapi", "marketsignal")


def install_stdlib_capture() -> None:
    for name in STDLIB_CAPTURE_LOGGERS:
        target = logging.getLogger(name)
        if not any(isinstance(h, ServerLogHandler) for h in target.handlers):
            target.addHandler(ServerLogHandler(level=logging.WARNING))


def remove_stdlib_capture() -> None:
    for name in STDLIB_CAPTURE_LOGGERS:
        target = logging.getLogger(name)
        for handler in [h for h in target.handlers if isinstance(h, ServerLogHandler)]:
            target.removeHandler(handler)
