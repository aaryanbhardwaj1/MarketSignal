"""Export saved demo conversations to a deterministic, committable JSON snapshot (read-only).

    make demo-export            # NORTHSTAR featured conversations -> seed_data/demo/...json
    uv --directory backend run python ../scripts/demo_export.py --check   # byte-identical?

Connects with the schema-owner URL (``MS_MIGRATIONS_DATABASE_URL``) inside a READ ONLY
transaction scoped with ``app.workspace_id``. Token events are dropped (the ``final`` event
carries the full answer), ``workspace_id`` is dropped, and corpus UUIDs become logical keys
(see ``_demo_common``). The export fails if any string matches the safety denylist, if a UUID
other than the snapshot's own row ids survives, or if a logical key does not resolve back to
the exact id it replaced.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _demo_common import (
    DEFAULT_SNAPSHOT,
    FEATURED_NORTHSTAR,
    SNAPSHOT_FORMAT,
    SNAPSHOT_FORMAT_VERSION,
    SnapshotError,
    child_lookup,
    child_refs_in,
    denylist_hits,
    foreign_uuids,
    load_denylist,
    logicalize_children,
    resolve_children,
    scope_to,
    workspace_id,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

_RUN_CHILDREN = {
    "run_events": (
        "SELECT to_jsonb(t) - 'workspace_id' "
        "FROM run_events t WHERE run_id = CAST(:r AS uuid) AND type <> 'token' "
        "ORDER BY seq"
    ),
    "tool_runs": (
        "SELECT to_jsonb(t) - 'workspace_id' "
        "FROM tool_runs t WHERE query_run_id = CAST(:r AS uuid) "
        "ORDER BY step, call_index, id"
    ),
    "verification_attempts": (
        "SELECT to_jsonb(t) - 'workspace_id' "
        "FROM verification_attempts t WHERE query_run_id = CAST(:r AS uuid) "
        "ORDER BY attempt, id"
    ),
    "retrieval_traces": (
        "SELECT to_jsonb(t) - 'workspace_id' "
        "FROM retrieval_traces t WHERE query_run_id = CAST(:r AS uuid) "
        "OR tool_run_id IN (SELECT id FROM tool_runs WHERE query_run_id = CAST(:r AS uuid)) "
        "ORDER BY created_at, id"
    ),
    "analytics_results": (
        "SELECT to_jsonb(t) - 'workspace_id' - 'source_version_id' - 'table_id' "
        "|| jsonb_build_object('dataset_ref', jsonb_build_object("
        "'source_code', s.source_code, 'version', v.version, "
        "'sheet_ordinal', d.sheet_ordinal, 'table', d.name)) "
        "FROM analytics_results t JOIN source_versions v ON v.id = t.source_version_id "
        "JOIN sources s ON s.id = v.source_id JOIN dataset_tables d ON d.id = t.table_id "
        "WHERE t.query_run_id = CAST(:r AS uuid) ORDER BY t.created_at, t.id"
    ),
}


async def _rows(conn: AsyncConnection, sql: str, **params: Any) -> list[dict[str, Any]]:
    result = await conn.execute(text(sql), params)
    return [dict(r[0]) for r in result.all()]


async def _conversation(conn: AsyncConnection, conversation_id: str) -> dict[str, Any]:
    found = await _rows(
        conn,
        "SELECT to_jsonb(t) - 'workspace_id' FROM conversations t WHERE id = CAST(:c AS uuid)",
        c=conversation_id,
    )
    if not found:
        raise SnapshotError(f"conversation {conversation_id} not found in this workspace")
    messages = await _rows(
        conn,
        "SELECT to_jsonb(t) - 'workspace_id' "
        "FROM messages t WHERE conversation_id = CAST(:c AS uuid) "
        "ORDER BY created_at, id",
        c=conversation_id,
    )
    query_runs = await _rows(
        conn,
        "SELECT to_jsonb(t) - 'workspace_id' "
        "FROM query_runs t WHERE conversation_id = CAST(:c AS uuid) "
        "ORDER BY created_at, id",
        c=conversation_id,
    )
    runs = []
    for run in query_runs:
        entry: dict[str, Any] = {"query_run": run}
        for table, sql in _RUN_CHILDREN.items():
            entry[table] = await _rows(conn, sql, r=run["id"])
        runs.append(entry)
    return {"conversation": found[0], "messages": messages, "runs": runs}


def own_ids(snapshot: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for conv in snapshot["conversations"]:
        ids.add(conv["conversation"]["id"])
        ids.update(m["id"] for m in conv["messages"])
        for run in conv["runs"]:
            ids.add(run["query_run"]["id"])
            for table in ("tool_runs", "verification_attempts", "retrieval_traces"):
                ids.update(r["id"] for r in run[table])
            ids.update(r["id"] for r in run["analytics_results"])
    return ids


async def export_snapshot(
    engine: AsyncEngine, workspace_code: str, conversation_ids: list[str]
) -> dict[str, Any]:
    """Build the logical snapshot and prove it resolves back to the live rows."""
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.execute(text("SET LOCAL TimeZone = 'UTC'"))
            await scope_to(conn, await workspace_id(conn, workspace_code))
            raw = {
                "format": SNAPSHOT_FORMAT,
                "format_version": SNAPSHOT_FORMAT_VERSION,
                "workspace": workspace_code,
                "conversations": [await _conversation(conn, c) for c in conversation_ids],
            }
            logical: dict[str, Any] = logicalize_children(raw)
            lookup = await child_lookup(conn, child_refs_in(logical))
        finally:
            await transaction.rollback()
    if resolve_children(logical, lookup) != raw:
        raise SnapshotError("a logical child key does not resolve back to its original id")
    return logical


def check_safe(snapshot: dict[str, Any]) -> None:
    hits = denylist_hits(snapshot, load_denylist())
    if hits:
        raise SnapshotError(f"denylisted content at {len(hits)} path(s), e.g. {hits[:3]}")
    stray = foreign_uuids(snapshot, own_ids(snapshot))
    if stray:
        raise SnapshotError(f"foreign UUIDs left at {len(stray)} path(s), e.g. {stray[:3]}")


def render(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


async def _fetch(workspace: str, conversations: list[str]) -> dict[str, Any]:
    from marketsignal.config import get_settings

    url = get_settings().migrations_database_url.get_secret_value()
    engine = create_async_engine(url)
    try:
        return await export_snapshot(engine, workspace, conversations)
    finally:
        await engine.dispose()


def _write(args: argparse.Namespace, conversations: list[str]) -> int:
    snapshot = asyncio.run(_fetch(args.workspace, conversations))
    check_safe(snapshot)
    body = render(snapshot)
    out: Path = args.out
    if args.check:
        same = out.is_file() and out.read_text(encoding="utf-8") == body
        print(f"{out.name}: {'up to date' if same else 'DIFFERS from the database'}")
        return 0 if same else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    runs = sum(len(c["runs"]) for c in snapshot["conversations"])
    print(f"wrote {out.name}: {len(conversations)} conversations, {runs} runs, {len(body)} bytes")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="NORTHSTAR")
    parser.add_argument("--conversation", action="append", help="repeatable; display order")
    parser.add_argument("--out", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--check", action="store_true", help="compare only; exit 1 if different")
    args = parser.parse_args()
    conversations = args.conversation or (
        list(FEATURED_NORTHSTAR) if args.workspace == "NORTHSTAR" else []
    )
    if not conversations:
        print("--conversation is required outside NORTHSTAR", file=sys.stderr)
        return 2
    try:
        return _write(args, conversations)
    except SnapshotError as exc:
        print(f"export refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
