"""Let purge redact model-written tool arguments in place (Phase 4 security review, finding 18).

The research agent writes follow-up queries and keyword terms after reading evidence, so a
``tool_runs.args`` value can quote a document. Purge must remove that text but keep the audit
row (tool, status, handles, timing). ``tool_runs`` stays append-only for the runtime role
except for this one column: ``UPDATE (args)`` only, no other column can be changed.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "ms_app"


def upgrade() -> None:
    op.execute(f"GRANT UPDATE (args) ON tool_runs TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (args) ON tool_runs FROM {APP_ROLE}")
