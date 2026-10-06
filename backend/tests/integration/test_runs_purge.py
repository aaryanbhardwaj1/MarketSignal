# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""Purge always wins over runs and answers (ADR-0016), end to end as ``ms_app`` under RLS.

After a source is purged nothing stored or replayable may still quote its text: not the
answer (cited *or* merely in the run's evidence pack), not its citation cards, not the run's
event log (including events a run in flight writes after the purge), and not the
conversation's rolling summary that later prompts are built from.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.db.scope import WorkspaceScope
from marketsignal.providers.llm.fake import FakeLLM, ScriptedResponse
from marketsignal.runs import store
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_runs_api import FACT, GOOD, OTHER, _ask, _install, _scoped, _stream

pytestmark = pytest.mark.integration

RETURNS = "Returns for fit reasons rose to 31 percent of online orders in the spring season."
QUESTION = "fit inconsistency top frustration Gen Z buyers percent"


async def _seed_sections(h: Harness, ws: str, code: str, *sections: tuple[str, str]) -> None:
    body = "# Research notes\n\n" + "".join(f"## {t}\n\n{p}\n\n" for t, p in sections)
    response = await h.upload(ws, f"{code.lower()}.md", body.encode(), source_code=code)
    assert response.status_code in (200, 202), response.text
    await h.drain()


async def _source_id(h: Harness, ws: str, code: str) -> str:
    sources = (await h.client.get(f"/api/workspaces/{ws}/sources")).json()
    return str(next(s["source_id"] for s in sources if s["source_code"] == code))


async def _purge(h: Harness, ws: str, code: str) -> None:
    response = await h.client.delete(
        f"/api/workspaces/{ws}/sources/{await _source_id(h, ws, code)}"
    )
    assert response.status_code == 200, response.text


async def _run(h: Harness, ws: str, run_id: str) -> dict[str, Any]:
    body: dict[str, Any] = (await h.client.get(f"/api/workspaces/{ws}/runs/{run_id}")).json()
    return body


async def _events_quoting(engine: AsyncEngine, ws: str, run_id: str, needle: str) -> int:
    """Occurrences of ``needle`` in the run's stored events; token text is joined first, since
    coalescing can split a phrase across two ``token`` events."""
    async with engine.begin() as conn:
        await _scoped(conn, ws)
        rows = (
            await conn.execute(
                text(
                    "SELECT type, payload FROM run_events WHERE run_id = CAST(:r AS uuid) "
                    "ORDER BY seq"
                ),
                {"r": run_id},
            )
        ).all()
    tokens = "".join(str(p.get("text", "")) for t, p in rows if t == "token")
    others = " ".join(json.dumps(p) for t, p in rows if t != "token")
    return tokens.count(needle) + others.count(needle)


async def _conversation(engine: AsyncEngine, ws: str, conversation: str) -> dict[str, Any]:
    async with engine.begin() as conn:
        await _scoped(conn, ws)
        row = (
            await conn.execute(
                text(
                    "SELECT rolling_summary, recent_questions, recent_handles, "
                    "summary_through_message_id FROM conversations WHERE id = CAST(:c AS uuid)"
                ),
                {"c": conversation},
            )
        ).one()
    return {"summary": row[0], "questions": row[1], "handles": row[2], "through": row[3]}


async def _wait_for_tokens(engine: AsyncEngine, ws: str, run_id: str) -> None:
    for _ in range(500):
        async with engine.begin() as conn:
            await _scoped(conn, ws)
            n = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM run_events WHERE run_id = CAST(:r AS uuid) "
                        "AND type = 'token'"
                    ),
                    {"r": run_id},
                )
            ).scalar_one()
        if n:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the run never streamed a token")


async def test_purge_mid_stream_leaves_no_replayable_quote(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    fake = FakeLLM([ScriptedResponse(text=GOOD, chunk_size=10, delay_s=0.05)])
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    conversation, run = await _ask(harness, ws, QUESTION)
    await _wait_for_tokens(app_engine, ws, run["run_id"])
    await _purge(harness, ws, "MEMO")  # tokens quoting "27 percent" are streamed after this
    events = await _stream(harness, run["stream_url"])
    assert events[-1]["event"] == "done"
    assert "SOURCE_DELETED_DURING_RUN" in events[-1]["data"]["flags"]
    assert await _events_quoting(app_engine, ws, run["run_id"], "27 percent") == 0
    replay = await _stream(harness, run["stream_url"], last_event_id=0)
    assert all("27 percent" not in str(e["data"]) for e in replay)
    messages = (
        await harness.client.get(f"/api/workspaces/{ws}/conversations/{conversation}/messages")
    ).json()
    assert all("27 percent" not in m["content"] for m in messages)
    assert all(c["source_code"] != "MEMO" or c.get("purged") for c in messages[-1]["citations"])
    state = await _conversation(app_engine, ws, conversation)
    assert "27 percent" not in state["summary"]
    assert not any("/MEMO@v" in h for h in state["handles"])


async def test_purge_of_an_uncited_pack_source_mid_run_is_not_stored(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    fake = FakeLLM([ScriptedResponse(text=GOOD, chunk_size=10, delay_s=0.05)])
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    await _seed_sections(harness, ws, "NOTES", ("Traffic", OTHER))
    conversation, run = await _ask(harness, ws, QUESTION)
    await _wait_for_tokens(app_engine, ws, run["run_id"])
    pack = (await _run(harness, ws, run["run_id"]))["pack_handles"]
    assert pack[0].startswith(f"{ws}/MEMO@v")  # E1, the only cited alias
    assert any(h.startswith(f"{ws}/NOTES@v") for h in pack)
    await _purge(harness, ws, "NOTES")  # in the pack, never cited
    events = await _stream(harness, run["stream_url"])
    assert "SOURCE_DELETED_DURING_RUN" in events[-1]["data"]["flags"]
    final = next(e["data"] for e in events if e["event"] == "final")
    assert all(c["source_code"] == "MEMO" for c in final["citations"])
    assert await _events_quoting(app_engine, ws, run["run_id"], "Store traffic") == 0
    messages = (
        await harness.client.get(f"/api/workspaces/{ws}/conversations/{conversation}/messages")
    ).json()
    assert messages[-1]["status"] == "complete"
    assert all("Store traffic" not in m["content"] for m in messages)


async def test_purge_fallback_drops_every_parent_of_the_purged_source(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    fake = FakeLLM([ScriptedResponse(text=GOOD, chunk_size=10, delay_s=0.05)])
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT), ("Returns", RETURNS))
    await _seed_sections(harness, ws, "NOTES", ("Traffic", OTHER))
    _, run = await _ask(harness, ws, QUESTION)
    await _wait_for_tokens(app_engine, ws, run["run_id"])
    pack = (await _run(harness, ws, run["run_id"]))["pack_handles"]
    assert sum(h.startswith(f"{ws}/MEMO@v") for h in pack) == 2
    await _purge(harness, ws, "MEMO")
    events = await _stream(harness, run["stream_url"])
    assert events[-1]["data"]["termination_state"] != "tool_failure"
    final = next(e["data"] for e in events if e["event"] == "final")
    assert final["citations"]
    assert all(c["source_code"] == "NOTES" for c in final["citations"])
    stored = await _run(harness, ws, run["run_id"])
    assert stored["status"] == "completed"
    assert all(h.startswith(f"{ws}/NOTES@v") for h in stored["cited_handles"])
    assert await _events_quoting(app_engine, ws, run["run_id"], "31 percent") == 0


async def test_purge_after_answer_redacts_uncited_use_summary_and_cards(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    await _seed_sections(harness, ws, "NOTES", ("Traffic", OTHER))
    conversation, run = await _ask(harness, ws, QUESTION)
    await _stream(harness, run["stream_url"])
    before = await _conversation(app_engine, ws, conversation)
    assert "27 percent" in before["summary"]
    assert before["handles"]
    pack = (await _run(harness, ws, run["run_id"]))["pack_handles"]
    assert any(h.startswith(f"{ws}/NOTES@v") for h in pack)

    await _purge(harness, ws, "NOTES")  # in the pack, never cited: the answer is still redacted
    messages = (
        await harness.client.get(f"/api/workspaces/{ws}/conversations/{conversation}/messages")
    ).json()
    assert messages[1]["status"] == "redacted"
    assert "27 percent" not in messages[1]["content"]
    after = await _conversation(app_engine, ws, conversation)
    assert after == {"summary": "", "questions": [], "handles": [], "through": None}

    await _purge(harness, ws, "MEMO")  # the cited source: its cards become tombstones
    messages = (
        await harness.client.get(f"/api/workspaces/{ws}/conversations/{conversation}/messages")
    ).json()
    cards = messages[1]["citations"]
    assert cards
    for card in cards:
        assert card["source_code"] == "MEMO"
        assert set(card) == {"handle", "source_code", "purged"}
        assert card["purged"] is True


async def test_purge_clears_summary_of_a_conversation_that_cited_the_source(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    conversation, run = await _ask(harness, ws, QUESTION)
    await _stream(harness, run["stream_url"])
    assert "27 percent" in (await _conversation(app_engine, ws, conversation))["summary"]
    await _purge(harness, ws, "MEMO")
    after = await _conversation(app_engine, ws, conversation)
    assert after == {"summary": "", "questions": [], "handles": [], "through": None}


async def test_freezing_a_pack_drops_sources_purged_since_it_was_read(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    await _seed_sections(harness, ws, "NOTES", ("Traffic", OTHER))
    conversation, run = await _ask(harness, ws, QUESTION)
    await _stream(harness, run["stream_url"])
    pack = (await _run(harness, ws, run["run_id"]))["pack_handles"]
    app = harness.client._transport.app  # type: ignore[attr-defined]
    factory = app.state.session_factory
    async with app_engine.begin() as conn:
        ws_id = (
            await conn.execute(text("SELECT id FROM workspaces WHERE code = :c"), {"c": ws})
        ).scalar_one()
    scope = WorkspaceScope(uuid.UUID(str(ws_id)), ws)
    new_run = await store.create_run(
        factory,
        scope,
        conversation_id=uuid.UUID(conversation),
        question="q",
        mode="standard",
        persona="general",
        config_hash="x",
        prompt_version="x",
    )
    await _purge(harness, ws, "NOTES")  # after build_pack read it, before the pack is frozen
    gone = await store.freeze_pack(
        factory,
        scope,
        new_run,
        items=[(h, h.split("/", 1)[1].split("@v", 1)[0]) for h in pack],
    )
    assert gone == {"NOTES"}
    frozen = (await _run(harness, ws, str(new_run)))["pack_handles"]
    assert frozen
    assert all(h.startswith(f"{ws}/MEMO@v") for h in frozen)


async def test_failed_conversation_update_does_not_fail_a_finalized_run(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_: Any, **__: Any) -> bool:
        raise ConnectionResetError("conversation update lost")

    monkeypatch.setattr(store, "advance_conversation_state", boom)
    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    _, run = await _ask(harness, ws, QUESTION)
    events = await _stream(harness, run["stream_url"])
    assert [e["event"] for e in events][-2:] == ["final", "done"]
    assert events[-1]["data"]["termination_state"] == "completed"
    stored = await _run(harness, ws, run["run_id"])
    assert stored["status"] == "completed"
    assert stored["cited_handles"]
    assert "CONVERSATION_STATE_NOT_UPDATED" in stored["degradation_flags"]


# --- review follow-ups: withheld flood, re-upload, per-run locking, nothing after done ----------


async def _store_ctx(
    h: Harness, engine: AsyncEngine, ws: str, conversation: str
) -> tuple[Any, WorkspaceScope, uuid.UUID]:
    """(session factory, scope, a fresh in-flight run) for driving ``runs.store`` directly."""
    factory = h.client._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with engine.begin() as conn:
        ws_id = (
            await conn.execute(text("SELECT id FROM workspaces WHERE code = :c"), {"c": ws})
        ).scalar_one()
    scope = WorkspaceScope(uuid.UUID(str(ws_id)), ws)
    run_id = await store.create_run(
        factory,
        scope,
        conversation_id=uuid.UUID(conversation),
        question="q",
        mode="standard",
        persona="general",
        config_hash="x",
        prompt_version="x",
    )
    return factory, scope, run_id


def _items(handles: list[str]) -> list[tuple[str, str]]:
    return [(h, h.split("/", 1)[1].split("@v", 1)[0]) for h in handles]


async def test_withheld_draft_stops_generation_without_a_warning_flood(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    long_answer = GOOD.replace("other age groups.", "other age groups. " * 60)
    fake = FakeLLM([ScriptedResponse(text=long_answer, chunk_size=4, delay_s=0.02)])
    _install(harness, fake)  # streaming it all would take ~6 s
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    await _seed_sections(harness, ws, "NOTES", ("Traffic", OTHER))
    _, run = await _ask(harness, ws, QUESTION)
    await _wait_for_tokens(app_engine, ws, run["run_id"])
    started = asyncio.get_running_loop().time()
    await _purge(harness, ws, "MEMO")
    events = await _stream(harness, run["stream_url"])
    assert asyncio.get_running_loop().time() - started < 4  # generation was abandoned
    notices = [
        e
        for e in events
        if e["event"] == "warning" and e["data"]["code"] == "SOURCE_DELETED_DURING_RUN"
    ]
    assert 1 <= len(notices) <= 2
    final = next(e["data"] for e in events if e["event"] == "final")
    assert all(c["source_code"] == "NOTES" for c in final["citations"])
    assert events[-1]["data"]["termination_state"] != "completed"
    assert await _events_quoting(app_engine, ws, run["run_id"], "27 percent") == 0


async def test_reupload_after_purge_does_not_revive_the_purged_version(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    conversation, first = await _ask(harness, ws, QUESTION)
    await _stream(harness, first["stream_url"])
    pack = (await _run(harness, ws, first["run_id"]))["pack_handles"]
    assert pack
    assert all("/MEMO@v1:" in h for h in pack)
    factory, scope, run_id = await _store_ctx(harness, app_engine, ws, conversation)
    assert await store.freeze_pack(factory, scope, run_id, items=_items(pack)) == set()

    await _purge(harness, ws, "MEMO")  # run in flight, pack frozen on MEMO@v1 ...
    await _seed_sections(harness, ws, "MEMO", ("Returns", RETURNS))  # ... MEMO is back as v2

    stored = await store.append_event(
        factory, scope, run_id, 1, "token", {"attempt": 1, "text": FACT}
    )
    assert stored == "warning"
    card = {"handle": pack[0], "source_code": "MEMO"}
    outcome = await store.persist_answer(
        factory,
        scope,
        conversation_id=uuid.UUID(conversation),
        run_id=run_id,
        content=FACT,
        citations=[card],
        sections={},
        status="complete",
        model=None,
        usage={},
    )
    assert outcome.message_id is None
    assert outcome.purged_codes == frozenset({"MEMO"})
    _, _, late_run = await _store_ctx(harness, app_engine, ws, conversation)
    assert await store.freeze_pack(factory, scope, late_run, items=_items(pack)) == {"MEMO"}
    assert await _events_quoting(app_engine, ws, str(run_id), "27 percent") == 0


async def test_text_events_do_not_lock_shared_source_rows(
    harness: Harness, app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    conversation, first = await _ask(harness, ws, QUESTION)
    await _stream(harness, first["stream_url"])
    pack = (await _run(harness, ws, first["run_id"]))["pack_handles"]
    factory, scope, run_id = await _store_ctx(harness, app_engine, ws, conversation)
    await store.freeze_pack(factory, scope, run_id, items=_items(pack))
    async with owner_engine.connect() as conn, conn.begin():
        await _scoped(conn, ws)
        await conn.execute(
            text(
                "SELECT id FROM sources WHERE workspace_id = :ws AND source_code = 'MEMO' "
                "FOR UPDATE"
            ),
            {"ws": scope.workspace_id},
        )
        stored = await asyncio.wait_for(
            store.append_event(factory, scope, run_id, 1, "token", {"attempt": 1, "text": "x"}),
            timeout=3,
        )
    assert stored == "token"


async def test_nothing_is_appended_after_done(harness: Harness, app_engine: AsyncEngine) -> None:
    ws = await harness.create_workspace()
    created = await harness.client.post(f"/api/workspaces/{ws}/conversations", json={})
    factory, scope, run_id = await _store_ctx(
        harness, app_engine, ws, created.json()["conversation_id"]
    )
    assert await store.append_event(factory, scope, run_id, 1, "done", {}) == "done"
    assert await store.append_event(factory, scope, run_id, 2, "done", {}) is None
    assert await store.append_event(factory, scope, run_id, 3, "status", {}) is None
    assert [e.type for e in await store.load_events(factory, scope, run_id, 0)] == ["done"]


async def test_purge_deletes_verification_reports_of_runs_that_used_the_source(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    """Reports quote rejected model spans (which can quote evidence): purge removes them for
    every run whose pack held the source, and leaves other runs' reports alone."""
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    _, used = await _ask(harness, ws, QUESTION)
    await _stream(harness, used["stream_url"])
    _, other = await _ask(harness, ws, QUESTION, source_classes=["financial"])  # empty pack
    await _stream(harness, other["stream_url"])

    async def reports(run_id: str) -> int:
        async with app_engine.begin() as conn:
            await _scoped(conn, ws)
            return int(
                (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM verification_attempts "
                            "WHERE query_run_id = CAST(:r AS uuid)"
                        ),
                        {"r": run_id},
                    )
                ).scalar_one()
            )

    async with app_engine.begin() as conn:
        await _scoped(conn, ws)
        for run_id in (used["run_id"], other["run_id"]):
            await conn.execute(
                text(
                    "INSERT INTO verification_attempts (workspace_id, query_run_id, attempt, "
                    "disposition, report) SELECT workspace_id, id, 1, 'repaired', "
                    "CAST(:p AS jsonb) FROM query_runs WHERE id = CAST(:r AS uuid) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"r": run_id, "p": json.dumps({"rejected": [{"span": RETURNS[:40]}]})},
            )
    assert await reports(used["run_id"]) >= 1  # the run's own attempt report, or ours
    await _purge(harness, ws, "MEMO")
    assert await reports(used["run_id"]) == 0
    assert await reports(other["run_id"]) == 1


async def test_verification_attempt_written_after_purge_is_refused(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    """Review finding 17: a report insert takes the run-row lock and checks the pack's purge
    state in the same transaction, like every other text-bearing write."""
    from marketsignal.generation.types import VerificationReport
    from marketsignal.runs.verification_log import record_attempt

    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Fit", FACT))
    _, run = await _ask(harness, ws, QUESTION)
    await _stream(harness, run["stream_url"])
    await _purge(harness, ws, "MEMO")
    app = harness.client._transport.app  # type: ignore[attr-defined]
    async with app_engine.begin() as conn:
        await _scoped(conn, ws)
        ws_id = (await conn.execute(text("SELECT app.current_workspace()"))).scalar_one()
    scope = WorkspaceScope(uuid.UUID(str(ws_id)), ws)
    report = VerificationReport(passed=False, attempt=1, disposition="rejected")
    stored = await record_attempt(
        app.state.session_factory, scope, uuid.UUID(run["run_id"]), report
    )
    assert stored is False
    async with app_engine.begin() as conn:
        await _scoped(conn, ws)
        count = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM verification_attempts "
                    "WHERE query_run_id = CAST(:r AS uuid)"
                ),
                {"r": run["run_id"]},
            )
        ).scalar_one()
    assert count == 0


async def test_purge_redacts_agent_tool_args_and_trace_of_runs_that_saw_the_source(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    """Review finding 18: a research agent's later tool arguments can quote what it read.
    Purge redacts tool_runs.args and the agent trace (keeping the audit rows and counts) and
    deletes the event log of every run whose agent saw one of the source's handles."""
    from marketsignal.providers.llm.fake import FakeAgentLLM, ScriptedTurn, tool_use_block

    quoted = "Returns for fit reasons rose to 31 percent"
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    agent_llm = FakeAgentLLM(
        [
            ScriptedTurn(content=(tool_use_block("c1", "search_evidence", {"query": "returns"}),)),
            ScriptedTurn(content=(tool_use_block("c2", "search_evidence", {"query": quoted}),)),
            ScriptedTurn(
                content=(tool_use_block("c3", "finish_research", {"sufficient": True, "gaps": []}),)
            ),
        ]
    )
    app = harness.client._transport.app  # type: ignore[attr-defined]
    app.state.agent_llm_provider = lambda: agent_llm
    ws = await harness.create_workspace()
    await _seed_sections(harness, ws, "MEMO", ("Returns", RETURNS))
    _, run = await _ask(harness, ws, "What drives fit returns?", mode="research")
    await _stream(harness, run["stream_url"])

    async def state() -> tuple[list[str], dict[str, Any], int]:
        async with app_engine.begin() as conn:
            await _scoped(conn, ws)
            args = [
                json.dumps(r[0])
                for r in await conn.execute(
                    text("SELECT args FROM tool_runs WHERE query_run_id = CAST(:r AS uuid)"),
                    {"r": run["run_id"]},
                )
            ]
            agent = (
                await conn.execute(
                    text("SELECT agent FROM query_runs WHERE id = CAST(:r AS uuid)"),
                    {"r": run["run_id"]},
                )
            ).scalar_one()
            events = (
                await conn.execute(
                    text("SELECT count(*) FROM run_events WHERE run_id = CAST(:r AS uuid)"),
                    {"r": run["run_id"]},
                )
            ).scalar_one()
        return args, dict(agent), int(events)

    args, agent, events = await state()
    assert any(quoted in a for a in args)
    assert "trace" in agent
    assert events > 0
    await _purge(harness, ws, "MEMO")
    args, agent, events = await state()
    assert len(args) == 2  # audit rows kept
    assert all(json.loads(a) == {"redacted": True} for a in args)
    assert "trace" not in agent
    assert agent["trace_redacted"] is True
    assert agent["tool_calls"] == 2  # counts kept
    assert events == 0


async def test_purge_deletes_computed_results_and_cleans_runs_that_computed_them(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    """Phase 5: a computed analytics result is derived from a source version; purging the
    source deletes the result and treats the run that computed it as affected."""
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    ws = await harness.create_workspace()
    csv = b"segment,nps,verbatim\nGen Z,9,Fits well\nMillennial,6,Runs small\n"
    response = await harness.upload(ws, "data.csv", csv, source_code="DATA")
    assert response.status_code in (200, 202), response.text
    await harness.drain()
    # Empty pack (no financial sources): only the computed result ties this run to DATA.
    _, run = await _ask(harness, ws, "What do buyers say about fit?", source_classes=["financial"])
    await _stream(harness, run["stream_url"])

    async def count(sql: str) -> int:
        async with app_engine.begin() as conn:
            await _scoped(conn, ws)
            return int((await conn.execute(text(sql), {"r": run["run_id"]})).scalar_one())

    async with app_engine.begin() as conn:
        await _scoped(conn, ws)
        await conn.execute(
            text(
                "INSERT INTO analytics_results (workspace_id, query_run_id, source_version_id, "
                "table_id, tool, spec, result) SELECT t.workspace_id, CAST(:r AS uuid), "
                "t.source_version_id, t.id, 'aggregate', '{}', '{\"rows\": []}' "
                "FROM dataset_tables t LIMIT 1"
            ),
            {"r": run["run_id"]},
        )
    results = "SELECT count(*) FROM analytics_results WHERE query_run_id = CAST(:r AS uuid)"
    events = "SELECT count(*) FROM run_events WHERE run_id = CAST(:r AS uuid)"
    assert await count(results) == 1
    assert await count(events) > 0
    await _purge(harness, ws, "DATA")
    assert await count(results) == 0
    assert await count(events) == 0
