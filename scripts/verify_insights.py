"""Dev-DB acceptance for the curated analyst brief (plan §5.4; schema v1 and v2).

Resolves a curated brief fixture against the seeded database, exactly as
``GET /api/workspaces/<WS>/insights`` does, and reports every item. It exits non-zero unless
every quoted passage (opportunity risks included) is ``verified``, every named analysis is
``computed``, every analysis summary passes the number check (schema v2), no analysis
interpretation is withheld by it, and every brief item rolls up to ``verified``. It is
read-only: it uses the application role under the workspace scope, never commits, and checks
that the ``analytics_results`` row count is unchanged afterwards. No model is called.

    uv --directory backend run python ../scripts/verify_insights.py
    uv --directory backend run python ../scripts/verify_insights.py --fixture /abs/draft.json

Without ``--fixture`` the newest committed fixture of ``--workspace`` (default NORTHSTAR) is
checked; with it, any draft file is validated and checked against its own ``workspace`` before
it is moved into ``insights/fixtures/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

from marketsignal.config import get_settings
from marketsignal.db.engine import create_engine, create_session_factory
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session, unscoped_session
from marketsignal.insights.analyses import run_parts
from marketsignal.insights.fixture import Fixture, FixtureError, load_fixture, parse_fixture
from marketsignal.insights.service import build_bundle

WORKSPACE = "NORTHSTAR"
_COUNT = "SELECT count(*) FROM analytics_results WHERE workspace_id = :ws"


async def _scope(factory: SessionFactory, workspace: str) -> WorkspaceScope:
    async with unscoped_session(factory) as session:
        row = (
            await session.execute(
                text("SELECT id, code FROM workspaces WHERE code = :c"), {"c": workspace}
            )
        ).one_or_none()
    if row is None:
        raise SystemExit(f"workspace {workspace} not found (seed the dev database first)")
    return WorkspaceScope(row[0], row[1])


def _item_refs(item: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    refs = item.get("evidence") or [*item["supporting"], *item["contradicting"]]
    out = [("", r) for r in refs]
    for n, risk in enumerate(item.get("risks") or [], 1):
        out += [(f"risk {n} ", r) for r in risk["evidence"]]
    return out


def _item_report(item: dict[str, Any]) -> tuple[str, list[str]]:
    """One line for the item plus a line per problem."""
    refs = _item_refs(item)
    problems = [
        f"      {where}{r['integrity']} {r['handle']}"
        for where, r in refs
        if r["integrity"] != "verified"
    ]
    problems += [
        f"      metric withheld: {m['label']}" for m in item["metrics"] if m["value"] is None
    ]
    if item["integrity"] != "verified":
        problems.append(f"      item integrity {item['integrity']}")
    risks = len(item.get("risks") or [])
    tag = "FAIL" if problems else "ok  "
    line = f"  {tag} {item['id']}: {len(refs)} refs, {len(item['metrics'])} metrics" + (
        f", {risks} risks" if risks else ""
    )
    return line, problems


async def _analysis_report(
    factory: SessionFactory, scope: WorkspaceScope, fixture: Fixture, analysis: dict[str, Any]
) -> tuple[str, list[str]]:
    problems: list[str] = []
    summary = analysis.get("summary_status", "absent")
    interpretation = analysis.get("interpretation_status", "absent")
    if analysis["status"] != "computed":
        problems.append(f"      {analysis['status']}")
        spec = fixture.analysis(analysis["id"])
        if spec is not None:
            async with scoped_session(factory, scope) as session:
                run = await run_parts(session, scope, get_settings(), spec)
            problems += [f"      got {row.group} = {row.value}" for row in run.rows]
    if fixture.schema_version >= 2 and summary != "verified":
        problems.append(f"      summary {summary}: every number must be a computed figure")
    if interpretation == "unverified":
        problems.append("      interpretation unverified: every number must be a computed figure")
    tag = "FAIL" if problems else "ok  "
    line = f"  {tag} {analysis['id']}: {analysis['status']}, summary {summary}"
    return f"{line}, interpretation {interpretation}", problems


def _load(args: argparse.Namespace) -> Fixture:
    if args.fixture is None:
        fixture = load_fixture(args.workspace)
        if fixture is None:
            raise SystemExit(f"no fixture for {args.workspace}")
        return fixture
    path = Path(args.fixture).resolve()
    try:
        return parse_fixture(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, FixtureError) as exc:
        raise SystemExit(f"{path.name}: invalid fixture: {exc}") from exc


async def main(args: argparse.Namespace) -> int:
    fixture = _load(args)
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    lines: list[str] = []
    failed = False
    try:
        scope = await _scope(factory, fixture.workspace)
        async with scoped_session(factory, scope) as session:
            before = (await session.execute(text(_COUNT), {"ws": scope.workspace_id})).scalar_one()
            bundle = await build_bundle(session, scope, settings, fixture)
            after = (await session.execute(text(_COUNT), {"ws": scope.workspace_id})).scalar_one()
            await session.rollback()
        for heading, items in (
            ("signals", bundle.brief["signals"]),
            ("opportunities", bundle.brief["opportunities"]),
        ):
            lines.append(heading)
            for item in items:
                line, problems = _item_report(item)
                lines += [line, *problems]
                failed |= bool(problems)
        lines.append("analyses")
        for analysis in bundle.analyses["analyses"]:
            line, problems = await _analysis_report(factory, scope, fixture, analysis)
            lines += [line, *problems]
            failed |= bool(problems)
        if before != after:
            lines.append(f"FAIL analytics_results changed: {before} -> {after}")
            failed = True
        if bundle.brief["corpus_check"]["status"] != "ok":
            drifted = bundle.brief["corpus_check"]["drifted_sources"]
            lines.append(f"FAIL corpus drift: {drifted}")
            failed = True
    finally:
        await engine.dispose()
    print(
        f"{fixture.fixture_version} (schema v{fixture.schema_version}): "
        f"{len(fixture.signals)} signals, {len(fixture.opportunities)} opportunities, "
        f"{len(fixture.analyses)} analyses, {len(fixture.all_evidence())} evidence references"
    )
    print("\n".join(lines))
    if failed:
        print("FAILED")
        return 1
    print("OK: every passage verified, every analysis computed, no rows written")
    return 0


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", help="verify this fixture file (e.g. a draft) instead")
    parser.add_argument("--workspace", default=WORKSPACE, help="workspace of the committed brief")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_args())))
