"""Request dependencies: settings, sessions, principal and the workspace scope.

``workspace_scope_dep`` is the only way a request obtains a :class:`WorkspaceScope`. It
validates the code, then checks that the principal is a member via the non-tenant
``workspaces``/``workspace_members`` tables, *before* any tenant data is touched. A workspace
the principal cannot see is indistinguishable from one that does not exist (404).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Path, Request
from sqlalchemy import text

from marketsignal.api.errors import AppError
from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, unscoped_session
from marketsignal.evidence.handles import is_valid_workspace_code


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session_factory(request: Request) -> SessionFactory:
    factory: SessionFactory = request.app.state.session_factory
    return factory


def get_principal(settings: Annotated[Settings, Depends(get_settings_dep)]) -> str:
    # Phase 1: one demo principal. ADR-0014 replaces this with verified session tokens.
    return settings.demo_principal


async def workspace_scope_dep(
    ws: Annotated[str, Path(description="Workspace code, e.g. NORTHSTAR")],
    factory: Annotated[SessionFactory, Depends(get_session_factory)],
    principal: Annotated[str, Depends(get_principal)],
) -> WorkspaceScope:
    if not is_valid_workspace_code(ws):
        raise AppError(404, "WORKSPACE_NOT_FOUND", "workspace not found")
    async with unscoped_session(factory) as session:
        row = (
            await session.execute(
                text(
                    "SELECT w.id, w.code FROM workspaces w JOIN workspace_members m "
                    "ON m.workspace_id = w.id WHERE w.code = :code AND m.principal_id = :p"
                ),
                {"code": ws, "p": principal},
            )
        ).one_or_none()
    if row is None:
        raise AppError(404, "WORKSPACE_NOT_FOUND", "workspace not found")
    return WorkspaceScope(row[0], row[1])


Scope = Annotated[WorkspaceScope, Depends(workspace_scope_dep)]
Factory = Annotated[SessionFactory, Depends(get_session_factory)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
Principal = Annotated[str, Depends(get_principal)]
