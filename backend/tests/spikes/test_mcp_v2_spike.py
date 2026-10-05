"""MCP SDK v2 compatibility spike (Phase 0), kept as an executable contract test.

Pins the SDK assumptions the governed tool boundary (ADR-0006) depends on, so an SDK upgrade
that breaks any of them fails CI instead of failing the demo:

1. An ``MCPServer`` Streamable-HTTP app mounts inside FastAPI, with the session manager run
   from the parent lifespan, and is reachable over loopback by the official v2 ``Client``.
2. Bearer tokens are verified by our own ``TokenVerifier`` (HS256 JWT, pinned algorithm,
   audience ``mcp``); missing, wrong-audience and expired tokens are rejected with 401.
3. Inside a tool handler, trusted claims (the workspace) come from ``get_access_token()``,
   never from tool arguments.
4. ``Context`` parameters are excluded from the tool's advertised input schema.
5. A Pydantic return type is exposed as structured content (and an output schema).
"""

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx2
import jwt
import pytest
import uvicorn
from fastapi import FastAPI
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, MCPServer
from pydantic import BaseModel, Field

SECRET = "spike-only-signing-key-0123456789abcdef"
AUDIENCE = "mcp"
ISSUER = "marketsignal-api"


class HmacJwtVerifier:
    """Verifies run-scoped capability tokens minted by the API (ADR-0006)."""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                SECRET,
                algorithms=["HS256"],  # pinned: never trust the token's own alg header
                audience=AUDIENCE,
                issuer=ISSUER,
                leeway=5,
                options={"require": ["exp", "iat", "aud", "iss", "sub", "jti", "ws"]},
            )
        except jwt.PyJWTError:
            return None
        return AccessToken(
            token=token,
            client_id="marketsignal-agent",
            scopes=list(claims.get("tools", [])),
            expires_at=int(claims["exp"]),
            subject=str(claims["sub"]),
            claims=claims,
        )


def mint(**overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "demo-principal",
        "jti": "run-123",
        "iat": now,
        "exp": now + 60,
        "ws": "11111111-1111-1111-1111-111111111111",
        "wsc": "NORTHSTAR",
        "tools": ["whoami"],
    }
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


class WhoAmI(BaseModel):
    workspace_code: str
    query: str


def build_mcp() -> MCPServer:
    mcp = MCPServer(
        "marketsignal-spike",
        token_verifier=HmacJwtVerifier(),
        auth=AuthSettings(
            issuer_url="http://127.0.0.1",
            resource_server_url=None,
            validate_token_resource=False,  # audience is checked by our verifier
            required_scopes=[],
        ),
    )

    @mcp.tool()
    async def whoami(
        query: Annotated[str, Field(min_length=1, description="Echoed search text")],
        ctx: Context,
    ) -> WhoAmI:
        """Return the workspace taken from the verified token, plus the query."""
        token = get_access_token()
        assert token is not None
        assert token.claims is not None
        return WhoAmI(workspace_code=str(token.claims["wsc"]), query=query)

    return mcp


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture
async def mcp_url() -> AsyncIterator[str]:
    mcp = build_mcp()
    mcp_app = mcp.streamable_http_app(streamable_http_path="/", stateless_http=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    api = FastAPI(lifespan=lifespan)
    api.mount("/mcp", mcp_app)

    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(api, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    task = asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.02)
    assert server.started, "uvicorn did not start"
    yield f"http://127.0.0.1:{port}/mcp/"
    server.should_exit = True
    await task


@asynccontextmanager
async def client_with(token: str, url: str) -> AsyncIterator[Client]:
    async with (
        httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http,
        Client(streamable_http_client(url, http_client=http)) as client,
    ):
        yield client


async def test_tool_schema_hides_context_and_exposes_output_schema(mcp_url: str) -> None:
    async with client_with(mint(), mcp_url) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    whoami = tools["whoami"]
    props = whoami.input_schema["properties"]
    assert set(props) == {"query"}, props  # ctx is not model-visible
    assert whoami.output_schema is not None
    assert set(whoami.output_schema["properties"]) == {"workspace_code", "query"}


async def test_workspace_comes_from_verified_claims(mcp_url: str) -> None:
    async with client_with(mint(wsc="NORTHSTAR"), mcp_url) as client:
        result = await client.call_tool("whoami", {"query": "gen z pain points"})
    assert not result.is_error
    assert result.structured_content == {
        "workspace_code": "NORTHSTAR",
        "query": "gen z pain points",
    }


@pytest.mark.parametrize(
    "auth_header",
    [
        None,
        f"Bearer {mint(aud='sse')}",  # wrong audience
        f"Bearer {mint(exp=int(time.time()) - 120, iat=int(time.time()) - 180)}",  # expired
        f"Bearer {jwt.encode({'aud': AUDIENCE}, 'wrong-key-' + '0' * 32, algorithm='HS256')}",
        "Bearer not-a-jwt",
    ],
    ids=["missing", "wrong-audience", "expired", "bad-signature", "garbage"],
)
async def test_unauthenticated_requests_are_rejected(mcp_url: str, auth_header: str | None) -> None:
    headers = {"Accept": "application/json, text/event-stream"}
    if auth_header:
        headers["Authorization"] = auth_header
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    async with httpx2.AsyncClient() as http:
        response = await http.post(mcp_url, json=body, headers=headers)
    assert response.status_code == 401
