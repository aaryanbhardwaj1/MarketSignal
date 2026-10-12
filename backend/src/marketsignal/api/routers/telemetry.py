"""Run telemetry (final productization phase, developer tools): summary, runs and run detail
from persisted run records. Read-only, workspace-scoped; never exposes model reasoning or
answer content.

* ``GET /summary`` - ``TelemetrySummary`` (``since``, ``until``, ``mode``, ``include_test_runs``).
* ``GET /runs`` - a keyset page of ``TelemetryRunRow``, newest first, with filters.
* ``GET /runs/{run_id}`` - ``TelemetryRunDetail``; another workspace's run, an unknown id and a
  missing one all look the same: 404 ``RUN_NOT_FOUND``.

Mounted only when ``env != "prod"`` and ``dev_endpoints_enabled`` (like the evaluation router):
it returns raw tool arguments, route cues, model names, token usage and cost estimates, and no
role check exists yet (ADR-0014 principals), so it is a developer tool, not a product endpoint.

Test-harness runs (``fake-llm``) are excluded unless ``include_test_runs=true``; the run detail
serves any run of the workspace. Shapes: ``frontend/src/lib/api/contracts.ts`` (E10).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from marketsignal.api.deps import Factory, Scope
from marketsignal.api.errors import AppError
from marketsignal.db.session import scoped_session
from marketsignal.devtools.run_telemetry import (
    RunFilters,
    list_runs,
    run_detail,
    telemetry_summary,
)
from marketsignal.devtools.run_telemetry_view import decode_cursor

router = APIRouter(prefix="/api/workspaces/{ws}/telemetry", tags=["telemetry"])

Mode = Literal["standard", "research"]
DispositionQ = Literal["accepted", "repaired", "regenerate", "rejected", "fallback"]
ShortText = Annotated[str | None, Query(max_length=64)]


def _window(since: datetime | None, until: datetime | None) -> None:
    for name, value in (("since", since), ("until", until)):
        if value is not None and value.tzinfo is None:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "request validation failed",
                fields=[{"location": f"query.{name}", "message": "timezone offset required"}],
            )


@router.get("/summary")
async def get_summary(
    scope: Scope,
    factory: Factory,
    since: datetime | None = None,
    until: datetime | None = None,
    mode: Mode | None = None,
    include_test_runs: bool = False,
) -> dict[str, Any]:
    _window(since, until)
    filters = RunFilters(since=since, until=until, mode=mode, include_test_runs=include_test_runs)
    async with scoped_session(factory, scope) as session:
        return await telemetry_summary(session, scope, filters)


@router.get("/runs")
async def get_runs(
    scope: Scope,
    factory: Factory,
    mode: Mode | None = None,
    status: ShortText = None,
    termination_state: ShortText = None,
    degraded: bool | None = None,
    model: ShortText = None,
    disposition: DispositionQ | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    include_test_runs: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> dict[str, Any]:
    _window(since, until)
    position = None
    if cursor:
        try:
            position = decode_cursor(cursor)
        except ValueError:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "request validation failed",
                fields=[{"location": "query.cursor", "message": "invalid cursor"}],
            ) from None
    filters = RunFilters(
        since=since,
        until=until,
        mode=mode,
        include_test_runs=include_test_runs,
        status=status,
        termination_state=termination_state,
        degraded=degraded,
        model=model,
        disposition=disposition,
    )
    async with scoped_session(factory, scope) as session:
        return await list_runs(session, scope, filters, limit=limit, cursor=position)


@router.get("/runs/{run_id}")
async def get_run_detail(scope: Scope, factory: Factory, run_id: uuid.UUID) -> dict[str, Any]:
    async with scoped_session(factory, scope) as session:
        detail = await run_detail(session, scope, run_id)
    if detail is None:
        raise AppError(404, "RUN_NOT_FOUND", "run not found")
    return detail
