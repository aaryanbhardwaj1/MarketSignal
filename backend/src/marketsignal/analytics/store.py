"""The only SQL the analytics engine runs on data: one parameterized, RLS-scoped row fetch by
table id (column names never reach SQL) and the ``analytics_results`` insert.

Purge ordering (:func:`lock_live_version`): in the insert's transaction, the source row is
locked ``FOR SHARE`` (``purge_source`` takes ``FOR UPDATE`` on it first), then the version's
status is re-read in a new statement (a fresh READ COMMITTED snapshot, taken after any lock
wait). Either the purge waits for this insert to commit and then sees the result (its
``computed_runs`` capture and the cascade delete cover it), or this insert waits for the purge,
sees the version ``purged`` and stores nothing: the tool returns ``NOT_FOUND``, exactly as a
call made after the purge (the dataset is no longer analysable).
"""

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


_LOCK_SOURCE = """
SELECT id FROM sources WHERE workspace_id = :ws AND source_code = :code FOR SHARE
"""
_VERSION_STATUS = "SELECT status FROM source_versions WHERE id = :v"


async def lock_live_version(
    session: AsyncSession, workspace_id: uuid.UUID, source_code: str, source_version_id: uuid.UUID
) -> bool:
    """Lock the source row ``FOR SHARE`` and report whether the version is still unpurged.
    Must run in the transaction that inserts the result, right before the insert."""
    locked = (
        await session.execute(text(_LOCK_SOURCE), {"ws": workspace_id, "code": source_code})
    ).scalar_one_or_none()
    if locked is None:
        return False
    status = (
        await session.execute(text(_VERSION_STATUS), {"v": source_version_id})
    ).scalar_one_or_none()
    return status is not None and status != "purged"


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
