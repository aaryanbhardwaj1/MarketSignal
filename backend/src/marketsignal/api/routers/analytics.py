"""Analytics browsing (final productization phase): datasets and persisted computed results.

Read-only, workspace-scoped (forced RLS). Owned by the core-API workstream.

* ``GET /datasets`` and ``/datasets/{dataset_id}`` reuse the analytics engine's dataset lookup
  (``analytics.schema.find_datasets``): only the active, ready version of each non-deleted source
  is analysable, so purged and superseded versions never appear. Every confidentiality level is
  listed, as the sources list already does.
* ``GET /results`` lists persisted ``analytics_results`` (summary only; the full record stays at
  ``/results/{id}``), newest first, keyset-paged on ``created_at, id``. Results of test-harness
  runs are hidden unless ``include_test_runs``.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import ValidationError
from sqlalchemy import text

from marketsignal.analytics.schema import MAX_DATASETS, find_datasets, parse_dataset_id
from marketsignal.api.deps import Factory, Scope
from marketsignal.api.errors import AppError
from marketsignal.api.routers.runs import decode_cursor, encode_cursor
from marketsignal.db.session import scoped_session
from marketsignal.domain.enums import Confidentiality
from marketsignal.generation.results import build_result_item
from marketsignal.retrieval.types import allowed_confidentiality
from marketsignal.tools.analytics_contracts import AnalyticsResult

router = APIRouter(prefix="/api/workspaces/{ws}/analytics", tags=["analytics"])

ALL_CONFIDENTIALITY = allowed_confidentiality(Confidentiality.RESTRICTED)
MAX_DATASET_ID = 80
# Same rule as runs.NOT_TEST_RUN_SQL, on the joined run ``r`` (a result without a run is kept).
_NOT_TEST_RUN_R = "coalesce(r.models->>'synthesis', '') <> 'fake-llm'"


@router.get("/datasets")
async def list_datasets(scope: Scope, factory: Factory) -> dict[str, Any]:
    async with scoped_session(factory, scope) as session:
        refs = await find_datasets(
            session,
            scope.workspace_id,
            confidentiality=ALL_CONFIDENTIALITY,
            classes=[],
            limit=MAX_DATASETS + 1,
        )
    return {
        "datasets": [r.info(with_columns=False).model_dump() for r in refs[:MAX_DATASETS]],
        "truncated": len(refs) > MAX_DATASETS,
    }


@router.get("/datasets/{dataset_id}")
async def get_dataset(scope: Scope, factory: Factory, dataset_id: str) -> dict[str, Any]:
    if len(dataset_id) > MAX_DATASET_ID or parse_dataset_id(dataset_id) is None:
        raise AppError(404, "DATASET_NOT_FOUND", "dataset not found")
    async with scoped_session(factory, scope) as session:
        refs = await find_datasets(
            session,
            scope.workspace_id,
            confidentiality=ALL_CONFIDENTIALITY,
            classes=[],
            dataset=dataset_id,
            limit=1,
        )
    if not refs:
        raise AppError(404, "DATASET_NOT_FOUND", "dataset not found")
    return refs[0].info(with_columns=True).model_dump()


_RESULTS = f"""
SELECT a.id, a.tool, a.query_run_id, a.created_at, a.spec, a.result, r.conversation_id
FROM analytics_results a
LEFT JOIN query_runs r ON r.workspace_id = a.workspace_id AND r.id = a.query_run_id
WHERE a.workspace_id = :ws
  AND (CAST(:include_test AS boolean) OR r.id IS NULL OR {_NOT_TEST_RUN_R})
  AND (CAST(:tool AS text) IS NULL OR a.tool = CAST(:tool AS text))
  AND (CAST(:run_id AS uuid) IS NULL OR a.query_run_id = CAST(:run_id AS uuid))
  AND (CAST(:c_at AS timestamptz) IS NULL
       OR (a.created_at, a.id) < (CAST(:c_at AS timestamptz), CAST(:c_id AS uuid)))
ORDER BY a.created_at DESC, a.id DESC
LIMIT :limit
"""  # noqa: S608 - interpolates only the _NOT_TEST_RUN_R constant


def _metric_keys(spec: Any) -> list[str]:
    metrics = spec.get("metrics") if isinstance(spec, dict) else None
    keys = [m.get("key") for m in metrics or [] if isinstance(m, dict)]
    return [str(k) for k in keys if k]


def _summary(result: Any) -> str | None:
    """The deterministic one-line summary used for result citations (None if unparseable)."""
    try:
        return build_result_item("R1", AnalyticsResult.model_validate(result)).summary
    except (ValidationError, ValueError, TypeError):
        return None


def _result_item(row: Any) -> dict[str, Any]:
    result = row.result if isinstance(row.result, dict) else {}
    return {
        "result_id": str(row.id),
        "tool": row.tool,
        "dataset": str(result.get("dataset", "")),
        "source_code": str(result.get("source_code", "")),
        "source_version": int(result.get("source_version") or 0),
        "summary": _summary(result),
        "metrics": _metric_keys(row.spec),
        "query_run_id": str(row.query_run_id) if row.query_run_id else None,
        "conversation_id": str(row.conversation_id) if row.conversation_id else None,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/results")
async def list_results(
    scope: Scope,
    factory: Factory,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    tool: Literal["aggregate", "filter_rows", "group_compare"] | None = None,
    run_id: uuid.UUID | None = None,
    include_test_runs: bool = False,
) -> dict[str, Any]:
    after = decode_cursor(cursor)
    params = {
        "ws": scope.workspace_id,
        "include_test": include_test_runs,
        "tool": tool,
        "run_id": run_id,
        "c_at": after[0] if after else None,
        "c_id": after[1] if after else None,
        "limit": limit + 1,
    }
    async with scoped_session(factory, scope) as session:
        rows = (await session.execute(text(_RESULTS), params)).all()
    page = rows[:limit]
    next_cursor = (
        encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit and page else None
    )
    return {"items": [_result_item(r) for r in page], "next_cursor": next_cursor}
