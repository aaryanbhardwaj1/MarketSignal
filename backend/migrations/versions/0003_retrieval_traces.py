"""Retrieval traces: one row per retrieval request (plan §5, §25; Phase 2).

``stages`` records dense and lexical candidates (child id, parent handle, rank, score, span),
the lexical query (lexemes, IDF, phrases), fused parents with lane ranks and RRF scores, the
rerank pool and pair scores, balancing decisions and the final ranked handles with their anchor
child. ``timings`` holds per-stage milliseconds; ``flags`` the degradation flags.

Purge behaviour (ADR-0016 checklist): traces hold identifiers, ranks and scores, never document
text, so a purge does not need to touch them; a purged handle in an old trace resolves to the
410 tombstone. The query text is user input, not document content. Retention (30 days) is the
Phase 8 nightly job, which is why the runtime role keeps DELETE; UPDATE is revoked.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "ms_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE retrieval_traces (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
            query_run_id uuid,
            tool_run_id uuid,
            origin text NOT NULL CHECK (origin IN ('api', 'eval', 'tool')),
            query text NOT NULL CHECK (length(query) <= 4000),
            config_hash text NOT NULL,
            corpus_version bigint,
            result_handles text[] NOT NULL DEFAULT '{}',
            stages jsonb NOT NULL,
            timings jsonb NOT NULL DEFAULT '{}',
            flags text[] NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX retrieval_traces_ws_time ON retrieval_traces (workspace_id, created_at)"
    )
    op.execute(
        "CREATE INDEX retrieval_traces_run ON retrieval_traces (query_run_id) "
        "WHERE query_run_id IS NOT NULL"
    )
    op.execute("ALTER TABLE retrieval_traces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE retrieval_traces FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY retrieval_traces_workspace_isolation ON retrieval_traces "
        "USING (workspace_id = app.current_workspace()) "
        "WITH CHECK (workspace_id = app.current_workspace())"
    )
    op.execute(f"REVOKE UPDATE ON retrieval_traces FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS retrieval_traces")
