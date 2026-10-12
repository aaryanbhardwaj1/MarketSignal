"""Curated analyst brief (final productization phase): key signals, growth opportunities and
named analyses from a versioned fixture, re-resolved against current evidence and recomputed
deterministically on every request. Read-only; never persists analytics results.

* ``GET /api/workspaces/{ws}/insights``                    -> ``InsightsBrief``
* ``GET /api/workspaces/{ws}/analytics/analyses``          -> ``AnalysesResponse``
* ``GET /api/workspaces/{ws}/analytics/analyses/{id}``     -> ``Analysis`` (404 ANALYSIS_NOT_FOUND)

A workspace without a fixture gets an empty brief (``fixture_version: null``).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from marketsignal.api.deps import Factory, Scope, SettingsDep
from marketsignal.api.errors import AppError
from marketsignal.db.session import scoped_session
from marketsignal.insights.fixture import FixtureLoader, load_fixture
from marketsignal.insights.service import Bundle, build_bundle, empty_analyses, empty_brief

router = APIRouter(prefix="/api/workspaces/{ws}", tags=["insights"])


def get_fixture_loader() -> FixtureLoader:
    """Overridable in tests (``app.dependency_overrides``) to inject a synthetic fixture."""
    return load_fixture


Loader = Annotated[FixtureLoader, Depends(get_fixture_loader)]


async def _bundle(
    scope: Scope, factory: Factory, settings: SettingsDep, loader: Loader
) -> Bundle | None:
    fixture = loader(scope.workspace_code)
    if fixture is None:
        return None
    async with scoped_session(factory, scope) as session:
        return await build_bundle(session, scope, settings, fixture)


@router.get("/insights")
async def get_insights(
    scope: Scope, factory: Factory, settings: SettingsDep, loader: Loader
) -> dict[str, Any]:
    bundle = await _bundle(scope, factory, settings, loader)
    return empty_brief() if bundle is None else bundle.brief


@router.get("/analytics/analyses")
async def list_analyses(
    scope: Scope, factory: Factory, settings: SettingsDep, loader: Loader
) -> dict[str, Any]:
    bundle = await _bundle(scope, factory, settings, loader)
    return empty_analyses() if bundle is None else bundle.analyses


@router.get("/analytics/analyses/{analysis_id}")
async def get_analysis(
    analysis_id: str, scope: Scope, factory: Factory, settings: SettingsDep, loader: Loader
) -> dict[str, Any]:
    bundle = await _bundle(scope, factory, settings, loader)
    items: list[dict[str, Any]] = [] if bundle is None else bundle.analyses["analyses"]
    found = next((a for a in items if a["id"] == analysis_id), None)
    if found is None:
        raise AppError(404, "ANALYSIS_NOT_FOUND", "analysis not found")
    return found
