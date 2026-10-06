"""Startup reaper for orphaned runs (plan §21).

A run whose process died never emitted ``done``; its stream would hang. At API startup every
run still ``running`` and older than the run deadline plus a margin is marked ``interrupted``
and given a terminal ``done`` event (``termination_state = interrupted``, an extension of the
plan §28 enum recorded in ADR-0008). The age condition makes the reaper safe with several API
processes: no live run can outlive its deadline, so only true orphans match.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session, unscoped_session

ORPHAN_AFTER_S = 120


async def reap_interrupted_runs(factory: SessionFactory, older_than_s: int = ORPHAN_AFTER_S) -> int:
    async with unscoped_session(factory) as session:
        workspaces = (await session.execute(text("SELECT id, code FROM workspaces"))).all()
    reaped = 0
    for ws_id, code in workspaces:
        scope = WorkspaceScope(uuid.UUID(str(ws_id)), str(code))
        async with scoped_session(factory, scope) as session:
            runs = (
                await session.execute(
                    text(
                        "SELECT r.id, (SELECT coalesce(max(e.seq), 0) FROM run_events e "
                        "  WHERE e.workspace_id = r.workspace_id AND e.run_id = r.id) "
                        "FROM query_runs r WHERE r.workspace_id = :ws AND r.status = 'running' "
                        "AND r.created_at < now() - make_interval(secs => :age) "
                        "FOR UPDATE OF r"
                    ),
                    {"ws": scope.workspace_id, "age": older_than_s},
                )
            ).all()
            for run_id, last_seq in runs:
                payload = {
                    "run_id": str(run_id),
                    "seq": int(last_seq) + 1,
                    "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                    "termination_state": "interrupted",
                    "flags": ["RUN_INTERRUPTED"],
                    "cache_status": "disabled",
                    "timings": {},
                }
                await session.execute(
                    text(
                        "INSERT INTO run_events (workspace_id, run_id, seq, type, payload) "
                        "VALUES (:ws, :r, :s, 'done', CAST(:p AS jsonb))"
                    ),
                    {
                        "ws": scope.workspace_id,
                        "r": run_id,
                        "s": payload["seq"],
                        "p": json.dumps(payload),
                    },
                )
                await session.execute(
                    text(
                        "UPDATE query_runs SET status = 'interrupted', "
                        "termination_state = 'interrupted', finished_at = now(), "
                        "degradation_flags = array_append(degradation_flags, 'RUN_INTERRUPTED') "
                        "WHERE workspace_id = :ws AND id = :r"
                    ),
                    {"ws": scope.workspace_id, "r": run_id},
                )
                reaped += 1
            await session.commit()
    return reaped
