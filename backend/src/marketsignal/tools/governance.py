"""The governance pipeline (plan §17), implemented once and used by both transports.

Per call, in this order:

1. Verify the capability token -> ``ToolContext`` (any failure: ``UNAUTHENTICATED``).
2. Revocation: a token carrying a run id is honoured only while that run is ``running``
   (cancelled/done/missing: ``UNAUTHENTICATED`` - the token is revoked, not merely denied).
3. Policy: the tool must be in ``claims.tools`` (else ``POLICY_DENIED``); unknown tools are
   ``NOT_FOUND``.
4. Strict input validation against the closed contract model (JSON mode, no coercion); an
   extra field such as ``workspace_id`` is a ``VALIDATION_ERROR``.
5. Execute under ``asyncio.wait_for(settings.tool_timeout_s)`` in sessions scoped to the
   *claims'* workspace whose every transaction runs ``SET LOCAL statement_timeout``.
6. Cap the output (items, then serialized characters) and flag ``TRUNCATED``.
6b. Re-check revocation after the body: if the run stopped being ``running`` while the tool
   executed, the output is discarded and the call returns ``UNAUTHENTICATED``. That call *is*
   audited (status ``error``, code ``UNAUTHENTICATED``, no handles): it did read the workspace.
7. Normalize every failure to a contract code with a fixed, safe message.
8. Write a ``tool_runs`` audit row (sanitized arguments: every string truncated, control
   characters dropped; never credentials or document text). Calls that fail steps 1-2 have no
   trusted workspace and are not audited (logged only). An audit write failure fails the call
   closed (``INTERNAL``). The write is purge-safe: in the same transaction it takes
   ``FOR KEY SHARE`` on the run's ``query_runs`` row (the row a purge locks ``FOR UPDATE``) and,
   if any earlier audited call of the run or this call returned a handle whose version is now
   purged, stores ``{"redacted": true}`` instead of the arguments (model-written arguments can
   quote text the model already saw). Either the purge's redaction sees this row, or this
   write sees the purge.
9. Return ``ToolResult``: the typed output plus a bounded observation for the model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session

from marketsignal.config import Settings
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.retrieval.pipeline import RetrievalService
from marketsignal.retrieval.types import InvalidFiltersError
from marketsignal.runs.store import _lock_run_pack, _purged_pack_codes
from marketsignal.tools.capability import UnauthenticatedError, verify
from marketsignal.tools.contracts import (
    TRUNCATED,
    ErrorCode,
    ToolCall,
    ToolContext,
    ToolError,
    ToolResult,
    ToolSpec,
    Transport,
    has_control_chars,
)
from marketsignal.tools.env import ToolEnv, ToolInputError, ToolNotFoundError, scope_from
from marketsignal.tools.observation import error_observation, render
from marketsignal.tools.registry import OUTPUT_MAX_CHARS, ToolEntry, ToolRegistry, default_registry

log = logging.getLogger(__name__)

QUERY_AUDIT_CHARS = 200
REDACTED_ARGS: dict[str, Any] = {"redacted": True}
STATEMENT_TIMEOUT_KEY = "marketsignal.statement_timeout_ms"
MESSAGES: dict[str, str] = {
    "UNAUTHENTICATED": "tool credential rejected",
    "POLICY_DENIED": "tool not permitted for this run",
    "NOT_FOUND": "unknown tool",
    "TIMEOUT": "tool timed out",
    "UNAVAILABLE": "tool service unavailable",
    "INTERNAL": "internal tool error",
}
_AUDIT_STATUS = {"POLICY_DENIED": "denied", "TIMEOUT": "timeout"}


class _CallFailedError(Exception):
    def __init__(self, code: ErrorCode, message: str | None = None) -> None:
        super().__init__(code)
        self.code: ErrorCode = code
        self.message = message or MESSAGES[code]


# --- statement timeout -----------------------------------------------------------------------


class _TimedSession(Session):
    """Sessions for tool execution: every transaction gets a transaction-local timeout."""


def _apply_statement_timeout(session: Session, _tx: Any, connection: Any) -> None:
    ms = session.info.get(STATEMENT_TIMEOUT_KEY)
    if ms:
        connection.execute(
            text("SELECT set_config('statement_timeout', :ms, true)"), {"ms": f"{int(ms)}ms"}
        )


event.listen(_TimedSession, "after_begin", _apply_statement_timeout)


def timed_factory(factory: SessionFactory, statement_timeout_ms: int) -> SessionFactory:
    """The same engine/options as ``factory``, with ``SET LOCAL statement_timeout``."""
    kw = {k: v for k, v in factory.kw.items() if k not in ("sync_session_class", "info")}
    return async_sessionmaker(
        **kw,
        sync_session_class=_TimedSession,
        info={STATEMENT_TIMEOUT_KEY: statement_timeout_ms},
    )


# --- results ---------------------------------------------------------------------------------


def failure_result(
    call: ToolCall,
    code: ErrorCode,
    message: str | None = None,
    *,
    transport: Transport = "inprocess",
    duration_ms: float = 0.0,
) -> ToolResult:
    """The one way an error result is built (both transports use it, so they stay equal)."""
    text_ = message or MESSAGES[code]
    return ToolResult(
        call_id=call.call_id,
        name=call.name,
        ok=False,
        output=None,
        observation=error_observation(code, text_),
        error=ToolError(code, text_),
        duration_ms=duration_ms,
        transport=transport,
    )


def _validation_message(name: str, exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:6]:
        loc = ".".join(str(p)[:40] for p in err["loc"]) or "arguments"
        parts.append(f"{loc} ({err['type']})")
    return f"invalid arguments for {name[:64]}: " + "; ".join(parts)


def _unvalidated_args(arguments: Any) -> dict[str, Any]:
    """Audit shape for arguments that were never validated: key names only, bounded."""
    keys = arguments.keys() if isinstance(arguments, dict) else []
    return {"unvalidated_keys": sorted(str(k)[:40] for k in keys)[:10]}


def _bounded(value: Any) -> Any:
    if isinstance(value, str):
        if has_control_chars(value):
            value = "".join(ch for ch in value if not has_control_chars(ch))
        return value[:QUERY_AUDIT_CHARS]
    if isinstance(value, list):
        return [_bounded(v) for v in value]
    if isinstance(value, dict):
        return {str(k)[:40]: _bounded(v) for k, v in value.items()}
    return value


def sanitize_args(args: BaseModel) -> dict[str, Any]:
    """The audit/trace form of validated arguments: every string (list items included) is
    truncated to ``QUERY_AUDIT_CHARS`` and stripped of control characters (never a NUL)."""
    dumped: dict[str, Any] = _bounded(args.model_dump(mode="json", exclude_none=True))
    return dumped


def cap_output(entry: ToolEntry, output: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return a new output capped to ``entry.max_items`` items and ``OUTPUT_MAX_CHARS``.
    Outputs whose ``items_key`` is not a list (analytics: one persisted ``result``) are bounded
    by their implementation before persistence and are returned unchanged."""
    truncated = TRUNCATED in (output.get("warnings") or [])
    if entry.items_key in output and not isinstance(output[entry.items_key], list):
        return output, truncated
    items = list(output.get(entry.items_key) or [])
    if len(items) > entry.max_items:
        items, truncated = items[: entry.max_items], True
    capped = {**output, entry.items_key: items}
    while items and len(json.dumps(capped, default=str)) > OUTPUT_MAX_CHARS:
        items, truncated = items[:-1], True
        capped = {**capped, entry.items_key: items}
    if truncated:
        warnings = [w for w in capped.get("warnings") or [] if w != TRUNCATED]
        capped = {**capped, "warnings": [*warnings, TRUNCATED]}
    return capped, truncated


# --- governor --------------------------------------------------------------------------------


class ToolGovernor:
    """Runs one governed call. Never raises for auth/policy/validation/tool failures."""

    def __init__(
        self,
        *,
        factory: SessionFactory,
        settings: Settings,
        retrieval: RetrievalService,
        registry: ToolRegistry | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._factory = factory
        self._timed = timed_factory(factory, settings.tool_statement_timeout_ms)
        self._settings = settings
        self._retrieval = retrieval
        self.registry = registry or default_registry()
        self._clock = clock

    def specs(self) -> list[ToolSpec]:
        return self.registry.specs()

    def authenticate(self, credential: str) -> ToolContext:
        """Signature and claims only (no database)."""
        return verify(self._settings.mcp_token_key, credential)

    async def authenticate_live(self, credential: str) -> ToolContext:
        """Signature, claims and revocation (the HTTP bearer check: a revoked run's token
        gets 401 at the edge, for ``tools/list`` too). A database failure during the revocation
        lookup also raises ``UnauthenticatedError`` (fail closed)."""
        ctx = self.authenticate(credential)
        try:
            await self._check_not_revoked(ctx)
        except _CallFailedError:
            raise UnauthenticatedError() from None
        return ctx

    async def execute(
        self,
        call: ToolCall,
        *,
        credential: str,
        transport: Transport,
    ) -> ToolResult:
        start = self._clock()

        def elapsed() -> float:
            return round((self._clock() - start) * 1000, 3)

        try:
            ctx = self.authenticate(credential)
            await self._check_not_revoked(ctx)
        except UnauthenticatedError:
            log.info("tool call rejected: tool=%s code=UNAUTHENTICATED", call.name[:64])
            return failure_result(call, "UNAUTHENTICATED", transport=transport)
        except _CallFailedError as exc:
            log.warning("tool revocation check failed: code=%s", exc.code)
            return failure_result(call, exc.code, transport=transport)

        audit_args: dict[str, Any] = _unvalidated_args(call.arguments)
        try:
            entry, args = self._admit(call, ctx)
            audit_args = sanitize_args(args)
            output, truncated = await self._run(entry, args, ctx)
            await self._check_still_running(ctx)
        except _CallFailedError as exc:
            result = failure_result(
                call, exc.code, exc.message, transport=transport, duration_ms=elapsed()
            )
            return await self._audited(call, ctx, result, audit_args)
        observation = render(entry.name, output, self._settings.obs_max_tokens)
        result = ToolResult(
            call_id=call.call_id,
            name=call.name,
            ok=True,
            output=output,
            observation=observation,
            truncated=truncated,
            warnings=tuple(output.get("warnings") or ()),
            duration_ms=elapsed(),
            transport=transport,
        )
        return await self._audited(call, ctx, result, audit_args)

    # -- steps --

    async def _check_not_revoked(self, ctx: ToolContext) -> None:
        if ctx.run_id is None:
            return
        try:
            async with scoped_session(self._timed, scope_from(ctx)) as session:
                status = (
                    await session.execute(
                        text("SELECT status FROM query_runs WHERE workspace_id = :ws AND id = :id"),
                        {"ws": uuid.UUID(ctx.workspace_id), "id": uuid.UUID(ctx.run_id)},
                    )
                ).scalar_one_or_none()
        except SQLAlchemyError:
            raise _CallFailedError("UNAVAILABLE") from None
        if status != "running":
            raise UnauthenticatedError()

    async def _check_still_running(self, ctx: ToolContext) -> None:
        """Step 6b: the run may have been cancelled/finished while the body ran."""
        try:
            await self._check_not_revoked(ctx)
        except UnauthenticatedError:
            log.info("tool output discarded: run no longer running")
            raise _CallFailedError("UNAUTHENTICATED") from None

    def _admit(self, call: ToolCall, ctx: ToolContext) -> tuple[ToolEntry, BaseModel]:
        if call.name not in ctx.tools:
            raise _CallFailedError("POLICY_DENIED")
        entry = self.registry.get(call.name)
        if entry is None:
            raise _CallFailedError("NOT_FOUND")
        try:
            payload = json.dumps(call.arguments if isinstance(call.arguments, dict) else None)
            args = entry.input_model.model_validate_json(payload, strict=True)
        except (ValidationError, TypeError, ValueError) as exc:
            message = (
                _validation_message(call.name, exc)
                if isinstance(exc, ValidationError)
                else f"invalid arguments for {call.name[:64]}"
            )
            raise _CallFailedError("VALIDATION_ERROR", message) from None
        return entry, args

    async def _run(
        self, entry: ToolEntry, args: BaseModel, ctx: ToolContext
    ) -> tuple[dict[str, Any], bool]:
        env = ToolEnv(ctx, scope_from(ctx), self._timed, self._retrieval, self._settings)
        try:
            out = await asyncio.wait_for(entry.impl(env, args), self._settings.tool_timeout_s)
            dumped = entry.output_model.model_validate(out.model_dump()).model_dump(mode="json")
        except TimeoutError:
            raise _CallFailedError("TIMEOUT") from None
        except ToolNotFoundError as exc:
            raise _CallFailedError("NOT_FOUND", f"not found: {str(exc)[:200]}") from None
        except (ToolInputError, InvalidFiltersError) as exc:
            message = f"invalid arguments: {str(exc)[:200]}"
            raise _CallFailedError("VALIDATION_ERROR", message) from None
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "57014" or "statement timeout" in str(
                exc.orig
            ):
                raise _CallFailedError("TIMEOUT") from None
            log.warning("tool %s database error: %s", entry.name, type(exc.orig).__name__)
            code: ErrorCode = "UNAVAILABLE" if isinstance(exc, OperationalError) else "INTERNAL"
            raise _CallFailedError(code) from None
        except (SQLAlchemyError, OSError, ConnectionError):
            log.warning("tool %s unavailable", entry.name)
            raise _CallFailedError("UNAVAILABLE") from None
        except Exception as exc:
            log.error("tool %s failed: %s", entry.name, type(exc).__name__)
            raise _CallFailedError("INTERNAL") from None
        return cap_output(entry, dumped)

    async def _audited(
        self, call: ToolCall, ctx: ToolContext, result: ToolResult, args: dict[str, Any]
    ) -> ToolResult:
        code = result.error.code if result.error else None
        status = (
            ("truncated" if result.truncated else "ok")
            if result.ok
            else _AUDIT_STATUS.get(code or "", "error")
        )
        output = result.output or {}
        count = len(output.get("hits") or output.get("items") or output.get("sources") or [])
        try:
            async with scoped_session(self._factory, scope_from(ctx)) as session:
                if await self._purge_redacts(session, ctx, result):
                    args = REDACTED_ARGS
                await session.execute(
                    text(
                        "INSERT INTO tool_runs (workspace_id, query_run_id, step, call_index, "
                        "tool, args, status, error_code, result_handles, result_count, "
                        "total_matches, truncated, warnings, duration_ms, transport) VALUES "
                        "(:ws, :run, :step, :idx, :tool, CAST(:args AS jsonb), :status, :code, "
                        ":handles, :count, :total, :truncated, :warnings, :duration, :transport)"
                    ),
                    {
                        "ws": uuid.UUID(ctx.workspace_id),
                        "run": None if ctx.run_id is None else uuid.UUID(ctx.run_id),
                        "step": max(0, int(call.step)),
                        "idx": max(0, int(call.call_index)),
                        "tool": call.name[:64],
                        "args": json.dumps(args),
                        "status": status,
                        "code": code,
                        "handles": list(result.handles()),
                        "count": count,
                        "total": output.get("total_matches"),
                        "truncated": result.truncated,
                        "warnings": list(result.warnings),
                        "duration": result.duration_ms,
                        "transport": result.transport,
                    },
                )
                await session.commit()
        except SQLAlchemyError as exc:
            log.error("tool audit write failed: %s", type(exc).__name__)
            return failure_result(call, "INTERNAL", transport=result.transport)
        return result

    @staticmethod
    async def _purge_redacts(session: Any, ctx: ToolContext, result: ToolResult) -> bool:
        """Purge-safe audit (module doc, step 8): lock the run row ``FOR KEY SHARE``, then
        report whether this run's earlier or current result handles hit a purged version."""
        if ctx.run_id is None:
            return False
        scope, run = scope_from(ctx), uuid.UUID(ctx.run_id)
        await _lock_run_pack(session, scope, run)
        earlier = (
            await session.execute(
                text(
                    "SELECT DISTINCT unnest(result_handles) FROM tool_runs "
                    "WHERE workspace_id = :ws AND query_run_id = :run"
                ),
                {"ws": scope.workspace_id, "run": run},
            )
        ).scalars()
        handles = sorted({str(h) for h in earlier} | set(result.handles()))
        return bool(await _purged_pack_codes(session, scope, handles))
