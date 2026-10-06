"""Structured JSON logging with credential redaction.

Logs are correlated by ``request_id`` (and later ``run_id`` / ``workspace_id``) through
structlog context variables. A redaction processor runs before rendering so that tokens,
cookies, passwords and DSN credentials never reach log sinks.
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
        "x-api-key",
        "st",  # SSE stream token query parameter
        "database_url",
        "migrations_database_url",
        "redis_url",
    }
)
_REDACTED = "[REDACTED]"
# user:password@ in DSNs, and token-bearing query parameters in URLs.
_DSN_CREDENTIALS = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@", re.I)
_TOKEN_QUERY = re.compile(r"(?P<key>[?&](?:st|token|access_token|api_key)=)[^&\s]+", re.I)


def _scrub_string(value: str) -> str:
    value = _DSN_CREDENTIALS.sub(r"\g<scheme>[REDACTED]@", value)
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


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    _install_access_log_scrubber()
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_sensitive,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
