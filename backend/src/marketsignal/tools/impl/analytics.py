"""The governed analytics tools: ``describe_dataset``, ``aggregate``, ``group_compare`` and
``filter_rows`` (plan §18; contract in ``tools/analytics_contracts.py``).

Each call runs in the claims-scoped (RLS, ``statement_timeout``) session the governor provides,
sees only analysable datasets (``analytics.schema``), validates against the stored profile
(``analytics.validate``), computes in Python (``analytics.engine``) within
``analytics_timeout_s`` and, for the three computing tools, persists the ``AnalyticsResult`` in
``analytics_results`` *before* returning it: the stored JSON and the returned JSON are equal.
The insert is ordered against a concurrent purge of the source (``analytics.store`` module
docstring): if the version was purged meanwhile, nothing is stored and the call is
``NOT_FOUND``.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable
from typing import Any

from marketsignal.analytics import engine
from marketsignal.analytics.rounding import ROUNDING
from marketsignal.analytics.schema import DatasetRef, find_datasets
from marketsignal.analytics.store import fetch_rows, lock_live_version, save_result
from marketsignal.analytics.validate import (
    AggregatePlan,
    FilterRowsPlan,
    GroupComparePlan,
    Limits,
    aggregate_plan,
    filter_rows_plan,
    group_compare_plan,
)
from marketsignal.db.session import scoped_session
from marketsignal.retrieval.types import allowed_confidentiality
from marketsignal.tools.analytics_contracts import (
    AggregateIn,
    AnalyticsOut,
    AnalyticsResult,
    DescribeDatasetIn,
    DescribeDatasetOut,
    FilterRowsIn,
    GroupCompareIn,
    ResultRow,
)
from marketsignal.tools.contracts import TRUNCATED
from marketsignal.tools.env import ToolEnv, ToolNotFoundError

MAX_DATASETS = 50
# below the governor's OUTPUT_MAX_CHARS: analytics outputs are bounded here, before persistence,
# so the governor never trims a result after it was stored
RESULT_MAX_CHARS = 30_000
Plan = AggregatePlan | GroupComparePlan | FilterRowsPlan


def _visibility(env: ToolEnv) -> dict[str, Any]:
    return {
        "confidentiality": allowed_confidentiality(env.max_confidentiality),
        "classes": sorted(env.ctx.source_classes),
    }


async def describe_dataset(env: ToolEnv, args: DescribeDatasetIn) -> DescribeDatasetOut:
    async with asyncio.timeout(env.settings.analytics_timeout_s):
        async with scoped_session(env.factory, env.scope) as session:
            refs = await find_datasets(
                session,
                env.scope.workspace_id,
                dataset=args.dataset,
                limit=MAX_DATASETS + 1,  # one extra row tells the governor to flag TRUNCATED
                **_visibility(env),
            )
    if args.dataset is not None:
        if not refs:
            raise ToolNotFoundError("unknown dataset (see describe_dataset)")
        return DescribeDatasetOut(datasets=[refs[0].info(with_columns=True)])
    return DescribeDatasetOut(datasets=[r.info(with_columns=False) for r in refs])


async def _compute(
    env: ToolEnv,
    dataset: str,
    build: Callable[[DatasetRef, Limits], Plan],
    run: Callable[..., engine.Computed],
    operation: str,
) -> AnalyticsOut:
    limits = Limits.from_settings(env.settings)
    deadline = time.monotonic() + limits.timeout_s
    async with asyncio.timeout(limits.timeout_s):
        async with scoped_session(env.factory, env.scope) as session:
            refs = await find_datasets(
                session, env.scope.workspace_id, dataset=dataset, limit=1, **_visibility(env)
            )
            if not refs:
                raise ToolNotFoundError("unknown dataset (see describe_dataset)")
            ref = refs[0]
            plan = build(ref, limits)
            rows = await fetch_rows(session, env.scope.workspace_id, ref.table_id, limits.scan_rows)
            computed = run(plan, rows, deadline=deadline)
            result = AnalyticsResult(
                result_id=str(uuid.uuid4()),
                workspace=env.scope.workspace_code,
                dataset=ref.dataset,
                source_code=ref.source_code,
                source_version=ref.source_version,
                table=ref.table,
                operation=operation,
                spec=plan.spec,
                rows=computed.rows,
                rows_scanned=computed.rows_scanned,
                rows_matched=computed.rows_matched,
                rounding=ROUNDING,
                difference=computed.difference,
                warnings=computed.warnings,
            )
            result = _bounded(result)
            if not await lock_live_version(
                session, env.scope.workspace_id, ref.source_code, ref.source_version_id
            ):
                raise ToolNotFoundError("unknown dataset (see describe_dataset)")
            await save_result(
                session,
                workspace_id=env.scope.workspace_id,
                run_id=None if env.ctx.run_id is None else uuid.UUID(env.ctx.run_id),
                source_version_id=ref.source_version_id,
                table_id=ref.table_id,
                result=result,
            )
            await session.commit()
    return AnalyticsOut(result=result, warnings=list(result.warnings))


async def aggregate(env: ToolEnv, args: AggregateIn) -> AnalyticsOut:
    return await _compute(
        env,
        args.dataset,
        lambda ref, lim: aggregate_plan(ref, args, lim),
        engine.aggregate,
        "aggregate",
    )


async def group_compare(env: ToolEnv, args: GroupCompareIn) -> AnalyticsOut:
    return await _compute(
        env,
        args.dataset,
        lambda ref, lim: group_compare_plan(ref, args, lim),
        engine.group_compare,
        "group_compare",
    )


async def filter_rows(env: ToolEnv, args: FilterRowsIn) -> AnalyticsOut:
    return await _compute(
        env,
        args.dataset,
        lambda ref, lim: filter_rows_plan(ref, args, lim),
        engine.filter_rows,
        "filter_rows",
    )


def _bounded(result: AnalyticsResult) -> AnalyticsResult:
    """Drop trailing rows until the serialized result fits ``RESULT_MAX_CHARS`` (+``TRUNCATED``)."""
    rows: list[ResultRow] = list(result.rows)
    current = result
    while rows and len(json.dumps(current.model_dump(mode="json"))) > RESULT_MAX_CHARS:
        rows = rows[:-1]
        warnings = [*(w for w in result.warnings if w != TRUNCATED), TRUNCATED]
        current = result.model_copy(update={"rows": rows, "warnings": warnings})
    return current
