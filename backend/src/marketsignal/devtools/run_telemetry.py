# ruff: noqa: S608  (all SQL here is composed from module constants; user values are bound)
"""Run telemetry (developer tools): summary, run list and run detail from persisted run records.

Everything here is read-only SQL inside a workspace-scoped session (forced RLS) with an explicit
``workspace_id = :ws`` filter as defence in depth. The rules this module keeps:

* **Never fabricate.** A stage, usage counter or trace that was not recorded is ``null`` (or
  omitted) and is counted in ``n``/coverage, never zeroed. Percentiles are computed server-side
  with ``percentile_cont`` and always report ``n``.
* **Test-harness runs** (``models->>'synthesis' = 'fake-llm'``) are excluded unless
  ``include_test_runs`` is set; the summary reports how many were excluded.
* **Cost is an estimate**: persisted token usage (synthesis + research agent) priced at the list
  prices in ``run_telemetry_view``. Nothing about cost is persisted.
* **No content**: the timeline never carries token text, answer content, citation cards or draft
  text; verification summaries never carry rejected spans; the agent record is an allowlist (no
  model reasoning is stored anywhere, and none is returned).

Dynamic SQL is assembled only from the constants in this module; every user value is bound.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.db.scope import WorkspaceScope
from marketsignal.devtools.run_telemetry_view import (
    EventRow,
    agent_view,
    build_timeline,
    cost_estimate,
    encode_cursor,
    estimate_cost_usd,
    event_offset_ms,
    is_redacted_args,
    numeric_only,
    pct,
    route_view,
    verification_summary,
)

TEST_HARNESS_MODEL = "fake-llm"
TOP_FINAL_LIMIT = 10
STAGE_KEYS = ("retrieval", "agent", "pack", "synthesis", "verification", "first_token")
RETRIEVAL_TIMING_KEYS = (
    "embed_ms",
    "lexical_prep_ms",
    "lexical_ms",
    "dense_ms",
    "fusion_ms",
    "total_ms",
)
LANE_KEYS = ("lexical", "dense", "fused", "final")
TOOL_STATUSES = ("ok", "truncated", "error", "denied", "timeout")
TOKEN_KEYS = ("input", "output", "cache_read", "cache_write")
# usage key in query_runs.usage / agent.usage for each token kind
_USAGE_KEYS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_input_tokens",
    "cache_write": "cache_creation_input_tokens",
}

# ------------------------------------------------------------------------- SQL helpers


def num(column: str, key: str) -> str:
    """SQL for a numeric jsonb field as float8, NULL when absent or not a number (constants)."""
    return (
        f"(CASE WHEN jsonb_typeof({column}->'{key}') = 'number' "
        f"THEN ({column}->>'{key}')::float8 END)"
    )


def pct_sql(expr: str) -> str:
    """p50, p95 and n of ``expr`` (percentile_cont ignores NULLs; n counts non-NULL values)."""
    return (
        f"percentile_cont(0.5) WITHIN GROUP (ORDER BY {expr}), "
        f"percentile_cont(0.95) WITHIN GROUP (ORDER BY {expr}), count({expr})"
    )


# --------------------------------------------------------------------------- filters + SQL


@dataclass(frozen=True)
class RunFilters:
    since: datetime | None = None
    until: datetime | None = None
    mode: str | None = None
    include_test_runs: bool = False
    status: str | None = None
    termination_state: str | None = None
    degraded: bool | None = None
    model: str | None = None
    disposition: str | None = None


_AGENT_USAGE = "(r.agent->'usage')"
_NOT_TEST = f"coalesce(r.models->>'synthesis', '') <> '{TEST_HARNESS_MODEL}'"
_IS_TEST = f"coalesce(r.models->>'synthesis', '') = '{TEST_HARNESS_MODEL}'"
_FINAL_DISPOSITION = (
    "(SELECT va.disposition FROM verification_attempts va WHERE va.workspace_id = r.workspace_id "
    "AND va.query_run_id = r.id ORDER BY va.attempt DESC LIMIT 1)"
)
_HAS_ATTEMPT = (
    "EXISTS (SELECT 1 FROM verification_attempts va WHERE va.workspace_id = r.workspace_id "
    "AND va.query_run_id = r.id{extra})"
)
_REGENERATED = (
    f"({_HAS_ATTEMPT.format(extra=' AND va.attempt >= 2')} OR r.timings ? 'synthesis_ms_2')"
)
_FALLBACK = (
    f"({_HAS_ATTEMPT.format(extra=" AND va.disposition = 'fallback'")} "
    "OR 'CITATION_VERIFICATION_FAILED' = ANY(r.degradation_flags))"
)
_PLANNER_FALLBACK = (
    "(r.agent->>'stop_reason' IN ('planner_unavailable', 'no_successful_search') "
    "OR EXISTS (SELECT 1 FROM unnest(r.degradation_flags) f WHERE starts_with(f, 'PLANNER_')))"
)
_MODEL_CALLS = (
    f"(CASE WHEN r.usage ? 'llm_attempts' THEN {num('r.usage', 'llm_attempts')} "
    f"+ coalesce({num(_AGENT_USAGE, 'llm_attempts')}, 0) END)"
)
_HAS_USAGE = (
    "(r.usage ?| array['input_tokens', 'output_tokens'] "
    "OR coalesce(r.agent->'usage', '{}'::jsonb) ?| array['input_tokens', 'output_tokens'])"
)


def run_where(filters: RunFilters, ws: uuid.UUID) -> tuple[str, dict[str, Any]]:
    """WHERE clause over ``query_runs r`` (constant SQL fragments; values bound)."""
    clauses = ["r.workspace_id = :ws"]
    params: dict[str, Any] = {"ws": ws}
    equalities = (
        ("since", "r.created_at >= :since"),
        ("until", "r.created_at < :until"),
        ("mode", "r.mode = :mode"),
        ("status", "r.status = :status"),
        ("termination_state", "r.termination_state = :termination_state"),
        ("model", "r.models->>'synthesis' = :model"),
        ("disposition", f"{_FINAL_DISPOSITION} = :disposition"),
    )
    for name, clause in equalities:
        value = getattr(filters, name)
        if value is not None:
            clauses.append(clause)
            params[name] = value
    if filters.degraded is not None:
        op = ">" if filters.degraded else "="
        clauses.append(f"cardinality(r.degradation_flags) {op} 0")
    if not filters.include_test_runs:
        clauses.append(_NOT_TEST)
    return " AND ".join(clauses), params


_STAGE_SQL = {
    "retrieval": num("r.timings", "retrieval_ms"),
    "agent": num("r.timings", "agent_ms"),
    "pack": num("r.timings", "pack_ms"),
    # Attempt 1 plus any regeneration attempt; NULL when attempt 1 was not recorded.
    "synthesis": f"({num('r.timings', 'synthesis_ms_1')} "
    f"+ coalesce({num('r.timings', 'synthesis_ms_2')}, 0))",
    "verification": f"({num('r.timings', 'verify_ms_1')} "
    f"+ coalesce({num('r.timings', 'verify_ms_2')}, 0))",
    "first_token": num("r.timings", "first_token_ms"),  # from synthesis start
}


def _array_len(expr: str) -> str:
    return f"(CASE WHEN jsonb_typeof({expr}) = 'array' THEN jsonb_array_length({expr}) END)"


def _with_runs(where: str) -> str:
    return (
        "WITH runs AS (SELECT r.id, r.workspace_id, r.mode, r.status, r.termination_state, "
        "r.degradation_flags, r.timings, r.usage, r.agent, r.route, r.models, "
        "r.pack_handles, r.cited_handles, r.error_class "
        f"FROM query_runs r WHERE {where}) "
    )


def _tokens(row: Sequence[Any], offset: int) -> dict[str, int]:
    return {key: int(row[offset + i] or 0) for i, key in enumerate(TOKEN_KEYS)}


def _ratio(n: Any, total: int) -> float:
    return round(int(n or 0) / total, 4) if total else 0.0


def _mean(value: float, n: int) -> float | None:
    return round(value / n, 2) if n else None


async def _rows(session: AsyncSession, sql: str, params: Mapping[str, Any]) -> list[Any]:
    return list((await session.execute(text(sql), dict(params))).all())


# --- summary ---------------------------------------------------------------------------------


def _main_pass_sql() -> str:
    cols = [f"coalesce({num('r.usage', _USAGE_KEYS[k])}, 0)" for k in TOKEN_KEYS]
    cols += [f"coalesce({num(_AGENT_USAGE, _USAGE_KEYS[k])}, 0)" for k in TOKEN_KEYS]
    lateral = ", ".join(f"{col} AS v{i}" for i, col in enumerate(cols))
    return (
        "SELECT count(*), "
        f"count(*) FILTER (WHERE {_HAS_USAGE}), "
        f"{', '.join(f'sum(t.v{i})' for i in range(8))}, "
        "sum(t.calls), count(*) FILTER (WHERE NOT r.usage ? 'llm_attempts'), "
        "count(*) FILTER (WHERE r.route <> '{}'::jsonb), "
        "count(*) FILTER (WHERE r.agent <> '{}'::jsonb), "
        f"count(*) FILTER (WHERE {_HAS_ATTEMPT.format(extra='')}), "
        f"count(*) FILTER (WHERE {_REGENERATED}), "
        f"count(*) FILTER (WHERE {_FALLBACK}), "
        f"count(*) FILTER (WHERE {_PLANNER_FALLBACK}), "
        "count(*) FILTER (WHERE cardinality(r.degradation_flags) > 0) "
        f"FROM runs r CROSS JOIN LATERAL (SELECT {lateral}, {_MODEL_CALLS} AS calls) t"
    )


def _stages_sql() -> str:
    values = ", ".join(f"('{key}', {expr})" for key, expr in _STAGE_SQL.items())
    return (
        f"SELECT s.stage, {pct_sql('s.v')} FROM runs r "
        f"CROSS JOIN LATERAL (VALUES {values}) AS s(stage, v) GROUP BY s.stage"
    )


_TOOLS_SQL = (
    "SELECT t.tool, count(*), "
    + ", ".join(f"count(*) FILTER (WHERE t.status = '{s}')" for s in TOOL_STATUSES)
    + f", {pct_sql('t.duration_ms')}, "
    "count(*) FILTER (WHERE t.args = CAST('{\"redacted\": true}' AS jsonb)) "
    "FROM tool_runs t JOIN runs r ON r.id = t.query_run_id "
    "WHERE t.workspace_id = :ws GROUP BY t.tool ORDER BY 2 DESC, 1"
)
_FLAGS_SQL = (
    "SELECT f, count(*) FROM runs r, unnest(r.degradation_flags) AS f GROUP BY f ORDER BY 2 DESC, 1"
)
_ROUTES_SQL = (
    "SELECT r.route->>'reason', count(*) FROM runs r WHERE r.route ? 'reason' "
    "GROUP BY 1 ORDER BY 2 DESC, 1"
)
_DISPOSITIONS_SQL = (
    "SELECT va.disposition, va.attempt, count(*) FROM verification_attempts va "
    "JOIN runs r ON r.id = va.query_run_id WHERE va.workspace_id = :ws "
    "GROUP BY 1, 2 ORDER BY 2, 3 DESC, 1"
)
_CATEGORIES_SQL = (
    "SELECT c, count(*) FROM verification_attempts va JOIN runs r ON r.id = va.query_run_id "
    "CROSS JOIN LATERAL jsonb_array_elements_text(CASE WHEN "
    "jsonb_typeof(va.report->'failure_categories') = 'array' "
    "THEN va.report->'failure_categories' ELSE '[]'::jsonb END) AS c "
    "WHERE va.workspace_id = :ws GROUP BY c ORDER BY 2 DESC, 1"
)
_MESSAGES_SQL = (
    "SELECT count(*) FROM messages m JOIN runs r ON r.id = m.query_run_id "
    "WHERE m.workspace_id = :ws AND m.status = 'redacted'"
)
_TRACE_ROWS = (
    "SELECT "
    + ", ".join(f"{num('tr.timings', k)} AS {k}" for k in RETRIEVAL_TIMING_KEYS)
    + ", "
    + ", ".join(f"{_array_len(f"tr.stages->'{k}'")} AS n_{k}" for k in LANE_KEYS)
    + ", CASE WHEN jsonb_typeof(tr.stages->'query_embedding'->'cache_hit') = 'boolean' "
    "THEN (tr.stages->'query_embedding'->>'cache_hit')::boolean END AS hit "
    "FROM retrieval_traces tr JOIN runs r ON r.id = tr.query_run_id "
    "WHERE tr.workspace_id = :ws AND tr.origin = 'api'"
)
_RETRIEVAL_SQL = (
    "SELECT count(*), "
    + ", ".join(pct_sql(f"x.{k}") for k in RETRIEVAL_TIMING_KEYS)
    + ", "
    + ", ".join(pct_sql(f"x.n_{k}") for k in LANE_KEYS)
    + ", avg(CASE WHEN x.hit THEN 1.0 WHEN NOT x.hit THEN 0.0 END) "
    f"FROM ({_TRACE_ROWS}) AS x"
)
_BY_MODE_SQL = f"SELECT r.mode, {pct_sql(num('r.timings', 'total_ms'))} FROM runs r GROUP BY r.mode"
_COUNTS_SQL = "SELECT r.mode, r.status, r.termination_state, count(*) FROM runs r GROUP BY 1, 2, 3"
_ERRORS_SQL = (
    "SELECT r.error_class, count(*) FROM runs r WHERE r.status = 'failed' "
    "GROUP BY 1 ORDER BY 2 DESC, 1 NULLS LAST"
)
_PACK_SQL = (
    f"SELECT {pct_sql('cardinality(r.pack_handles)')}, {pct_sql('cardinality(r.cited_handles)')} "
    "FROM runs r"
)


def _bump(counter: dict[str, int], key: str | None, n: int) -> None:
    label = key if key is not None else "none"
    counter[label] = counter.get(label, 0) + n


def _run_counts(rows: Sequence[Any]) -> dict[str, Any]:
    by_mode: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_term: dict[str, int] = {}
    for mode, status, termination, n in rows:
        _bump(by_mode, mode, int(n))
        _bump(by_status, status, int(n))
        _bump(by_term, termination, int(n))
    total = sum(by_mode.values())
    return {
        "total": total,
        "by_mode": by_mode,
        "by_status": by_status,
        "by_termination_state": by_term,
    }


def _tool_section(rows: Sequence[Any], total_runs: int) -> tuple[dict[str, Any], dict[str, Any]]:
    by_tool = []
    status_mix = dict.fromkeys(TOOL_STATUSES, 0)
    redacted = 0
    for row in rows:
        tool, n, *statuses = row[:7]
        stats = dict(zip(TOOL_STATUSES, (int(s) for s in statuses), strict=True))
        for key, value in stats.items():
            status_mix[key] += value
        timing = pct(*row[7:10])
        redacted += int(row[10])
        by_tool.append(
            {"tool": tool, "n": int(n), **stats, "p50_ms": timing["p50"], "p95_ms": timing["p95"]}
        )
    total = sum(t["n"] for t in by_tool)
    tool_calls = {"total": total, "per_run_mean": _mean(total, total_runs), "by_tool": by_tool}
    governance = {"tool_status": status_mix, "redacted_tool_args": redacted}
    return tool_calls, governance


def _retrieval_section(row: Sequence[Any]) -> dict[str, Any]:
    values = list(row)
    n = int(values[0] or 0)
    cursor = 1
    timings: dict[str, Any] = {}
    for key in RETRIEVAL_TIMING_KEYS:
        timings[key] = pct(*values[cursor : cursor + 3])
        cursor += 3
    candidates: dict[str, Any] = {}
    for key in LANE_KEYS:
        candidates[key] = pct(*values[cursor : cursor + 3])
        cursor += 3
    hit_rate = values[cursor]
    return {
        "n": n,
        "timings": timings,
        "candidates": candidates,
        "embedding_cache_hit_rate": None if hit_rate is None else round(float(hit_rate), 4),
    }


def _pack_section(row: Sequence[Any]) -> dict[str, Any]:
    """Evidence pack size and cited-handle count per run (p50/p95/n)."""
    return {"size": pct(*row[0:3]), "cited": pct(*row[3:6])}


async def _test_runs_excluded(session: AsyncSession, filters: RunFilters, ws: uuid.UUID) -> int:
    if filters.include_test_runs:
        return 0
    where, params = run_where(
        RunFilters(
            since=filters.since, until=filters.until, mode=filters.mode, include_test_runs=True
        ),
        ws,
    )
    sql = f"SELECT count(*) FROM query_runs r WHERE {where} AND {_IS_TEST}"
    return int((await _rows(session, sql, params))[0][0])


async def telemetry_summary(
    session: AsyncSession, scope: WorkspaceScope, filters: RunFilters
) -> dict[str, Any]:
    """``TelemetrySummary`` over the runs matching ``since/until/mode/include_test_runs``."""
    base = RunFilters(
        since=filters.since,
        until=filters.until,
        mode=filters.mode,
        include_test_runs=filters.include_test_runs,
    )
    where, params = run_where(base, scope.workspace_id)
    cte = _with_runs(where)
    counts = _run_counts(await _rows(session, cte + _COUNTS_SQL, params))
    total = counts["total"]
    main = (await _rows(session, cte + _main_pass_sql(), params))[0]
    n_usage = int(main[1] or 0)
    synthesis, agent = _tokens(main, 2), _tokens(main, 6)
    totals = {k: synthesis[k] + agent[k] for k in TOKEN_KEYS}
    calls, missing = int(main[10] or 0), int(main[11] or 0)
    by_mode = {m: pct(*rest) for m, *rest in await _rows(session, cte + _BY_MODE_SQL, params)}
    stage_rows = {s: pct(*rest) for s, *rest in await _rows(session, cte + _stages_sql(), params)}
    stages = {key: stage_rows.get(key, pct(None, None, 0)) for key in STAGE_KEYS}
    tool_calls, governance = _tool_section(await _rows(session, cte + _TOOLS_SQL, params), total)
    redacted_messages = (await _rows(session, cte + _MESSAGES_SQL, params))[0][0]
    retrieval_row = (await _rows(session, cte + _RETRIEVAL_SQL, params))[0]
    return {
        "window": {
            "since": filters.since.isoformat() if filters.since else None,
            "until": filters.until.isoformat() if filters.until else None,
        },
        "runs": counts,
        "latency_ms": {"total_by_mode": by_mode, "stages": stages},
        "tokens": {
            **totals,
            "per_run_mean": {
                "input": _mean(totals["input"], n_usage),
                "output": _mean(totals["output"], n_usage),
            },
            "by_source": {"synthesis": synthesis, "agent": agent},
        },
        "model_calls": {
            "total": calls,
            "per_run_mean": _mean(calls, total - missing),
            "n_runs_missing": missing,
        },
        "tool_calls": tool_calls,
        "cost": cost_estimate(totals, n_usage),
        "rates": {
            "regeneration": _ratio(main[15], total),
            "verification_fallback": _ratio(main[16], total),
            "planner_fallback": _ratio(main[17], total),
            "degraded": _ratio(main[18], total),
            # additive (E12): outcome rates from the run status counts
            "success": _ratio(counts["by_status"].get("completed"), total),
            "failed": _ratio(counts["by_status"].get("failed"), total),
            "cancelled": _ratio(counts["by_status"].get("cancelled"), total),
        },
        "errors": [
            {"error_class": c, "n": int(n)}
            for c, n in await _rows(session, cte + _ERRORS_SQL, params)
        ],
        "evidence_pack": _pack_section((await _rows(session, cte + _PACK_SQL, params))[0]),
        "flags": [
            {"code": c, "n": int(n)} for c, n in await _rows(session, cte + _FLAGS_SQL, params)
        ],
        "route_reasons": [
            {"reason": r, "n": int(n)} for r, n in await _rows(session, cte + _ROUTES_SQL, params)
        ],
        "verification": {
            "dispositions": [
                {"disposition": d, "attempt": int(a), "n": int(n)}
                for d, a, n in await _rows(session, cte + _DISPOSITIONS_SQL, params)
            ],
            "failure_categories": [
                {"category": c, "n": int(n)}
                for c, n in await _rows(session, cte + _CATEGORIES_SQL, params)
            ],
        },
        "retrieval": _retrieval_section(retrieval_row),
        "governance": {**governance, "redacted_messages": int(redacted_messages or 0)},
        "coverage": {
            "runs_with_route": int(main[12] or 0),
            "runs_with_agent": int(main[13] or 0),
            "runs_with_verification": int(main[14] or 0),
        },
        "test_runs_excluded": await _test_runs_excluded(session, filters, scope.workspace_id),
    }


# --- run rows --------------------------------------------------------------------------------


def _row_sql() -> str:
    cols = [f"coalesce({num('r.usage', _USAGE_KEYS[k])}, 0)" for k in TOKEN_KEYS]
    cols += [f"coalesce({num(_AGENT_USAGE, _USAGE_KEYS[k])}, 0)" for k in TOKEN_KEYS]
    return (
        "SELECT r.id, r.conversation_id, r.created_at, r.original_query, r.mode, r.status, "
        "r.termination_state, r.degradation_flags, r.route->>'reason', r.route->>'task_type', "
        f"r.models->>'synthesis', {num('r.timings', 'total_ms')}, r.tool_calls, {_MODEL_CALLS}, "
        f"{', '.join(cols)}, {_HAS_USAGE}, cardinality(r.pack_handles), "
        f"cardinality(r.cited_handles), {_FINAL_DISPOSITION}, {_REGENERATED}, "
        "(SELECT count(*) FROM analytics_results ar WHERE ar.workspace_id = r.workspace_id "
        "AND ar.query_run_id = r.id) "
    )


def run_row(row: Sequence[Any]) -> dict[str, Any]:
    """``TelemetryRunRow`` from a :func:`_row_sql` row."""
    synthesis, agent = _tokens(row, 14), _tokens(row, 18)
    totals = {k: synthesis[k] + agent[k] for k in TOKEN_KEYS}
    total_ms, model_calls = row[11], row[13]
    return {
        "id": str(row[0]),
        "conversation_id": str(row[1]) if row[1] else None,
        "created_at": row[2].isoformat(),
        "question": row[3],
        "mode": row[4],
        "status": row[5],
        "termination_state": row[6],
        "flags": list(row[7] or []),
        "route_reason": row[8],
        "task_type": row[9],
        "model": row[10],
        "total_ms": None if total_ms is None else round(float(total_ms), 1),
        "tool_calls": int(row[12] or 0),
        "model_calls": None if model_calls is None else int(model_calls),
        "tokens_in": totals["input"],
        "tokens_out": totals["output"],
        "est_cost_usd": estimate_cost_usd(totals) if row[22] else None,
        "evidence_count": int(row[23] or 0),
        "cited_count": int(row[24] or 0),
        "verification_disposition": row[25],
        "regenerated": bool(row[26]),
        "result_count": int(row[27] or 0),
    }


async def list_runs(
    session: AsyncSession,
    scope: WorkspaceScope,
    filters: RunFilters,
    *,
    limit: int,
    cursor: tuple[datetime, uuid.UUID] | None,
) -> dict[str, Any]:
    """A keyset page of ``TelemetryRunRow``, newest first (``(created_at, id)`` descending)."""
    where, params = run_where(filters, scope.workspace_id)
    if cursor is not None:
        where += " AND (r.created_at, r.id) < (:c_at, :c_id)"
        params = {**params, "c_at": cursor[0], "c_id": cursor[1]}
    sql = (
        f"{_row_sql()} FROM query_runs r WHERE {where} "
        "ORDER BY r.created_at DESC, r.id DESC LIMIT :limit"
    )
    rows = await _rows(session, sql, {**params, "limit": limit + 1})
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1][2], page[-1][0]) if len(rows) > limit else None
    return {"items": [run_row(r) for r in page], "next_cursor": next_cursor}


# --- run detail ------------------------------------------------------------------------------

# Streaming and answer events are reduced in SQL so their text never leaves the database.
_EVENTS_SQL = (
    "SELECT e.seq, e.type, e.created_at, CASE "
    "WHEN e.type IN ('token', 'citation') "
    "THEN jsonb_build_object('ts', e.payload->'ts', 'attempt', e.payload->'attempt') "
    "WHEN e.type = 'final' THEN jsonb_build_object('ts', e.payload->'ts', "
    f"'citations', {_array_len("e.payload->'citations'")}, "
    "'passed', e.payload->'verification'->'passed') "
    "ELSE e.payload - 'run_id' END "
    "FROM run_events e WHERE e.workspace_id = :ws AND e.run_id = :id ORDER BY e.seq"
)
_TOOL_ROWS_SQL = (
    "SELECT step, call_index, tool, status, error_code, result_count, total_matches, truncated, "
    "warnings, duration_ms, transport, args FROM tool_runs "
    "WHERE workspace_id = :ws AND query_run_id = :id ORDER BY step, call_index, created_at"
)
_VERIFICATION_SQL = (
    "SELECT va.attempt, va.disposition, coalesce((va.report->>'passed')::boolean, false), "
    "va.report->'citations', CASE WHEN jsonb_typeof(va.report->'failure_categories') = 'array' "
    "THEN va.report->'failure_categories' ELSE '[]'::jsonb END, "
    f"coalesce({_array_len("va.report->'repairs'")}, 0), "
    # rejected entries keep reason, section and aliases only: never the rejected span text
    "(SELECT coalesce(jsonb_agg(jsonb_build_object('reason', x.e->'reason', "
    "'section', x.e->'section', 'aliases', x.e->'aliases') ORDER BY x.o), '[]'::jsonb) "
    "FROM jsonb_array_elements(CASE WHEN jsonb_typeof(va.report->'rejected') = 'array' "
    "THEN va.report->'rejected' ELSE '[]'::jsonb END) WITH ORDINALITY AS x(e, o)), "
    "CASE WHEN jsonb_typeof(va.report->'result_ids') = 'array' "
    "THEN va.report->'result_ids' ELSE '[]'::jsonb END "
    "FROM verification_attempts va WHERE va.workspace_id = :ws AND va.query_run_id = :id "
    "ORDER BY va.attempt"
)
# Traces average ~19 KB: lane sizes and the top of the final list are computed in SQL.
_RETRIEVAL_DETAIL_SQL = (
    "SELECT tr.timings, "
    + ", ".join(_array_len(f"tr.stages->'{k}'") for k in LANE_KEYS)
    + ", CASE WHEN jsonb_typeof(tr.stages->'query_embedding'->'cache_hit') = 'boolean' "
    "THEN (tr.stages->'query_embedding'->>'cache_hit')::boolean END, "
    "CASE WHEN jsonb_typeof(tr.stages->'active_versions') = 'number' "
    "THEN (tr.stages->>'active_versions')::int END, "
    "(SELECT coalesce(jsonb_agg(jsonb_build_object('rank', x.e->'rank', 'handle', x.e->'handle', "
    "'source', x.e->'source', 'lanes', x.e->'lanes', 'rrf', x.e->'rrf') ORDER BY x.o), "
    "'[]'::jsonb) FROM jsonb_array_elements(CASE WHEN jsonb_typeof(tr.stages->'final') = 'array' "
    "THEN tr.stages->'final' ELSE '[]'::jsonb END) WITH ORDINALITY AS x(e, o) "
    "WHERE x.o <= :top) "
    "FROM retrieval_traces tr WHERE tr.workspace_id = :ws AND tr.query_run_id = :id "
    "AND tr.origin = 'api' ORDER BY tr.created_at DESC LIMIT 1"
)
_RESULT_IDS_SQL = (
    "SELECT id FROM analytics_results WHERE workspace_id = :ws AND query_run_id = :id "
    "ORDER BY created_at, id"
)


def tool_call(row: Sequence[Any]) -> dict[str, Any]:
    step, call_index, tool, status, error_code, result_count, total_matches = row[:7]
    truncated, warnings, duration_ms, transport, args = row[7:]
    return {
        "step": int(step),
        "call_index": int(call_index),
        "tool": tool,
        "status": status,
        "error_code": error_code,
        "result_count": result_count,
        "total_matches": total_matches,
        "truncated": bool(truncated),
        "warnings": list(warnings or []),
        "duration_ms": None if duration_ms is None else round(float(duration_ms), 1),
        "transport": transport,
        "args": args,
        "redacted": is_redacted_args(args),
    }


def _final_entry(item: Mapping[str, Any]) -> dict[str, Any]:
    lanes = item.get("lanes")
    return {
        "rank": item.get("rank"),
        "handle": item.get("handle"),
        "source": item.get("source"),
        "lanes": dict(lanes) if isinstance(lanes, dict) else {},
        "rrf": item.get("rrf"),
    }


def retrieval_view(row: Sequence[Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    timings, *lanes = row[:5]
    hit, active_versions, top = row[5:]
    return {
        "timings": numeric_only(timings),
        "lanes": {key: int(n or 0) for key, n in zip(LANE_KEYS, lanes, strict=True)},
        "embedding_cache_hit": hit,
        "active_versions": int(active_versions or 0),
        "top_final": [_final_entry(item) for item in top or [] if isinstance(item, dict)],
    }


_DETAIL_SQL = (
    f"{_row_sql()}, r.timings, r.usage, r.route, r.models, r.agent "
    "FROM query_runs r WHERE r.workspace_id = :ws AND r.id = :id"
)


async def run_detail(
    session: AsyncSession, scope: WorkspaceScope, run_id: uuid.UUID
) -> dict[str, Any] | None:
    """``TelemetryRunDetail`` for one run, or ``None`` when it is not visible in the scope."""
    params = {"ws": scope.workspace_id, "id": run_id}
    rows = await _rows(session, _DETAIL_SQL, params)
    if not rows:
        return None
    row = rows[0]
    timings, usage, route, models, agent = row[28:]
    run_start: datetime = row[2]
    events = [
        EventRow(seq, kind, event_offset_ms(payload, created_at, run_start), payload)
        for seq, kind, created_at, payload in await _rows(session, _EVENTS_SQL, params)
    ]
    retrieval = await _rows(session, _RETRIEVAL_DETAIL_SQL, {**params, "top": TOP_FINAL_LIMIT})
    return {
        "run": {
            **run_row(row),
            "timings": numeric_only(timings),
            "usage": numeric_only(usage),
            "route": route_view(route),
            "models": {k: v for k, v in (models or {}).items() if isinstance(v, str)},
        },
        "agent": agent_view(agent),
        "timeline": build_timeline(events),
        "tools": [tool_call(r) for r in await _rows(session, _TOOL_ROWS_SQL, params)],
        "verification": [
            verification_summary(r) for r in await _rows(session, _VERIFICATION_SQL, params)
        ],
        "retrieval": retrieval_view(retrieval[0] if retrieval else None),
        "analytics_result_ids": [str(r[0]) for r in await _rows(session, _RESULT_IDS_SQL, params)],
    }
