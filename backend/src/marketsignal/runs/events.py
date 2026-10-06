"""Run event writer: the single path by which a run emits SSE events (ADR-0008, plan §21).

* Every event is persisted to ``run_events`` (``seq`` 1, 2, 3, … per run) *before* live
  subscribers are woken, so replay (``seq > Last-Event-ID``) and live tail are one code path.
* ``token`` text is coalesced to about ``coalesce_ms`` (default 100 ms); any other event first
  flushes the pending token text, so ordering is preserved (``citation`` precedes the token
  text carrying its marker; ``final`` precedes ``done``).
* ``done`` is terminal: after it, the writer refuses further events.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory
from marketsignal.runs import store
from marketsignal.runs.broker import RunBroker

EVENT_TYPES = frozenset(
    {
        "run_started",
        "status",
        "tool_started",
        "tool_completed",
        "evidence",
        "draft_reset",
        "token",
        "citation",
        "warning",
        "final",
        "error",
        "done",
    }
)


class EventAfterDoneError(RuntimeError):
    """An event was emitted after the terminal ``done``."""


class EventWriter:
    def __init__(
        self,
        factory: SessionFactory,
        scope: WorkspaceScope,
        run_id: uuid.UUID,
        broker: RunBroker,
        *,
        coalesce_ms: int = 100,
    ) -> None:
        self._factory = factory
        self._scope = scope
        self.run_id = run_id
        self._broker = broker
        self._coalesce_s = coalesce_ms / 1000
        self.seq = 0
        self.done = False
        self._pending: dict[int, str] = {}  # attempt -> buffered token text
        self._last_flush = time.monotonic()
        self.tokens_emitted = 0

    async def _write(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.done:
            raise EventAfterDoneError(event_type)
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {event_type}")
        self.seq += 1
        body = {
            "run_id": str(self.run_id),
            "seq": self.seq,
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            **payload,
        }
        await store.append_event(
            self._factory, self._scope, self.run_id, self.seq, event_type, body
        )
        if event_type == "done":
            self.done = True
        self._broker.notify(self.run_id)

    async def flush_tokens(self) -> None:
        for attempt, text_ in sorted(self._pending.items()):
            if text_:
                await self._write("token", {"attempt": attempt, "text": text_})
                self.tokens_emitted += 1
        self._pending.clear()
        self._last_flush = time.monotonic()

    async def token(self, attempt: int, text_: str) -> None:
        if not text_:
            return
        self._pending[attempt] = self._pending.get(attempt, "") + text_
        if time.monotonic() - self._last_flush >= self._coalesce_s:
            await self.flush_tokens()

    async def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        await self.flush_tokens()
        await self._write(event_type, payload or {})
