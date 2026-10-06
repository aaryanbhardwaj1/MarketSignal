"""Governed tools over the in-process transport (plan §17-18; ADR-0006).

Real Postgres (RLS), real ingestion (hash embedder), the production retrieval service. Every
call goes through ``ToolGovernor``: token -> revocation -> policy -> validation -> timeout +
statement_timeout -> caps -> normalized errors -> audit -> observation.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from typing import Any

import jwt
import pytest
from pydantic import BaseModel
from sqlalchemy import text

from marketsignal.config import Settings
from marketsignal.db.engine import create_engine, create_session_factory
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.providers.embeddings import HashEmbedder
from marketsignal.retrieval.pipeline import RetrievalService
from marketsignal.retrieval.rerank import RerankExecutor
from marketsignal.retrieval.types import RetrievalConfig
from marketsignal.runs import store
from marketsignal.tools.capability import AUDIENCE, ISSUER, issue
from marketsignal.tools.contracts import TOOL_NAMES, ToolCall, ToolResult
from marketsignal.tools.env import ToolEnv
from marketsignal.tools.governance import ToolGovernor
from marketsignal.tools.inprocess import InProcessToolTransport
from marketsignal.tools.registry import ToolEntry, default_registry
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture

pytestmark = pytest.mark.integration

FIT = "Fit inconsistency across categories is the top frustration for 27 percent of Gen Z buyers."
CANARY_B = "Quorvex tread compound lowered outsole wear by 44 percent."
SECRET_A = "Project Halcyon acquisition target price is 912 million dollars."
LONG = " ".join(f"Sentence {i} about sizing charts and return policies." for i in range(60))
RETURNS_CSV = (
    "return_id,segment,comment\n"
    "RV-00412,Gen Z,Sleeves ran long and the fit was inconsistent\n"
    "RV-00413,Millennial,Arrived late\n"
    "RV-00999,Gen Z,Colour faded after one wash\n"
)


class ExplodingReranker:
    """Fails the test if the experimental reranker is ever invoked."""

    calls = 0

    def score(self, *args: Any, **kwargs: Any) -> Any:
        ExplodingReranker.calls += 1
        raise AssertionError("search_evidence must not rerank")


@dataclass
class World:
    h: Harness
    settings: Settings
    factory: SessionFactory
    governor: ToolGovernor
    ws_a: WorkspaceScope
    ws_b: WorkspaceScope

    def token(self, scope: WorkspaceScope | None = None, **overrides: Any) -> str:
        scope = scope or self.ws_a
        kwargs: dict[str, Any] = {
            "run_id": None,
            "workspace_id": scope.workspace_id,
            "workspace_code": scope.workspace_code,
            "principal": "demo-user",
            "persona": "analyst",
            "tools": list(TOOL_NAMES),
            "max_conf": "confidential",
            "ttl_s": 120,
        }
        kwargs.update(overrides)
        return issue(self.settings.mcp_token_key, **kwargs)

    def raw_token(self, key: str | None = None, **claims: Any) -> str:
        now = int(time.time())
        base: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "demo-user",
            "iat": now,
            "nbf": now,
            "exp": now + 60,
            "ws": str(self.ws_a.workspace_id),
            "wsc": self.ws_a.workspace_code,
            "persona": "analyst",
            "tools": list(TOOL_NAMES),
            "max_conf": "confidential",
        }
        base.update(claims)
        return jwt.encode(
            base, key or self.settings.mcp_token_key.get_secret_value(), algorithm="HS256"
        )

    def governor_with(self, entry: ToolEntry | None = None, **settings: Any) -> ToolGovernor:
        return ToolGovernor(
            factory=self.factory,
            settings=self.settings.model_copy(update=settings),
            retrieval=self.governor._retrieval,
            registry=default_registry().replace(entry) if entry else None,
        )

    async def audit(self, scope: WorkspaceScope | None = None) -> list[dict[str, Any]]:
        async with scoped_session(self.factory, scope or self.ws_a) as session:
            rows = await session.execute(
                text(
                    "SELECT workspace_id, query_run_id, step, call_index, tool, args, status, "
                    "error_code, result_handles, result_count, total_matches, truncated, "
                    "warnings, transport FROM tool_runs ORDER BY created_at, call_index"
                )
            )
            return [dict(r._mapping) for r in rows]

    async def start_run(self) -> uuid.UUID:
        conversation = await store.create_conversation(
            self.factory, self.ws_a, persona="analyst", title="t"
        )
        return await store.create_run(
            self.factory,
            self.ws_a,
            conversation_id=conversation,
            question="q",
            mode="research",
            persona="analyst",
            config_hash="test",
            prompt_version="test",
        )

    async def set_run_status(self, run_id: uuid.UUID, status: str) -> None:
        async with scoped_session(self.factory, self.ws_a) as session:
            await session.execute(
                text("UPDATE query_runs SET status = :s WHERE id = :id"),
                {"s": status, "id": run_id},
            )
            await session.commit()


async def _scope(h: Harness, code: str) -> WorkspaceScope:
    response = await h.client.get(f"/api/workspaces/{code}")
    assert response.status_code == 200, response.text
    return WorkspaceScope(uuid.UUID(response.json()["id"]), code)


async def _upload(h: Harness, ws: str, name: str, body: str, **form: str) -> None:
    response = await h.upload(ws, name, body.encode(), **form)
    assert response.status_code in (200, 202), response.text


@pytest.fixture
async def world(harness: Harness) -> AsyncIterator[World]:  # noqa: F811
    a, b = await harness.create_workspace(), await harness.create_workspace()
    await _upload(
        harness, a, "memo.md", f"# Notes\n\n{FIT}\n\n## Policy\n\n{LONG}\n", source_code="MEMO"
    )
    await _upload(harness, a, "returns.csv", RETURNS_CSV, source_code="RETURNS")
    await _upload(
        harness,
        a,
        "deal.md",
        f"# Deal\n\n{SECRET_A}\n",
        source_code="DEAL",
        source_class="internal",
        confidentiality="restricted",
    )
    await _upload(
        harness, b, "other.md", f"# B\n\n{CANARY_B}\n\nRV-00412 {FIT}\n", source_code="MEMO"
    )
    await harness.drain()
    settings = harness.settings
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    retrieval = RetrievalService(
        RetrievalConfig(embed_model_id="hash-test", rerank=True),  # the tool must force it off
        embedder=lambda: HashEmbedder(model_id="hash-test"),
        rerank_executor=RerankExecutor(ExplodingReranker()),  # type: ignore[arg-type]
    )
    governor = ToolGovernor(factory=factory, settings=settings, retrieval=retrieval)
    yield World(
        harness, settings, factory, governor, await _scope(harness, a), await _scope(harness, b)
    )
    await engine.dispose()


async def call(
    world: World, name: str, args: dict[str, Any], *, credential: str | None = None, idx: int = 0
) -> ToolResult:
    transport = InProcessToolTransport(world.governor)
    return await transport.call(
        ToolCall(f"c{idx}", name, args, step=1, call_index=idx),
        credential=world.token() if credential is None else credential,
    )


# --- each tool -------------------------------------------------------------------------------


async def test_search_evidence_production_hybrid(world: World) -> None:
    r = await call(world, "search_evidence", {"query": "Gen Z fit frustration"})
    assert r.ok, r.error
    assert r.output is not None
    hits = r.output["hits"]
    assert hits
    assert len(hits) <= 8
    assert [h["fused_rank"] for h in hits] == sorted(h["fused_rank"] for h in hits)
    assert hits[0]["fused_rank"] == 1
    top = next(h for h in hits if h["source_code"] == "MEMO")
    assert "Fit inconsistency" in top["snippet"]
    assert all(len(h["snippet"]) <= 280 for h in hits)
    assert top["anchor_char_end"] > top["anchor_char_start"]
    assert r.output["classes_found"] == {"customer": len(hits)}
    assert ExplodingReranker.calls == 0  # experimental reranker never used
    assert f'<evidence handle="{top["handle"]}" class="customer"' in r.observation
    assert world.ws_a.workspace_code in top["handle"]
    assert str(world.ws_a.workspace_id) not in r.observation
    assert r.handles() == tuple(h["handle"] for h in hits)


async def test_search_evidence_top_k_and_filters(world: World) -> None:
    r = await call(world, "search_evidence", {"query": "fit", "top_k": 1})
    assert r.ok
    assert r.output is not None
    assert len(r.output["hits"]) == 1
    none = await call(world, "search_evidence", {"query": "fit", "source_classes": ["market"]})
    assert none.ok
    assert none.output == {"hits": [], "classes_found": {}, "warnings": none.output["warnings"]}  # type: ignore[index]


async def test_keyword_search_exact_identifiers(world: World) -> None:
    r = await call(world, "search_evidence_keyword", {"terms": ["rv-00412"]})
    assert r.ok, r.error
    assert r.output is not None
    assert r.output["total_matches"] == 1
    assert r.output["matches_by_source"] == {"RETURNS": 1}
    hit = r.output["hits"][0]
    assert "RV-00412" in hit["snippet"]
    assert "RV-00412" in r.observation
    assert "Quorvex" not in r.observation  # workspace B also has RV-00412

    any_ = await call(
        world,
        "search_evidence_keyword",
        {"terms": ["RV-00413", "Fit inconsistency"], "match": "any"},
    )
    assert any_.output is not None
    assert any_.output["matches_by_source"] == {"MEMO": 1, "RETURNS": 1}
    all_ = await call(
        world, "search_evidence_keyword", {"terms": ["RV-00413", "Fit inconsistency"]}
    )
    assert all_.output is not None
    assert all_.output["total_matches"] == 0
    phrase = await call(
        world, "search_evidence_keyword", {"terms": ["top", "frustration"], "match": "phrase"}
    )
    assert phrase.output is not None
    assert phrase.output["matches_by_source"] == {"MEMO": 1}
    limited = await call(world, "search_evidence_keyword", {"terms": ["RV-00"], "limit": 1})
    assert limited.output is not None
    assert len(limited.output["hits"]) == 1
    assert limited.output["total_matches"] >= 1  # exhaustive, not capped by limit
    again = await call(world, "search_evidence_keyword", {"terms": ["RV-00"], "limit": 1})
    assert again.output == limited.output  # deterministic


async def test_get_evidence_per_item_reasons(world: World) -> None:
    search = await call(world, "search_evidence", {"query": "sizing charts return policies"})
    handle = next(h for h in search.handles() if "MEMO" in h)
    foreign = handle.replace(world.ws_a.workspace_code, world.ws_b.workspace_code)
    missing = handle.replace("@v1:", "@v9:")
    r = await call(world, "get_evidence", {"handles": [handle, "not a handle", foreign, missing]})
    assert r.ok, r.error
    assert r.output is not None
    items = r.output["items"]
    assert items[0]["found"]
    assert items[0]["source_class"] == "customer"
    assert [i["miss_reason"] for i in items] == [None, "MALFORMED", "NOT_FOUND", "NOT_FOUND"]
    assert r.handles() == (handle,)


async def test_get_evidence_long_text_is_truncated(world: World) -> None:
    kw = await call(world, "search_evidence_keyword", {"terms": ["Sentence 59"]})
    assert kw.output is not None
    handle = kw.output["hits"][0]["handle"]
    r = await call(world, "get_evidence", {"handles": [handle]})
    assert r.ok
    assert r.truncated
    assert "TRUNCATED" in r.warnings
    assert r.output is not None
    assert len(r.output["items"][0]["text"]) <= 1200
    assert (await world.audit())[-1]["status"] == "truncated"


async def test_list_sources_respects_max_confidentiality(world: World) -> None:
    r = await call(world, "list_sources", {})
    assert r.ok
    assert r.output is not None
    assert [s["source_code"] for s in r.output["sources"]] == ["MEMO", "RETURNS"]  # DEAL restricted
    full = await call(world, "list_sources", {}, credential=world.token(max_conf="restricted"))
    assert full.output is not None
    assert [s["source_code"] for s in full.output["sources"]] == ["DEAL", "MEMO", "RETURNS"]
    only = await call(
        world,
        "list_sources",
        {"source_classes": ["internal"]},
        credential=world.token(max_conf="restricted"),
    )
    assert only.output is not None
    assert [s["source_code"] for s in only.output["sources"]] == ["DEAL"]
    hidden = await call(world, "search_evidence_keyword", {"terms": ["Halcyon"]})
    assert hidden.output is not None
    assert hidden.output["total_matches"] == 0


# --- isolation and auth ----------------------------------------------------------------------


async def test_forged_workspace_never_returns_other_workspace_data(world: World) -> None:
    cases: list[tuple[str, dict[str, Any]]] = [
        ("search_evidence", {"query": "Quorvex tread compound outsole wear"}),
        ("search_evidence_keyword", {"terms": ["Quorvex"]}),
        ("list_sources", {}),
    ]
    for name, args in cases:
        r = await call(world, name, args)
        assert r.ok
        assert "Quorvex" not in r.observation
        assert "Quorvex" not in str(r.output)
    smuggled = await call(
        world, "search_evidence", {"query": "Quorvex", "workspace_id": str(world.ws_b.workspace_id)}
    )
    assert smuggled.error is not None
    assert smuggled.error.code == "VALIDATION_ERROR"
    assert "workspace_id" in smuggled.error.message
    # token for B sees B, not A
    rb = await call(
        world,
        "search_evidence_keyword",
        {"terms": ["Fit inconsistency"]},
        credential=world.token(world.ws_b),
    )
    assert rb.output is not None
    assert rb.output["matches_by_source"] == {"MEMO": 1}
    assert all(world.ws_b.workspace_code in h for h in rb.handles())
    # a token whose ws and wsc disagree cannot read B either (RLS uses the uuid, handles the code)
    mixed = world.token(
        workspace_id=world.ws_a.workspace_id, workspace_code=world.ws_b.workspace_code
    )
    rm = await call(world, "search_evidence_keyword", {"terms": ["Quorvex"]}, credential=mixed)
    assert rm.output is not None
    assert rm.output["total_matches"] == 0


AUTH_CASES: dict[str, Callable[[World], str]] = {
    "missing": lambda w: "",
    "expired": lambda w: w.raw_token(exp=int(time.time()) - 120, iat=int(time.time()) - 180),
    "wrong_audience": lambda w: w.raw_token(aud="sse"),
    "wrong_key": lambda w: w.raw_token(key="test-only-forged-signing-key-000000000000"),
    "malformed": lambda w: "not-a-jwt",
}


@pytest.mark.parametrize("case", sorted(AUTH_CASES))
async def test_unauthenticated_credentials(world: World, case: str) -> None:
    r = await call(world, "search_evidence", {"query": "fit"}, credential=AUTH_CASES[case](world))
    assert not r.ok
    assert r.error is not None
    assert r.error.code == "UNAUTHENTICATED"
    assert r.error.message == "tool credential rejected"
    assert r.output is None
    assert await world.audit() == []  # no trusted workspace: not audited


async def test_tool_not_granted_is_policy_denied(world: World) -> None:
    r = await call(
        world, "get_evidence", {"handles": ["x"]}, credential=world.token(tools=["search_evidence"])
    )
    assert r.error is not None
    assert r.error.code == "POLICY_DENIED"
    rows = await world.audit()
    assert rows[-1]["status"] == "denied"
    assert rows[-1]["error_code"] == "POLICY_DENIED"
    assert rows[-1]["args"] == {"unvalidated_keys": ["handles"]}


async def test_revoked_run_token_is_unauthenticated(world: World) -> None:
    run_id = await world.start_run()
    token = world.token(run_id=run_id)
    ok = await call(world, "list_sources", {}, credential=token)
    assert ok.ok
    await world.set_run_status(run_id, "cancelled")
    revoked = await call(world, "list_sources", {}, credential=token)
    assert revoked.error is not None
    assert revoked.error.code == "UNAUTHENTICATED"
    rows = await world.audit()
    assert len(rows) == 1
    assert rows[0]["query_run_id"] == run_id
    unknown = await call(world, "list_sources", {}, credential=world.token(run_id=uuid.uuid4()))
    assert unknown.error is not None
    assert unknown.error.code == "UNAUTHENTICATED"


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("search_evidence", {"query": "x"}),
        ("search_evidence", {"query": "fit", "top_k": 13}),
        ("search_evidence", {"query": "fit", "top_k": "8"}),
        ("search_evidence", {"query": "fit", "source_classes": ["secret"]}),
        ("search_evidence_keyword", {"terms": []}),
        ("search_evidence_keyword", {"terms": ["x" * 61]}),
        ("search_evidence_keyword", {"terms": ["   "]}),
        ("get_evidence", {"handles": ["h"] * 9}),
        ("list_sources", {"path": "/etc/passwd"}),
    ],
    ids=[
        "short-query",
        "top-k-max",
        "coerced-int",
        "bad-class",
        "no-terms",
        "long-term",
        "blank-term",
        "too-many-handles",
        "extra-field",
    ],
)
async def test_validation_errors(world: World, name: str, args: dict[str, Any]) -> None:
    r = await call(world, name, args)
    assert r.error is not None
    assert r.error.code == "VALIDATION_ERROR"
    assert r.observation.startswith("ERROR VALIDATION_ERROR")
    assert (await world.audit())[-1]["status"] == "error"


# --- timeouts and audit ----------------------------------------------------------------------


class _Slow(BaseModel):
    pass


async def test_wall_clock_timeout(world: World) -> None:
    async def slow(env: ToolEnv, args: BaseModel) -> BaseModel:
        await asyncio.sleep(5)
        raise AssertionError("unreachable")

    entry = replace(default_registry().get("list_sources"), impl=slow)  # type: ignore[type-var]
    governor = world.governor_with(entry, tool_timeout_s=0.05)
    r = await InProcessToolTransport(governor).call(
        ToolCall("c", "list_sources", {}), credential=world.token()
    )
    assert r.error is not None
    assert r.error.code == "TIMEOUT"
    assert (await world.audit())[-1]["status"] == "timeout"


async def test_statement_timeout_is_set_locally(world: World) -> None:
    seen: list[str] = []

    async def sleepy(env: ToolEnv, args: BaseModel) -> BaseModel:
        async with scoped_session(env.factory, env.scope) as session:
            seen.append(str((await session.execute(text("SHOW statement_timeout"))).scalar_one()))
            await session.execute(text("SELECT pg_sleep(2)"))
        raise AssertionError("unreachable")

    entry = replace(default_registry().get("list_sources"), impl=sleepy)  # type: ignore[type-var]
    governor = world.governor_with(entry, tool_statement_timeout_ms=150, tool_timeout_s=5.0)
    r = await InProcessToolTransport(governor).call(
        ToolCall("c", "list_sources", {}), credential=world.token()
    )
    assert seen == ["150ms"]
    assert r.error is not None
    assert r.error.code == "TIMEOUT"
    async with scoped_session(world.factory, world.ws_a) as session:  # not leaked to the pool
        assert (await session.execute(text("SHOW statement_timeout"))).scalar_one() != "150ms"


async def test_internal_errors_are_normalized(world: World) -> None:
    async def broken(env: ToolEnv, args: BaseModel) -> BaseModel:
        raise RuntimeError("/srv/secret/path SELECT * FROM x")

    entry = replace(default_registry().get("list_sources"), impl=broken)  # type: ignore[type-var]
    r = await InProcessToolTransport(world.governor_with(entry)).call(
        ToolCall("c", "list_sources", {}), credential=world.token()
    )
    assert r.error is not None
    assert r.error.code == "INTERNAL"
    assert "secret" not in r.observation
    assert "SELECT" not in r.error.message


async def test_audit_rows_are_sanitized_and_scoped(world: World) -> None:
    run_id = await world.start_run()
    token = world.token(run_id=run_id)
    query = "fit " + "q" * 380
    r = await call(world, "search_evidence", {"query": query}, credential=token, idx=3)
    assert r.ok
    rows = await world.audit()
    assert len(rows) == 1
    row = rows[0]
    assert row["query_run_id"] == run_id
    assert row["workspace_id"] == world.ws_a.workspace_id
    assert (row["step"], row["call_index"], row["tool"]) == (1, 3, "search_evidence")
    assert row["args"] == {"query": query[:200]}
    assert row["status"] in ("ok", "truncated")
    assert row["result_handles"] == list(r.handles())
    assert row["result_count"] == len(r.handles())
    assert row["transport"] == "inprocess"
    assert token not in str(row)
    assert await world.audit(world.ws_b) == []  # RLS: B cannot see A's audit


async def test_get_evidence_after_delete_is_source_deleted(world: World) -> None:
    kw = await call(world, "search_evidence_keyword", {"terms": ["RV-00412"]})
    assert kw.output is not None
    handle = kw.output["hits"][0]["handle"]
    sources = await world.h.client.get(f"/api/workspaces/{world.ws_a.workspace_code}/sources")
    returns = next(s for s in sources.json() if s["source_code"] == "RETURNS")
    deleted = await world.h.client.delete(
        f"/api/workspaces/{world.ws_a.workspace_code}/sources/{returns['source_id']}"
    )
    assert deleted.status_code == 200
    r = await call(world, "get_evidence", {"handles": [handle]})
    assert r.output is not None
    assert r.output["items"][0]["miss_reason"] == "SOURCE_DELETED"
    gone = await call(world, "search_evidence_keyword", {"terms": ["RV-00412"]})
    assert gone.output is not None
    assert gone.output["total_matches"] == 0
