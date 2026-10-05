"""Workspaces: create, list, and the dashboard summary."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from marketsignal.api.deps import Factory, Principal, Scope
from marketsignal.api.errors import AppError
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import scoped_session, unscoped_session
from marketsignal.ingestion import repository as repo

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,15}$", description="Immutable; prefixes handles")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    default_persona: str = Field(default="generalist", max_length=40)


@router.post("", status_code=201)
async def create_workspace(
    body: WorkspaceCreate, factory: Factory, principal: Principal
) -> dict[str, Any]:
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
async def list_workspaces(factory: Factory, principal: Principal) -> list[dict[str, Any]]:
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
    }
