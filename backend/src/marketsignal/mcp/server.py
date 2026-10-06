"""MCP Streamable HTTP server over the governed tools (plan §17; ADR-0006; spike 0001).

``GovernedMCPServer`` is an ``MCPServer("marketsignal")`` whose ``list_tools``/``call_tool``
delegate to the *same* ``ToolGovernor`` as the in-process transport - there is no second
implementation, schema or validation path:

* The bearer token is checked at the HTTP edge by ``CapabilityTokenVerifier`` (the same
  ``capability.verify`` plus the run-revocation lookup): missing/forged/expired/wrong-audience
  tokens and tokens of a run that is no longer ``running`` get 401 before any MCP handling,
  ``tools/list`` included (a database failure during that lookup also yields 401: fail
  closed). The handler then passes the raw token to the governor, which re-verifies it,
  checks revocation and runs the full pipeline (so both transports audit identically).
* Arguments reach the governor unvalidated by the SDK (no tool is registered with the SDK's
  function-signature validation), so ``VALIDATION_ERROR`` results are identical in-process and
  over HTTP. The advertised input schema is the contract model's JSON schema.
* The result's ``structured_content`` is the wire form of ``ToolResult`` (``to_wire``); its
  text content is the bounded observation. Step/call index for the audit row travel in the
  ``x-marketsignal-step`` / ``x-marketsignal-call-index`` headers (bounded integers).
* ``LoopbackOnly`` rejects non-loopback clients with 403 unless ``settings.mcp_public``. It
  also rejects (403) any request carrying ``Forwarded`` / ``X-Forwarded-For`` /
  ``X-Real-IP``: uvicorn's proxy-headers middleware rewrites ``scope['client']`` from
  ``X-Forwarded-For`` for trusted proxies, and the internal ``HttpToolTransport`` never sends
  them. Deployment rule: ``FORWARDED_ALLOW_IPS`` must never be ``*`` (and a same-host reverse
  proxy must not forward ``/mcp``), or the loopback check is meaningless.
* Host allowlist (DNS-rebinding protection): non-public mode allows only loopback hosts.
  Public mode allows the hosts passed as ``allowed_hosts`` (``host:port`` patterns as the MCP
  SDK expects, e.g. ``["api.example.com", "api.example.com:*"]``); the lead wires them from a
  setting, e.g. ``build_mcp_app(gov, settings, allowed_hosts=settings.mcp_allowed_hosts)``
  with ``mcp_allowed_hosts: list[str]`` in ``config.py``. Without it, public mode still only
  accepts loopback ``Host`` headers.

Mounting (the lead, in ``api/app.py``)::

    mcp_server, mcp_app = build_mcp_app(governor, settings)
    app.mount("/mcp", mcp_app)
    # lifespan: the parent app's lifespan MUST enter the session manager (spike 0001):
    async with mcp_server.session_manager.run():
        yield

The app serves the endpoint at the mount root (``streamable_http_path="/"``), stateless.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from mcp.types import Tool as MCPTool
from starlette.types import ASGIApp, Receive, Scope, Send

from marketsignal.config import Settings
from marketsignal.tools.capability import UnauthenticatedError
from marketsignal.tools.contracts import ToolCall, ToolResult
from marketsignal.tools.governance import ToolGovernor

STEP_HEADER = "x-marketsignal-step"
CALL_INDEX_HEADER = "x-marketsignal-call-index"
CALL_ID_HEADER = "x-marketsignal-call-id"
_MAX_INDEX = 10_000
LOOPBACK_HOSTS: tuple[str, ...] = ("127.0.0.1:*", "localhost:*", "[::1]:*")
LOOPBACK_ORIGINS: tuple[str, ...] = ("http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*")
PROXY_HEADERS = frozenset({b"forwarded", b"x-forwarded-for", b"x-real-ip"})


def to_wire(result: ToolResult) -> dict[str, Any]:
    """The transport-independent part of a ``ToolResult`` (``mcp.client`` rebuilds it)."""
    return {
        "ok": result.ok,
        "output": result.output,
        "observation": result.observation,
        "error": None
        if result.error is None
        else {"code": result.error.code, "message": result.error.message},
        "truncated": result.truncated,
        "warnings": list(result.warnings),
        "duration_ms": result.duration_ms,
    }


class CapabilityTokenVerifier:
    """HTTP-edge bearer check: signature, claims and run revocation."""

    def __init__(self, governor: ToolGovernor) -> None:
        self._governor = governor

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            ctx = await self._governor.authenticate_live(token)
        except UnauthenticatedError:
            return None
        return AccessToken(
            token=token,
            client_id="marketsignal-agent",
            scopes=sorted(ctx.tools),
            subject=ctx.principal,
        )


def _header_int(headers: Mapping[str, str] | None, name: str) -> int:
    raw = (headers or {}).get(name, "0")
    return min(_MAX_INDEX, max(0, int(raw))) if raw.isdigit() and len(raw) <= 6 else 0


class GovernedMCPServer(MCPServer):
    def __init__(self, governor: ToolGovernor) -> None:
        super().__init__(
            "marketsignal",
            token_verifier=CapabilityTokenVerifier(governor),
            auth=AuthSettings(
                issuer_url="http://127.0.0.1",
                resource_server_url=None,
                validate_token_resource=False,  # audience is checked by our verifier
                required_scopes=[],
            ),
        )
        self.governor = governor

    async def list_tools(self) -> list[MCPTool]:
        tools = []
        for name in self.governor.registry.names():
            entry = self.governor.registry.get(name)
            assert entry is not None
            tools.append(
                MCPTool(
                    name=entry.name,
                    description=entry.description,
                    input_schema=entry.input_model.model_json_schema(),
                )
            )
        return tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any], context: Context[Any, Any] | None = None
    ) -> CallToolResult:
        token = get_access_token()
        headers = context.headers if context is not None else None
        call = ToolCall(
            call_id=str((headers or {}).get(CALL_ID_HEADER, "mcp"))[:128],
            name=name,
            arguments=arguments,
            step=_header_int(headers, STEP_HEADER),
            call_index=_header_int(headers, CALL_INDEX_HEADER),
        )
        result = await self.governor.execute(
            call, credential=token.token if token is not None else "", transport="http"
        )
        return CallToolResult(
            content=[TextContent(type="text", text=result.observation)],
            structured_content=to_wire(result),
            is_error=not result.ok,
        )


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


class LoopbackOnly:
    """ASGI guard: 403 for non-loopback clients unless the endpoint is explicitly public."""

    def __init__(self, app: ASGIApp, *, public: bool) -> None:
        self._app = app
        self._public = public

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not self._public:
            client = scope.get("client")
            proxied = any(name.lower() in PROXY_HEADERS for name, _ in scope.get("headers", []))
            if proxied or not client or not _is_loopback(str(client[0])):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": b'{"error":"forbidden"}'})
                return
        await self._app(scope, receive, send)


def build_mcp_app(
    governor: ToolGovernor,
    settings: Settings,
    *,
    host: str = "127.0.0.1",
    allowed_hosts: Sequence[str] | None = None,
) -> tuple[GovernedMCPServer, ASGIApp]:
    """The server (whose ``session_manager.run()`` the parent lifespan must enter) and the
    guarded ASGI app to mount at ``/mcp``. ``allowed_hosts`` is the ``Host`` allowlist used
    when ``settings.mcp_public`` (default: loopback only); it is ignored otherwise."""
    server = GovernedMCPServer(governor)
    if settings.mcp_public:  # no browser origins: the agent client sends no Origin header
        hosts, origins = list(allowed_hosts or LOOPBACK_HOSTS), []
    else:
        hosts, origins = list(LOOPBACK_HOSTS), list(LOOPBACK_ORIGINS)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )
    app = server.streamable_http_app(
        streamable_http_path="/", stateless_http=True, host=host, transport_security=security
    )
    return server, LoopbackOnly(app, public=settings.mcp_public)
