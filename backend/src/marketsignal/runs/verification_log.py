"""Per-attempt verification audit rows (``verification_attempts``, migration 0005; A6).

One row per verified synthesis attempt: the structured :class:`VerificationReport` (attempt
number, failure categories, rejected spans with their aliases, evidence checked, repairs,
regeneration requested, disposition). Reports hold only model answer spans, aliases and
canonical handles: no prompts, no hidden reasoning, no secrets. The table is append-only for
the runtime role; purge deletes the rows of runs whose pack included a purged source.

Disposition (DB CHECK): ``accepted`` (passed, nothing changed), ``repaired`` (passed after
repairs), ``regenerate`` (failed; one regeneration follows), ``rejected`` (failed; no time
left to regenerate, so the run falls back to evidence-only), ``fallback`` (the regenerated
attempt failed too; evidence-only answer).

Writing the audit row never fails the user's run: a database error is logged with the run id
and the run continues.
"""

from __future__ import annotations

import json
import uuid
from typing import Final

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.generation.types import VerificationReport
from marketsignal.telemetry.logging import get_logger

log = get_logger(__name__)

ACCEPTED: Final = "accepted"
REPAIRED: Final = "repaired"
REGENERATE: Final = "regenerate"
REJECTED: Final = "rejected"
FALLBACK: Final = "fallback"

_INSERT: Final = text(
    "INSERT INTO verification_attempts (workspace_id, query_run_id, attempt, disposition, report)"
    " VALUES (:ws, :run, :attempt, :disposition, CAST(:report AS jsonb))"
)


def disposition(report: VerificationReport, *, ok: bool, regenerate: bool, final: bool) -> str:
    """Disposition of one verified attempt (see module docstring)."""
    if ok:
        changed = report.repairs or report.numeric_violations or report.unknown_aliases
        return REPAIRED if changed or report.leaks_removed else ACCEPTED
    if regenerate:
        return REGENERATE
    return FALLBACK if final else REJECTED


async def record_attempt(
    factory: SessionFactory,
    scope: WorkspaceScope,
    run_id: uuid.UUID,
    report: VerificationReport,
) -> bool:
    """Insert one attempt row; returns False (and logs) if the database rejects it."""
    params = {
        "ws": scope.workspace_id,
        "run": run_id,
        "attempt": report.attempt,
        "disposition": report.disposition,
        "report": json.dumps(report.attempt_record(), sort_keys=True),
    }
    try:
        async with scoped_session(factory, scope) as session:
            await session.execute(_INSERT, params)
            await session.commit()
    except SQLAlchemyError as exc:
        log.warning(
            "verification_attempt_not_recorded",
            run_id=str(run_id),
            attempt=report.attempt,
            error=type(exc).__name__,
        )
        return False
    return True
