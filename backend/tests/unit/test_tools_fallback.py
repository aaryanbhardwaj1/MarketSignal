"""``FallbackToolTransport`` (plan §27 "MCP unreachable"; security finding 21): a transport
failure of the primary (HTTP) transport re-runs the same call in-process and says so; governor
results (including UNAVAILABLE from the governor itself) are never retried."""

from __future__ import annotations

from dataclasses import replace

from marketsignal.tools.contracts import (
    TOOLS_TRANSPORT_FALLBACK,
    TRANSPORT_FAILURE,
    ToolCall,
    ToolResult,
    ToolSpec,
    Transport,
)
from marketsignal.tools.fallback import FallbackToolTransport
from marketsignal.tools.governance import failure_result

CALL = ToolCall("c1", "list_sources", {}, step=1, call_index=2)


class _Scripted:
    def __init__(self, transport: Transport, result: ToolResult) -> None:
        self._transport: Transport = transport
        self._result = result
        self.calls: list[tuple[ToolCall, str]] = []

    @property
    def transport(self) -> Transport:
        return self._transport

    async def list_tools(self) -> list[ToolSpec]:
        return [ToolSpec(self._transport, "d", {"type": "object"})]

    async def call(self, call: ToolCall, *, credential: str) -> ToolResult:
        self.calls.append((call, credential))
        return self._result


def _ok(transport: Transport) -> ToolResult:
    return ToolResult(
        call_id=CALL.call_id,
        name=CALL.name,
        ok=True,
        output={"sources": [], "warnings": []},
        observation="0 sources",
        warnings=("X",),
        transport=transport,
    )


def _transport_failure() -> ToolResult:
    base = failure_result(CALL, "UNAVAILABLE", transport="http")
    return replace(base, warnings=(TRANSPORT_FAILURE,))


async def test_transport_failure_falls_back_with_warning() -> None:
    primary = _Scripted("http", _transport_failure())
    fallback = _Scripted("inprocess", _ok("inprocess"))
    t = FallbackToolTransport(primary, fallback)
    r = await t.call(CALL, credential="tok")
    assert r.ok
    assert r.transport == "inprocess"
    assert r.warnings == ("X", TOOLS_TRANSPORT_FALLBACK)
    assert fallback.calls == [(CALL, "tok")]  # the same call and credential


async def test_governor_results_are_never_retried() -> None:
    for result in (
        failure_result(CALL, "UNAVAILABLE", transport="http"),  # governor-side UNAVAILABLE
        failure_result(CALL, "UNAUTHENTICATED", transport="http"),
        failure_result(CALL, "TIMEOUT", transport="http"),
        _ok("http"),
    ):
        primary = _Scripted("http", result)
        fallback = _Scripted("inprocess", _ok("inprocess"))
        r = await FallbackToolTransport(primary, fallback).call(CALL, credential="tok")
        assert r is result
        assert fallback.calls == []


async def test_failed_fallback_keeps_both_warnings() -> None:
    primary = _Scripted("http", _transport_failure())
    fallback = _Scripted("inprocess", failure_result(CALL, "UNAVAILABLE"))
    r = await FallbackToolTransport(primary, fallback).call(CALL, credential="tok")
    assert not r.ok
    assert r.error is not None
    assert r.error.code == "UNAVAILABLE"
    assert TOOLS_TRANSPORT_FALLBACK in r.warnings


async def test_transport_identity_and_listing_come_from_primary() -> None:
    primary = _Scripted("http", _ok("http"))
    t = FallbackToolTransport(primary, _Scripted("inprocess", _ok("inprocess")))
    assert t.transport == "http"
    assert [s.name for s in await t.list_tools()] == ["http"]
