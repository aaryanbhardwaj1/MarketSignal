"""``HttpToolTransport``: the agent's ``ToolTransport`` over MCP Streamable HTTP (spike 0001).

One short-lived ``httpx2`` client + MCP ``Client`` per call (the server is stateless and the
credential is per run), with the capability token as the bearer. Mapping:

* HTTP 401 (bearer rejected at the edge) -> ``UNAUTHENTICATED`` (the same result the in-process
  governor returns for a bad token, built by the same ``failure_result``);
* any other transport/protocol failure (connection refused, 403/5xx, timeout, malformed
  result) -> ``UNAVAILABLE``. When the server was never reached (connection refused/failed or
  connect timeout: no HTTP response at all), the result also carries the ``TRANSPORT_FAILURE``
  warning, so ``tools.fallback.FallbackToolTransport`` may safely re-run the call in-process
  (no tool ran, nothing was audited). Governor results never carry it;
* otherwise the server's ``structured_content`` (``to_wire``) becomes the ``ToolResult``.

Tool specs: ``list_tools()`` fetches the server's advertised input schemas when a
``list_credential`` is configured and adapts them with the same strict adapter; without one it
returns the shared registry's specs (identical by construction, asserted in the parity tests).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from marketsignal.mcp.server import CALL_ID_HEADER, CALL_INDEX_HEADER, STEP_HEADER
from marketsignal.tools.contracts import (
    TRANSPORT_FAILURE,
    ToolCall,
    ToolError,
    ToolResult,
    ToolSpec,
    Transport,
)
from marketsignal.tools.governance import failure_result
from marketsignal.tools.registry import ToolRegistry, default_registry
from marketsignal.tools.schema import strict_schema

log = logging.getLogger(__name__)


class HttpToolTransport:
    def __init__(
        self,
        url: str,
        *,
        timeout_s: float = 15.0,
        list_credential: str | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self._url = url if url.endswith("/") else url + "/"
        self._timeout_s = timeout_s
        self._list_credential = list_credential
        self._registry = registry or default_registry()

    @property
    def transport(self) -> Transport:
        return "http"

    @asynccontextmanager
    async def _client(
        self, credential: str, extra: dict[str, str], statuses: list[int] | None = None
    ) -> AsyncIterator[Client]:
        """``statuses`` collects every HTTP status seen, so an edge 401 is recognised exactly
        (the SDK surfaces it as a generic protocol error)."""
        headers = {**extra}
        if credential:
            headers["Authorization"] = f"Bearer {credential}"
        seen = statuses if statuses is not None else []

        async def record(response: httpx2.Response) -> None:
            seen.append(response.status_code)

        async with (
            httpx2.AsyncClient(
                headers=headers, timeout=self._timeout_s, event_hooks={"response": [record]}
            ) as http,
            Client(streamable_http_client(self._url, http_client=http)) as client,
        ):
            yield client

    async def list_tools(self) -> list[ToolSpec]:
        if self._list_credential is None:
            return self._registry.specs()
        async with self._client(self._list_credential, {}) as client:
            tools = (await client.list_tools()).tools
        specs = []
        for tool in sorted(tools, key=lambda t: t.name):
            schema = strict_schema(dict(tool.input_schema))
            entry = self._registry.get(tool.name)
            notes = entry.field_descriptions if entry is not None else {}
            props = {
                k: ({**v, "description": notes[k]} if k in notes else v)
                for k, v in schema.get("properties", {}).items()
            }
            specs.append(
                ToolSpec(tool.name, tool.description or "", {**schema, "properties": props})
            )
        return specs

    async def call(self, call: ToolCall, *, credential: str) -> ToolResult:
        meta = {
            STEP_HEADER: str(call.step),
            CALL_INDEX_HEADER: str(call.call_index),
            CALL_ID_HEADER: call.call_id[:128],
        }
        statuses: list[int] = []
        try:
            async with self._client(credential, meta, statuses) as client:
                result = await client.call_tool(call.name, call.arguments)
            wire = result.structured_content
            if not isinstance(wire, dict):
                raise ValueError("missing structured content")
            return self._from_wire(call, wire)
        except Exception as exc:
            if 401 in statuses:
                return failure_result(call, "UNAUTHENTICATED", transport="http")
            log.warning("mcp transport failure: %s", type(exc).__name__)
            failed = failure_result(call, "UNAVAILABLE", transport="http")
            if not statuses and _unreachable(exc):
                return replace(failed, warnings=(TRANSPORT_FAILURE,))
            return failed

    @staticmethod
    def _from_wire(call: ToolCall, wire: dict[str, Any]) -> ToolResult:
        error = wire.get("error")
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            ok=bool(wire["ok"]),
            output=wire.get("output"),
            observation=str(wire["observation"]),
            error=None if not error else ToolError(error["code"], str(error["message"])),
            truncated=bool(wire.get("truncated", False)),
            warnings=tuple(wire.get("warnings") or ()),
            duration_ms=float(wire.get("duration_ms", 0.0)),
            transport="http",
        )


_UNREACHABLE = (httpx2.ConnectError, httpx2.ConnectTimeout, ConnectionError)


def _unreachable(exc: BaseException) -> bool:
    """A connection-level failure anywhere in ``exc`` (causes, contexts, exception groups)."""
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        e = stack.pop()
        if id(e) in seen:
            continue
        seen.add(id(e))
        if isinstance(e, _UNREACHABLE):
            return True
        if isinstance(e, BaseExceptionGroup):
            stack.extend(e.exceptions)
        stack.extend(x for x in (e.__cause__, e.__context__) if x is not None)
    return False
