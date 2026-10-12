"""Remove leftover test-harness workspaces (codes ``T`` + 10 upper-case hex) from a database.

    uv --directory backend run python ../scripts/demo_reset.py --drop-test-workspaces --dry-run
    uv --directory backend run python ../scripts/demo_reset.py --drop-test-workspaces --yes

Only codes matching ``^T[0-9A-F]{10}$`` are ever touched; ``--code`` narrows the set further
and is refused for any other code. Deletes run per workspace as the schema owner, inside that
workspace's RLS scope, with every statement also filtered on ``workspace_id`` and the role
checked to be subject to RLS (never a superuser or BYPASSRLS role): run tables first, then the
source chain (the integration-test purge order), then the workspace row. Without ``--yes``
nothing is deleted.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _demo_common import TEST_WORKSPACE_CODE, SnapshotError, is_test_workspace_code, scope_to
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Run tables (children first), then tests/integration/conftest.py `_PURGE_ORDER`.
# Every statement is filtered on workspace_id explicitly, so isolation never depends on RLS
# alone (scope_to also refuses superuser/BYPASSRLS roles).
PURGE_ORDER: tuple[str, ...] = (
    "DELETE FROM run_events WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM tool_runs WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM verification_attempts WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM analytics_results WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM retrieval_traces WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM messages WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM query_runs WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM conversations WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM chunk_embeddings WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM child_chunks WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM parent_chunks WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM dataset_tables WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM source_blobs WHERE workspace_id = CAST(:ws AS uuid)",
    "UPDATE sources SET current_version_id = NULL WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM source_versions WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM sources WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM audit_events WHERE workspace_id = CAST(:ws AS uuid)",
    "DELETE FROM workspace_corpus_state WHERE workspace_id = CAST(:ws AS uuid)",
)
COUNTED = ("sources", "conversations", "query_runs")


def select_targets(found: list[str], only: list[str] | None) -> list[str]:
    """Test codes to drop: every match, or the requested subset. Refuses non-test codes."""
    bad = [code for code in (only or []) if not is_test_workspace_code(code)]
    if bad:
        raise ValueError(f"refusing non-test workspace codes: {bad}")
    matching = [code for code in found if is_test_workspace_code(code)]
    return sorted(c for c in matching if only is None or c in only)


async def list_test_workspaces(engine: AsyncEngine) -> list[tuple[str, str]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT code, id::text FROM workspaces WHERE code ~ :re ORDER BY code"),
            {"re": TEST_WORKSPACE_CODE.pattern},
        )
        return [(str(c), str(i)) for c, i in rows.all()]


_COUNT_SQL = {
    table: f"SELECT count(*) FROM {table} WHERE workspace_id = CAST(:ws AS uuid)"  # noqa: S608
    for table in COUNTED
}


async def counts(engine: AsyncEngine, ws_id: str) -> dict[str, int]:
    async with engine.connect() as conn, conn.begin():
        await scope_to(conn, ws_id)
        return {
            table: int((await conn.execute(text(sql), {"ws": ws_id})).scalar_one())
            for table, sql in _COUNT_SQL.items()
        }


async def drop_workspace(engine: AsyncEngine, code: str, ws_id: str) -> None:
    if not is_test_workspace_code(code):  # defence in depth: never trust the caller
        raise ValueError(f"refusing to drop non-test workspace {code}")
    async with engine.begin() as conn:
        await scope_to(conn, ws_id)
        for statement in PURGE_ORDER:
            await conn.execute(text(statement), {"ws": ws_id})
        await conn.execute(
            text("DELETE FROM workspaces WHERE id = CAST(:id AS uuid) AND code = :c"),
            {"id": ws_id, "c": code},
        )


async def reset(
    engine: AsyncEngine, *, only: list[str] | None, yes: bool, dry_run: bool
) -> list[str]:
    """Drop (or, without ``yes`` / with ``dry_run``, only report) test workspaces."""
    found = dict(await list_test_workspaces(engine))
    targets = select_targets(list(found), only)
    for code in targets:
        summary = ", ".join(f"{k}={v}" for k, v in (await counts(engine, found[code])).items())
        print(f"  {code}: {summary}")
        if yes and not dry_run:
            await drop_workspace(engine, code, found[code])
    return targets


async def _main(args: argparse.Namespace) -> int:
    from marketsignal.config import get_settings

    engine = create_async_engine(get_settings().migrations_database_url.get_secret_value())
    try:
        targets = await reset(engine, only=args.code, yes=args.yes, dry_run=args.dry_run)
    finally:
        await engine.dispose()
    action = "dropped" if args.yes and not args.dry_run else "would drop (dry run)"
    print(f"{action}: {len(targets)} test workspace(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--drop-test-workspaces", action="store_true", required=True)
    parser.add_argument("--code", action="append", help="limit to these test codes (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="report only")
    parser.add_argument("--yes", action="store_true", help="actually delete")
    args = parser.parse_args()
    if not args.yes and not args.dry_run:
        print("refusing to delete without --yes (use --dry-run to preview)", file=sys.stderr)
        return 2
    try:
        return asyncio.run(_main(args))
    except (ValueError, SnapshotError) as exc:
        print(f"reset refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
