"""RLS and composite-FK isolation for every Phase 1 tenant table, exercised as ``ms_app``.

For each table we prove four things:
1. reads under workspace A's scope never see workspace B's rows;
2. writes that claim workspace B under A's scope are rejected by RLS ``WITH CHECK``;
3. a row in workspace B cannot *reference* a row of workspace A (composite FK), even when
   the RLS scope is B - the database itself refuses the cross-tenant pointer;
4. without a scope every table fails closed.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

pytestmark = pytest.mark.integration

SET_SCOPE = text("SELECT set_config('app.workspace_id', :ws, true)")
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
SHA = hashlib.sha256(b"x").hexdigest()
VEC = "[" + ",".join(["0.05"] * 384) + "]"


@dataclass(frozen=True)
class Chain:
    workspace_id: uuid.UUID
    source_id: uuid.UUID
    version_id: uuid.UUID
    parent_id: uuid.UUID
    child_id: uuid.UUID
    table_id: uuid.UUID


async def _scoped(conn: AsyncConnection, ws: uuid.UUID) -> None:
    await conn.execute(SET_SCOPE, {"ws": str(ws)})


async def _seed_chain(engine: AsyncEngine, ws: uuid.UUID, code: str) -> Chain:
    """Insert one row in every tenant table for ``ws``, as ms_app under ws's scope."""
    async with engine.begin() as conn:
        await _scoped(conn, ws)

        async def one(sql: str, **params: object) -> uuid.UUID:
            result = await conn.execute(text(sql), {"ws": ws, **params})
            value: uuid.UUID = result.scalar_one()
            return value

        source_id = await one(
            "INSERT INTO sources (workspace_id, source_code, title, source_type) "
            "VALUES (:ws, 'SURVEY', 'Survey', 'csv') RETURNING id"
        )
        version_id = await one(
            "INSERT INTO source_versions (workspace_id, source_id, version, source_class, "
            "confidentiality, content_hash, mime_type, byte_size, parser_version, "
            "structure_version) VALUES (:ws, :s, 1, 'customer', 'internal', :h, 'text/csv', 10, "
            "'p1', 's1') RETURNING id",
            s=source_id,
            h=SHA,
        )
        await conn.execute(
            text(
                "INSERT INTO source_blobs (workspace_id, source_version_id, bytes) "
                "VALUES (:ws, :v, :b)"
            ),
            {"v": version_id, "ws": ws, "b": b"a,b\n1,2\n"},
        )
        parent_id = await one(
            "INSERT INTO parent_chunks (workspace_id, source_version_id, handle, ordinal, locator, "
            "locator_label, text, token_count, content_hash) VALUES (:ws, :v, :handle, 0, "
            "'{}'::jsonb, 'Row 2', 'a: 1; b: 2', 4, :h) RETURNING id",
            v=version_id,
            handle=f"{code}/SURVEY@v1:R2",
            h=SHA,
        )
        child_id = await one(
            "INSERT INTO child_chunks (workspace_id, parent_id, source_version_id, source_class, "
            "confidentiality, ordinal, kind, text, char_start, char_end, token_count, "
            "text_sha256, chunking_policy_version) VALUES (:ws, :p, :v, 'customer', 'internal', "
            "0, 'row', 'a: 1; b: 2', 0, 10, 4, :h, 'c1') RETURNING id",
            p=parent_id,
            v=version_id,
            h=SHA,
        )
        await conn.execute(
            text(
                "INSERT INTO chunk_embeddings (child_id, workspace_id, model_id, embedding, "
                "embed_input_sha256) VALUES (:c, :ws, 'bge-small-en-v1.5', CAST(:e AS vector), :h)"
            ),
            {"c": child_id, "ws": ws, "e": VEC, "h": SHA},
        )
        table_id = await one(
            "INSERT INTO dataset_tables (workspace_id, source_version_id, sheet_ordinal, name, "
            "header_row, columns, row_count) VALUES (:ws, :v, 1, 'data', 1, '[]'::jsonb, 1) "
            "RETURNING id",
            v=version_id,
        )
        await conn.execute(
            text(
                "INSERT INTO dataset_rows (workspace_id, table_id, row_number, parent_handle, "
                "values) VALUES (:ws, :t, 2, :handle, '{}'::jsonb)"
            ),
            {"ws": ws, "t": table_id, "handle": f"{code}/SURVEY@v1:R2"},
        )
        await conn.execute(
            text(
                "INSERT INTO audit_events (workspace_id, actor, action) "
                "VALUES (:ws, 'test', 'seed')"
            ),
            {"ws": ws},
        )
    return Chain(ws, source_id, version_id, parent_id, child_id, table_id)


@pytest.fixture
async def chains(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, two_workspaces: tuple[uuid.UUID, uuid.UUID]
) -> tuple[Chain, Chain]:
    ws_a, ws_b = two_workspaces
    async with owner_engine.connect() as conn:
        codes = dict(
            (
                await conn.execute(
                    text("SELECT id, code FROM workspaces WHERE id = ANY(:ids)"),
                    {"ids": [ws_a, ws_b]},
                )
            ).all()
        )
    a = await _seed_chain(app_engine, ws_a, codes[ws_a])
    b = await _seed_chain(app_engine, ws_b, codes[ws_b])
    return a, b


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_reads_are_confined_to_scope(
    app_engine: AsyncEngine, chains: tuple[Chain, Chain], table: str
) -> None:
    a, b = chains
    async with app_engine.begin() as conn:
        await _scoped(conn, a.workspace_id)
        seen = (
            (await conn.execute(text(f"SELECT DISTINCT workspace_id FROM {table}"))).scalars().all()
        )
        foreign = (
            await conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE workspace_id = :b"),
                {"b": b.workspace_id},
            )
        ).scalar_one()
    assert seen == [a.workspace_id]
    assert foreign == 0


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_unscoped_access_fails_closed(
    app_engine: AsyncEngine, chains: tuple[Chain, Chain], table: str
) -> None:
    with pytest.raises(DBAPIError, match="WORKSPACE_SCOPE_NOT_SET"):
        async with app_engine.begin() as conn:
            await conn.execute(text(f"SELECT count(*) FROM {table}"))


async def _write_as(engine: AsyncEngine, scope: uuid.UUID, sql: str, **params: object) -> None:
    async with engine.begin() as conn:
        await _scoped(conn, scope)
        await conn.execute(text(sql), params)


# Each statement is executed under workspace A's scope but writes a row claiming workspace B.
FOREIGN_WRITES: dict[str, str] = {
    "sources": "INSERT INTO sources (workspace_id, source_code, title, source_type) "
    "VALUES (:b, 'X', 'x', 'csv')",
    "source_versions": "UPDATE source_versions SET status = 'failed' WHERE workspace_id = :b",
    "audit_events": "INSERT INTO audit_events (workspace_id, actor, action) VALUES (:b, 'x', 'x')",
    "dataset_tables": "INSERT INTO dataset_tables (workspace_id, source_version_id, sheet_ordinal, "
    "name, header_row, columns, row_count) VALUES (:b, :bv, 9, 'x', 1, '[]', 0)",
}


@pytest.mark.parametrize("table", sorted(FOREIGN_WRITES))
async def test_writes_claiming_another_workspace_are_rejected(
    app_engine: AsyncEngine, chains: tuple[Chain, Chain], table: str
) -> None:
    a, b = chains
    sql = FOREIGN_WRITES[table]
    if sql.startswith("UPDATE"):
        # RLS hides B's rows from A: the UPDATE affects nothing rather than erroring.
        async with app_engine.begin() as conn:
            await _scoped(conn, a.workspace_id)
            result = await conn.execute(text(sql), {"b": b.workspace_id})
        assert result.rowcount == 0
        return
    with pytest.raises(DBAPIError, match="row-level security"):
        await _write_as(app_engine, a.workspace_id, sql, b=b.workspace_id, bv=b.version_id)


# Each statement runs under workspace B's scope, claims workspace B, but points at A's rows.
CROSS_REFERENCES: dict[str, str] = {
    "source_versions->sources": "INSERT INTO source_versions (workspace_id, source_id, version, "
    "source_class, confidentiality, mime_type, byte_size, parser_version, structure_version) "
    "VALUES (:b, :a_source, 2, 'customer', 'internal', 'text/csv', 1, 'p', 's')",
    "parent_chunks->source_versions": "INSERT INTO parent_chunks (workspace_id, "
    "source_version_id, handle, ordinal, locator, locator_label, text, token_count, "
    "content_hash) VALUES (:b, :a_version, 'X', 99, '{}', 'x', 'x', 1, :h)",
    "child_chunks->parent_chunks": "INSERT INTO child_chunks (workspace_id, parent_id, "
    "source_version_id, source_class, confidentiality, ordinal, kind, text, char_start, "
    "char_end, token_count, text_sha256, chunking_policy_version) VALUES (:b, :a_parent, "
    ":b_version, 'customer', 'internal', 99, 'row', 'x', 0, 1, 1, :h, 'c')",
    "chunk_embeddings->child_chunks": "INSERT INTO chunk_embeddings (child_id, workspace_id, "
    "model_id, embedding, embed_input_sha256) VALUES (:a_child, :b, 'other-model', "
    "'[1,2,3]', :h)",
    "dataset_rows->dataset_tables": "INSERT INTO dataset_rows (workspace_id, table_id, "
    "row_number, parent_handle, values) VALUES (:b, :a_table, 99, 'X', '{}')",
    "source_blobs->source_versions": "INSERT INTO source_blobs (workspace_id, source_version_id, "
    "bytes) VALUES (:b, :a_version, 'x')",
}


@pytest.mark.parametrize("edge", sorted(CROSS_REFERENCES))
async def test_cross_tenant_references_are_rejected_by_composite_fks(
    app_engine: AsyncEngine, chains: tuple[Chain, Chain], edge: str
) -> None:
    a, b = chains
    with pytest.raises(IntegrityError, match="foreign key"):
        await _write_as(
            app_engine,
            b.workspace_id,
            CROSS_REFERENCES[edge],
            b=b.workspace_id,
            b_version=b.version_id,
            a_source=a.source_id,
            a_version=a.version_id,
            a_parent=a.parent_id,
            a_child=a.child_id,
            a_table=a.table_id,
            h=SHA,
        )


@pytest.mark.parametrize(
    "statement", ["UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"]
)
async def test_audit_trail_is_append_only_for_app_role(
    app_engine: AsyncEngine, chains: tuple[Chain, Chain], statement: str
) -> None:
    a, _ = chains
    with pytest.raises(DBAPIError, match="permission denied"):
        await _write_as(app_engine, a.workspace_id, statement)


async def test_live_content_idempotency_index(
    app_engine: AsyncEngine, chains: tuple[Chain, Chain]
) -> None:
    """A second live version with identical bytes + pipeline versions is rejected; a failed
    version does not block re-upload (retry after fix)."""
    a, _ = chains
    insert = (
        "INSERT INTO source_versions (workspace_id, source_id, version, source_class, "
        "confidentiality, content_hash, mime_type, byte_size, parser_version, structure_version, "
        "status) VALUES (:ws, :s, :ver, 'customer', 'internal', :h, 'text/csv', 10, 'p1', 's1', "
        ":status)"
    )
    with pytest.raises(IntegrityError, match="source_versions_live_content"):
        await _write_as(
            app_engine,
            a.workspace_id,
            insert,
            ws=a.workspace_id,
            s=a.source_id,
            ver=2,
            h=SHA,
            status="queued",
        )
    await _write_as(
        app_engine,
        a.workspace_id,
        insert,
        ws=a.workspace_id,
        s=a.source_id,
        ver=3,
        h=SHA,
        status="failed",
    )
