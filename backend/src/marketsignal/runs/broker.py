"""Live-tail notification for run events (ADR-0008).

Events are always persisted to ``run_events`` first; subscribers read from the table
(``seq > last``), so replay and live tail are the same code path. This broker only wakes
in-process subscribers early. Across processes a subscriber falls back to polling the table
every ``sse_poll_interval_s`` (LISTEN/NOTIFY is the documented next step), so a stream served
by another API process still sees every event, just with up to one poll interval of delay.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict


class RunBroker:
    def __init__(self) -> None:
        self._events: dict[uuid.UUID, set[asyncio.Event]] = defaultdict(set)

    def notify(self, run_id: uuid.UUID) -> None:
        for event in list(self._events.get(run_id, ())):
            event.set()

    async def wait(self, run_id: uuid.UUID, timeout_s: float) -> None:
        """Return when an event for ``run_id`` is published or after ``timeout_s``."""
        event = asyncio.Event()
        self._events[run_id].add(event)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_s)
        except TimeoutError:
            pass
        finally:
            self._events[run_id].discard(event)
            if not self._events[run_id]:
                self._events.pop(run_id, None)
