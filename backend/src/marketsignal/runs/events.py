"""Run event writer: the single path by which a run emits SSE events (ADR-0008, plan §21).

* Every event is persisted to ``run_events`` (``seq`` 1, 2, 3, … per run) *before* live
  subscribers are woken, so replay (``seq > Last-Event-ID``) and live tail are one code path.
* ``token`` text is coalesced to about ``coalesce_ms`` (default 100 ms); any other event first
  flushes the pending token text, so ordering is preserved (``citation`` precedes the token
  text carrying its marker; ``final`` precedes ``done``).
* ``done`` is terminal: after it, the writer refuses further events.
* ``seq`` advances only after the row is written, so a failed write leaves no gap. A write that
  was *interrupted* (cancelled or errored mid-commit) may or may not have landed, so the next
  write re-reads ``max(seq)`` first; token text whose write failed is dropped, never re-sent
  (it is an unverified draft, withdrawn by ``draft_reset`` if no ``final`` follows).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
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


_DRAFT_TYPES = frozenset({"token", "citation"})


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
        self.final_emitted = False
        self.draft_open = False  # token text may be visible with no draft_reset since
        self._pending: dict[int, str] = {}  # attempt -> buffered token text
        self._last_flush = time.monotonic()
        self.tokens_emitted = 0
        self._uncertain = False  # the last write may or may not have committed
        # The store withheld a text event (a pack source was purged): later draft text is
        # dropped here, not stored as one more notice each (runs.store.append_event).
        self.withheld = False

    async def _max_seq(self) -> int:
        async with scoped_session(self._factory, self._scope) as session:
            value = (
                await session.execute(
                    text(
                        "SELECT coalesce(max(seq), 0) FROM run_events "
                        "WHERE workspace_id = :ws AND run_id = :r"
                    ),
                    {"ws": self._scope.workspace_id, "r": self.run_id},
                )
            ).scalar_one()
        return int(value)

    async def _write(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.done:
            raise EventAfterDoneError(event_type)
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {event_type}")
        if self.withheld and event_type in _DRAFT_TYPES:
            return
        if self._uncertain:
            self.seq = max(self.seq, await self._max_seq())
            self._uncertain = False
        seq = self.seq + 1
        body = {
            "run_id": str(self.run_id),
            "seq": seq,
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            **payload,
        }
        try:
            stored = await store.append_event(
                self._factory, self._scope, self.run_id, seq, event_type, body
            )
        except BaseException:
            self._uncertain = True
            raise
        if stored is None:  # the log already ends with ``done``: nothing more is ever stored
            self.done = True
            if event_type == "done":
                return
            raise EventAfterDoneError(event_type)
        self.seq = seq
        if stored != event_type:  # a text event stored as the withheld-content warning
            self.withheld = True
        elif event_type == "done":
            self.done = True
        elif event_type == "final":
            self.final_emitted = True
        elif event_type == "draft_reset":
            self.draft_open = False
        self._broker.notify(self.run_id)

    async def flush_tokens(self) -> None:
        for attempt in sorted(self._pending):
            text_ = self._pending.pop(attempt)  # popped first: a failed write is never re-sent
            if text_ and not self.withheld:
                self.draft_open = True  # conservatively: an interrupted write may have landed
                await self._write("token", {"attempt": attempt, "text": text_})
                self.tokens_emitted += 1
        self._last_flush = time.monotonic()

    def discard_pending(self) -> None:
        """Drop buffered, unsent draft text (abort paths: no point streaming then withdrawing)."""
        self._pending.clear()

    async def token(self, attempt: int, text_: str) -> None:
        if not text_:
            return
        self._pending[attempt] = self._pending.get(attempt, "") + text_
        if time.monotonic() - self._last_flush >= self._coalesce_s:
            await self.flush_tokens()

    async def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        await self.flush_tokens()
        await self._write(event_type, payload or {})
