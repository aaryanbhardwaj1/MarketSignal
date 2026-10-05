"""``/healthz`` (liveness) and ``/readyz`` (readiness) endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from marketsignal.config import Settings
from marketsignal.health import (
    Readiness,
    aggregate,
    check_database,
    check_db_role,
    check_migrations,
    check_pgvector,
    check_redis,
    run_check,
)

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up and the event loop responds. No dependencies checked."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    state = request.app.state
    settings: Settings = state.settings
    engine = state.engine
    results = dict(
        await asyncio.gather(
            run_check("database", lambda: check_database(engine)),
            run_check("db_role", lambda: check_db_role(engine)),
            run_check("migrations", lambda: check_migrations(engine, settings.alembic_ini_path)),
            run_check("pgvector", lambda: check_pgvector(engine, settings.min_pgvector_version)),
            run_check("redis", lambda: check_redis(state.redis), required=False),
        )
    )
    readiness = aggregate(results)
    checks: dict[str, Any] = {name: r.as_dict() for name, r in results.items()}
    if settings.env == "prod":  # never expose internal error text publicly
        for check in checks.values():
            check.pop("detail", None)
    status_code = 503 if readiness is Readiness.NOT_READY else 200
    return JSONResponse({"status": readiness.value, "checks": checks}, status_code=status_code)
