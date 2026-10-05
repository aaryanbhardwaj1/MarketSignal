# Spike 0001: MCP Python SDK v2 compatibility

| | |
|---|---|
| Date | 2026-10-05 (Phase 0) |
| SDK | `mcp==2.3.0` (official SDK, Model Context Protocol / LF Projects); spec revision 2026-07-28 |
| Result | **Pass.** All ADR-0006 assumptions hold. |
| Executable record | `backend/tests/spikes/test_mcp_v2_spike.py` (7 tests, run in CI) |

## Why

ADR-0006 puts every model data access behind a governed MCP server, with the workspace taken from a verified capability token. The plan depends on five SDK behaviours. SDK v2 was released days before this spike, so each behaviour was verified against the installed package rather than taken from documentation.

## Verified behaviour

| # | Assumption (ADR-0006) | Finding |
|---|---|---|
| 1 | An MCP Streamable-HTTP app mounts inside FastAPI | `MCPServer.streamable_http_app(streamable_http_path="/", stateless_http=True)` returns a Starlette app that mounts at `/mcp`. The sub-app's session manager is **not** started by a mounted app's lifespan. The parent FastAPI lifespan must enter `mcp.session_manager.run()`. |
| 2 | Our own bearer-token verifier gates every call | `MCPServer(token_verifier=..., auth=AuthSettings(issuer_url=..., resource_server_url=None, validate_token_resource=False))`. With `resource_server_url=None` the SDK does not check token audience, so **our verifier does**: HS256 pinned, `aud=mcp`, `iss`, required claims, 5 s leeway. Missing, wrong-audience, expired, bad-signature and malformed tokens all return **401**. |
| 3 | Trusted claims reach handlers out of band | `mcp.server.auth.middleware.auth_context.get_access_token()` returns the verifier's `AccessToken`, including our `claims` (the workspace), inside the tool handler. No tool argument carries the workspace. |
| 4 | `Context` is not model-visible | A `ctx: Context` parameter is excluded from the advertised `input_schema`. Only `query` is listed. |
| 5 | Typed outputs | A Pydantic return type yields `output_schema` and `structured_content` on the result. That is the typed tool output the agent's evidence pool consumes. |

## Facts recorded for Phase 4

- **Client:** `Client(streamable_http_client(url, http_client=httpx2.AsyncClient(headers=...)))`. Auth headers go on the HTTP client.
- **HTTP library.** The SDK's HTTP layer is **`httpx2`**, a required dependency of `mcp` 2.x. It is published by the httpx author and its source is `github.com/pydantic/httpx2`; provenance was checked before installing. MarketSignal's own code uses `httpx` except where an MCP API requires `httpx2`.
- **In-process transport.** `Client(<MCPServer instance>)` connects in-process. That gives Phase 4a an in-process transport over the same server, and makes the Phase 4b HTTP parity test straightforward.
- **Transport security.** `streamable_http_app` accepts `transport_security` and `host` (default `127.0.0.1`). The loopback-only guard and run-liveness token revocation in ADR-0006 are still MarketSignal's responsibility.
- **Deprecated in spec 2026-07-28, not to be relied on:** Sampling, Roots, Logging.

## Not covered (deliberately)

- Anthropic tool-use, thinking and effort behaviour. The live check needs an API key and is scheduled for Phase 3.
- Render pgvector version and role privileges. These need a Render account and are scheduled before deployment (Phase 9 at the latest).
