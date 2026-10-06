"""Orphaned-run reaper (plan §21).

A run whose process died never emitted ``done``; its stream would hang and its row would stay
``running``. A run still ``running`` past ``run_deadline_s + run_reap_margin_s`` is an orphan:
no live executor outlives it: finalization after the deadline is bounded by
``run_finalize_timeout_s`` plus a best-effort conclusion of at most half the rest of the margin
(validated ``< run_reap_margin_s``), so the age condition is safe with several API processes.
Runs still live in *this* process (``live_run_ids``) are excluded outright. The reaper runs at
startup, periodically from the app lifespan, and on demand from a stream that finds its run
overdue.

* No ``done`` yet: exactly one ``done`` (``termination_state = interrupted``, an extension of
  the plan §28 enum recorded in ADR-0008) is inserted, guarded by ``NOT EXISTS`` + the ``seq``
  primary key, and the row is marked ``interrupted``.
* ``done`` already written (the process died between ``done`` and the row update): nothing is
  inserted; the row is synced from that ``done`` payload.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Collection, Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session, unscoped_session

ORPHAN_AFTER_S = 120  # fallback when no settings are given
INTERRUPTED = "interrupted"
RUN_INTERRUPTED = "RUN_INTERRUPTED"
_FAILED = frozenset({"timeout", "tool_failure"})


def live_run_ids(tasks: Mapping[uuid.UUID, asyncio.Task[Any]]) -> frozenset[uuid.UUID]:
    """Runs whose executor is still running in *this* process: never orphans, whatever their
    age (a DB-starved finalize may outlive the threshold); the reaper must leave them alone."""
    return frozenset(run_id for run_id, task in tasks.items() if not task.done())


def orphan_after_s(settings: Settings) -> float:
    return settings.run_deadline_s + settings.run_reap_margin_s


def status_for_termination(termination: str) -> str:
    """``query_runs.status`` implied by a ``done`` event's ``termination_state``."""
    if termination in ("cancelled", INTERRUPTED):
        return termination
    return "failed" if termination in _FAILED else "completed"


def synthesized_done(run: Mapping[str, Any], seq: int) -> dict[str, Any]:
    """A ``done`` payload built from the stored run, for a stream whose events are gone."""
    termination = run.get("termination_state")
    flags = list(run.get("degradation_flags") or [])
    if not termination or run.get("status") == "running":
        termination = INTERRUPTED
        if RUN_INTERRUPTED not in flags:
            flags.append(RUN_INTERRUPTED)
    return {
        "run_id": str(run["run_id"]),
        "seq": seq,
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "termination_state": termination,
        "flags": flags,
        "cache_status": "disabled",
        "timings": dict(run.get("timings") or {}),
    }


async def _reap_one(
    session: AsyncSession, scope: WorkspaceScope, run_id: Any, done: dict[str, Any] | None
) -> bool:
    params: dict[str, Any] = {"ws": scope.workspace_id, "r": run_id}
    if done is not None:  # terminated, but the row update was lost: sync, never re-terminate
        termination = str(done.get("termination_state") or "completed")
        await session.execute(
            text(
                "UPDATE query_runs SET status = :st, termination_state = :ts, "
                "degradation_flags = :flags, finished_at = coalesce(finished_at, now()) "
                "WHERE workspace_id = :ws AND id = :r"
            ),
            {
                **params,
                "st": status_for_termination(termination),
                "ts": termination,
                "flags": [str(f) for f in done.get("flags") or []],
            },
        )
        return True
    payload = {
        "run_id": str(run_id),
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "termination_state": INTERRUPTED,
        "flags": [RUN_INTERRUPTED],
        "cache_status": "disabled",
        "timings": {},
    }
    inserted = await session.execute(
        text(
            "INSERT INTO run_events (workspace_id, run_id, seq, type, payload) "
            "SELECT :ws, :r, s.next, 'done', "
            "       CAST(:p AS jsonb) || jsonb_build_object('seq', s.next) "
            "FROM (SELECT coalesce(max(seq), 0) + 1 AS next FROM run_events "
            "      WHERE workspace_id = :ws AND run_id = :r) s "
            "WHERE NOT EXISTS (SELECT 1 FROM run_events WHERE workspace_id = :ws "
            "                  AND run_id = :r AND type = 'done') "
            "ON CONFLICT DO NOTHING"
        ),
        {**params, "p": json.dumps(payload)},
    )
    if not getattr(inserted, "rowcount", 0):
        return False  # a live writer raced us; the next pass syncs from its done
    await session.execute(
        text(
            "UPDATE query_runs SET status = 'interrupted', "
            "termination_state = 'interrupted', finished_at = now(), "
            "degradation_flags = array_append(degradation_flags, 'RUN_INTERRUPTED') "
            "WHERE workspace_id = :ws AND id = :r"
        ),
        params,
    )
    return True


async def _reap_scope(
    factory: SessionFactory,
    scope: WorkspaceScope,
    older_than_s: float,
    run_id: uuid.UUID | None = None,
    exclude: Collection[uuid.UUID] = (),
) -> int:
    reaped = 0
    async with scoped_session(factory, scope) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT r.id, (SELECT e.payload FROM run_events e "
                    "  WHERE e.workspace_id = r.workspace_id AND e.run_id = r.id "
                    "  AND e.type = 'done' ORDER BY e.seq LIMIT 1) "
                    "FROM query_runs r WHERE r.workspace_id = :ws AND r.status = 'running' "
                    "AND r.created_at < now() - make_interval(secs => :age) "
                    "AND (CAST(:rid AS uuid) IS NULL OR r.id = CAST(:rid AS uuid)) "
                    "FOR UPDATE OF r SKIP LOCKED"
                ),
                {"ws": scope.workspace_id, "age": float(older_than_s), "rid": run_id},
            )
        ).all()
        for rid, done in rows:
            if uuid.UUID(str(rid)) in exclude:
                continue
            if await _reap_one(session, scope, rid, dict(done) if done is not None else None):
                reaped += 1
        await session.commit()
    return reaped


async def done_seq(factory: SessionFactory, scope: WorkspaceScope, run_id: uuid.UUID) -> int | None:
    """``seq`` of the run's ``done`` event, or ``None`` when it has none (never written, or
    purged)."""
    async with scoped_session(factory, scope) as session:
        value = (
            await session.execute(
                text(
                    "SELECT min(seq) FROM run_events "
                    "WHERE workspace_id = :ws AND run_id = :r AND type = 'done'"
                ),
                {"ws": scope.workspace_id, "r": run_id},
            )
        ).scalar_one_or_none()
    return None if value is None else int(value)


def is_overdue(run: Mapping[str, Any], settings: Settings) -> bool:
    created = run.get("created_at")
    if run.get("status") != "running" or not isinstance(created, datetime):
        return False
    return (datetime.now(UTC) - created).total_seconds() > orphan_after_s(settings)


async def reap_run(
    factory: SessionFactory,
    scope: WorkspaceScope,
    run_id: uuid.UUID,
    older_than_s: float,
    *,
    exclude: Collection[uuid.UUID] = (),
) -> bool:
    """Reap one run if it is an overdue orphan (used by a stream that finds it so)."""
    return await _reap_scope(factory, scope, older_than_s, run_id, exclude) > 0


async def reap_interrupted_runs(
    factory: SessionFactory,
    older_than_s: float = ORPHAN_AFTER_S,
    *,
    exclude: Collection[uuid.UUID] = (),
) -> int:
    """Reap every overdue orphan; ``exclude`` lists runs still live in this process."""
    async with unscoped_session(factory) as session:
        workspaces = (await session.execute(text("SELECT id, code FROM workspaces"))).all()
    reaped = 0
    for ws_id, code in workspaces:
        scope = WorkspaceScope(uuid.UUID(str(ws_id)), str(code))
        reaped += await _reap_scope(factory, scope, older_than_s, exclude=exclude)
    return reaped
