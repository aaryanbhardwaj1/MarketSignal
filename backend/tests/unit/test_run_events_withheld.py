"""EventWriter when the store withholds text (a pack source was purged) or refuses after done."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from marketsignal.db.scope import WorkspaceScope
from marketsignal.runs import events as events_mod
from marketsignal.runs.broker import RunBroker
from marketsignal.runs.events import EventAfterDoneError, EventWriter

TEXT = {"token", "citation", "final"}


class _Store:
    """``append_event`` stand-in: text events become warnings once ``purged``; nothing after
    a stored ``done`` (returns ``None``)."""

    def __init__(self) -> None:
        self.rows: list[tuple[int, str]] = []
        self.purged = False

    async def append(
        self, _f: Any, _s: Any, _r: Any, seq: int, event_type: str, _p: dict[str, Any]
    ) -> str | None:
        if any(t == "done" for _, t in self.rows):
            return None
        stored = "warning" if self.purged and event_type in TEXT else event_type
        self.rows.append((seq, stored))
        return stored


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> _Store:
    store = _Store()
    monkeypatch.setattr(events_mod.store, "append_event", store.append)
    return store


def _writer() -> EventWriter:
    scope = WorkspaceScope(uuid.uuid4(), "WS")
    return EventWriter(None, scope, uuid.uuid4(), RunBroker(), coalesce_ms=0)  # type: ignore[arg-type]


async def test_first_withheld_text_event_is_the_only_one_stored(fake: _Store) -> None:
    writer = _writer()
    await writer.token(1, "before")
    fake.purged = True
    await writer.token(1, "quoted")
    await writer.emit("citation", {"attempt": 1, "alias": "E1"})
    await writer.token(1, "more")
    assert writer.withheld
    assert [t for _, t in fake.rows] == ["token", "warning"]
    assert [s for s, _ in fake.rows] == [1, 2]  # dropped events consume no seq


async def test_withheld_final_is_not_treated_as_emitted(fake: _Store) -> None:
    writer = _writer()
    fake.purged = True
    await writer.emit("final", {"content": "x"})
    assert writer.withheld
    assert not writer.final_emitted
    fake.purged = False  # the fallback's pack no longer includes the purged source
    await writer.emit("final", {"content": "fallback"})
    assert writer.final_emitted
    assert [t for _, t in fake.rows] == ["warning", "final"]


async def test_a_refused_done_means_already_done(fake: _Store) -> None:
    writer = _writer()
    fake.rows.append((1, "done"))  # e.g. the reaper closed the run
    writer.seq = 1
    await writer.emit("done", {})
    assert writer.done
    with pytest.raises(EventAfterDoneError):
        await writer.emit("status", {})


async def test_a_refused_event_after_done_raises(fake: _Store) -> None:
    writer = _writer()
    fake.rows.append((1, "done"))
    writer.seq = 1
    with pytest.raises(EventAfterDoneError):
        await writer.emit("status", {})
    assert writer.done
