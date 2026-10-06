"""``FallbackToolTransport``: plan §27 "MCP unreachable" (security finding 21).

Wraps the primary transport (normally ``HttpToolTransport``). When the primary reports that the
*transport itself* failed - an ``UNAVAILABLE`` result carrying the ``TRANSPORT_FAILURE``
warning, which ``HttpToolTransport`` sets only when the server was never reached - the same
call (same id, arguments, step, index and credential) is re-run through the fallback
(normally ``InProcessToolTransport`` over the same governor) and the fallback's result gains
the ``TOOLS_TRANSPORT_FALLBACK`` warning. Every other result, including an ``UNAVAILABLE`` the
governor produced, is returned unchanged: governor results are never retried.

``transport`` and ``list_tools`` are the primary's (the specs are identical by construction).
"""

from __future__ import annotations

from dataclasses import replace

from marketsignal.tools.contracts import (
    TOOLS_TRANSPORT_FALLBACK,
    TRANSPORT_FAILURE,
    ToolCall,
    ToolResult,
    ToolSpec,
    ToolTransport,
    Transport,
)


def is_transport_failure(result: ToolResult) -> bool:
    return (
        not result.ok
        and result.error is not None
        and result.error.code == "UNAVAILABLE"
        and TRANSPORT_FAILURE in result.warnings
    )


class FallbackToolTransport:
    def __init__(self, primary: ToolTransport, fallback: ToolTransport) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def transport(self) -> Transport:
        return self._primary.transport

    async def list_tools(self) -> list[ToolSpec]:
        return await self._primary.list_tools()

    async def call(self, call: ToolCall, *, credential: str) -> ToolResult:
        result = await self._primary.call(call, credential=credential)
        if not is_transport_failure(result):
            return result
        retried = await self._fallback.call(call, credential=credential)
        warnings = tuple(w for w in retried.warnings if w != TOOLS_TRANSPORT_FALLBACK)
        return replace(retried, warnings=(*warnings, TOOLS_TRANSPORT_FALLBACK))
