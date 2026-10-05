"""Evidence model: sources, immutable versions, blobs, parent/child chunks, embeddings, datasets,
audit trail, and the Procrastinate job queue.

Design references: ADR-0001 (single system of record), ADR-0003 (parent = citation unit,
children = retrieval windows with spans into the parent), ADR-0009 (RLS + composite tenant
FKs), ADR-0010 (Postgres-native queue), ADR-0012 (per-model embedding table), ADR-0016
(versioning and purge).

Isolation invariants enforced here, not in application code:
* every tenant table has ENABLE + FORCE RLS with ``workspace_id = app.current_workspace()``;
* every cross-table reference is a composite ``(workspace_id, x_id)`` foreign key, so a row can
  never point at another tenant's row even if application code is wrong;
* ``audit_events`` is append-only for the runtime role.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op
from procrastinate.schema import SchemaManager

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "ms_app"
# Embedding models with a dedicated partial expression HNSW index (ADR-0012). Adding a model is
# a new migration: (model_id, dimensions).
EMBEDDING_MODELS: tuple[tuple[str, int], ...] = (("bge-small-en-v1.5", 384),)

SOURCE_TYPES = "('pdf','docx','pptx','xlsx','csv','markdown','text')"
SOURCE_CLASSES = "('internal','customer','competitor','market','financial')"
CONFIDENTIALITY = "('public','internal','confidential','restricted')"
VERSION_STATUSES = (
    "('queued','parsing','chunking','embedding','indexing','ready','ready_degraded',"
    "'failed','superseded','purged')"
)
TENANT_TABLES = (
    "sources",
    "source_versions",
    "source_blobs",
    "parent_chunks",
    "child_chunks",
    "chunk_embeddings",
    "dataset_tables",
    "dataset_rows",
    "audit_events",
)


def _tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = app.current_workspace()) "
        f"WITH CHECK (workspace_id = app.current_workspace())"
    )


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE sources (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
            source_code text NOT NULL
                CHECK (source_code ~ '^[A-Z0-9]{{1,12}}(-[A-Z0-9]{{1,12}}){{0,5}}$'),
            title text NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
            source_type text NOT NULL CHECK (source_type IN {SOURCE_TYPES}),
            current_version_id uuid,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, source_code),
            UNIQUE (workspace_id, id)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE source_versions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL,
            source_id uuid NOT NULL,
            version integer NOT NULL CHECK (version BETWEEN 1 AND 9999),
            source_class text NOT NULL CHECK (source_class IN {SOURCE_CLASSES}),
            confidentiality text NOT NULL CHECK (confidentiality IN {CONFIDENTIALITY}),
            content_hash char(64) CHECK (content_hash ~ '^[0-9a-f]{{64}}$'),
            original_filename text,
            mime_type text NOT NULL,
            byte_size bigint NOT NULL CHECK (byte_size > 0),
            status text NOT NULL DEFAULT 'queued' CHECK (status IN {VERSION_STATUSES}),
            reason text NOT NULL DEFAULT 'upload' CHECK (reason IN ('upload', 'reindex')),
            error_code text,
            error_detail text,
            warnings text[] NOT NULL DEFAULT '{{}}',
            attempts integer NOT NULL DEFAULT 0,
            parser_version text NOT NULL,
            structure_version text NOT NULL,
            chunking_policy_version text,
            embedding_model text,
            parent_count integer,
            child_count integer,
            health jsonb,
            timings jsonb NOT NULL DEFAULT '{{}}',
            created_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            ready_at timestamptz,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (source_id, version),
            UNIQUE (workspace_id, id),
            FOREIGN KEY (workspace_id, source_id)
                REFERENCES sources (workspace_id, id) ON DELETE RESTRICT
        )
        """
    )
    # Idempotency (ADR-0016): one live version per (source, bytes, parser, structure policy).
    # Failed / superseded / purged versions do not block re-upload (retry, revert, re-add).
    op.execute(
        """
        CREATE UNIQUE INDEX source_versions_live_content
            ON source_versions (source_id, content_hash, parser_version, structure_version)
            WHERE status NOT IN ('failed', 'superseded', 'purged')
        """
    )
    op.execute("CREATE INDEX source_versions_ws_status ON source_versions (workspace_id, status)")
    op.execute(
        """
        ALTER TABLE sources ADD CONSTRAINT sources_current_version_fk
            FOREIGN KEY (workspace_id, current_version_id)
            REFERENCES source_versions (workspace_id, id) ON DELETE RESTRICT
        """
    )

    op.execute(
        """
        CREATE TABLE source_blobs (
            workspace_id uuid NOT NULL,
            source_version_id uuid NOT NULL,
            bytes bytea NOT NULL,
            -- Keys are tenant-scoped so a foreign id never yields a uniqueness error that would
            -- reveal another workspace's row exists (no cross-tenant existence oracle).
            PRIMARY KEY (workspace_id, source_version_id),
            FOREIGN KEY (workspace_id, source_version_id)
                REFERENCES source_versions (workspace_id, id) ON DELETE RESTRICT
        )
        """
    )

    op.execute(
        """
        CREATE TABLE parent_chunks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL,
            source_version_id uuid NOT NULL,
            handle text NOT NULL CHECK (length(handle) <= 96),
            ordinal integer NOT NULL CHECK (ordinal >= 0),
            locator jsonb NOT NULL,
            locator_label text NOT NULL,
            heading_path text[] NOT NULL DEFAULT '{}',
            text text NOT NULL CHECK (length(text) > 0),
            token_count integer NOT NULL CHECK (token_count >= 0),
            content_hash char(64) NOT NULL,
            list_group_id text,
            metadata jsonb NOT NULL DEFAULT '{}',
            UNIQUE (workspace_id, handle),
            UNIQUE (workspace_id, id),
            UNIQUE (source_version_id, ordinal),
            FOREIGN KEY (workspace_id, source_version_id)
                REFERENCES source_versions (workspace_id, id) ON DELETE RESTRICT
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE child_chunks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL,
            parent_id uuid NOT NULL,
            source_version_id uuid NOT NULL,
            source_class text NOT NULL CHECK (source_class IN {SOURCE_CLASSES}),
            confidentiality text NOT NULL CHECK (confidentiality IN {CONFIDENTIALITY}),
            ordinal integer NOT NULL CHECK (ordinal >= 0),
            kind text NOT NULL CHECK (kind IN ('window', 'row', 'summary')),
            text text NOT NULL CHECK (length(text) > 0),
            heading_text text NOT NULL DEFAULT '',
            char_start integer NOT NULL,
            char_end integer NOT NULL,
            token_count integer NOT NULL CHECK (token_count >= 0),
            text_sha256 char(64) NOT NULL,
            chunking_policy_version text NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('english'::regconfig, coalesce(heading_text, '')), 'A')
                || setweight(to_tsvector('english'::regconfig, coalesce(text, '')), 'D')
            ) STORED,
            tsv_body tsvector GENERATED ALWAYS AS (
                to_tsvector('english'::regconfig, coalesce(text, ''))
            ) STORED,
            metadata jsonb NOT NULL DEFAULT '{{}}',
            CHECK (char_start >= 0 AND char_end > char_start),
            UNIQUE (workspace_id, id),
            UNIQUE (parent_id, ordinal),
            FOREIGN KEY (workspace_id, parent_id)
                REFERENCES parent_chunks (workspace_id, id) ON DELETE CASCADE,
            FOREIGN KEY (workspace_id, source_version_id)
                REFERENCES source_versions (workspace_id, id) ON DELETE RESTRICT
        )
        """
    )
    op.execute("CREATE INDEX child_chunks_tsv ON child_chunks USING gin (tsv)")
    op.execute(
        "CREATE INDEX child_chunks_ws_version ON child_chunks (workspace_id, source_version_id)"
    )

    op.execute(
        """
        CREATE TABLE chunk_embeddings (
            child_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            model_id text NOT NULL,
            embedding vector NOT NULL,
            embed_input_sha256 char(64) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, child_id, model_id),
            FOREIGN KEY (workspace_id, child_id)
                REFERENCES child_chunks (workspace_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX chunk_embeddings_reuse ON chunk_embeddings (model_id, embed_input_sha256)"
    )
    for model_id, dims in EMBEDDING_MODELS:
        index = "chunk_embeddings_hnsw_" + model_id.replace("-", "_").replace(".", "_")
        op.execute(
            f"ALTER TABLE chunk_embeddings ADD CONSTRAINT {index}_dims "
            f"CHECK (model_id <> '{model_id}' OR vector_dims(embedding) = {dims})"
        )
        op.execute(
            f"CREATE INDEX {index} ON chunk_embeddings "
            f"USING hnsw ((embedding::vector({dims})) vector_cosine_ops) "
            f"WITH (m = 16, ef_construction = 64) WHERE model_id = '{model_id}'"
        )

    op.execute(
        """
        CREATE TABLE dataset_tables (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL,
            source_version_id uuid NOT NULL,
            sheet_ordinal integer NOT NULL CHECK (sheet_ordinal >= 1),
            name text NOT NULL,
            header_row integer NOT NULL CHECK (header_row >= 1),
            columns jsonb NOT NULL,
            row_count integer NOT NULL CHECK (row_count >= 0),
            UNIQUE (workspace_id, id),
            UNIQUE (source_version_id, sheet_ordinal),
            FOREIGN KEY (workspace_id, source_version_id)
                REFERENCES source_versions (workspace_id, id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE dataset_rows (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL,
            table_id uuid NOT NULL,
            row_number integer NOT NULL CHECK (row_number >= 1),
            parent_handle text NOT NULL,
            values jsonb NOT NULL,
            UNIQUE (table_id, row_number),
            FOREIGN KEY (workspace_id, table_id)
                REFERENCES dataset_tables (workspace_id, id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE audit_events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            workspace_id uuid NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
            actor text NOT NULL,
            action text NOT NULL,
            target text,
            metadata jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX audit_events_ws_time ON audit_events (workspace_id, created_at)")

    for table in TENANT_TABLES:
        _tenant_rls(table)
    # Audit trail is append-only for the runtime role.
    op.execute(f"REVOKE UPDATE, DELETE ON audit_events FROM {APP_ROLE}")

    # Procrastinate job queue (ADR-0010). Not tenant data: jobs carry only ids; the worker sets
    # the workspace scope from the job arguments before touching tenant tables. The schema SQL
    # contains PL/pgSQL "%" placeholders, so it runs on a raw cursor with no parameters.
    raw = op.get_bind().connection.dbapi_connection
    assert raw is not None
    with raw.cursor() as cursor:
        cursor.execute(SchemaManager.get_schema())


def downgrade() -> None:
    raw = op.get_bind().connection.dbapi_connection
    assert raw is not None
    with raw.cursor() as cursor:
        cursor.execute(
            """
            DROP TABLE IF EXISTS procrastinate_events, procrastinate_periodic_defers,
                procrastinate_jobs, procrastinate_workers CASCADE;
            DROP TYPE IF EXISTS procrastinate_job_to_defer_v1, procrastinate_job_event_type,
                procrastinate_job_status CASCADE;
            DO $drop$
            DECLARE fn regprocedure;
            BEGIN
                FOR fn IN SELECT p.oid::regprocedure FROM pg_proc p
                          JOIN pg_namespace n ON n.oid = p.pronamespace
                          WHERE n.nspname = 'public' AND p.proname LIKE 'procrastinate\_%'
                LOOP
                    EXECUTE 'DROP FUNCTION ' || fn || ' CASCADE';
                END LOOP;
            END
            $drop$;
            """
        )
    for table in (
        "audit_events",
        "dataset_rows",
        "dataset_tables",
        "chunk_embeddings",
        "child_chunks",
        "parent_chunks",
        "source_blobs",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_current_version_fk")
    op.execute("DROP TABLE IF EXISTS source_versions")
    op.execute("DROP TABLE IF EXISTS sources")
