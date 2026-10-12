"""Conversations, standard-mode runs and the SSE run stream (plan §21; ADR-0008, D7, D8).

* ``POST /conversations/{cid}/runs`` creates the run (and the user message) and returns
  ``202 {run_id, stream_url}`` at once; the run executes as a background task that keeps going
  if the client disconnects (a disconnect is not a cancel).
* ``GET /runs/{rid}/events?st=…`` streams the run's events: first every persisted event with
  ``seq > Last-Event-ID`` (header or ``?last_event_id``), then the live tail, ending after
  ``done``. Replay and live tail read the same ``run_events`` rows, so a reconnect receives
  exactly the missed events. FastAPI's native ``EventSourceResponse`` sends ``: ping`` every
  15 s.
* ``POST /runs/{rid}/cancel`` cancels the run task; the run still ends with ``done``
  (``termination_state = cancelled``). Repeated cancels are idempotent.
* A stream never hangs or loops: a run with no ``done`` row that is no longer running (e.g. its
  events were purged) gets a ``done`` synthesized from ``query_runs``; a run still ``running``
  past its deadline + reap margin (its process died) is reaped, which writes ``done``.
* ``GET /conversations`` lists conversations (keyset pages on ``updated_at, id``; curated
  ``featured`` list; harness runs hidden unless ``include_test_runs``), and
  ``GET /runs/{rid}/verification`` summarizes the verification attempts without rejected spans
  (final productization phase).
* ``POST …/runs`` and ``POST …/conversations`` refuse with ``503 PROVIDER_UNAVAILABLE`` *before*
  creating any row when live generation is unavailable (``providers.llm.availability``); no
  provider text is returned.
* Modes (ADR-0015): the deterministic router (``runs.router``) decides ``standard`` or
  ``research`` from the request mode, the conversation's persona default and the cue rules; the
  decision is stored in ``query_runs.route`` and sent in ``run_started``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from marketsignal.api.deps import Factory, Principal, Scope, SettingsDep
from marketsignal.api.errors import AppError
from marketsignal.api.routers.capabilities import current_generation_status
from marketsignal.db.session import scoped_session
from marketsignal.demo import featured as featured_conversations
from marketsignal.domain.enums import SourceClass
from marketsignal.generation.prompts import PROMPT_VERSION
from marketsignal.runs import store, tokens
from marketsignal.runs.executor import RunRequest
from marketsignal.runs.reaper import (
    done_seq,
    is_overdue,
    live_run_ids,
    orphan_after_s,
    reap_run,
    synthesized_done,
)
from marketsignal.runs.router import PERSONA_DEFAULT_MODES, route

router = APIRouter(prefix="/api/workspaces/{ws}", tags=["runs"])

PROVIDER_UNAVAILABLE_MESSAGE = "Answer generation is unavailable; saved runs remain browsable."
# Test-harness runs (FakeLLM) are hidden from product lists unless include_test_runs is set.
NOT_TEST_RUN_SQL = "coalesce(models->>'synthesis', '') <> 'fake-llm'"


class ConversationIn(BaseModel):
    title: str = Field(default="", max_length=200)
    persona: str = Field(default="generalist", max_length=40)

    @field_validator("persona")
    @classmethod
    def _known_persona(cls, value: str) -> str:
        # Personas are configuration (ADR-0018): never free text that reaches a prompt.
        if value not in PERSONA_DEFAULT_MODES:
            raise ValueError(f"unknown persona; expected one of {sorted(PERSONA_DEFAULT_MODES)}")
        return value


class RunIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Absent: the persona default applies; "auto": the cue rules (ADR-0015 precedence).
    mode: Literal["auto", "standard", "research"] | None = None
    source_classes: list[SourceClass] = Field(default_factory=list, max_length=5)


def require_generation(request: Request) -> None:
    """``503 PROVIDER_UNAVAILABLE`` when live generation is unavailable; called before any row
    is written, so a refused request leaves nothing behind."""
    availability = current_generation_status(request)
    if not availability.available:
        raise AppError(
            503,
            "PROVIDER_UNAVAILABLE",
            PROVIDER_UNAVAILABLE_MESSAGE,
            reason=availability.reason,
            retryable=False,
        )


@router.post("/conversations", status_code=201)
async def create_conversation(
    request: Request, scope: Scope, factory: Factory, body: ConversationIn
) -> dict[str, Any]:
    # A conversation exists only to hold runs: refuse it up front when no run could start, so
    # the offline demo never gains empty conversations (and the API never writes there).
    require_generation(request)
    conversation_id = await store.create_conversation(
        factory, scope, persona=body.persona, title=body.title
    )
    return {"conversation_id": str(conversation_id)}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    scope: Scope, factory: Factory, conversation_id: uuid.UUID
) -> list[dict[str, Any]]:
    async with scoped_session(factory, scope) as session:
        exists = (
            await session.execute(
                text("SELECT 1 FROM conversations WHERE workspace_id = :ws AND id = :c"),
                {"ws": scope.workspace_id, "c": conversation_id},
            )
        ).first()
        if exists is None:
            raise AppError(404, "CONVERSATION_NOT_FOUND", "conversation not found")
        rows = await session.execute(
            text(
                "SELECT id, role, content, citations, sections, status, query_run_id, created_at "
                "FROM messages WHERE workspace_id = :ws AND conversation_id = :c "
                "ORDER BY created_at, id"
            ),
            {"ws": scope.workspace_id, "c": conversation_id},
        )
        return [
            {
                "message_id": str(r[0]),
                "role": r[1],
                "content": r[2],
                "citations": r[3],
                "sections": r[4],
                "status": r[5],
                "run_id": str(r[6]) if r[6] else None,
                "created_at": r[7].isoformat(),
            }
            for r in rows.all()
        ]


@router.post("/conversations/{conversation_id}/runs", status_code=202)
async def start_run(
    request: Request,
    scope: Scope,
    factory: Factory,
    settings: SettingsDep,
    principal: Principal,
    conversation_id: uuid.UUID,
    body: RunIn,
) -> dict[str, Any]:
    state = await store.conversation_state(factory, scope, conversation_id)
    if state is None:
        raise AppError(404, "CONVERSATION_NOT_FOUND", "conversation not found")
    require_generation(request)  # before create_run: a refused run leaves no rows
    question = body.question.strip()
    decision = route(
        question,
        requested=body.mode,
        persona=state.persona,
        recent_questions=tuple(state.recent_questions),
    )
    service = request.app.state.retrieval_service
    run_id = await store.create_run(
        factory,
        scope,
        conversation_id=conversation_id,
        question=question,
        mode=decision.decided,
        persona=state.persona,
        config_hash=service.config_hash,
        prompt_version=PROMPT_VERSION,
        route=decision.as_dict(),
    )
    run_request = RunRequest(
        run_id=run_id,
        scope=scope,
        conversation_id=conversation_id,
        question=question,
        persona=state.persona,
        mode=decision.decided,
        route=decision.as_dict(),
        source_classes=tuple(dict.fromkeys(c.value for c in body.source_classes)),
    )
    task = asyncio.create_task(request.app.state.run_executor().execute(run_request))
    tasks: dict[uuid.UUID, asyncio.Task[None]] = request.app.state.run_tasks
    tasks[run_id] = task
    task.add_done_callback(lambda _: tasks.pop(run_id, None))
    stream_token = tokens.issue(
        settings.stream_token_secret.get_secret_value(),
        run_id=run_id,
        workspace_code=scope.workspace_code,
        subject=principal,
        ttl_s=int(settings.run_deadline_s) + settings.stream_token_replay_s,
    )
    base = f"/api/workspaces/{scope.workspace_code}/runs/{run_id}"
    return {
        "run_id": str(run_id),
        "stream_url": f"{base}/events?st={stream_token}",
        "mode": decision.decided,
        "route": decision.as_dict(),
    }


@router.get("/runs/{run_id}")
async def get_run(scope: Scope, factory: Factory, run_id: uuid.UUID) -> dict[str, Any]:
    run = await store.get_run(factory, scope, run_id)
    if run is None:
        raise AppError(404, "RUN_NOT_FOUND", "run not found")
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in run.items()}


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(
    request: Request, scope: Scope, factory: Factory, run_id: uuid.UUID
) -> dict[str, Any]:
    run = await store.get_run(factory, scope, run_id)
    if run is None:
        raise AppError(404, "RUN_NOT_FOUND", "run not found")
    task: asyncio.Task[None] | None = request.app.state.run_tasks.get(run_id)
    if task is None or task.done():
        # Cancellation is process-local (known limitation): a run executing in another API
        # process is not reachable from here, so this reports cancel_requested=false and that
        # run ends at its deadline. Cross-process cancel needs a shared signal (LISTEN/NOTIFY).
        requested = False
    elif task.cancelling():
        requested = True  # already cancelling: a second cancel would interrupt its termination
    else:
        requested = task.cancel()
    return {"run_id": str(run_id), "cancel_requested": requested, "status": run["status"]}


async def authorized_stream(
    scope: Scope,
    factory: Factory,
    settings: SettingsDep,
    run_id: uuid.UUID,
    st: Annotated[str, Query(min_length=10, max_length=2000)],
) -> uuid.UUID:
    """Validated *before* the stream starts (a generator cannot turn errors into a status code):
    a bad, expired or foreign token and an unknown run all look like ``404``."""
    try:
        tokens.verify(
            settings.stream_token_secret.get_secret_value(),
            st,
            run_id=run_id,
            workspace_code=scope.workspace_code,
        )
    except tokens.InvalidStreamTokenError as exc:
        raise AppError(404, "RUN_NOT_FOUND", "run not found") from exc
    if await store.get_run(factory, scope, run_id) is None:
        raise AppError(404, "RUN_NOT_FOUND", "run not found")
    return run_id


@router.get("/runs/{run_id}/events", response_class=EventSourceResponse)
async def run_events(
    request: Request,
    scope: Scope,
    factory: Factory,
    settings: SettingsDep,
    run_id: Annotated[uuid.UUID, Depends(authorized_stream)],
    last_event_id: Annotated[int | None, Query(ge=0)] = None,
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> AsyncIterator[ServerSentEvent]:
    after = last_event_id or 0
    if last_event_id_header and last_event_id_header.isdigit():
        after = max(after, int(last_event_id_header))
    broker = request.app.state.run_broker
    while True:
        events = await store.load_events(factory, scope, run_id, after)
        for event in events:
            after = event.seq
            yield ServerSentEvent(data=event.payload, event=event.type, id=str(event.seq))
            if event.type == "done":
                return
        if await request.is_disconnected():
            return
        if not events:
            run = await store.get_run(factory, scope, run_id)
            if run is None:
                return
            if run["status"] != "running":
                last_done = await done_seq(factory, scope, run_id)
                if last_done is not None and last_done > after:
                    continue  # done landed after our read: the next pass delivers it
                if last_done is None:  # no done row at all (e.g. purged): never leave it open
                    seq = after + 1
                    yield ServerSentEvent(
                        data=synthesized_done(run, seq), event="done", id=str(seq)
                    )
                return  # complete: the client already has done
            if is_overdue(run, settings) and await reap_run(
                factory,
                scope,
                run_id,
                orphan_after_s(settings),
                exclude=live_run_ids(request.app.state.run_tasks),  # live here: not an orphan
            ):
                continue  # the orphan now has its done
        await broker.wait(run_id, settings.sse_poll_interval_s)


# --- conversation list and verification summary (final productization phase) ------------------


def encode_cursor(at: datetime, row_id: uuid.UUID) -> str:
    """Opaque keyset cursor: base64("<iso timestamp>|<uuid>")."""
    return base64.urlsafe_b64encode(f"{at.isoformat()}|{row_id}".encode()).decode()


def decode_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    """The cursor's (timestamp, id), ``None`` for no cursor; a malformed one is a 422."""
    if not cursor:
        return None
    try:
        at, _, row_id = base64.urlsafe_b64decode(cursor.encode()).decode().partition("|")
        parsed = datetime.fromisoformat(at), uuid.UUID(row_id)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise AppError(422, "VALIDATION_ERROR", "invalid cursor", fields=[]) from exc
    if parsed[0].tzinfo is None:
        raise AppError(422, "VALIDATION_ERROR", "invalid cursor", fields=[])
    return parsed


def like_pattern(q: str | None) -> str | None:
    """``%q%`` for ILIKE with ``\\`` as the escape character; ``None`` for an empty query."""
    q = (q or "").strip()
    if not q:
        return None
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


_CONVERSATIONS = f"""
WITH page AS (
    -- Filter, order and limit first (index conversations_ws_updated); only the page's rows
    -- are then joined to their first question, message count and latest run.
    SELECT c.id, c.workspace_id, c.title, c.created_at, c.updated_at
    FROM conversations c
    WHERE c.workspace_id = :ws
      AND (CAST(:include_test AS boolean) OR NOT EXISTS (
            SELECT 1 FROM query_runs t
            WHERE t.workspace_id = c.workspace_id AND t.conversation_id = c.id
              AND NOT ({NOT_TEST_RUN_SQL})))
      AND (CAST(:q AS text) IS NULL
           OR c.title ILIKE CAST(:q AS text) ESCAPE '\\'
           OR (SELECT m.content FROM messages m
                WHERE m.workspace_id = c.workspace_id AND m.conversation_id = c.id
                  AND m.role = 'user'
                ORDER BY m.created_at, m.id LIMIT 1) ILIKE CAST(:q AS text) ESCAPE '\\')
      AND (CAST(:ids AS uuid[]) IS NULL OR c.id = ANY(CAST(:ids AS uuid[])))
      AND (CAST(:c_at AS timestamptz) IS NULL
           OR (c.updated_at, c.id) < (CAST(:c_at AS timestamptz), CAST(:c_id AS uuid)))
    ORDER BY c.updated_at DESC, c.id DESC
    LIMIT :limit
)
SELECT p.id, p.title, p.created_at, p.updated_at, fq.content AS first_question,
       (SELECT count(*) FROM messages m
         WHERE m.workspace_id = p.workspace_id AND m.conversation_id = p.id) AS message_count,
       lr.id AS run_id, lr.mode, lr.status, lr.termination_state, lr.degradation_flags,
       lr.created_at AS run_created_at, lr.finished_at
FROM page p
LEFT JOIN LATERAL (
    SELECT content FROM messages m
    WHERE m.workspace_id = p.workspace_id AND m.conversation_id = p.id AND m.role = 'user'
    ORDER BY m.created_at, m.id LIMIT 1
) fq ON true
LEFT JOIN LATERAL (
    -- index query_runs_ws_conversation
    SELECT id, mode, status, termination_state, degradation_flags, created_at, finished_at
    FROM query_runs r
    WHERE r.workspace_id = p.workspace_id AND r.conversation_id = p.id
    ORDER BY r.created_at DESC, r.id DESC LIMIT 1
) lr ON true
ORDER BY p.updated_at DESC, p.id DESC
"""  # noqa: S608 - the only interpolation is the NOT_TEST_RUN_SQL constant


def _conversation_item(row: Any, featured_set: frozenset[uuid.UUID]) -> dict[str, Any]:
    title = (row.title or "").strip()
    last_run = None
    if row.run_id is not None:
        last_run = {
            "run_id": str(row.run_id),
            "mode": row.mode,
            "status": row.status,
            "termination_state": row.termination_state,
            "degradation_flags": list(row.degradation_flags or []),
            "created_at": row.run_created_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }
    return {
        "conversation_id": str(row.id),
        "title": title or (row.first_question or "").strip(),
        "title_source": "title" if title else "first_question",
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "message_count": int(row.message_count),
        "featured": row.id in featured_set,
        "last_run": last_run,
    }


@router.get("/conversations")
async def list_conversations(
    scope: Scope,
    factory: Factory,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    featured: bool = False,
    include_test_runs: bool = False,
) -> dict[str, Any]:
    """Conversations, newest activity first. ``featured=true`` returns the curated list in its
    display order (one page; ids missing from this workspace are dropped)."""
    featured_order = featured_conversations.featured_ids(scope.workspace_code)
    featured_set = frozenset(featured_order)
    after = None if featured else decode_cursor(cursor)
    if featured and not featured_order:
        return {"items": [], "next_cursor": None}
    params = {
        "ws": scope.workspace_id,
        "include_test": include_test_runs,
        "q": like_pattern(q),
        "ids": list(featured_order) if featured else None,
        "c_at": after[0] if after else None,
        "c_id": after[1] if after else None,
        "limit": len(featured_order) if featured else limit + 1,
    }
    async with scoped_session(factory, scope) as session:
        rows = (await session.execute(text(_CONVERSATIONS), params)).all()
    if featured:
        position = {cid: i for i, cid in enumerate(featured_order)}
        ordered = sorted(rows, key=lambda r: position[r.id])[:limit]
        return {
            "items": [_conversation_item(r, featured_set) for r in ordered],
            "next_cursor": None,
        }
    page = rows[:limit]
    next_cursor = (
        encode_cursor(page[-1].updated_at, page[-1].id) if len(rows) > limit and page else None
    )
    return {
        "items": [_conversation_item(r, featured_set) for r in page],
        "next_cursor": next_cursor,
    }


def _str_list(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _attempt_summary(attempt: int, disposition: str, report: Any) -> dict[str, Any]:
    """One attempt, without the rejected model spans (reason, section and aliases only)."""
    report = report if isinstance(report, dict) else {}
    rejected = [
        {
            "reason": str(r.get("reason", "")),
            "section": str(r["section"]) if r.get("section") is not None else None,
            "aliases": _str_list(r.get("aliases")),
        }
        for r in report.get("rejected") or []
        if isinstance(r, dict)
    ]
    return {
        "attempt": attempt,
        "disposition": disposition,
        "passed": bool(report.get("passed", False)),
        "citations": int(report.get("citations") or 0),
        "failure_categories": _str_list(report.get("failure_categories")),
        "repairs_n": len(report.get("repairs") or []),
        "rejected": rejected,
        "result_ids": _str_list(report.get("result_ids")),
    }


@router.get("/runs/{run_id}/verification")
async def get_run_verification(scope: Scope, factory: Factory, run_id: uuid.UUID) -> dict[str, Any]:
    async with scoped_session(factory, scope) as session:
        exists = (
            await session.execute(
                text("SELECT 1 FROM query_runs WHERE workspace_id = :ws AND id = :r"),
                {"ws": scope.workspace_id, "r": run_id},
            )
        ).first()
        if exists is None:
            raise AppError(404, "RUN_NOT_FOUND", "run not found")
        rows = (
            await session.execute(
                text(
                    "SELECT attempt, disposition, report FROM verification_attempts "
                    "WHERE workspace_id = :ws AND query_run_id = :r ORDER BY attempt, created_at"
                ),
                {"ws": scope.workspace_id, "r": run_id},
            )
        ).all()
    attempts = [_attempt_summary(int(r[0]), str(r[1]), r[2]) for r in rows]
    return {
        "run_id": str(run_id),
        "final_disposition": attempts[-1]["disposition"] if attempts else None,
        "attempts": attempts,
    }
