"""Baseline: extensions, scope function, workspaces, and RLS scaffolding.

Establishes the isolation machinery every later tenant table reuses (ADR-0009):

* ``app.current_workspace()``: reads the transaction-local GUC ``app.workspace_id`` and
  raises ``WORKSPACE_SCOPE_NOT_SET`` when it is missing or empty. Both pool-history failure
  modes (GUC never defined vs. defined-but-empty after an earlier transaction) therefore
  produce the same clear error, and unscoped tenant queries fail closed.
* ``workspaces`` / ``workspace_members``: not tenant tables (membership is checked before
  a scope exists); read through a membership-checking repository only.
* ``workspace_corpus_state``: the first tenant table, with ENABLE + FORCE RLS. Its version
  counter drives answer-cache invalidation (ADR-0011) and lives in its own row so ingest
  bumps never contend with workspace-metadata updates.

Revision ID: 0001
Revises:
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "ms_app"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Readiness compares the schema revision with the build's Alembic head. The version table
    # exists before this migration runs, so it needs an explicit, read-only grant.
    op.execute(f"GRANT SELECT ON alembic_version TO {APP_ROLE}")

    # Objects created by the owner become usable by the app role (DML only, never DDL).
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )

    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute(f"GRANT USAGE ON SCHEMA app TO {APP_ROLE}")
    op.execute(
        """
        CREATE FUNCTION app.current_workspace() RETURNS uuid
        LANGUAGE plpgsql STABLE
        AS $$
        DECLARE
            raw text := current_setting('app.workspace_id', true);
        BEGIN
            IF raw IS NULL OR raw = '' THEN
                RAISE EXCEPTION 'WORKSPACE_SCOPE_NOT_SET'
                    USING ERRCODE = '42501',
                          HINT = 'set app.workspace_id via set_config(..., true) in this transaction';
            END IF;
            RETURN raw::uuid;
        END
        $$
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION app.current_workspace() TO {APP_ROLE}")

    op.execute(
        r"""
        CREATE TABLE workspaces (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            code text NOT NULL UNIQUE CHECK (code ~ '^[A-Z][A-Z0-9]{1,15}$'),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
            description text NOT NULL DEFAULT '',
            default_persona text NOT NULL DEFAULT 'generalist',
            llm_max_confidentiality text NOT NULL DEFAULT 'confidential'
                CHECK (llm_max_confidentiality IN ('public', 'internal', 'confidential', 'restricted')),
            demo_read_only boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE workspace_members (
            workspace_id uuid NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
            principal_id text NOT NULL,
            role text NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'member', 'viewer')),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, principal_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE workspace_corpus_state (
            workspace_id uuid PRIMARY KEY REFERENCES workspaces (id) ON DELETE CASCADE,
            version bigint NOT NULL DEFAULT 0 CHECK (version >= 0)
        )
        """
    )
    enable_tenant_rls("workspace_corpus_state")


def enable_tenant_rls(table: str) -> None:
    """Standard tenant policy: rows visible/writable only inside the current workspace scope."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = app.current_workspace()) "
        f"WITH CHECK (workspace_id = app.current_workspace())"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_corpus_state")
    op.execute("DROP TABLE IF EXISTS workspace_members")
    op.execute("DROP TABLE IF EXISTS workspaces")
    op.execute("DROP FUNCTION IF EXISTS app.current_workspace()")
    op.execute("DROP SCHEMA IF EXISTS app")
