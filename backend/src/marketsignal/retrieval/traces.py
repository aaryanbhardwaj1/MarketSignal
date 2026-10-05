"""Persist retrieval traces (``retrieval_traces``, migration 0003).

Written in its own short transaction after the retrieval read, so trace writes never hold locks
during retrieval and never touch source, version or chunk rows (no lock-order interaction with
ingestion activation or purge). A failed trace write is logged and swallowed: tracing must not
fail a query.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.retrieval.types import RetrievalResult
from marketsignal.telemetry.logging import get_logger

log = get_logger(__name__)
MAX_QUERY_CHARS = 4000


async def persist_trace(
    factory: SessionFactory,
    scope: WorkspaceScope,
    result: RetrievalResult,
    *,
    origin: str = "api",
    query_run_id: uuid.UUID | None = None,
    tool_run_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    trace = result.trace
    try:
        async with scoped_session(factory, scope) as session:
            trace_id = (
                await session.execute(
                    text(
                        "INSERT INTO retrieval_traces (workspace_id, query_run_id, tool_run_id, "
                        "origin, query, config_hash, corpus_version, result_handles, stages, "
                        "timings, flags) VALUES (:ws, :qr, :tr, :origin, :q, :ch, "
                        "(SELECT version FROM workspace_corpus_state WHERE workspace_id = :ws), "
                        ":handles, CAST(:stages AS jsonb), CAST(:timings AS jsonb), :flags) "
                        "RETURNING id"
                    ),
                    {
                        "ws": scope.workspace_id,
                        "qr": query_run_id,
                        "tr": tool_run_id,
                        "origin": origin,
                        "q": trace.query[:MAX_QUERY_CHARS],
                        "ch": trace.config_hash,
                        "handles": [p.handle for p in result.parents[:50]],
                        "stages": json.dumps(trace.stages, default=str),
                        "timings": json.dumps(trace.timings_ms),
                        "flags": list(trace.flags),
                    },
                )
            ).scalar_one()
            await session.commit()
    except Exception:
        log.exception("retrieval_trace_write_failed", workspace=scope.workspace_code)
        return None
    return uuid.UUID(str(trace_id))
