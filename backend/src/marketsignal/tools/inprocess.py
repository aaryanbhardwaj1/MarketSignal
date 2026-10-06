"""In-process tool transport: calls the governance pipeline directly with the credential.

The same ``ToolGovernor`` backs the MCP server, so in-process and HTTP calls are governed
identically (parity is tested); only the wire differs."""

from __future__ import annotations

from marketsignal.tools.contracts import ToolCall, ToolResult, ToolSpec, Transport
from marketsignal.tools.governance import ToolGovernor


class InProcessToolTransport:
    def __init__(self, governor: ToolGovernor) -> None:
        self._governor = governor

    @property
    def transport(self) -> Transport:
        return "inprocess"

    async def list_tools(self) -> list[ToolSpec]:
        return self._governor.specs()

    async def call(self, call: ToolCall, *, credential: str) -> ToolResult:
        return await self._governor.execute(call, credential=credential, transport="inprocess")
