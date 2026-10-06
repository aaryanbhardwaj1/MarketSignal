"""The only SQL the analytics engine runs on data: one parameterized, RLS-scoped row fetch by
table id (column names never reach SQL) and the ``analytics_results`` insert."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.analytics.engine import Row
from marketsignal.tools.analytics_contracts import AnalyticsResult
from marketsignal.tools.env import ToolInputError

_ROWS = """
SELECT row_number, parent_handle, values FROM dataset_rows
WHERE workspace_id = :ws AND table_id = :t
ORDER BY row_number
LIMIT :limit
"""

_INSERT = """
INSERT INTO analytics_results
    (id, workspace_id, query_run_id, source_version_id, table_id, tool, spec, result)
VALUES (:id, :ws, :run, :v, :t, :tool, CAST(:spec AS jsonb), CAST(:result AS jsonb))
"""


class ScanLimitError(ToolInputError):
    """The dataset version has more rows than ``analytics_max_scan_rows``."""


async def fetch_rows(
    session: AsyncSession, workspace_id: uuid.UUID, table_id: uuid.UUID, max_rows: int
) -> list[Row]:
    rows = (
        await session.execute(
            text(_ROWS), {"ws": workspace_id, "t": table_id, "limit": max_rows + 1}
        )
    ).all()
    if len(rows) > max_rows:
        raise ScanLimitError(f"dataset exceeds the analytics scan limit ({max_rows} rows)")
    return [Row(int(r[0]), str(r[1]), _values(r[2])) for r in rows]


def _values(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw if isinstance(raw, dict) else {}


async def save_result(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID | None,
    source_version_id: uuid.UUID,
    table_id: uuid.UUID,
    result: AnalyticsResult,
) -> None:
    """Persist the exact JSON that is returned (``result_id`` included)."""
    await session.execute(
        text(_INSERT),
        {
            "id": uuid.UUID(result.result_id),
            "ws": workspace_id,
            "run": run_id,
            "v": source_version_id,
            "t": table_id,
            "tool": result.operation,
            "spec": json.dumps(result.spec),
            "result": json.dumps(result.model_dump(mode="json")),
        },
    )
