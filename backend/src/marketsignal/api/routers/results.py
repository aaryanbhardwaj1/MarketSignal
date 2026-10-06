"""Computed analytics results: ``GET /api/workspaces/{ws}/results/{result_id}`` (Phase 5).

A computed result is not text evidence: answers cite it as ``[[result:<id>]]`` and the client
renders it as a result card (metric, value, unit, denominator, filters, grouping, dataset and
source version, rounding) — distinct from an evidence citation. The row is read in the
workspace scope (forced RLS), so another workspace's id, an unknown id or a result deleted by a
purge all look the same: 404 RESULT_NOT_FOUND.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from marketsignal.api.deps import Factory, Scope
from marketsignal.api.errors import AppError
from marketsignal.db.session import scoped_session

router = APIRouter(prefix="/api/workspaces/{ws}/results", tags=["results"])


@router.get("/{result_id}")
async def get_result(scope: Scope, factory: Factory, result_id: uuid.UUID) -> dict[str, Any]:
    async with scoped_session(factory, scope) as session:
        row = (
            await session.execute(
                text(
                    "SELECT result, tool, query_run_id, created_at FROM analytics_results "
                    "WHERE workspace_id = :ws AND id = :id"
                ),
                {"ws": scope.workspace_id, "id": result_id},
            )
        ).one_or_none()
    if row is None:
        raise AppError(404, "RESULT_NOT_FOUND", "result not found")
    result, tool, run_id, created_at = row
    return {
        "kind": "result",
        "tool": tool,
        "query_run_id": str(run_id) if run_id else None,
        "created_at": created_at.isoformat(),
        "result": result,
    }
