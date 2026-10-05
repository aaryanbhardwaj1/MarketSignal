import asyncio

import pytest

from marketsignal.health import (
    CheckResult,
    CheckStatus,
    Readiness,
    aggregate,
    check_redis,
    parse_version,
    run_check,
)

OK = CheckResult(CheckStatus.OK, "ok")


def test_all_ok_is_ready() -> None:
    assert aggregate({"database": OK, "redis": CheckResult(CheckStatus.OK, "", False)}) is (
        Readiness.READY
    )


def test_optional_failure_is_degraded_not_unready() -> None:
    redis_down = CheckResult(CheckStatus.DEGRADED, "down", required=False)
    assert aggregate({"database": OK, "redis": redis_down}) is Readiness.DEGRADED


def test_required_failure_is_not_ready() -> None:
    role_bad = CheckResult(CheckStatus.FAILED, "superuser")
    assert aggregate({"database": OK, "db_role": role_bad}) is Readiness.NOT_READY


@pytest.mark.parametrize(
    ("version", "minimum", "ok"),
    [("0.8.7", "0.8.0", True), ("0.8.0", "0.8.0", True), ("0.7.4", "0.8.0", False)],
)
def test_pgvector_version_comparison(version: str, minimum: str, ok: bool) -> None:
    assert (parse_version(version) >= parse_version(minimum)) is ok


async def test_run_check_converts_exceptions_to_failures() -> None:
    async def boom() -> CheckResult:
        raise ConnectionError("refused")

    name, result = await run_check("database", boom)
    assert name == "database"
    assert result.status is CheckStatus.FAILED
    assert "ConnectionError" in result.detail


async def test_optional_check_exception_degrades() -> None:
    async def boom() -> CheckResult:
        raise ConnectionError("refused")

    _, result = await run_check("redis", boom, required=False)
    assert result.status is CheckStatus.DEGRADED
    assert result.required is False


async def test_run_check_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("marketsignal.health.CHECK_TIMEOUT_S", 0.01)

    async def slow() -> CheckResult:
        await asyncio.sleep(1)
        return OK

    _, result = await run_check("database", slow)
    assert result.status is CheckStatus.FAILED
    assert "TimeoutError" in result.detail


async def test_missing_redis_is_degraded() -> None:
    result = await check_redis(None)
    assert result.status is CheckStatus.DEGRADED
    assert result.required is False
