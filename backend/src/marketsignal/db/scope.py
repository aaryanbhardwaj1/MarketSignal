"""Workspace scope: the bridge between application authorization and Postgres RLS.

Every tenant table has a row-level-security policy ``workspace_id = app.current_workspace()``.
``app.current_workspace()`` reads the transaction-local GUC ``app.workspace_id`` and raises
``WORKSPACE_SCOPE_NOT_SET`` if it is missing, so an unscoped query fails closed.

The GUC is set by an ``after_begin`` listener on every ORM session transaction, from a
context variable that only trusted code (the authorizing API dependency or a worker job
prologue) can set. ``set_config(..., true)`` is used rather than ``SET LOCAL`` because
``SET`` cannot take bind parameters; ``true`` makes the setting transaction-local, so it
never leaks across pooled connections.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.orm import Session, SessionTransaction

SET_SCOPE_SQL = text("SELECT set_config('app.workspace_id', :workspace_id, true)")
UNSCOPED_SESSION_KEY = "marketsignal.unscoped"


class WorkspaceScopeNotSetError(RuntimeError):
    """A tenant-data transaction began without a workspace scope."""


@dataclass(frozen=True, slots=True)
class WorkspaceScope:
    workspace_id: UUID
    workspace_code: str


_current_scope: ContextVar[WorkspaceScope | None] = ContextVar("workspace_scope", default=None)


def current_scope() -> WorkspaceScope | None:
    return _current_scope.get()


@contextmanager
def workspace_scope(scope: WorkspaceScope) -> Iterator[WorkspaceScope]:
    """Bind ``scope`` for the duration of the block (async-task local)."""
    token = _current_scope.set(scope)
    try:
        yield scope
    finally:
        _current_scope.reset(token)


def mark_unscoped(session: Any) -> None:
    """Allow a session to run without a workspace scope.

    Only for non-tenant tables (``workspaces``, ``workspace_members``) read by the
    membership-checking dependency. RLS still blocks every tenant table for such sessions.
    """
    session.info[UNSCOPED_SESSION_KEY] = True


def _set_scope_on_begin(
    session: Session, _transaction: SessionTransaction, connection: Any
) -> None:
    scope = _current_scope.get()
    if scope is None:
        if session.info.get(UNSCOPED_SESSION_KEY):
            return
        raise WorkspaceScopeNotSetError(
            "tenant transaction began without a workspace scope; "
            "wrap the work in workspace_scope(...) or use an explicitly unscoped session"
        )
    connection.execute(SET_SCOPE_SQL, {"workspace_id": str(scope.workspace_id)})


_installed = False


def install_scope_listener() -> None:
    """Register the listener once for every ORM Session (sync core of AsyncSession)."""
    global _installed
    if _installed:
        return
    event.listen(Session, "after_begin", _set_scope_on_begin)
    _installed = True
