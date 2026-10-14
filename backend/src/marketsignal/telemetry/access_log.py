"""One structured ``http.request`` event per HTTP request (pure ASGI middleware).

Logged when the response finishes (for SSE streams: when the stream ends, so ``duration_ms`` is
the stream's lifetime) with the method, the matched route *template*
(``/api/workspaces/{ws}/runs/{run_id}``), the raw path without its query string (stream tokens
travel in ``?st=``), the status, the duration and the request id. Never headers, bodies or the
query string. 5xx logs at ERROR, 4xx at WARNING, everything else at INFO. Health, metrics and the
server log endpoint itself carry ``noise=True`` so the developer UI can hide them by default.

The path is client-controlled and percent-decoded: control characters are replaced with ``?``
(no newline/ANSI injection into console logs) and it is cut to :data:`MAX_PATH` characters
(``path_truncated=True``) before it is logged, as are the ``ws``/``run_id`` path parameters.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from marketsignal.telemetry.logging import get_logger

log = get_logger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

NOISE_PATHS = frozenset({"/healthz", "/readyz", "/livez", "/metrics", "/favicon.ico"})
NOISE_PREFIXES = ("/api/dev/logs",)
MAX_PATH = 512
_CONTROL_CHARS = {code: "?" for code in [*range(0x20), 0x7F]}


def safe_text(value: str, limit: int = MAX_PATH) -> tuple[str, bool]:
    """``(value cut to limit with control characters replaced by "?", was it cut)``."""
    return value[:limit].translate(_CONTROL_CHARS), len(value) > limit


def is_noise(path: str) -> bool:
    return path in NOISE_PATHS or path.startswith(NOISE_PREFIXES)


def route_template(scope: Scope) -> str | None:
    route = scope.get("route")
    template = getattr(route, "path_format", None) or getattr(route, "path", None)
    return template if isinstance(template, str) else None


def _path_param(scope: Scope, name: str) -> str | None:
    params = scope.get("path_params")
    value = params.get(name) if isinstance(params, dict) else None
    return None if value is None else safe_text(str(value), 128)[0]


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        seen: dict[str, Any] = {"status": None, "request_id": None, "stream": False}

        async def capture(message: Message) -> None:
            if message.get("type") == "http.response.start":
                seen["status"] = int(message.get("status", 0))
                for name, value in message.get("headers") or ():
                    if name.lower() == b"x-request-id":
                        seen["request_id"] = value.decode("latin-1")
                    elif name.lower() == b"content-type":
                        seen["stream"] = value.startswith(b"text/event-stream")
            await send(message)

        failed = True
        try:
            await self.app(scope, receive, capture)
            failed = False
        finally:
            self._emit(scope, seen, started, failed)

    @staticmethod
    def _emit(scope: Scope, seen: dict[str, Any], started: float, failed: bool) -> None:
        try:
            status = seen["status"]
            if status is None and failed:
                status = 500
            raw_path = str(scope.get("path") or "")
            path, truncated = safe_text(raw_path)
            fields: dict[str, Any] = {}
            if is_noise(raw_path):
                fields["noise"] = True
            if truncated:
                fields["path_truncated"] = True
            if seen["stream"]:
                fields["stream"] = True
            if failed and seen["status"] is not None:
                fields["interrupted"] = True  # the response started, then the app raised
            code = status or 0
            level = "error" if code >= 500 else "warning" if code >= 400 else "info"
            getattr(log, level)(
                "http.request",
                kind="http",
                method=str(scope.get("method") or ""),
                route=route_template(scope),
                path=path,
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                request_id=seen["request_id"],
                workspace=_path_param(scope, "ws"),
                run_id=_path_param(scope, "run_id"),
                **fields,
            )
        except Exception:  # an access log must never break a response
            return
