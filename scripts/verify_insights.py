"""Dev-DB acceptance for the curated analyst brief (plan §5.4).

Resolves the committed NORTHSTAR fixture against the seeded database, exactly as
``GET /api/workspaces/NORTHSTAR/insights`` does, and exits non-zero unless every quoted passage
is ``verified``, every named analysis is ``computed`` and every brief item rolls up to
``verified``. It is read-only: it uses the application role under the workspace scope, never
commits, and checks that the ``analytics_results`` row count is unchanged afterwards. No model
is called.

    uv --directory backend run python ../scripts/verify_insights.py
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from sqlalchemy import text

from marketsignal.config import get_settings
from marketsignal.db.engine import create_engine, create_session_factory
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session, unscoped_session
from marketsignal.insights.analyses import run_parts
from marketsignal.insights.fixture import Fixture, load_fixture
from marketsignal.insights.service import build_bundle

WORKSPACE = "NORTHSTAR"
_COUNT = "SELECT count(*) FROM analytics_results WHERE workspace_id = :ws"


async def _scope(factory: SessionFactory) -> WorkspaceScope:
    async with unscoped_session(factory) as session:
        row = (
            await session.execute(
                text("SELECT id, code FROM workspaces WHERE code = :c"), {"c": WORKSPACE}
            )
        ).one_or_none()
    if row is None:
        raise SystemExit(f"workspace {WORKSPACE} not found (seed the dev database first)")
    return WorkspaceScope(row[0], row[1])


def _evidence_failures(brief: dict[str, Any]) -> list[str]:
    out = []
    for item in [*brief["signals"], *brief["opportunities"]]:
        refs = item.get("evidence") or [*item["supporting"], *item["contradicting"]]
        out += [
            f"  {item['id']}: {r['integrity']} {r['handle']}"
            for r in refs
            if r["integrity"] != "verified"
        ]
        out += [
            f"  {item['id']}: metric withheld: {m['label']}"
            for m in item["metrics"]
            if m["value"] is None
        ]
        if item["integrity"] != "verified":
            out.append(f"  {item['id']}: item integrity {item['integrity']}")
    return out


async def _analysis_failures(
    factory: SessionFactory, scope: WorkspaceScope, fixture: Fixture, payload: dict[str, Any]
) -> list[str]:
    out = []
    settings = get_settings()
    for analysis in payload["analyses"]:
        if analysis["status"] == "computed":
            continue
        out.append(f"  {analysis['id']}: {analysis['status']}")
        spec = fixture.analysis(analysis["id"])
        if spec is None:
            continue
        async with scoped_session(factory, scope) as session:
            run = await run_parts(session, scope, settings, spec)
        for row in run.rows:
            out.append(f"      got {row.group} = {row.value}")
    return out


async def main() -> int:
    fixture = load_fixture(WORKSPACE)
    if fixture is None:
        print(f"no fixture for {WORKSPACE}")
        return 1
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        scope = await _scope(factory)
        async with scoped_session(factory, scope) as session:
            before = (await session.execute(text(_COUNT), {"ws": scope.workspace_id})).scalar_one()
            bundle = await build_bundle(session, scope, settings, fixture)
            after = (await session.execute(text(_COUNT), {"ws": scope.workspace_id})).scalar_one()
            await session.rollback()
        failures = _evidence_failures(bundle.brief)
        failures += await _analysis_failures(factory, scope, fixture, bundle.analyses)
        if before != after:
            failures.append(f"  analytics_results changed: {before} -> {after}")
        if bundle.brief["corpus_check"]["status"] != "ok":
            failures.append(f"  corpus drift: {bundle.brief['corpus_check']['drifted_sources']}")
    finally:
        await engine.dispose()
    refs = len(fixture.all_evidence())
    print(
        f"{fixture.fixture_version}: {len(fixture.signals)} signals, "
        f"{len(fixture.opportunities)} opportunities, {len(fixture.analyses)} analyses, "
        f"{refs} evidence references"
    )
    if failures:
        print("FAILED")
        print("\n".join(failures))
        return 1
    print("OK: every passage verified, every analysis computed, no rows written")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
