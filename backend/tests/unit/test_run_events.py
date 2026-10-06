"""EventWriter sequencing under failed / interrupted writes, and pure run-liveness helpers."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.runs import events as events_mod
from marketsignal.runs.broker import RunBroker
from marketsignal.runs.events import EventWriter
from marketsignal.runs.reaper import orphan_after_s, status_for_termination, synthesized_done


class _FakeLog:
    """Stands in for ``run_events``: committed rows, plus scripted failures."""

    def __init__(self) -> None:
        self.rows: dict[int, tuple[str, dict[str, Any]]] = {}
        self.fail_next: BaseException | None = None
        self.commit_then_fail = False

    async def append(
        self, _f: Any, _s: Any, _r: Any, seq: int, event_type: str, payload: dict[str, Any]
    ) -> str | None:
        if seq in self.rows:
            raise RuntimeError(f"duplicate seq {seq}")
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            if self.commit_then_fail:  # the row committed, but the caller saw an error
                self.rows[seq] = (event_type, payload)
                self.commit_then_fail = False
            raise exc
        self.rows[seq] = (event_type, payload)
        return event_type


@pytest.fixture
def log(monkeypatch: pytest.MonkeyPatch) -> _FakeLog:
    fake = _FakeLog()
    monkeypatch.setattr(events_mod.store, "append_event", fake.append)

    async def max_seq(_self: EventWriter) -> int:
        return max(fake.rows, default=0)

    monkeypatch.setattr(EventWriter, "_max_seq", max_seq)
    return fake


def _writer() -> EventWriter:
    scope = WorkspaceScope(uuid.uuid4(), "WS")
    return EventWriter(None, scope, uuid.uuid4(), RunBroker(), coalesce_ms=10_000)  # type: ignore[arg-type]


async def test_seq_is_not_consumed_by_a_failed_write(log: _FakeLog) -> None:
    writer = _writer()
    await writer.emit("status", {"phase": "a"})
    log.fail_next = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        await writer.emit("status", {"phase": "b"})
    assert writer.seq == 1
    await writer.emit("done", {})
    assert sorted(log.rows) == [1, 2]  # no gap
    assert writer.done


async def test_interrupted_write_that_committed_resyncs_seq(log: _FakeLog) -> None:
    writer = _writer()
    await writer.emit("status", {})
    log.fail_next = asyncio.CancelledError()
    log.commit_then_fail = True
    with pytest.raises(asyncio.CancelledError):
        await writer.emit("status", {})
    await writer.emit("done", {})  # must not collide with the committed seq 2
    assert sorted(log.rows) == [1, 2, 3]
    assert log.rows[3][0] == "done"


async def test_failed_token_flush_is_not_resent(log: _FakeLog) -> None:
    writer = _writer()
    await writer.token(1, "unverified draft")
    log.fail_next = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        await writer.flush_tokens()
    await writer.emit("done", {})
    texts = [p.get("text") for t, p in log.rows.values() if t == "token"]
    assert texts == []  # the failed text is dropped, never duplicated or replayed later
    assert writer.draft_open  # conservatively treated as possibly visible


async def test_discard_pending_drops_unflushed_text(log: _FakeLog) -> None:
    writer = _writer()
    await writer.token(1, "draft")
    writer.discard_pending()
    await writer.emit("done", {})
    assert [t for t, _ in log.rows.values()] == ["done"]
    assert not writer.draft_open


async def test_draft_open_tracks_reset_and_final(log: _FakeLog) -> None:
    writer = _writer()
    await writer.token(1, "draft")
    await writer.flush_tokens()
    assert writer.draft_open
    await writer.emit("draft_reset", {"attempt": 0, "reason": "x"})
    assert not writer.draft_open
    assert not writer.final_emitted
    await writer.emit("final", {})
    assert writer.final_emitted


def test_orphan_threshold_follows_the_deadline() -> None:
    settings = Settings(run_deadline_s=90, run_reap_margin_s=30)  # type: ignore[call-arg]
    assert orphan_after_s(settings) == 120


@pytest.mark.parametrize(
    ("termination", "status"),
    [
        ("cancelled", "cancelled"),
        ("timeout", "failed"),
        ("tool_failure", "failed"),
        ("interrupted", "interrupted"),
        ("completed", "completed"),
        ("generation_unavailable", "completed"),
        ("no_relevant_evidence", "completed"),
    ],
)
def test_status_for_termination(termination: str, status: str) -> None:
    assert status_for_termination(termination) == status


def test_synthesized_done_reflects_the_stored_run() -> None:
    run_id = uuid.uuid4()
    run = {
        "run_id": run_id,
        "status": "completed",
        "termination_state": "generation_unavailable",
        "degradation_flags": ["LLM_SYNTHESIS_UNAVAILABLE"],
        "timings": {"total_ms": 5.0},
        "created_at": datetime.now(UTC),
    }
    done = synthesized_done(run, seq=4)
    assert done["run_id"] == str(run_id)
    assert done["seq"] == 4
    assert done["termination_state"] == "generation_unavailable"
    assert done["flags"] == ["LLM_SYNTHESIS_UNAVAILABLE"]
    orphan = synthesized_done({**run, "termination_state": None, "status": "running"}, seq=1)
    assert orphan["termination_state"] == "interrupted"
    assert "RUN_INTERRUPTED" in orphan["flags"]


def test_finalize_timeout_must_fit_inside_the_reap_margin() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="run_finalize_timeout_s"):
        Settings(run_finalize_timeout_s=60, run_reap_margin_s=60)  # type: ignore[call-arg]
    ok = Settings(run_finalize_timeout_s=20, run_reap_margin_s=60)  # type: ignore[call-arg]
    assert ok.run_finalize_timeout_s < ok.run_reap_margin_s


async def test_live_run_ids_lists_only_unfinished_tasks() -> None:
    from marketsignal.runs.reaper import live_run_ids

    live, finished = uuid.uuid4(), uuid.uuid4()
    blocker = asyncio.Event()
    running = asyncio.create_task(blocker.wait())
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    try:
        assert live_run_ids({live: running, finished: done}) == frozenset({live})
    finally:
        blocker.set()
        await running
