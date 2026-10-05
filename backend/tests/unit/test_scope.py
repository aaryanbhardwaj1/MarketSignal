import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from marketsignal.db.scope import (
    UNSCOPED_SESSION_KEY,
    WorkspaceScope,
    WorkspaceScopeNotSetError,
    _set_scope_on_begin,
    current_scope,
    mark_unscoped,
    workspace_scope,
)


class _RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: Any, params: dict[str, Any]) -> None:
        self.calls.append((str(statement), params))


def _session(**info: Any) -> Any:
    return SimpleNamespace(info=dict(info))


SCOPE = WorkspaceScope(workspace_id=uuid.uuid4(), workspace_code="NORTHSTAR")


def test_begin_without_scope_fails_closed() -> None:
    with pytest.raises(WorkspaceScopeNotSetError):
        _set_scope_on_begin(_session(), None, _RecordingConnection())  # type: ignore[arg-type]


def test_explicitly_unscoped_session_is_allowed_and_sets_nothing() -> None:
    session = _session()
    mark_unscoped(session)
    conn = _RecordingConnection()
    _set_scope_on_begin(session, None, conn)  # type: ignore[arg-type]
    assert session.info[UNSCOPED_SESSION_KEY] is True
    assert conn.calls == []


def test_scope_sets_transaction_local_guc_with_bind_parameter() -> None:
    conn = _RecordingConnection()
    with workspace_scope(SCOPE):
        _set_scope_on_begin(_session(), None, conn)  # type: ignore[arg-type]
    ((sql, params),) = conn.calls
    assert "set_config('app.workspace_id', :workspace_id, true)" in sql
    assert params == {"workspace_id": str(SCOPE.workspace_id)}


def test_scope_is_reset_after_block() -> None:
    assert current_scope() is None
    with workspace_scope(SCOPE):
        assert current_scope() == SCOPE
    assert current_scope() is None


def test_scope_is_reset_even_on_error() -> None:
    with pytest.raises(ValueError, match="boom"), workspace_scope(SCOPE):
        raise ValueError("boom")
    assert current_scope() is None
