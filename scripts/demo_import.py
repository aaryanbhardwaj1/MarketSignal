"""Import the demo snapshot into a freshly seeded workspace (idempotent, fail-closed).

    make demo-seed              # after `make seed`
    uv --directory backend run python ../scripts/demo_import.py --dry-run   # guards only

Runs as the schema owner in ONE transaction scoped with ``app.workspace_id``:

1. Guards (any failure aborts before a row is written; the corpus has drifted):
   * every pack/cited/citation handle's source version exists and is ``ready``/``superseded``;
   * every evidence citation's ``parent_content_hash`` equals the live parent's hash;
   * every logical child key resolves to exactly one child chunk;
   * every analytics ``dataset_ref`` resolves to a live version's dataset table.
2. Inserts in FK order with ``ON CONFLICT DO NOTHING``: conversations, query_runs, messages,
   run_events, tool_runs, retrieval_traces, verification_attempts, analytics_results.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _demo_common import (
    DEFAULT_SNAPSHOT,
    LIVE_VERSION_STATUSES,
    SNAPSHOT_FORMAT,
    SNAPSHOT_FORMAT_VERSION,
    SnapshotError,
    child_lookup,
    child_refs_in,
    parse_handle,
    resolve_children,
    scope_to,
    workspace_id,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

INSERT_ORDER = (
    "conversations",
    "query_runs",
    "messages",
    "run_events",
    "tool_runs",
    "retrieval_traces",
    "verification_attempts",
    "analytics_results",
)
_RUN_TABLES = INSERT_ORDER[3:]


@dataclass
class ImportReport:
    inserted: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)


def validate_format(snapshot: dict[str, Any]) -> None:
    if snapshot.get("format") != SNAPSHOT_FORMAT:
        raise SnapshotError("not a MarketSignal demo snapshot")
    if snapshot.get("format_version") != SNAPSHOT_FORMAT_VERSION:
        raise SnapshotError(f"unsupported snapshot version {snapshot.get('format_version')}")


def rows_by_table(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Flatten the nested snapshot into insert order (stable within each table)."""
    out: dict[str, list[dict[str, Any]]] = {table: [] for table in INSERT_ORDER}
    for conv in snapshot["conversations"]:
        out["conversations"].append(conv["conversation"])
        out["messages"].extend(conv["messages"])
        for run in conv["runs"]:
            out["query_runs"].append(run["query_run"])
            for table in _RUN_TABLES:
                out[table].extend(run[table])
    return out


def evidence_citations(rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    cites = [c for m in rows["messages"] for c in m.get("citations") or []]
    return [c for c in cites if c.get("kind", "evidence") == "evidence" and c.get("handle")]


def version_keys(rows: dict[str, list[dict[str, Any]]]) -> set[tuple[str, int]]:
    """(source_code, version) of every pack, cited, citation and dataset reference."""
    handles: set[str] = set()
    for run in rows["query_runs"]:
        handles.update(run.get("pack_handles") or [])
        handles.update(run.get("cited_handles") or [])
    for message in rows["messages"]:
        handles.update(c["handle"] for c in message.get("citations") or [] if c.get("handle"))
    keys = {(k.source_code, k.version) for h in handles if (k := parse_handle(h)) is not None}
    keys.update(
        (r["dataset_ref"]["source_code"], int(r["dataset_ref"]["version"]))
        for r in rows["analytics_results"]
    )
    return keys


def drifted_versions(wanted: set[tuple[str, int]], live: dict[tuple[str, int], str]) -> list[str]:
    return sorted(
        f"{code}@v{version}:{live.get((code, version), 'missing')}"
        for code, version in wanted
        if live.get((code, version)) not in LIVE_VERSION_STATUSES
    )


def hash_mismatches(cites: list[dict[str, Any]], live: dict[str, str]) -> list[str]:
    return sorted(
        {
            c["handle"]
            for c in cites
            if c.get("parent_content_hash") and live.get(c["handle"]) != c["parent_content_hash"]
        }
    )


async def _version_statuses(conn: AsyncConnection, codes: set[str]) -> dict[tuple[str, int], str]:
    rows = await conn.execute(
        text(
            "SELECT s.source_code, v.version, v.status FROM sources s "
            "JOIN source_versions v ON v.source_id = s.id WHERE s.source_code = ANY(:codes) "
            "AND s.workspace_id = CAST(current_setting('app.workspace_id', true) AS uuid)"
        ),
        {"codes": sorted(codes)},
    )
    return {(str(c), int(v)): str(st) for c, v, st in rows.all()}


async def _parent_hashes(conn: AsyncConnection, handles: set[str]) -> dict[str, str]:
    rows = await conn.execute(
        text(
            "SELECT handle, content_hash FROM parent_chunks WHERE handle = ANY(:h) "
            "AND workspace_id = CAST(current_setting('app.workspace_id', true) AS uuid)"
        ),
        {"h": sorted(handles)},
    )
    return {str(h): str(ch).strip() for h, ch in rows.all()}


async def _dataset_ids(conn: AsyncConnection, ref: dict[str, Any]) -> tuple[str, str]:
    row = await conn.execute(
        text(
            "SELECT v.id::text, d.id::text FROM sources s "
            "JOIN source_versions v ON v.source_id = s.id "
            "JOIN dataset_tables d ON d.source_version_id = v.id "
            "WHERE s.source_code = :c AND v.version = :v AND d.sheet_ordinal = :o AND d.name = :n "
            "AND s.workspace_id = CAST(current_setting('app.workspace_id', true) AS uuid)"
        ),
        {
            "c": ref["source_code"],
            "v": int(ref["version"]),
            "o": ref["sheet_ordinal"],
            "n": ref["table"],
        },
    )
    found = row.all()
    if len(found) != 1:
        raise SnapshotError(
            f"corpus drift: dataset {ref['source_code']}@v{ref['version']} not found"
        )
    return str(found[0][0]), str(found[0][1])


async def _resolve(
    conn: AsyncConnection, rows: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    """Run every guard, then return rows with live corpus ids filled in."""
    wanted = version_keys(rows)
    drift = drifted_versions(wanted, await _version_statuses(conn, {c for c, _ in wanted}))
    if drift:
        raise SnapshotError(f"corpus drift: versions not ready/superseded: {drift[:5]}")
    cites = evidence_citations(rows)
    mismatched = hash_mismatches(cites, await _parent_hashes(conn, {c["handle"] for c in cites}))
    if mismatched:
        raise SnapshotError(f"corpus drift: parent hash differs for {mismatched[:5]}")
    resolved: dict[str, list[dict[str, Any]]] = resolve_children(
        rows, await child_lookup(conn, child_refs_in(rows))
    )
    results = []
    for result in resolved["analytics_results"]:
        version_id, table_id = await _dataset_ids(conn, result["dataset_ref"])
        live = {k: v for k, v in result.items() if k != "dataset_ref"}
        results.append({**live, "source_version_id": version_id, "table_id": table_id})
    return {**resolved, "analytics_results": results}


async def import_snapshot(
    engine: AsyncEngine,
    snapshot: dict[str, Any],
    *,
    workspace_code: str | None = None,
    dry_run: bool = False,
) -> ImportReport:
    validate_format(snapshot)
    code = str(snapshot["workspace"])
    if workspace_code is not None and workspace_code != code:
        raise SnapshotError(f"snapshot handles belong to {code}, not {workspace_code}")
    report = ImportReport()
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            ws_id = await workspace_id(conn, code)
            await scope_to(conn, ws_id)
            resolved = await _resolve(conn, rows_by_table(snapshot))
            for table in INSERT_ORDER:  # constant identifiers, never user input
                sql = text(
                    f"INSERT INTO {table} SELECT * FROM jsonb_populate_record("  # noqa: S608
                    f"NULL::{table}, CAST(:row AS jsonb)) ON CONFLICT DO NOTHING"
                )
                inserted = 0
                for row in resolved[table]:
                    payload = json.dumps({**row, "workspace_id": ws_id})
                    inserted += (await conn.execute(sql, {"row": payload})).rowcount or 0
                report.inserted[table] = inserted
                report.skipped[table] = len(resolved[table]) - inserted
        except BaseException:
            await transaction.rollback()
            raise
        if dry_run:
            await transaction.rollback()
        else:
            await transaction.commit()
    return report


async def _main(args: argparse.Namespace, snapshot: dict[str, Any]) -> int:
    from marketsignal.config import get_settings

    url = get_settings().migrations_database_url.get_secret_value()
    engine = create_async_engine(url)
    try:
        report = await import_snapshot(
            engine, snapshot, workspace_code=args.workspace, dry_run=args.dry_run
        )
    finally:
        await engine.dispose()
    verb = "would insert" if args.dry_run else "inserted"
    for table in INSERT_ORDER:
        done, skipped = report.inserted[table], report.skipped[table]
        print(f"  {table:<22} {verb} {done:>4}, already present {skipped:>4}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--workspace", help="must equal the snapshot's workspace (safety check)")
    parser.add_argument(
        "--dry-run", action="store_true", help="run guards and inserts, then roll back"
    )
    args = parser.parse_args()
    try:
        snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        return asyncio.run(_main(args, snapshot))
    except SnapshotError as exc:
        print(f"import aborted: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
