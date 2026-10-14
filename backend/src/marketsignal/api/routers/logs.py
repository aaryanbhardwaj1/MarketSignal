"""Server log (developer tools): ``GET /api/dev/logs``.

Reads the API process's in-memory log ring buffer (``devtools.server_log``): sanitized
structured events (HTTP access, runs, tool calls, verification, warnings and errors). Entries
carry ids, enums, counts and durations only; never questions, answers, passages, tool
arguments, prompts, headers, query strings or credentials. The ingestion worker runs in its own
process, so its logs are not here (``scope: "api_process"``).

Mounted only when ``env != "prod"`` and ``dev_endpoints_enabled`` (like telemetry). Not
workspace-scoped: it is a process-level developer tool, never a product endpoint.
Shapes: ``frontend/src/lib/api/contracts.ts`` (E12).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from marketsignal.devtools.server_log import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Kind,
    Level,
    LogQuery,
    StatusClass,
    get_server_log,
    query_logs,
)

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.get("/logs")
async def get_logs(
    level: Level | None = None,
    kind: Kind | None = None,
    method: Annotated[str | None, Query(pattern=r"^[A-Za-z]{3,7}$")] = None,
    status_class: StatusClass | None = None,
    route: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    include_noise: bool = False,
    after_seq: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> dict[str, Any]:
    query = LogQuery(
        level=level,
        kind=kind,
        method=method.upper() if method else None,
        status_class=status_class,
        route=route,
        q=q.strip() or None if q else None,
        include_noise=include_noise,
        after_seq=after_seq,
        limit=limit,
    )
    return query_logs(get_server_log(), query)
