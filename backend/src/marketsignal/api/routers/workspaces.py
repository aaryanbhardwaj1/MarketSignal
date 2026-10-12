"""Workspaces: create, list, and the dashboard summary (the product overview).

With ``settings.hide_test_workspaces`` the list omits test-harness workspaces (codes ``T`` + 10
hex digits); that code shape is reserved, so outside ``env == "test"`` it cannot be created.
Overview run counts exclude test-harness (FakeLLM) runs.
"""

from __future__ import annotations

import re
from typing import Any, Final

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.api.deps import Factory, Principal, Scope, SettingsDep
from marketsignal.api.errors import AppError
from marketsignal.api.routers.runs import NOT_TEST_RUN_SQL
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import scoped_session, unscoped_session
from marketsignal.ingestion import repository as repo

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

TEST_WORKSPACE_CODE: Final = re.compile(r"^T[0-9A-F]{10}$")


class WorkspaceCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,15}$", description="Immutable; prefixes handles")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    default_persona: str = Field(default="generalist", max_length=40)


@router.post("", status_code=201)
async def create_workspace(
    body: WorkspaceCreate, factory: Factory, principal: Principal, settings: SettingsDep
) -> dict[str, Any]:
    if TEST_WORKSPACE_CODE.match(body.code) and settings.env != "test":
        # Reserved for the test harness: such a workspace would be hidden from the list
        # (hide_test_workspaces) and purged by scripts/demo_reset.py.
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "request validation failed",
            fields=[
                {
                    "location": "body.code",
                    "message": "codes of the form T + 10 hex digits are reserved for tests",
                }
            ],
        )
    async with unscoped_session(factory) as session:
        try:
            workspace_id = (
                await session.execute(
                    text(
                        "INSERT INTO workspaces (code, name, description, default_persona) "
                        "VALUES (:c, :n, :d, :p) RETURNING id"
                    ),
                    {
                        "c": body.code,
                        "n": body.name,
                        "d": body.description,
                        "p": body.default_persona,
                    },
                )
            ).scalar_one()
        except IntegrityError as exc:
            raise AppError(409, "WORKSPACE_EXISTS", "workspace code already in use") from exc
        await session.execute(
            text(
                "INSERT INTO workspace_members (workspace_id, principal_id, role) "
                "VALUES (:w, :p, 'owner')"
            ),
            {"w": workspace_id, "p": principal},
        )
        await session.commit()
    scope = WorkspaceScope(workspace_id, body.code)
    async with scoped_session(factory, scope) as session:
        await session.execute(
            text("INSERT INTO workspace_corpus_state (workspace_id) VALUES (:w)"),
            {"w": workspace_id},
        )
        await repo.audit(session, workspace_id, principal, "workspace.created", body.code)
        await session.commit()
    return {"id": str(workspace_id), **body.model_dump()}


@router.get("")
async def list_workspaces(
    factory: Factory, principal: Principal, settings: SettingsDep
) -> list[dict[str, Any]]:
    async with unscoped_session(factory) as session:
        rows = await session.execute(
            text(
                "SELECT w.id, w.code, w.name, w.description, w.default_persona, w.created_at "
                "FROM workspaces w JOIN workspace_members m ON m.workspace_id = w.id "
                "WHERE m.principal_id = :p ORDER BY w.created_at"
            ),
            {"p": principal},
        )
        return [
            {
                "id": str(r.id),
                "code": r.code,
                "name": r.name,
                "description": r.description,
                "default_persona": r.default_persona,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
            if not (settings.hide_test_workspaces and TEST_WORKSPACE_CODE.match(r.code))
        ]


@router.get("/{ws}")
async def workspace_summary(scope: Scope, factory: Factory) -> dict[str, Any]:
    """Dashboard: identity, corpus version, sources by class and by status, evidence counts."""
    async with unscoped_session(factory) as session:
        meta = (
            await session.execute(
                text("SELECT name, description, default_persona FROM workspaces WHERE id = :id"),
                {"id": scope.workspace_id},
            )
        ).one()
    async with scoped_session(factory, scope) as session:
        corpus_version = (
            await session.execute(text("SELECT version FROM workspace_corpus_state"))
        ).scalar_one_or_none()
        by_class: dict[str, int] = dict(
            (
                await session.execute(
                    text(
                        "SELECT v.source_class, count(*) FROM sources s JOIN source_versions v "
                        "ON v.id = s.current_version_id WHERE s.deleted_at IS NULL GROUP BY 1"
                    )
                )
            ).all()
        )
        by_status: dict[str, int] = dict(
            (
                await session.execute(
                    text(
                        "SELECT v.status, count(*) FROM sources s JOIN LATERAL ("
                        " SELECT status FROM source_versions WHERE source_id = s.id "
                        " ORDER BY version DESC LIMIT 1) v ON true "
                        "WHERE s.deleted_at IS NULL GROUP BY 1"
                    )
                )
            ).all()
        )
        counts = (
            await session.execute(
                text(
                    "SELECT (SELECT count(*) FROM parent_chunks p JOIN sources s "
                    "ON s.current_version_id = p.source_version_id WHERE s.deleted_at IS NULL), "
                    "(SELECT count(*) FROM child_chunks c JOIN sources s "
                    "ON s.current_version_id = c.source_version_id WHERE s.deleted_at IS NULL)"
                )
            )
        ).one()
        overview = await _overview(session, scope)
    return {
        "id": str(scope.workspace_id),
        "code": scope.workspace_code,
        "name": meta.name,
        "description": meta.description,
        "default_persona": meta.default_persona,
        "corpus_version": corpus_version or 0,
        "sources_by_class": by_class,
        "sources_by_status": by_status,
        "parent_count": counts[0],
        "child_count": counts[1],
        **overview,
    }


_OVERVIEW_COUNTS = f"""
SELECT
  (SELECT count(*) FROM dataset_tables dt
     JOIN source_versions v ON v.workspace_id = dt.workspace_id AND v.id = dt.source_version_id
     JOIN sources s ON s.workspace_id = v.workspace_id AND s.current_version_id = v.id
    WHERE dt.workspace_id = :ws AND s.deleted_at IS NULL
      AND v.status IN ('ready', 'ready_degraded')) AS dataset_count,
  (SELECT count(*) FROM analytics_results a
    WHERE a.workspace_id = :ws AND (a.query_run_id IS NULL OR EXISTS (
          SELECT 1 FROM query_runs r WHERE r.workspace_id = a.workspace_id
             AND r.id = a.query_run_id AND {NOT_TEST_RUN_SQL}))) AS analytics_result_count,
  (SELECT count(*) FROM conversations c
    WHERE c.workspace_id = :ws AND NOT EXISTS (
          SELECT 1 FROM query_runs t WHERE t.workspace_id = c.workspace_id
             AND t.conversation_id = c.id AND NOT ({NOT_TEST_RUN_SQL}))) AS conversation_count,
  (SELECT max(created_at) FROM query_runs WHERE workspace_id = :ws AND {NOT_TEST_RUN_SQL})
     AS last_run_at,
  (SELECT max(v.ready_at) FROM sources s JOIN source_versions v
     ON v.workspace_id = s.workspace_id AND v.source_id = s.id
    WHERE s.workspace_id = :ws AND s.deleted_at IS NULL) AS last_ready_at
"""  # noqa: S608 - interpolates only the NOT_TEST_RUN_SQL constant


async def _group_counts(session: AsyncSession, sql: str, ws: Any) -> dict[str, int]:
    rows = (await session.execute(text(sql), {"ws": ws})).all()
    return {str(k): int(n) for k, n in rows if k is not None}


async def _overview(session: AsyncSession, scope: WorkspaceScope) -> dict[str, Any]:
    """The overview additions: sources by type and class, analytics and run counts (test-harness
    runs excluded) and the latest source readiness."""
    ws = scope.workspace_id
    by_type = await _group_counts(
        session,
        "SELECT s.source_type, count(*) FROM sources s WHERE s.workspace_id = :ws "
        "AND s.deleted_at IS NULL GROUP BY 1",
        ws,
    )
    runs_by = (
        "SELECT {col}, count(*) FROM query_runs WHERE workspace_id = :ws "  # noqa: S608
        f"AND {NOT_TEST_RUN_SQL} GROUP BY 1"
    )
    by_mode = await _group_counts(session, runs_by.format(col="mode"), ws)
    by_termination = await _group_counts(session, runs_by.format(col="termination_state"), ws)
    counts = (await session.execute(text(_OVERVIEW_COUNTS), {"ws": ws})).one()
    return {
        "sources_by_type": by_type,
        "dataset_count": int(counts.dataset_count),
        "analytics_result_count": int(counts.analytics_result_count),
        "conversation_count": int(counts.conversation_count),
        "runs": {
            "total": sum(by_mode.values()),
            "by_mode": by_mode,
            "by_termination_state": by_termination,
            "last_run_at": counts.last_run_at.isoformat() if counts.last_run_at else None,
        },
        "last_ready_at": counts.last_ready_at.isoformat() if counts.last_ready_at else None,
    }
