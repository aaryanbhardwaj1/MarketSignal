"""``LoopbackOnly`` (security finding 1): when the endpoint is not public, a request carrying
proxy headers is refused even if ``scope['client']`` is loopback (uvicorn's proxy-headers
middleware may have rewritten the client from ``X-Forwarded-For``)."""

from __future__ import annotations

import httpx
import pytest
from starlette.types import Receive, Scope, Send

from marketsignal.mcp.server import LoopbackOnly


async def _ok(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _status(public: bool, client: str, headers: dict[str, str]) -> int:
    app = LoopbackOnly(_ok, public=public)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(client, 5555)),
        base_url="http://127.0.0.1",
    ) as http:
        return (await http.get("/", headers=headers)).status_code


@pytest.mark.parametrize(
    "header",
    ["X-Forwarded-For", "Forwarded", "X-Real-IP", "x-forwarded-for"],
)
async def test_proxy_headers_are_refused_when_not_public(header: str) -> None:
    assert await _status(False, "127.0.0.1", {header: "127.0.0.1"}) == 403


async def test_loopback_without_proxy_headers_passes() -> None:
    assert await _status(False, "127.0.0.1", {}) == 200
    assert await _status(False, "10.1.2.3", {}) == 403


async def test_public_mode_ignores_proxy_headers() -> None:
    assert await _status(True, "10.1.2.3", {"X-Forwarded-For": "1.2.3.4"}) == 200
