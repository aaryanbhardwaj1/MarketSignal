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
* Modes (ADR-0015): the deterministic router (``runs.router``) decides ``standard`` or
  ``research`` from the request mode, the conversation's persona default and the cue rules; the
  decision is stored in ``query_runs.route`` and sent in ``run_started``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from marketsignal.api.deps import Factory, Principal, Scope, SettingsDep
from marketsignal.api.errors import AppError
from marketsignal.db.session import scoped_session
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


@router.post("/conversations", status_code=201)
async def create_conversation(
    scope: Scope, factory: Factory, body: ConversationIn
) -> dict[str, Any]:
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
