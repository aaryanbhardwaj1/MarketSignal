"""Indexes for the conversation list (final productization phase).

``GET /conversations`` pages conversations by ``(updated_at, id)`` and, per conversation on the
page, looks up its latest run and checks for test-harness runs. Without these indexes the
latest-run lookup scanned every run in the workspace once per conversation (quadratic in
conversations x runs) and the page was sorted only after every row was joined.

* ``conversations_ws_updated``: the keyset page order (``updated_at DESC, id DESC``).
* ``query_runs_ws_conversation``: a conversation's runs, newest first (latest run, the
  test-run filter, and the overview's conversation count).

Plain ``CREATE INDEX`` (not ``CONCURRENTLY``): Alembic runs each migration in a transaction and
the tables are small.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS conversations_ws_updated "
        "ON conversations (workspace_id, updated_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS query_runs_ws_conversation "
        "ON query_runs (workspace_id, conversation_id, created_at DESC, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS query_runs_ws_conversation")
    op.execute("DROP INDEX IF EXISTS conversations_ws_updated")
