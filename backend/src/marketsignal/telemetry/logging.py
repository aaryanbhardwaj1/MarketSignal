"""Structured JSON logging with credential redaction.

Logs are correlated by ``request_id`` (and later ``run_id`` / ``workspace_id``) through
structlog context variables. A redaction processor runs before rendering (after tracebacks are
formatted) so that tokens, cookies, passwords, provider keys and DSN credentials never reach
log sinks. The HTTP client loggers are pinned to WARNING so request details are never logged.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "password",
        "secret",
        "token",
        "api_key",
        "anthropic_api_key",
        "stream_token_secret",
        "mcp_token_key",
        "x-api-key",
        "st",  # SSE stream token query parameter
        "database_url",
        "migrations_database_url",
        "redis_url",
    }
)
_REDACTED = "[REDACTED]"
# user:password@ in DSNs, and token-bearing query parameters in URLs.
# Linear time (no ReDoS): every pattern that can fail after a long scan anchors its start with a
# negative lookbehind (one candidate start per run of scheme/token characters) and uses
# possessive quantifiers. The scheme group keeps any leading digits of the run, so the output is
# the same as the original ``[a-z][a-z0-9+.-]*://`` pattern.
_DSN_CREDENTIALS = re.compile(
    r"(?<![a-z0-9+.-])(?P<scheme>[0-9+.-]*+[a-z][a-z0-9+.-]*+://)[^/@\s:]++:[^/@\s]++@", re.I
)
_TOKEN_QUERY = re.compile(r"(?P<key>[?&](?:st|token|access_token|api_key)=)[^&\s]+", re.I)
# Credential shapes, matched by pattern so the redactor never needs the secret value itself.
_CREDENTIAL_SHAPES = re.compile(
    r"sk-ant-[A-Za-z0-9_-]{8,}"  # Anthropic API keys
    r"|(?<=Bearer )[^\s,;\"']+"  # bearer values
    # JWTs (stream tokens), starting at a token boundary
    r"|(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{5,}+\.[A-Za-z0-9_-]{5,}+\.[A-Za-z0-9_-]{5,}+",
    re.I,
)
# Stdlib loggers that bypass structlog and can log request details at DEBUG.
_HTTP_CLIENT_LOGGERS = ("httpx", "httpcore", "httpx2", "httpcore2", "anthropic")


def _scrub_string(value: str) -> str:
    value = _DSN_CREDENTIALS.sub(r"\g<scheme>[REDACTED]@", value)
    value = _CREDENTIAL_SHAPES.sub(_REDACTED, value)
    return _TOKEN_QUERY.sub(r"\g<key>[REDACTED]", value)


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, Mapping):
        return {
            k: (_REDACTED if str(k).lower() in _SENSITIVE_KEYS else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(_scrub(v) for v in value)
    return value


def redact_sensitive(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: redact sensitive keys and credential-bearing strings."""
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = _REDACTED
        else:
            event_dict[key] = _scrub(event_dict[key])
    return event_dict


class UvicornAccessScrubFilter(logging.Filter):
    """Scrub token query parameters (e.g. the SSE ``?st=``) from uvicorn access records.

    uvicorn.access is a stdlib logger with its own handler, so the structlog redaction
    processor never sees it. uvicorn passes the request path (with query string) as a
    ``record.args`` element, so scrub both the format string and every string argument.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _scrub_string(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_scrub_string(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                k: _scrub_string(v) if isinstance(v, str) else v for k, v in record.args.items()
            }
        return True


def _install_access_log_scrubber() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, UvicornAccessScrubFilter) for f in logger.filters):
        logger.addFilter(UvicornAccessScrubFilter())


class _NamedPrintLogger(structlog.PrintLogger):
    """``PrintLogger`` that remembers the name passed to :func:`get_logger` (server log)."""

    def __init__(self, file: Any, name: str | None) -> None:
        super().__init__(file)
        self.name = name


class _NamedPrintLoggerFactory:
    def __init__(self, file: Any) -> None:
        self._file = file

    def __call__(self, *args: Any) -> _NamedPrintLogger:
        name = args[0] if args and isinstance(args[0], str) else None
        return _NamedPrintLogger(self._file, name)


def configure_logging(
    level: str = "INFO",
    json: bool = True,
    *,
    server_log_capacity: int | None = None,
    server_log_capture: bool = False,
) -> None:
    """``server_log_capture`` copies events into the dev server log; only when it is readable."""
    # Imported here: the capture module reuses this module's scrubber.
    from marketsignal.devtools.server_log import configure_server_log
    from marketsignal.telemetry.server_log_capture import (
        capture_server_log,
        install_stdlib_capture,
        remove_stdlib_capture,
        set_capture_enabled,
    )

    if server_log_capacity is not None:
        configure_server_log(server_log_capacity)
    _install_access_log_scrubber()
    set_capture_enabled(server_log_capture)
    if server_log_capture:
        install_stdlib_capture()
    else:
        remove_stdlib_capture()
    for name in _HTTP_CLIENT_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            redact_sensitive,  # after format_exc_info, so rendered tracebacks are scrubbed too
            # dev server log: sanitized copy (inert unless enabled), event passed through unchanged
            capture_server_log,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=_NamedPrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
