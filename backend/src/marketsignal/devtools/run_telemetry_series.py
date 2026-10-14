# ruff: noqa: S608  (all SQL here is composed from module constants; user values are bound)
"""Run telemetry series (developer tools): one compact point per run, oldest first.

Feeds the Telemetry page's time-series charts. Same rules as ``run_telemetry``: read-only SQL in
a workspace-scoped session with an explicit ``workspace_id = :ws`` filter, test-harness runs
excluded unless asked for, and **never fabricated** values: a stage, total or usage that was
not recorded stays ``null``. Cost is an estimate from persisted usage (``estimate_cost_usd``).
When more than ``limit`` runs match, the most recent ``limit`` are returned (``truncated``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.db.scope import WorkspaceScope
from marketsignal.devtools.run_telemetry import (
    _AGENT_USAGE,
    _FINAL_DISPOSITION,
    _HAS_USAGE,
    _MODEL_CALLS,
    _REGENERATED,
    _STAGE_SQL,
    _USAGE_KEYS,
    STAGE_KEYS,
    TOKEN_KEYS,
    RunFilters,
    _rows,
    _test_runs_excluded,
    _tokens,
    num,
    run_where,
)
from marketsignal.devtools.run_telemetry_view import estimate_cost_usd

MAX_SERIES_LIMIT = 2000
DEFAULT_SERIES_LIMIT = 500

_TOKEN_COLS = [f"coalesce({num('r.usage', _USAGE_KEYS[k])}, 0)" for k in TOKEN_KEYS] + [
    f"coalesce({num(_AGENT_USAGE, _USAGE_KEYS[k])}, 0)" for k in TOKEN_KEYS
]
_POINT_COLUMNS = (
    "r.id, r.created_at, r.mode, r.status, r.termination_state, "
    "cardinality(r.degradation_flags) > 0, "
    f"{num('r.timings', 'total_ms')}, "
    + ", ".join(_STAGE_SQL[k] for k in STAGE_KEYS)
    + ", "
    + ", ".join(_TOKEN_COLS)
    + f", {_HAS_USAGE}, {_MODEL_CALLS}, r.tool_calls, cardinality(r.pack_handles), "
    f"cardinality(r.cited_handles), {_FINAL_DISPOSITION}, {_REGENERATED}"
)
_STAGES_AT = 7
_TOKENS_AT = _STAGES_AT + len(STAGE_KEYS)


def _ms(value: Any) -> float | None:
    return None if value is None else round(float(value), 1)


def series_point(row: Sequence[Any]) -> dict[str, Any]:
    """``TelemetrySeriesPoint`` from a :data:`_POINT_COLUMNS` row."""
    synthesis, agent = _tokens(row, _TOKENS_AT), _tokens(row, _TOKENS_AT + 4)
    totals = {k: synthesis[k] + agent[k] for k in TOKEN_KEYS}
    has_usage, model_calls, tool_calls, evidence, cited, disposition, regenerated = row[
        _TOKENS_AT + 8 :
    ]
    stages = row[_STAGES_AT:_TOKENS_AT]
    return {
        "id": str(row[0]),
        "created_at": row[1].isoformat(),
        "mode": row[2],
        "status": row[3],
        "termination_state": row[4],
        "degraded": bool(row[5]),
        "total_ms": _ms(row[6]),
        "stages": {k: _ms(v) for k, v in zip(STAGE_KEYS, stages, strict=True)},
        "tokens_in": totals["input"] if has_usage else None,
        "tokens_out": totals["output"] if has_usage else None,
        "est_cost_usd": estimate_cost_usd(totals) if has_usage else None,
        "model_calls": None if model_calls is None else int(model_calls),
        "tool_calls": int(tool_calls or 0),
        "evidence_count": int(evidence or 0),
        "cited_count": int(cited or 0),
        "disposition": disposition,
        "regenerated": bool(regenerated),
    }


async def telemetry_series(
    session: AsyncSession, scope: WorkspaceScope, filters: RunFilters, *, limit: int
) -> dict[str, Any]:
    """``TelemetrySeries`` over the runs matching ``since/until/mode/include_test_runs``."""
    base = RunFilters(
        since=filters.since,
        until=filters.until,
        mode=filters.mode,
        include_test_runs=filters.include_test_runs,
    )
    where, params = run_where(base, scope.workspace_id)
    sql = (
        f"SELECT * FROM (SELECT {_POINT_COLUMNS} FROM query_runs r WHERE {where} "
        "ORDER BY r.created_at DESC, r.id DESC LIMIT :limit) AS p ORDER BY 2, 1"
    )
    rows = await _rows(session, sql, {**params, "limit": limit + 1})
    truncated = len(rows) > limit
    kept = rows[1:] if truncated else rows  # ascending: the oldest row is the extra one
    return {
        "window": {
            "since": filters.since.isoformat() if filters.since else None,
            "until": filters.until.isoformat() if filters.until else None,
        },
        "points": [series_point(r) for r in kept],
        "n": len(kept),
        "truncated": truncated,
        "test_runs_excluded": await _test_runs_excluded(session, filters, scope.workspace_id),
    }
