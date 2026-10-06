"""Runs, run events, conversations and messages (Phase 3, plan §6, §19-21; ADR-0008).

* ``conversations`` - deterministic, bounded conversation state (rolling summary, recent
  questions, recently cited handles); no transcript is replayed into prompts.
* ``messages`` - user questions and *verified* assistant answers. Answer content and citation
  cards hold canonical handles only (never run-local ``[E#]`` aliases, ADR-0004).
* ``query_runs`` - one row per question: retrieval/pack/citation handles, usage, timings,
  termination state and degradation flags, config hash and prompt version.
* ``run_events`` - the SSE event log (append-only for the runtime role), replayed on
  reconnect (``seq > Last-Event-ID``).

Isolation: every table has ENABLE + FORCE RLS, tenant-scoped keys and composite
``(workspace_id, id)`` foreign keys (ADR-0009).

Purge behaviour (ADR-0016 checklist): answers and token events can quote document text, so
purging a source redacts the content of messages that cited it and deletes the events of runs
whose evidence pack included it (``ingestion/purge.py``). ``query_runs`` stores handles,
never text. Retention of ``run_events`` (30 days) is the Phase 8 nightly job.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "ms_app"
TABLES = ("conversations", "messages", "query_runs", "run_events")
TERMINATION_STATES = (
    "('cancelled','timeout','tool_failure','no_relevant_evidence','generation_unavailable',"
    "'retrieval_degraded','completed_with_limited_evidence','completed','interrupted','error')"
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
            persona text NOT NULL DEFAULT 'generalist',
            title text NOT NULL DEFAULT '' CHECK (length(title) <= 200),
            rolling_summary text NOT NULL DEFAULT '',
            recent_questions text[] NOT NULL DEFAULT '{}',
            recent_handles text[] NOT NULL DEFAULT '{}',
            summary_through_message_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE query_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL,
            conversation_id uuid NOT NULL,
            mode text NOT NULL DEFAULT 'standard' CHECK (mode IN ('standard', 'research')),
            persona text NOT NULL DEFAULT 'generalist',
            original_query text NOT NULL CHECK (length(original_query) <= 4000),
            normalized_query text NOT NULL DEFAULT '',
            standalone_query text NOT NULL DEFAULT '',
            retrieved_handles text[] NOT NULL DEFAULT '{}',
            pack_handles text[] NOT NULL DEFAULT '{}',
            cited_handles text[] NOT NULL DEFAULT '{}',
            context_tokens integer NOT NULL DEFAULT 0,
            pack_tokens integer NOT NULL DEFAULT 0,
            models jsonb NOT NULL DEFAULT '{}',
            usage jsonb NOT NULL DEFAULT '{}',
            cache_status text NOT NULL DEFAULT 'disabled',
            timings jsonb NOT NULL DEFAULT '{}',
            status text NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'interrupted')),
            termination_state text CHECK (termination_state IN """
        + TERMINATION_STATES
        + """),
            degradation_flags text[] NOT NULL DEFAULT '{}',
            config_hash text NOT NULL DEFAULT '',
            prompt_version text NOT NULL DEFAULT '',
            corpus_version_start bigint,
            error_class text,
            created_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz,
            UNIQUE (workspace_id, id),
            FOREIGN KEY (workspace_id, conversation_id)
                REFERENCES conversations (workspace_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX query_runs_ws_time ON query_runs (workspace_id, created_at)")
    op.execute("CREATE INDEX query_runs_running ON query_runs (status) WHERE status = 'running'")
    op.execute(
        """
        CREATE TABLE messages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL,
            conversation_id uuid NOT NULL,
            role text NOT NULL CHECK (role IN ('user', 'assistant')),
            content text NOT NULL,
            citations jsonb NOT NULL DEFAULT '[]',
            sections jsonb NOT NULL DEFAULT '{}',
            status text NOT NULL DEFAULT 'complete'
                CHECK (status IN ('complete', 'incomplete', 'failed', 'redacted')),
            query_run_id uuid,
            model text,
            usage jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, id),
            FOREIGN KEY (workspace_id, conversation_id)
                REFERENCES conversations (workspace_id, id) ON DELETE CASCADE,
            FOREIGN KEY (workspace_id, query_run_id)
                REFERENCES query_runs (workspace_id, id) ON DELETE SET NULL (query_run_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX messages_conversation ON messages (workspace_id, conversation_id, created_at)"
    )
    op.execute(
        """
        CREATE TABLE run_events (
            workspace_id uuid NOT NULL,
            run_id uuid NOT NULL,
            seq integer NOT NULL CHECK (seq >= 1),
            type text NOT NULL,
            payload jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, run_id, seq),
            FOREIGN KEY (workspace_id, run_id)
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
    # The event log is append-only for the runtime role (retention/purge delete as owner paths).
    op.execute(f"REVOKE UPDATE ON run_events FROM {APP_ROLE}")
    # retrieval_traces.query_run_id now has a target; it stays a plain column (traces outlive
    # runs only until retention) but is indexed for the trace view.


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
