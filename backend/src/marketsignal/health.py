"""Liveness and readiness checks.

Readiness answers "can this process serve correct answers right now?":

* ``database``   - Postgres reachable.
* ``db_role``    - the runtime role is NOT superuser / BYPASSRLS (otherwise RLS is silently
                   bypassed and workspace isolation would be an illusion).
* ``migrations`` - schema is at the Alembic head this build expects.
* ``pgvector``   - the ``vector`` extension is installed at >= the minimum version
                   (iterative index scans need 0.8.0).
* ``redis``      - optional: failure marks the service *degraded*, never unready.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

CHECK_TIMEOUT_S = 3.0


class CheckStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class CheckResult:
    status: CheckStatus
    detail: str
    required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "detail": self.detail, "required": self.required}


class Readiness(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    NOT_READY = "not_ready"


def aggregate(results: Mapping[str, CheckResult]) -> Readiness:
    """Pure aggregation rule: any required failure => not ready; optional failure => degraded."""
    if any(r.required and r.status is not CheckStatus.OK for r in results.values()):
        return Readiness.NOT_READY
    if any(r.status is not CheckStatus.OK for r in results.values()):
        return Readiness.DEGRADED
    return Readiness.READY


def parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def expected_alembic_heads(alembic_ini: Path) -> set[str]:
    config = AlembicConfig(str(alembic_ini))
    config.set_main_option("script_location", str(alembic_ini.parent / "migrations"))
    return set(ScriptDirectory.from_config(config).get_heads())


async def role_is_privileged(engine: AsyncEngine) -> bool:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
        return bool(result.scalar_one())


async def check_database(engine: AsyncEngine) -> CheckResult:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return CheckResult(CheckStatus.OK, "reachable")


async def check_db_role(engine: AsyncEngine) -> CheckResult:
    if await role_is_privileged(engine):
        return CheckResult(
            CheckStatus.FAILED,
            "runtime role is superuser or BYPASSRLS; row-level security would be bypassed",
        )
    return CheckResult(CheckStatus.OK, "non-privileged application role")


async def check_migrations(engine: AsyncEngine, alembic_ini: Path) -> CheckResult:
    expected = expected_alembic_heads(alembic_ini)
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT version_num FROM alembic_version"))
        current = {row[0] for row in rows}
    if current == expected:
        return CheckResult(CheckStatus.OK, f"at head {sorted(current)}")
    return CheckResult(CheckStatus.FAILED, f"db at {sorted(current)}, expected {sorted(expected)}")


async def check_pgvector(engine: AsyncEngine, minimum: str) -> CheckResult:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
        version = result.scalar_one_or_none()
    if version is None:
        return CheckResult(CheckStatus.FAILED, "vector extension not installed")
    if parse_version(version) < parse_version(minimum):
        return CheckResult(CheckStatus.FAILED, f"pgvector {version} < required {minimum}")
    return CheckResult(CheckStatus.OK, f"pgvector {version}")


async def check_redis(redis: Any | None) -> CheckResult:
    if redis is None:
        return CheckResult(CheckStatus.DEGRADED, "redis not configured; cache bypassed", False)
    await redis.ping()
    return CheckResult(CheckStatus.OK, "reachable", False)


async def run_check(
    name: str, check: Callable[[], Awaitable[CheckResult]], *, required: bool = True
) -> tuple[str, CheckResult]:
    """Run one check with a timeout, converting any exception into a failed result."""
    try:
        return name, await asyncio.wait_for(check(), timeout=CHECK_TIMEOUT_S)
    except Exception as exc:  # readiness must report, never raise
        status = CheckStatus.FAILED if required else CheckStatus.DEGRADED
        return name, CheckResult(status, f"{type(exc).__name__}: {exc}"[:300], required)
