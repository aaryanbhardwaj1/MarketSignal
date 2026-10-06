"""Research runs: tool audit, per-attempt verification reports, route and agent traces (Phase 4).

* ``tool_runs`` - one audit row per governed tool call (plan §17 step 7; ADR-0006): tool name,
  sanitized arguments (model-supplied query text truncated; never auth or context), status,
  normalized error code, returned evidence handles, counts, truncation and duration, and the
  transport used (``inprocess`` | ``http``). No observation or document text is stored.
* ``verification_attempts`` - one structured report per verification attempt (attempt number,
  failure categories, rejected spans with their aliases, evidence checked, repairs,
  regeneration requested, final disposition). Rejected spans quote model output, which can
  quote evidence, so purge deletes the attempts of every run whose pack included the source
  (and, since the Phase 4 security review, every run whose research agent saw it).
* ``query_runs`` gains ``route`` (why this mode: requested mode, persona default, cue rules
  matched, final mode), ``agent`` (steps, tool calls, termination reason, bounds hit; never
  model reasoning) and ``tool_calls`` (executed tool calls, written once after the gather; the budget itself is
  enforced by the agent runtime).

Isolation: ENABLE + FORCE RLS and composite ``(workspace_id, ...)`` foreign keys (ADR-0009).
Neither new table is updated by the runtime role (append-only audit); purge and retention
delete as owner paths.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "ms_app"
TABLES = ("tool_runs", "verification_attempts")
TOOL_STATUSES = "('ok','error','denied','timeout','truncated')"
ERROR_CODES = (
    "('VALIDATION_ERROR','POLICY_DENIED','NOT_FOUND','TIMEOUT','UNAVAILABLE','INTERNAL',"
    "'UNAUTHENTICATED')"
)
DISPOSITIONS = "('accepted','repaired','regenerate','rejected','fallback')"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE query_runs
            ADD COLUMN route jsonb NOT NULL DEFAULT '{}',
            ADD COLUMN agent jsonb NOT NULL DEFAULT '{}',
            ADD COLUMN tool_calls integer NOT NULL DEFAULT 0 CHECK (tool_calls >= 0)
        """
    )
    op.execute(
        f"""
        CREATE TABLE tool_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL,
            query_run_id uuid,
            step integer NOT NULL DEFAULT 0 CHECK (step >= 0),
            call_index integer NOT NULL DEFAULT 0 CHECK (call_index >= 0),
            tool text NOT NULL CHECK (length(tool) <= 64),
            args jsonb NOT NULL DEFAULT '{{}}',
            status text NOT NULL CHECK (status IN {TOOL_STATUSES}),
            error_code text CHECK (error_code IN {ERROR_CODES}),
            result_handles text[] NOT NULL DEFAULT '{{}}',
            result_count integer NOT NULL DEFAULT 0,
            total_matches integer,
            truncated boolean NOT NULL DEFAULT false,
            warnings text[] NOT NULL DEFAULT '{{}}',
            duration_ms double precision NOT NULL DEFAULT 0,
            transport text NOT NULL DEFAULT 'inprocess'
                CHECK (transport IN ('inprocess', 'http')),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, id),
            FOREIGN KEY (workspace_id, query_run_id)
                REFERENCES query_runs (workspace_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX tool_runs_run ON tool_runs (workspace_id, query_run_id, step)")
    op.execute(
        f"""
        CREATE TABLE verification_attempts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL,
            query_run_id uuid NOT NULL,
            attempt integer NOT NULL CHECK (attempt BETWEEN 1 AND 3),
            disposition text NOT NULL CHECK (disposition IN {DISPOSITIONS}),
            report jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, query_run_id, attempt),
            FOREIGN KEY (workspace_id, query_run_id)
                REFERENCES query_runs (workspace_id, id) ON DELETE CASCADE
        )
        """
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_workspace_isolation ON {table} "
            f"USING (workspace_id = app.current_workspace()) "
            f"WITH CHECK (workspace_id = app.current_workspace())"
        )
        # Append-only audit for the runtime role; purge and retention delete as the owner.
        op.execute(f"REVOKE UPDATE ON {table} FROM {APP_ROLE}")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute(
        "ALTER TABLE query_runs DROP COLUMN IF EXISTS tool_calls, "
        "DROP COLUMN IF EXISTS agent, DROP COLUMN IF EXISTS route"
    )
