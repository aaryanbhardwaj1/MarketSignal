"""Persisted structured-analytics results (Phase 5; plan §18 analytics, ADR-0006).

``analytics_results`` holds every computed result an analytics tool returned, as the canonical
:class:`~marketsignal.tools.analytics_contracts.AnalyticsResult` JSON plus the normalized spec,
keyed by ``id`` (the ``result_id`` answers cite as ``[[result:<id>]]``). It records the dataset
table and source version the computation read, so a result is reproducible and auditable, and
purge can delete every result derived from a purged version (values computed from purged data
must not outlive it; answers citing them are redacted by ``ingestion/purge.py``).

A result cannot outlive the table or version it was computed from (``ON DELETE CASCADE``;
purge also deletes them explicitly, first). A computed result is not text evidence: it never becomes a parent/child chunk or an evidence
handle. Isolation: ENABLE + FORCE RLS; the runtime role may insert and read, never update.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "ms_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE analytics_results (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL,
            query_run_id uuid,
            source_version_id uuid NOT NULL,
            table_id uuid NOT NULL,
            tool text NOT NULL CHECK (tool IN ('aggregate', 'group_compare', 'filter_rows')),
            spec jsonb NOT NULL,
            result jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, id),
            FOREIGN KEY (workspace_id, query_run_id)
                REFERENCES query_runs (workspace_id, id) ON DELETE SET NULL (query_run_id),
            FOREIGN KEY (workspace_id, source_version_id)
                REFERENCES source_versions (workspace_id, id) ON DELETE CASCADE,
            FOREIGN KEY (workspace_id, table_id)
                REFERENCES dataset_tables (workspace_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX analytics_results_version ON analytics_results "
        "(workspace_id, source_version_id)"
    )
    op.execute(
        "CREATE INDEX analytics_results_run ON analytics_results (workspace_id, query_run_id)"
    )
    op.execute("ALTER TABLE analytics_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE analytics_results FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY analytics_results_workspace_isolation ON analytics_results "
        "USING (workspace_id = app.current_workspace()) "
        "WITH CHECK (workspace_id = app.current_workspace())"
    )
    op.execute(f"REVOKE UPDATE ON analytics_results FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analytics_results CASCADE")
