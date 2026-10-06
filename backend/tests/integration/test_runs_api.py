# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""Standard-mode grounded answering end to end, as ``ms_app`` under RLS, with a scripted LLM.

Real API, real ingestion and real hybrid retrieval (hash embedder); the model is ``FakeLLM`` so
every answer, failure and adversarial citation is deterministic. The real Anthropic model is
exercised by the live spike and the grounded-answer evaluation, not here.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.providers.embeddings import HashEmbedder
from marketsignal.providers.llm.base import LLMUnavailableError
from marketsignal.providers.llm.fake import FakeLLM, ScriptedResponse
from marketsignal.providers.rerankers import KeywordReranker
from marketsignal.retrieval.pipeline import RetrievalService
from marketsignal.retrieval.rerank import RerankExecutor
from marketsignal.retrieval.types import RetrievalConfig
from marketsignal.runs import store
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture

pytestmark = pytest.mark.integration

FACT = "Fit inconsistency across categories is the top frustration for 27 percent of Gen Z buyers."
OTHER = "Store traffic in the northeast region was flat compared with the prior quarter."
CANARY_B = "Quorvex tread compound lowered outsole wear by 44 percent."
RESTRICTED = "Project Halcyon acquisition target price is 912 million dollars."
ALIAS_IN_DB = re.compile(r"\[E\d{1,3}\]")

GOOD = (
    "### Answer\nFit inconsistency is the top frustration for 27 percent of Gen Z buyers [E1].\n\n"
    "### Key findings\n- 27 percent of Gen Z buyers name fit inconsistency as their top "
    "frustration [E1].\n\n### Gaps & unknowns\nThe evidence does not cover other age groups.\n"
)


def _install(h: Harness, fake: FakeLLM) -> None:
    app = h.client._transport.app  # type: ignore[attr-defined]
    app.state.query_embedder = lambda: HashEmbedder(model_id="hash-test")
    app.state.retrieval_service = RetrievalService(
        RetrievalConfig(embed_model_id="hash-test"),
        embedder=lambda: app.state.query_embedder(),
        rerank_executor=RerankExecutor(KeywordReranker()),
    )
    app.state.llm_provider = lambda: fake


async def _seed(h: Harness, ws: str, *paragraphs: str, code: str = "MEMO", **form: str) -> None:
    body = "# Research notes\n\n" + "\n\n".join(paragraphs) + "\n"
    response = await h.upload(ws, f"{code.lower()}.md", body.encode(), source_code=code, **form)
    assert response.status_code in (200, 202), response.text
    await h.drain()


def parse_sse(raw: str) -> list[dict[str, Any]]:
    events = []
    for block in raw.split("\n\n"):
        lines = [line for line in block.splitlines() if line and not line.startswith(":")]
        if not lines:
            continue
        event: dict[str, Any] = {}
        for line in lines:
            key, _, value = line.partition(":")
            event[key] = value[1:] if value.startswith(" ") else value
        event["data"] = json.loads(event["data"])
        events.append(event)
    return events


async def _ask(
    h: Harness, ws: str, question: str, conversation: str | None = None, **body: Any
) -> tuple[str, dict[str, Any]]:
    if conversation is None:
        created = await h.client.post(f"/api/workspaces/{ws}/conversations", json={})
        assert created.status_code == 201, created.text
        conversation = created.json()["conversation_id"]
    started = await h.client.post(
        f"/api/workspaces/{ws}/conversations/{conversation}/runs",
        json={"question": question, **body},
    )
    assert started.status_code == 202, started.text
    return conversation, started.json()


async def _stream(h: Harness, url: str, **params: Any) -> list[dict[str, Any]]:
    query = "".join(f"&{k}={v}" for k, v in params.items())  # keep the URL's own ?st=
    response = await asyncio.wait_for(h.client.get(url + query), timeout=30)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


def _types(events: list[dict[str, Any]]) -> list[str]:
    return [e["event"] for e in events]


async def _scoped(conn: Any, ws: str) -> None:
    await conn.execute(
        text(
            "SELECT set_config('app.workspace_id', "
            "(SELECT id::text FROM workspaces WHERE code = :c), true)"
        ),
        {"c": ws},
    )


# --- the happy path and the SSE contract -------------------------------------------------------


async def test_grounded_answer_end_to_end(harness: Harness, app_engine: AsyncEngine) -> None:
    fake = FakeLLM([ScriptedResponse(text=GOOD, chunk_size=7)])
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT, OTHER)
    conversation, run = await _ask(
        harness, ws, "What share of Gen Z buyers name fit as their top frustration?"
    )
    events = await _stream(harness, run["stream_url"])
    types = _types(events)
    assert types[0] == "run_started"
    assert types[-1] == "done"
    assert types[-2] == "final"
    assert [e["data"]["seq"] for e in events] == list(range(1, len(events) + 1))
    assert [int(e["id"]) for e in events] == list(range(1, len(events) + 1))
    for phase in ("tool_started", "tool_completed", "evidence", "token", "citation"):
        assert phase in types, phase
    # The citation event precedes the first token text that carries its marker.
    first_citation = types.index("citation")
    marker_token = next(
        i for i, e in enumerate(events) if e["event"] == "token" and "[E1]" in e["data"]["text"]
    )
    assert first_citation < marker_token
    final = events[-2]["data"]
    assert "[E1]" not in final["content"]
    assert ALIAS_IN_DB.search(final["content"]) is None
    handle = final["citations"][0]["handle"]
    assert f"[[{handle}]]" in final["content"]
    card = final["citations"][0]
    assert {"anchor_child_id", "char_start", "char_end", "parent_content_hash"} <= set(card)
    assert final["verification"]["passed"] is True
    done = events[-1]["data"]
    assert done["termination_state"] == "completed"
    assert done["cache_status"] == "disabled"
    # The cited anchor resolves to a highlight inside the cited parent (D1 end to end).
    evidence = (
        await harness.client.get(
            f"/api/workspaces/{ws}/evidence/{handle}", params={"child_id": card["anchor_child_id"]}
        )
    ).json()
    assert evidence["highlight"]["char_start"] == card["char_start"]
    # Persistence: canonical answer, run accounting, trace linked to the run.
    messages = (
        await harness.client.get(f"/api/workspaces/{ws}/conversations/{conversation}/messages")
    ).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == final["content"]
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["status"] == "completed"
    assert stored["cited_handles"] == [handle]
    assert handle in stored["pack_handles"]
    assert stored["usage"]["output_tokens"] > 0
    assert {"retrieval_ms", "pack_ms", "first_token_ms", "total_ms"} <= set(stored["timings"])
    async with app_engine.begin() as conn:
        await _scoped(conn, ws)
        traces = (
            await conn.execute(
                text("SELECT count(*) FROM retrieval_traces WHERE query_run_id = CAST(:r AS uuid)"),
                {"r": run["run_id"]},
            )
        ).scalar_one()
    assert traces == 1
    assert len(fake.requests) == 1


async def test_replay_returns_exactly_the_missed_events(harness: Harness) -> None:
    _install(harness, FakeLLM([ScriptedResponse(text=GOOD, chunk_size=5)]))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    full = await _stream(harness, run["stream_url"])
    cut = len(full) // 2
    resumed = await _stream(harness, run["stream_url"], last_event_id=cut)
    assert [e["data"]["seq"] for e in resumed] == list(range(cut + 1, len(full) + 1))
    assert resumed == full[cut:]
    header = await asyncio.wait_for(
        harness.client.get(run["stream_url"], headers={"Last-Event-ID": str(len(full) - 1)}),
        timeout=30,
    )
    assert _types(parse_sse(header.text)) == ["done"]


async def test_stream_tokens_are_bound_to_run_and_workspace(harness: Harness) -> None:
    _install(harness, FakeLLM([GOOD, GOOD]))
    a, b = await harness.create_workspace(), await harness.create_workspace()
    await _seed(harness, a, FACT)
    await _seed(harness, b, CANARY_B)
    _, run_a = await _ask(harness, a, "fit inconsistency share")
    _, run_b = await _ask(harness, b, "fit inconsistency share")
    token_a = run_a["stream_url"].split("st=")[1]
    # A's token on B's run, and A's run through B's route: both look like "not found".
    wrong_run = await harness.client.get(
        f"/api/workspaces/{b}/runs/{run_b['run_id']}/events", params={"st": token_a}
    )
    assert wrong_run.status_code == 404
    other_ws = await harness.client.get(
        f"/api/workspaces/{b}/runs/{run_a['run_id']}/events", params={"st": token_a}
    )
    assert other_ws.status_code == 404
    assert (
        await harness.client.get(f"/api/workspaces/{b}/runs/{run_a['run_id']}")
    ).status_code == 404
    missing = await harness.client.get(f"/api/workspaces/{a}/runs/{run_a['run_id']}/events")
    assert missing.status_code == 422
    await _stream(harness, run_a["stream_url"])
    await _stream(harness, run_b["stream_url"])


# --- citation adversaries ----------------------------------------------------------------------


async def test_invented_malformed_and_split_aliases(harness: Harness) -> None:
    tricky = (
        "### Answer\nFit inconsistency is the top frustration for 27 percent of Gen Z buyers "
        "[E1][E1]. Competitors are worse [E9]. Pricing is unclear [E].\n\n"
        "### Key findings\n- 27 percent name fit inconsistency **first**[E1].\n"
        "- Store traffic was flat [E12].\n\n### Gaps & unknowns\nOther segments are not "
        "covered [E1].\n"
    )
    chunks = tuple(tricky[i : i + 3] for i in range(0, len(tricky), 3))  # splits inside aliases
    fake = FakeLLM([ScriptedResponse(chunks=chunks)])
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    events = await _stream(harness, run["stream_url"])
    streamed = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "[E9]" not in streamed
    assert "[E]" not in streamed
    assert "[E12]" not in streamed
    warnings = [e["data"]["code"] for e in events if e["event"] == "warning"]
    assert warnings.count("UNKNOWN_ALIAS") == 2
    assert "MALFORMED_ALIAS" in warnings
    assert sum(1 for e in events if e["event"] == "citation") == 1  # E1 announced once
    final = events[-2]["data"]
    assert ALIAS_IN_DB.search(final["content"]) is None
    assert len(final["citations"]) == 1
    gaps = final["sections"]["gaps"]
    assert all("[[" not in unit for unit in gaps)  # citations stripped from Gaps
    assert "Store traffic" not in final["content"]  # finding citing a non-pack alias dropped


async def test_unfaithful_numbers_are_repaired_not_published(harness: Harness) -> None:
    wrong = GOOD.replace("- 27 percent of Gen Z", "- 31 percent of Gen Z")
    _install(harness, FakeLLM([wrong]))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    final = (await _stream(harness, run["stream_url"]))[-2]["data"]
    assert "31 percent" not in final["content"]
    assert final["verification"]["numeric_violations"]
    assert final["verification"]["passed"] is True  # repaired: the other units still stand


# --- abstention, regeneration and fallbacks -----------------------------------------------------


async def test_empty_pack_abstains_without_calling_the_model(harness: Harness) -> None:
    fake = FakeLLM([GOOD])
    _install(harness, fake)
    ws = await harness.create_workspace()
    _, run = await _ask(harness, ws, "What is Northstar's revenue in Japan?")
    events = await _stream(harness, run["stream_url"])
    assert fake.calls == 0
    assert "token" not in _types(events)
    final = events[-2]["data"]
    assert final["sections"]["abstained"] is True
    assert final["citations"] == []
    assert events[-1]["data"]["termination_state"] == "no_relevant_evidence"
    assert "EVIDENCE_EMPTY" in events[-1]["data"]["flags"]


async def test_structural_failure_regenerates_once_with_feedback(harness: Harness) -> None:
    no_answer = "### Key findings\n- 27 percent of Gen Z buyers name fit [E1].\n"
    fake = FakeLLM([no_answer, GOOD])
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    events = await _stream(harness, run["stream_url"])
    resets = [e["data"] for e in events if e["event"] == "draft_reset"]
    assert resets == [{**resets[0], "attempt": 2, "reason": "verification_failed"}]
    assert fake.calls == 2
    assert "verification_feedback" in fake.requests[1].messages[0]["content"]
    assert events[-1]["data"]["termination_state"] == "completed"
    assert events[-2]["data"]["verification"]["passed"] is True


@pytest.mark.parametrize(
    ("scripts", "flag"),
    [
        (["### Key findings\n- nothing\n", "still nothing"], "CITATION_VERIFICATION_FAILED"),
        ([ScriptedResponse(error=LLMUnavailableError("down"))], "LLM_SYNTHESIS_UNAVAILABLE"),
        (
            [ScriptedResponse(text="I can't help with that.", stop_reason="refusal")],
            "MODEL_REFUSAL",
        ),
        ([ScriptedResponse(text=GOOD[:60], stop_reason="max_tokens")], "GENERATION_TRUNCATED"),
    ],
)
async def test_failures_fall_back_to_evidence_only(
    harness: Harness,
    scripts: list[Any],
    flag: str,
) -> None:
    _install(harness, FakeLLM(scripts))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    events = await _stream(harness, run["stream_url"])
    final = events[-2]["data"]
    assert final["sections"]["evidence_only"]
    assert final["citations"]
    assert final["content"].startswith("### Evidence (no generated answer)")
    done = events[-1]["data"]
    assert flag in done["flags"]
    assert done["termination_state"] == "generation_unavailable"
    if "token" in _types(events):
        assert "draft_reset" in _types(events)  # the draft is withdrawn before the fallback


# --- isolation, confidentiality, purge, cancellation --------------------------------------------


async def test_pack_never_crosses_workspaces_or_confidentiality(harness: Harness) -> None:
    fake = FakeLLM([GOOD])
    _install(harness, fake)
    a, b = await harness.create_workspace(), await harness.create_workspace()
    await _seed(harness, a, FACT)
    await _seed(harness, a, RESTRICTED, code="DEAL", confidentiality="restricted")
    await _seed(harness, b, CANARY_B)
    _, run = await _ask(harness, a, "Quorvex tread compound and Project Halcyon target price")
    await _stream(harness, run["stream_url"])
    sent = fake.sent_text()
    assert "outsole wear by 44 percent" not in sent  # another workspace's document text
    assert "912 million" not in sent  # restricted > the workspace's LLM ceiling (confidential)
    stored = (await harness.client.get(f"/api/workspaces/{a}/runs/{run['run_id']}")).json()
    assert all(h.startswith(f"{a}/") for h in stored["pack_handles"])


async def test_purge_during_generation_never_stores_the_deleted_citation(
    harness: Harness,
) -> None:
    fake = FakeLLM([ScriptedResponse(text=GOOD, chunk_size=10, delay_s=0.05)])
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    source_id = (await harness.client.get(f"/api/workspaces/{ws}/sources")).json()[0]["source_id"]
    _, run = await _ask(harness, ws, "fit inconsistency share")
    while fake.calls == 0:  # noqa: ASYNC110 - test waits for the background run to call the LLM
        await asyncio.sleep(0.01)
    assert (
        await harness.client.delete(f"/api/workspaces/{ws}/sources/{source_id}")
    ).status_code == 200
    events = await _stream(harness, run["stream_url"])
    assert events[-1]["event"] == "done"
    final = next((e["data"] for e in events if e["event"] == "final"), None)
    assert final is not None
    assert all(c["source_code"] != "MEMO" for c in final["citations"])
    assert "SOURCE_DELETED_DURING_RUN" in events[-1]["data"]["flags"]


async def test_purge_after_answer_redacts_it_and_its_events(
    harness: Harness,
    app_engine: AsyncEngine,
) -> None:
    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    conversation, run = await _ask(harness, ws, "fit inconsistency share")
    await _stream(harness, run["stream_url"])
    source_id = (await harness.client.get(f"/api/workspaces/{ws}/sources")).json()[0]["source_id"]
    await harness.client.delete(f"/api/workspaces/{ws}/sources/{source_id}")
    messages = (
        await harness.client.get(f"/api/workspaces/{ws}/conversations/{conversation}/messages")
    ).json()
    assert messages[1]["status"] == "redacted"
    assert "27 percent" not in messages[1]["content"]
    async with app_engine.begin() as conn:
        await _scoped(conn, ws)
        left = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM run_events WHERE run_id = CAST(:r AS uuid) "
                    "AND payload::text LIKE '%27 percent%'"
                ),
                {"r": run["run_id"]},
            )
        ).scalar_one()
    assert left == 0


async def test_cancel_ends_with_done_cancelled(harness: Harness) -> None:
    fake = FakeLLM([ScriptedResponse(text=GOOD * 4, chunk_size=4, delay_s=0.05)])
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    while fake.calls == 0:  # noqa: ASYNC110 - test waits for the background run to call the LLM
        await asyncio.sleep(0.01)
    cancel = await harness.client.post(f"/api/workspaces/{ws}/runs/{run['run_id']}/cancel")
    assert cancel.status_code == 202
    events = await _stream(harness, run["stream_url"])
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["termination_state"] == "cancelled"
    assert "final" not in _types(events)
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["status"] == "cancelled"


# --- persistence invariants, conversation bounds, modes ----------------------------------------


async def test_no_run_local_alias_is_ever_persisted(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    _install(harness, FakeLLM([GOOD, GOOD]))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    conversation, run = await _ask(harness, ws, "fit inconsistency share")
    await _stream(harness, run["stream_url"])
    _, run2 = await _ask(harness, ws, "and other age groups?", conversation)
    await _stream(harness, run2["stream_url"])
    async with app_engine.begin() as conn:
        await _scoped(conn, ws)
        rows = (
            await conn.execute(
                text("SELECT content, citations::text, sections::text FROM messages")
            )
        ).all()
        convo = (
            await conn.execute(text("SELECT rolling_summary, recent_handles FROM conversations"))
        ).all()
    for row in rows:
        for value in row:
            assert ALIAS_IN_DB.search(value or "") is None
    for summary, handles in convo:
        assert ALIAS_IN_DB.search(summary) is None
        assert all(ALIAS_IN_DB.search(h) is None for h in handles)


async def test_conversation_context_is_bounded(harness: Harness) -> None:
    fake = FakeLLM([GOOD], repeat_last=True)
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    conversation = None
    for turn in range(20):  # enough turns for the rolling summary to reach its cap
        conversation, run = await _ask(
            harness, ws, f"fit inconsistency share, turn {turn}", conversation
        )
        await _stream(harness, run["stream_url"])
    sizes = [len(r.messages[0]["content"]) for r in fake.requests]
    last = fake.requests[-1].messages[0]["content"]
    earlier = next(line for line in last.splitlines() if line.startswith("Earlier questions"))
    assert "turn 17" in earlier
    assert "turn 18" in earlier
    assert "turn 16" not in earlier  # only the last two questions are carried verbatim
    context = last.split("</conversation_context>")[0]
    assert len(context) < 2200  # rolling summary capped (~400 tokens) + two questions
    assert max(sizes[-3:]) - min(sizes[-3:]) < 120  # once capped, input stays flat


async def test_modes(harness: Harness) -> None:
    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    created = await harness.client.post(f"/api/workspaces/{ws}/conversations", json={})
    conversation = created.json()["conversation_id"]
    research = await harness.client.post(
        f"/api/workspaces/{ws}/conversations/{conversation}/runs",
        json={"question": "x", "mode": "research"},
    )
    assert research.status_code == 422
    assert research.json()["error"]["code"] == "MODE_UNAVAILABLE"
    _, run = await _ask(harness, ws, "fit inconsistency share", conversation, mode="auto")
    events = await _stream(harness, run["stream_url"])
    assert events[0]["data"]["mode"] == "standard"


async def test_reaper_closes_orphaned_runs(harness: Harness, owner_engine: AsyncEngine) -> None:
    """A true orphan (no done) gets exactly one done(interrupted), however often reaped."""
    from marketsignal.runs.reaper import reap_interrupted_runs

    _install(harness, FakeLLM([GOOD]))
    app = harness.client._transport.app  # type: ignore[attr-defined]
    app.state.run_executor = lambda: _NoopExecutor()  # the "process died" before any event
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    await _age_run(owner_engine, ws, run["run_id"])
    assert await reap_interrupted_runs(app.state.session_factory) >= 1
    await reap_interrupted_runs(app.state.session_factory)  # idempotent
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["status"] == "interrupted"
    assert await _done_rows(owner_engine, ws, run["run_id"]) == 1
    events = await _stream(harness, run["stream_url"])
    assert _types(events) == ["done"]
    assert events[0]["data"]["termination_state"] == "interrupted"


async def test_reaper_never_adds_a_second_done(harness: Harness, owner_engine: AsyncEngine) -> None:
    """A run that wrote ``done`` but died before updating its row is synced, not re-terminated."""
    from marketsignal.runs.reaper import reap_interrupted_runs

    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    full = await _stream(harness, run["stream_url"])
    await _age_run(owner_engine, ws, run["run_id"])
    app = harness.client._transport.app  # type: ignore[attr-defined]
    await reap_interrupted_runs(app.state.session_factory)
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["status"] == "completed"
    assert stored["termination_state"] == full[-1]["data"]["termination_state"]
    assert await _done_rows(owner_engine, ws, run["run_id"]) == 1
    tail = await _stream(harness, run["stream_url"], last_event_id=10_000)
    assert tail == []


# --- termination robustness (adversarial review) ------------------------------------------------


class _NoopExecutor:
    async def execute(self, _req: Any) -> None:
        return None


async def _age_run(owner_engine: AsyncEngine, ws: str, run_id: str) -> None:
    async with owner_engine.begin() as conn:
        await _scoped(conn, ws)
        await conn.execute(
            text(
                "UPDATE query_runs SET status = 'running', created_at = now() - interval '1 hour' "
                "WHERE id = CAST(:r AS uuid)"
            ),
            {"r": run_id},
        )


async def _done_rows(owner_engine: AsyncEngine, ws: str, run_id: str) -> int:
    async with owner_engine.begin() as conn:
        await _scoped(conn, ws)
        return int(
            (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM run_events "
                        "WHERE run_id = CAST(:r AS uuid) AND type = 'done'"
                    ),
                    {"r": run_id},
                )
            ).scalar_one()
        )


def _use_executor(h: Harness, cls: type[Any] | None = None, **overrides: Any) -> None:
    from marketsignal.runs.executor import StandardRunExecutor

    app = h.client._transport.app  # type: ignore[attr-defined]
    settings = app.state.settings.model_copy(update=overrides)
    executor_cls = cls or StandardRunExecutor
    app.state.run_executor = lambda: executor_cls(
        app.state.session_factory,
        settings,
        app.state.retrieval_service,
        lambda: app.state.llm_provider(),
        app.state.run_broker,
    )


async def _wait_task(h: Harness, run_id: str) -> None:
    app = h.client._transport.app  # type: ignore[attr-defined]
    task = app.state.run_tasks.get(uuid.UUID(run_id))
    if task is not None:
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=30)


def _assert_single_terminal_done(events: list[dict[str, Any]]) -> None:
    types = _types(events)
    assert types.count("done") == 1
    assert types[-1] == "done"
    assert [e["data"]["seq"] for e in events] == list(range(1, len(events) + 1))


def _assert_draft_withdrawn(events: list[dict[str, Any]]) -> None:
    types = _types(events)
    assert "token" in types
    last_token = len(types) - 1 - types[::-1].index("token")
    assert "draft_reset" in types[last_token:]


async def _wait_for_tokens(h: Harness, owner_engine: AsyncEngine, ws: str, run_id: str) -> None:
    for _ in range(300):
        async with owner_engine.begin() as conn:
            await _scoped(conn, ws)
            n = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM run_events "
                        "WHERE run_id = CAST(:r AS uuid) AND type = 'token'"
                    ),
                    {"r": run_id},
                )
            ).scalar_one()
        if n:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("no token was streamed")


async def test_repeated_cancels_cannot_interrupt_termination(
    harness: Harness, owner_engine: AsyncEngine
) -> None:
    fake = FakeLLM([ScriptedResponse(text=GOOD * 4, chunk_size=4, delay_s=0.05)])
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    await _wait_for_tokens(harness, owner_engine, ws, run["run_id"])
    app = harness.client._transport.app  # type: ignore[attr-defined]
    task = app.state.run_tasks[uuid.UUID(run["run_id"])]
    for _ in range(200):  # a double cancel / shutdown storm while termination is running
        if task.done():
            break
        task.cancel()
        await asyncio.sleep(0.002)
    await _wait_task(harness, run["run_id"])
    events = await _stream(harness, run["stream_url"])
    _assert_single_terminal_done(events)
    assert events[-1]["data"]["termination_state"] == "cancelled"
    _assert_draft_withdrawn(events)
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["status"] == "cancelled"


async def test_cancel_twice_via_api_is_idempotent(
    harness: Harness, owner_engine: AsyncEngine
) -> None:
    fake = FakeLLM([ScriptedResponse(text=GOOD * 4, chunk_size=4, delay_s=0.05)])
    _install(harness, fake)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    await _wait_for_tokens(harness, owner_engine, ws, run["run_id"])
    url = f"/api/workspaces/{ws}/runs/{run['run_id']}/cancel"
    first, second = await asyncio.gather(harness.client.post(url), harness.client.post(url))
    assert first.status_code == second.status_code == 202
    await _wait_task(harness, run["run_id"])
    events = await _stream(harness, run["stream_url"])
    _assert_single_terminal_done(events)
    assert events[-1]["data"]["termination_state"] == "cancelled"
    assert events[-1]["data"]["flags"] is not None
    _assert_draft_withdrawn(events)


async def test_deadline_during_finalize_does_not_reterminate(harness: Harness) -> None:
    from marketsignal.runs.executor import StandardRunExecutor

    class SlowFinish(StandardRunExecutor):
        async def _finish(self, *args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(2.5)  # past the 2 s run deadline
            return await super()._finish(*args, **kwargs)

    _install(harness, FakeLLM([GOOD]))
    _use_executor(harness, SlowFinish, run_deadline_s=2.0, run_finalize_reserve_s=0.1)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    await _wait_task(harness, run["run_id"])
    events = await _stream(harness, run["stream_url"])
    _assert_single_terminal_done(events)
    assert _types(events)[-2] == "final"
    assert events[-1]["data"]["termination_state"] == "completed"
    assert "RUN_TIMEOUT" not in events[-1]["data"]["flags"]
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["status"] == "completed"


async def test_run_timeout_after_streaming_withdraws_the_draft(harness: Harness) -> None:
    from marketsignal.runs.executor import StandardRunExecutor

    class SlowVerify(StandardRunExecutor):
        async def _generate_and_verify(self, *args: Any, **kwargs: Any) -> Any:
            result = await super()._generate_and_verify(*args, **kwargs)
            await asyncio.sleep(10)  # the run deadline fires after tokens were streamed
            return result

    _install(harness, FakeLLM([ScriptedResponse(text=GOOD, chunk_size=4)]))
    _use_executor(
        harness, SlowVerify, run_deadline_s=3.0, run_finalize_reserve_s=0.5, sse_token_coalesce_ms=0
    )
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    await _wait_task(harness, run["run_id"])
    events = await _stream(harness, run["stream_url"])
    _assert_single_terminal_done(events)
    assert "final" not in _types(events)
    assert events[-1]["data"]["termination_state"] == "timeout"
    assert "RUN_TIMEOUT" in events[-1]["data"]["flags"]
    _assert_draft_withdrawn(events)
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["status"] == "failed"


async def test_slow_llm_is_clamped_to_the_deadline_and_falls_back(harness: Harness) -> None:
    fake = FakeLLM([ScriptedResponse(text=GOOD * 3, chunk_size=4, delay_s=0.1)])
    _install(harness, fake)
    _use_executor(harness, run_deadline_s=6.0, run_finalize_reserve_s=1.0)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    await _wait_task(harness, run["run_id"])
    events = await _stream(harness, run["stream_url"])
    _assert_single_terminal_done(events)
    assert fake.requests[0].timeout_s <= 5.0  # clamped: deadline - elapsed - reserve
    final = events[-2]["data"]
    assert final["sections"]["evidence_only"]
    done = events[-1]["data"]
    assert "LLM_SYNTHESIS_UNAVAILABLE" in done["flags"]
    assert "RUN_TIMEOUT" not in done["flags"]
    assert done["termination_state"] == "generation_unavailable"
    if "token" in _types(events):  # a loaded DB can leave no time to stream before the clamp
        _assert_draft_withdrawn(events)
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["status"] == "completed"
    assert stored["usage"]["llm_attempts"] == 1
    assert stored["usage"]["llm_failures"] == 1


@pytest.mark.parametrize("broken", ["unscripted", "construction"])
async def test_unusable_provider_falls_back_to_evidence_only(harness: Harness, broken: str) -> None:
    _install(harness, FakeLLM([]))
    if broken == "construction":
        app = harness.client._transport.app  # type: ignore[attr-defined]

        def missing_key() -> Any:
            raise ValueError("ANTHROPIC_API_KEY is not set")

        app.state.llm_provider = missing_key
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    events = await _stream(harness, run["stream_url"])
    _assert_single_terminal_done(events)
    assert events[-2]["data"]["sections"]["evidence_only"]
    done = events[-1]["data"]
    assert "LLM_SYNTHESIS_UNAVAILABLE" in done["flags"]
    assert done["termination_state"] == "generation_unavailable"
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["usage"]["llm_attempts"] == 1


async def test_stream_synthesizes_done_when_events_are_gone(
    harness: Harness, owner_engine: AsyncEngine
) -> None:
    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    await _stream(harness, run["stream_url"])
    async with owner_engine.begin() as conn:  # e.g. a purge removed the run's events
        await _scoped(conn, ws)
        await conn.execute(
            text("DELETE FROM run_events WHERE run_id = CAST(:r AS uuid)"), {"r": run["run_id"]}
        )
    events = await _stream(harness, run["stream_url"])
    assert _types(events) == ["done"]
    assert events[0]["data"]["termination_state"] == "completed"


async def test_stream_closes_an_overdue_orphan(harness: Harness, owner_engine: AsyncEngine) -> None:
    _install(harness, FakeLLM([GOOD]))
    app = harness.client._transport.app  # type: ignore[attr-defined]
    app.state.run_executor = lambda: _NoopExecutor()
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    await _age_run(owner_engine, ws, run["run_id"])
    events = await _stream(harness, run["stream_url"])
    assert _types(events) == ["done"]
    assert events[0]["data"]["termination_state"] == "interrupted"
    assert await _done_rows(owner_engine, ws, run["run_id"]) == 1


class _BlockedExecutor:
    """A live executor that has outlived the reap threshold (e.g. a DB-starved finalize)."""

    def __init__(self, release: asyncio.Event) -> None:
        self._release = release

    async def execute(self, _req: Any) -> None:
        await self._release.wait()


async def test_reaper_skips_runs_still_live_in_this_process(
    harness: Harness, owner_engine: AsyncEngine
) -> None:
    from marketsignal.api.app import _reap
    from marketsignal.runs.reaper import live_run_ids, reap_run

    _install(harness, FakeLLM([GOOD]))
    app = harness.client._transport.app  # type: ignore[attr-defined]
    release = asyncio.Event()
    app.state.run_executor = lambda: _BlockedExecutor(release)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    await _age_run(owner_engine, ws, run["run_id"])
    try:
        await _reap(app)  # the periodic reaper's pass
        scope = await _scope_of(owner_engine, ws)
        live = live_run_ids(app.state.run_tasks)
        assert uuid.UUID(run["run_id"]) in live
        assert not await reap_run(
            app.state.session_factory, scope, uuid.UUID(run["run_id"]), 0, exclude=live
        )
        assert await _done_rows(owner_engine, ws, run["run_id"]) == 0
    finally:
        release.set()
        await _wait_task(harness, run["run_id"])


async def _scope_of(owner_engine: AsyncEngine, ws: str) -> Any:
    from marketsignal.db.scope import WorkspaceScope

    async with owner_engine.begin() as conn:
        ws_id = (
            await conn.execute(text("SELECT id FROM workspaces WHERE code = :c"), {"c": ws})
        ).scalar_one()
    return WorkspaceScope(uuid.UUID(str(ws_id)), ws)


async def test_finalize_is_bounded_and_still_ends_with_one_done(harness: Harness) -> None:
    from marketsignal.runs.executor import StandardRunExecutor

    class StarvedFinish(StandardRunExecutor):
        async def _finish(self, *args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(30)  # e.g. pool checkout + statement timeouts under DB stress
            return await super()._finish(*args, **kwargs)

    _install(harness, FakeLLM([GOOD]))
    _use_executor(harness, StarvedFinish, run_finalize_timeout_s=1.0, run_reap_margin_s=10.0)
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    await asyncio.wait_for(_wait_task(harness, run["run_id"]), timeout=10)
    events = await _stream(harness, run["stream_url"])
    _assert_single_terminal_done(events)
    assert "final" not in _types(events)
    assert events[-1]["data"]["termination_state"] == "timeout"
    assert "RUN_TIMEOUT" in events[-1]["data"]["flags"]
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["status"] == "failed"


async def test_done_and_final_run_state_commit_together(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reader who sees ``done`` must also see the finished run row (status, usage): the two
    are committed in one transaction, never ``done`` first and the row later."""
    original = store.update_run

    async def slow_update_run(*args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(1.0)
        await original(*args, **kwargs)

    monkeypatch.setattr(store, "update_run", slow_update_run)
    _install(harness, FakeLLM([ScriptedResponse(text=GOOD)]))
    ws = await harness.create_workspace()
    await _seed(harness, ws, FACT)
    _, run = await _ask(harness, ws, "fit inconsistency share")
    events = await _stream(harness, run["stream_url"])
    assert events[-1]["event"] == "done"
    stored = (await harness.client.get(f"/api/workspaces/{ws}/runs/{run['run_id']}")).json()
    assert stored["status"] == "completed"
    assert stored["termination_state"] == events[-1]["data"]["termination_state"]
    assert stored["usage"]["llm_attempts"] == 1
    assert stored["finished_at"] is not None
