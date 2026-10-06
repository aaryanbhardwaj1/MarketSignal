"""MCP Streamable HTTP parity (ADR-0006): the same logical calls through the in-process and the
HTTP transports give equal results, equal audit rows (except ``transport``) and identical
isolation, because both run the one ``ToolGovernor``.

The HTTP side is a real loopback uvicorn server running the app ``build_mcp_app`` returns,
mounted at ``/mcp`` with the session manager entered from the parent lifespan (spike 0001)."""

from __future__ import annotations

import asyncio
import re
import socket
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy import text

from marketsignal.db.session import scoped_session
from marketsignal.mcp.client import HttpToolTransport
from marketsignal.mcp.server import build_mcp_app
from marketsignal.tools.contracts import (
    TOOLS_TRANSPORT_FALLBACK,
    TRANSPORT_FAILURE,
    ToolCall,
    ToolResult,
)
from marketsignal.tools.fallback import FallbackToolTransport
from marketsignal.tools.inprocess import InProcessToolTransport
from tests.integration.test_ingestion_api import harness  # noqa: F401 - fixture
from tests.integration.test_tools_governance import World, world  # noqa: F401 - fixture

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture
async def mcp_url(world: World) -> AsyncIterator[str]:  # noqa: F811
    server, mcp_app = build_mcp_app(world.governor, world.settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with server.session_manager.run():
            yield

    api = FastAPI(lifespan=lifespan)
    api.mount("/mcp", mcp_app)
    port = _free_port()
    uv = uvicorn.Server(
        uvicorn.Config(api, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    task = asyncio.create_task(uv.serve())
    for _ in range(250):
        if uv.started:
            break
        await asyncio.sleep(0.02)
    assert uv.started
    yield f"http://127.0.0.1:{port}/mcp/"
    uv.should_exit = True
    await task


Case = tuple[str, str, dict[str, Any], Callable[[World], str]]


def _cases(w: World) -> list[Case]:
    ok = w.token()
    b = w.token(w.ws_b)
    fin = w.token(source_classes=["financial"])
    now = int(time.time())
    return [
        ("class-claim", "search_evidence", {"query": "Gen Z fit frustration"}, lambda _: fin),
        (
            "class-filtered",
            "list_sources",
            {"source_classes": ["customer"]},
            lambda _: fin,
        ),
        (
            "class-get",
            "get_evidence",
            {"handles": [f"{w.ws_a.workspace_code}/RETURNS@v1:B1"]},
            lambda _: fin,
        ),
        ("nul-query", "search_evidence", {"query": "fit\x00gap"}, lambda _: ok),
        ("huge-handle", "get_evidence", {"handles": ["A" * 5000]}, lambda _: ok),
        ("no-jti", "list_sources", {}, lambda ww: ww.raw_token(jti=None)),
        (
            "long-lived",
            "list_sources",
            {},
            lambda ww: ww.raw_token(exp=now + 10 * 365 * 86400),
        ),
        ("search", "search_evidence", {"query": "Gen Z fit frustration", "top_k": 5}, lambda _: ok),
        ("keyword", "search_evidence_keyword", {"terms": ["RV-00412"]}, lambda _: ok),
        (
            "keyword-any",
            "search_evidence_keyword",
            {"terms": ["RV-00413", "Quorvex"], "match": "any"},
            lambda _: ok,
        ),
        (
            "get",
            "get_evidence",
            {"handles": ["nope", f"{w.ws_b.workspace_code}/MEMO@v1:B1"]},
            lambda _: ok,
        ),
        ("list", "list_sources", {}, lambda _: ok),
        ("list-b", "list_sources", {}, lambda _: b),
        ("keyword-b", "search_evidence_keyword", {"terms": ["Quorvex"]}, lambda _: b),
        (
            "smuggled-ws",
            "search_evidence",
            {"query": "Quorvex", "workspace_id": str(w.ws_b.workspace_id)},
            lambda _: ok,
        ),
        ("bad-top-k", "search_evidence", {"query": "fit", "top_k": 99}, lambda _: ok),
        ("blank-term", "search_evidence_keyword", {"terms": ["  "]}, lambda _: ok),
        ("denied", "get_evidence", {"handles": ["x"]}, lambda ww: ww.token(tools=["list_sources"])),
        ("missing-token", "list_sources", {}, lambda _: ""),
        ("expired", "list_sources", {}, lambda ww: ww.raw_token(exp=now - 120, iat=now - 180)),
        ("wrong-aud", "list_sources", {}, lambda ww: ww.raw_token(aud="sse")),
        (
            "wrong-key",
            "list_sources",
            {},
            lambda ww: ww.raw_token(key="test-only-forged-key-00000000000000000"),
        ),
        ("malformed", "list_sources", {}, lambda _: "not-a-jwt"),
        # Phase 5 analytics tools (RETURNS is a 3-row CSV in workspace A)
        ("an-describe", "describe_dataset", {}, lambda _: ok),
        ("an-describe-one", "describe_dataset", {"dataset": "RETURNS:1"}, lambda _: ok),
        ("an-class", "describe_dataset", {}, lambda _: fin),
        ("an-aggregate", "aggregate", _AN_AGG, lambda _: ok),
        ("an-compare", "group_compare", _AN_CMP, lambda _: ok),
        ("an-rows", "filter_rows", _AN_ROWS, lambda _: ok),
        ("an-foreign", "aggregate", {**_AN_AGG, "dataset": "RETURNS:1"}, lambda _: b),
        ("an-sqli", "aggregate", {**_AN_AGG, "dataset": _SQLI}, lambda _: ok),
        (
            "an-badcol",
            "aggregate",
            {"dataset": "RETURNS:1", "metrics": [{"fn": "sum", "column": _SQLI}]},
            lambda _: ok,
        ),
        (
            "an-nul",
            "filter_rows",
            {
                "dataset": "RETURNS:1",
                "filters": [{"column": "segment", "op": "eq", "value": "a\x00"}],
            },
            lambda _: ok,
        ),
    ]


_SQLI = "x'; DROP TABLE dataset_rows;--"
_GEN_Z = {"column": "segment", "op": "eq", "value": "Gen Z"}
_AN_AGG: dict[str, Any] = {
    "dataset": "RETURNS:1",
    "metrics": [{"fn": "count"}, {"fn": "share", "condition": _GEN_Z}],
    "group_by": ["segment"],
}
_AN_CMP: dict[str, Any] = {
    "dataset": "RETURNS:1",
    "metric": {"fn": "count"},
    "compare_column": "segment",
    "group_a": "Gen Z",
    "group_b": "Millennial",
}
_AN_ROWS: dict[str, Any] = {"dataset": "RETURNS:1", "filters": [_GEN_Z], "columns": ["return_id"]}
_RESULT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _masked(value: Any) -> Any:
    """result_id differs per call (each call persists its own result): mask it."""
    if isinstance(value, dict):
        return {k: "<rid>" if k == "result_id" else _masked(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_masked(v) for v in value]
    return _RESULT_ID.sub("<rid>", value) if isinstance(value, str) else value


def _view(r: ToolResult) -> tuple[Any, ...]:
    return (
        r.call_id,
        r.name,
        r.ok,
        None if r.error is None else (r.error.code, r.error.message),
        _masked(r.output),
        _masked(r.observation),
        r.truncated,
        r.warnings,
    )


async def _run_all(transport: Any, w: World, base: int) -> list[ToolResult]:
    out = []
    for i, (label, name, args, token) in enumerate(_cases(w)):
        call = ToolCall(label, name, args, step=2, call_index=base + i)
        out.append(await transport.call(call, credential=token(w)))
    return out


async def _stored_results(w: World, ids: list[str]) -> dict[str, Any]:
    async with scoped_session(w.factory, w.ws_a) as session:
        rows = await session.execute(
            text("SELECT id, result FROM analytics_results WHERE id = ANY(:ids)"),
            {"ids": [uuid.UUID(i) for i in ids]},
        )
        return {str(r[0]): r[1] for r in rows}


def _strip(rows: list[dict[str, Any]], base: int) -> list[dict[str, Any]]:
    return [
        {**{k: v for k, v in r.items() if k != "transport"}, "call_index": r["call_index"] - base}
        for r in rows
    ]


async def test_inprocess_and_http_are_equivalent(world: World, mcp_url: str) -> None:  # noqa: F811
    local = await _run_all(InProcessToolTransport(world.governor), world, 0)
    remote = await _run_all(HttpToolTransport(mcp_url), world, 100)

    assert [_view(r) for r in remote] == [_view(r) for r in local]
    assert all(r.transport == "http" for r in remote)
    assert all(r.transport == "inprocess" for r in local)
    codes = {r.call_id: (r.error.code if r.error else "OK") for r in local}
    assert codes == {
        "class-claim": "OK",
        "class-filtered": "OK",
        "class-get": "OK",
        "nul-query": "VALIDATION_ERROR",
        "huge-handle": "VALIDATION_ERROR",
        "no-jti": "UNAUTHENTICATED",
        "long-lived": "UNAUTHENTICATED",
        "search": "OK",
        "keyword": "OK",
        "keyword-any": "OK",
        "get": "OK",
        "list": "OK",
        "list-b": "OK",
        "keyword-b": "OK",
        "smuggled-ws": "VALIDATION_ERROR",
        "bad-top-k": "VALIDATION_ERROR",
        "blank-term": "VALIDATION_ERROR",
        "denied": "POLICY_DENIED",
        "missing-token": "UNAUTHENTICATED",
        "expired": "UNAUTHENTICATED",
        "wrong-aud": "UNAUTHENTICATED",
        "wrong-key": "UNAUTHENTICATED",
        "malformed": "UNAUTHENTICATED",
        "an-describe": "OK",
        "an-describe-one": "OK",
        "an-class": "OK",
        "an-aggregate": "OK",
        "an-compare": "OK",
        "an-rows": "OK",
        "an-foreign": "NOT_FOUND",
        "an-sqli": "NOT_FOUND",
        "an-badcol": "VALIDATION_ERROR",
        "an-nul": "VALIDATION_ERROR",
    }
    # analytics: identical computed results; each transport persisted its own equal row
    for label in ("an-aggregate", "an-compare", "an-rows"):
        lr = next(r for r in local if r.call_id == label)
        hr = next(r for r in remote if r.call_id == label)
        assert lr.output is not None
        assert hr.output is not None
        lid, hid = lr.output["result"]["result_id"], hr.output["result"]["result_id"]
        assert lid != hid
        assert lid in lr.observation
        stored = await _stored_results(world, [lid, hid])
        assert stored[lid] == lr.output["result"]
        assert stored[hid] == hr.output["result"]
        assert _masked(stored[lid]) == _masked(stored[hid])
    described = next(r for r in remote if r.call_id == "an-describe")
    assert described.output is not None
    assert [d["dataset"] for d in described.output["datasets"]] == ["RETURNS:1"]
    an_class = next(r for r in remote if r.call_id == "an-class")
    assert an_class.output is not None
    assert an_class.output["datasets"] == []
    # isolation is identical: A's results never contain B's canary, B's never contain A's data
    for r in [*local, *remote]:
        if r.call_id in ("search", "keyword", "keyword-any", "list", "get"):
            assert "Quorvex" not in r.observation
    keyword_any = next(r for r in remote if r.call_id == "keyword-any")
    assert keyword_any.output is not None
    assert keyword_any.output["matches_by_source"] == {"RETURNS": 1}
    filtered = next(r for r in remote if r.call_id == "class-filtered")
    assert filtered.warnings == ("SOURCE_CLASS_FILTERED",)
    claimed = next(r for r in remote if r.call_id == "class-claim")
    assert claimed.output is not None
    assert claimed.output["hits"] == []

    for scope in (world.ws_a, world.ws_b):
        rows = await world.audit(scope)
        inproc = [r for r in rows if r["transport"] == "inprocess"]
        http = [r for r in rows if r["transport"] == "http"]
        assert inproc
        assert _strip(http, 100) == _strip(inproc, 0)


async def test_http_tool_listing_matches_inprocess_specs(world: World, mcp_url: str) -> None:  # noqa: F811
    remote = await HttpToolTransport(mcp_url, list_credential=world.token()).list_tools()
    local = await InProcessToolTransport(world.governor).list_tools()
    assert remote == local


async def test_http_revoked_run_matches_inprocess(world: World, mcp_url: str) -> None:  # noqa: F811
    run_id = await world.start_run()
    token = world.token(run_id=run_id)
    http = HttpToolTransport(mcp_url)
    assert (await http.call(ToolCall("a", "list_sources", {}), credential=token)).ok
    await world.set_run_status(run_id, "completed")
    revoked = await http.call(ToolCall("b", "list_sources", {}), credential=token)
    local = await InProcessToolTransport(world.governor).call(
        ToolCall("b", "list_sources", {}), credential=token
    )
    assert _view(revoked) == _view(local)
    assert revoked.error is not None
    assert revoked.error.code == "UNAUTHENTICATED"


async def test_http_transport_failure_is_unavailable(world: World) -> None:  # noqa: F811
    dead = HttpToolTransport(f"http://127.0.0.1:{_free_port()}/mcp/", timeout_s=2.0)
    r = await dead.call(ToolCall("c", "list_sources", {}), credential=world.token())
    assert r.error is not None
    assert r.error.code == "UNAVAILABLE"
    assert r.transport == "http"
    assert r.warnings == (TRANSPORT_FAILURE,)


async def test_fallback_transport_reruns_in_process(world: World) -> None:  # noqa: F811
    dead = HttpToolTransport(f"http://127.0.0.1:{_free_port()}/mcp/", timeout_s=2.0)
    t = FallbackToolTransport(dead, InProcessToolTransport(world.governor))
    r = await t.call(ToolCall("c", "list_sources", {}), credential=world.token())
    assert r.ok, r.error
    assert r.transport == "inprocess"
    assert TOOLS_TRANSPORT_FALLBACK in r.warnings
    assert TRANSPORT_FAILURE not in r.warnings


async def test_http_governor_unavailable_is_not_a_transport_failure(
    world: World,  # noqa: F811
    mcp_url: str,
) -> None:
    run_id = await world.start_run()
    token = world.token(run_id=run_id)
    await world.set_run_status(run_id, "completed")
    r = await HttpToolTransport(mcp_url).call(ToolCall("c", "list_sources", {}), credential=token)
    assert r.error is not None
    assert TRANSPORT_FAILURE not in r.warnings


async def _post_list(app: Any, server: Any, client: str, headers: dict[str, str]) -> int:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    base = {"Accept": "application/json, text/event-stream", "Host": "127.0.0.1:8000"}
    async with (
        server.session_manager.run(),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(client, 5555)),
            base_url="http://127.0.0.1",
        ) as http,
    ):
        response = await http.post("/", json=body, headers={**base, **headers})
    return response.status_code


async def test_revoked_token_cannot_list_tools(world: World) -> None:  # noqa: F811
    run_id = await world.start_run()
    token = world.token(run_id=run_id)
    auth = {"Authorization": f"Bearer {token}"}
    server, app = build_mcp_app(world.governor, world.settings)
    assert await _post_list(app, server, "127.0.0.1", auth) == 200
    await world.set_run_status(run_id, "cancelled")
    server, app = build_mcp_app(world.governor, world.settings)
    assert await _post_list(app, server, "127.0.0.1", auth) == 401


async def test_public_mode_uses_configured_allowed_hosts(world: World) -> None:  # noqa: F811
    settings = world.settings.model_copy(update={"mcp_public": True})
    auth = {"Authorization": f"Bearer {world.token()}", "Host": "api.example.com"}
    server, app = build_mcp_app(world.governor, settings, allowed_hosts=["api.example.com"])
    assert await _post_list(app, server, "10.1.2.3", auth) == 200
    server, app = build_mcp_app(world.governor, settings, allowed_hosts=["api.example.com"])
    assert await _post_list(app, server, "10.1.2.3", {**auth, "Host": "evil.test"}) == 421
    server, app = build_mcp_app(world.governor, settings)  # default: loopback hosts only
    assert await _post_list(app, server, "10.1.2.3", auth) == 421


@pytest.mark.parametrize(
    ("public", "client", "status"),
    [
        (False, "10.1.2.3", 403),
        (False, "127.0.0.1", 401),
        (True, "10.1.2.3", 401),
    ],
)
async def test_loopback_guard(world: World, public: bool, client: str, status: int) -> None:  # noqa: F811
    settings = world.settings.model_copy(update={"mcp_public": public})
    server, app = build_mcp_app(world.governor, settings)
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {"Accept": "application/json, text/event-stream", "Host": "127.0.0.1"}
    async with (
        server.session_manager.run(),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(client, 5555)),
            base_url="http://127.0.0.1",
        ) as http,
    ):
        response = await http.post("/", json=body, headers=headers)
    assert response.status_code == status
