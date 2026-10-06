"""Ingestion pipeline: one source version from blob to searchable, resolvable evidence.

Runs in the worker (ADR-0010), scoped to the version's workspace from the job arguments.
Stages update the visible status: parsing -> chunking -> embedding -> indexing -> ready |
ready_degraded | failed | superseded. Content is written while the version is *not yet active*;
a health check runs against that inactive version; only then does a small, guarded "flip"
transaction make it current (and supersede the previous version, ADR-0016). A source purged
mid-flight stops the job and its version stays ``purged``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session
from marketsignal.domain.enums import IngestErrorCode, SourceType, VersionStatus
from marketsignal.evidence.handles import EvidenceHandle, LocatorKind, build_handle
from marketsignal.ingestion import repository as repo
from marketsignal.ingestion.chunking import HEADING_SEPARATOR, build_children
from marketsignal.ingestion.health import check_version_health
from marketsignal.ingestion.models import ChildDraft, IngestionError, ParentDraft
from marketsignal.ingestion.parsers import parse_source
from marketsignal.ingestion.tokenizer import Tokenizer
from marketsignal.providers.embeddings import CachedEmbedder, Embedder, EmbedderUnavailableError
from marketsignal.telemetry.logging import get_logger

log = get_logger(__name__)
ACTOR = "ingestion-worker"


class SourcePurgedError(Exception):
    """The source was purged while this version was in flight; the purge owns its state."""


@dataclass
class IngestionDeps:
    session_factory: SessionFactory
    settings: Settings
    embedder: Embedder
    tokenizer: Tokenizer
    clock: Callable[[], float] = time.perf_counter


@dataclass
class _Timer:
    clock: Callable[[], float]
    started: float = 0.0
    marks: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.started = self.clock()
        self._last = self.started

    def lap(self, name: str) -> None:
        now = self.clock()
        self.marks[f"{name}_ms"] = round((now - self._last) * 1000, 1)
        self._last = now

    def total(self) -> None:
        self.marks["total_ms"] = round((self.clock() - self.started) * 1000, 1)


def embed_input(title: str, child: ChildDraft) -> str:
    """Dense input: contextual header (source > heading path) + child text (plan §9)."""
    header = HEADING_SEPARATOR.join(p for p in (title, child.heading_text) if p)
    return f"{header}\n{child.text}"


def assign_handles(
    scope: WorkspaceScope, version: repo.VersionRow, parents: tuple[ParentDraft, ...]
) -> list[EvidenceHandle]:
    handles = [
        build_handle(scope.workspace_code, version.source_code, version.version, *p.locator)
        for p in parents
    ]
    if len({str(h) for h in handles}) != len(handles):
        raise IngestionError(
            IngestErrorCode.INGEST_EXTRACT_FAILED.value, "parser produced duplicate locators"
        )
    return handles


def _row_handle_factory(
    scope: WorkspaceScope, version: repo.VersionRow
) -> Callable[[int, int], str]:
    def make(sheet: int, row: int) -> str:
        units: list[tuple[LocatorKind, int]] = [(LocatorKind.ROW, row)]
        if version.source_type == SourceType.XLSX.value:
            units.insert(0, (LocatorKind.SHEET, sheet))
        return str(build_handle(scope.workspace_code, version.source_code, version.version, *units))

    return make


async def ingest_version(deps: IngestionDeps, scope: WorkspaceScope, version_id: uuid.UUID) -> str:
    """Process one queued version. Idempotent: a version not in ``queued`` is left untouched."""
    timer = _Timer(deps.clock)
    async with scoped_session(deps.session_factory, scope) as session:
        version = await repo.get_version(session, version_id, for_update=True)
        if version is None or version.status != VersionStatus.QUEUED.value:
            return version.status if version else "missing"
        await repo.set_status(
            session,
            version_id,
            VersionStatus.PARSING,
            attempts=version.attempts + 1,
            started_at=datetime.now(UTC),
        )
        data = await repo.load_blob(session, version_id)
        await session.commit()

    try:
        return await _run(deps, scope, version, data, timer)
    except SourcePurgedError:
        log.info("ingest_source_purged", version_id=str(version_id))
        return VersionStatus.PURGED.value
    except IngestionError as exc:
        return await _fail(deps, scope, version, exc.code, exc.message, timer)
    except TimeoutError:
        return await _fail(
            deps,
            scope,
            version,
            IngestErrorCode.PARSE_TIMEOUT.value,
            "parsing exceeded the time limit",
            timer,
        )
    except Exception:
        log.exception("ingestion_failed", version_id=str(version_id))
        return await _fail(
            deps,
            scope,
            version,
            IngestErrorCode.INGEST_EXTRACT_FAILED.value,
            "unexpected ingestion error",
            timer,
        )


async def _run(
    deps: IngestionDeps, scope: WorkspaceScope, version: repo.VersionRow, data: bytes, timer: _Timer
) -> str:
    settings = deps.settings
    parsed = await asyncio.wait_for(
        asyncio.to_thread(
            parse_source,
            SourceType(version.source_type),
            data,
            title=version.title,
            tokenizer=deps.tokenizer,
            settings=settings,
        ),
        timeout=settings.parse_timeout_s,
    )
    timer.lap("parse")
    if not parsed.parents:
        raise IngestionError(IngestErrorCode.EMPTY_DOCUMENT.value, "no content found")
    await _status(deps, scope, version, VersionStatus.CHUNKING)

    handles = assign_handles(scope, version, parsed.parents)
    sheet_names = {
        int(p.locator_meta["sheet"]): str(p.locator_meta["sheet_name"])
        for p in parsed.parents
        if "sheet" in p.locator_meta and "sheet_name" in p.locator_meta
    }
    labels = [h.locator_label(sheet_names) for h in handles]
    parent_tokens = [deps.tokenizer.count(p.text) for p in parsed.parents]
    children = build_children(
        parsed.parents, deps.tokenizer, settings.child_window_tokens, settings.child_overlap_tokens
    )
    timer.lap("chunk")
    await _status(deps, scope, version, VersionStatus.EMBEDDING)

    inputs = [embed_input(version.title, c) for c in children]
    warnings = list(parsed.warnings)
    vectors = None
    try:
        vectors = await asyncio.to_thread(deps.embedder.embed_passages, inputs)
    except EmbedderUnavailableError:
        log.warning("embedder_unavailable", version_id=str(version.id))
        warnings.append(IngestErrorCode.EMBEDDER_UNAVAILABLE.value)
    timer.lap("embed")
    if isinstance(deps.embedder, CachedEmbedder):
        timer.marks["embed_cache_hits"] = deps.embedder.last_hits
        timer.marks["embed_cache_misses"] = deps.embedder.last_misses

    async with scoped_session(deps.session_factory, scope) as session:
        await _ensure_live(session, version)
        await repo.set_status(session, version.id, VersionStatus.INDEXING)
        parent_ids = await repo.insert_parents(
            session,
            scope.workspace_id,
            version.id,
            parsed.parents,
            [str(h) for h in handles],
            labels,
            parent_tokens,
        )
        child_ids = await repo.insert_children(
            session,
            scope.workspace_id,
            version,
            parent_ids,
            children,
            settings.chunking_policy_version,
        )
        if vectors is not None:
            await repo.insert_embeddings(
                session,
                scope.workspace_id,
                child_ids,
                vectors,
                [repo.sha256_text(i) for i in inputs],
                deps.embedder.model_id,
            )
        await repo.insert_datasets(
            session,
            scope.workspace_id,
            version.id,
            parsed.tables,
            _row_handle_factory(scope, version),
        )
        await session.commit()
    timer.lap("index")

    async with scoped_session(deps.session_factory, scope) as session:
        health = await check_version_health(
            session, version.id, deps.embedder.model_id if vectors is not None else None, settings
        )
    timer.lap("health")
    if not health["ok"]:
        raise IngestionError(IngestErrorCode.HEALTH_CHECK_FAILED.value, health["reason"])

    final = VersionStatus.READY if vectors is not None else VersionStatus.READY_DEGRADED
    timer.total()
    embed_ms = timer.marks.get("embed_ms", 0.0)
    timer.marks.update(
        {
            "parents": len(parsed.parents),
            "children": len(children),
            "bytes": len(data),
            "children_per_s_embed": round(len(children) / (embed_ms / 1000), 1)
            if embed_ms
            else None,
        }
    )
    return await _flip(deps, scope, version, final, warnings, health, timer, children)


async def _ensure_live(session: AsyncSession, version: repo.VersionRow) -> None:
    """Every worker write first share-locks the source; a purged source stops the job."""
    if not await repo.lock_live_source(session, version.source_id):
        raise SourcePurgedError


async def _status(
    deps: IngestionDeps, scope: WorkspaceScope, version: repo.VersionRow, status: VersionStatus
) -> None:
    async with scoped_session(deps.session_factory, scope) as session:
        await _ensure_live(session, version)
        await repo.set_status(session, version.id, status)
        await session.commit()


async def _flip(
    deps: IngestionDeps,
    scope: WorkspaceScope,
    version: repo.VersionRow,
    final: VersionStatus,
    warnings: list[str],
    health: dict[str, Any],
    timer: _Timer,
    children: list[ChildDraft],
) -> str:
    """Guarded activation: only a newer version may become current; never resurrects deletes."""
    settings = deps.settings
    async with scoped_session(deps.session_factory, scope) as session:
        source = (
            await session.execute(
                text(
                    "SELECT s.current_version_id, s.deleted_at, cv.version FROM sources s "
                    "LEFT JOIN source_versions cv ON cv.id = s.current_version_id "
                    "WHERE s.id = :sid FOR UPDATE OF s"
                ),
                {"sid": version.source_id},
            )
        ).one()
        current_id, deleted_at, current_version = source
        common = {
            "warnings": warnings,
            "health": health,
            "timings": timer.marks,
            "parent_count": timer.marks["parents"],
            "child_count": len(children),
            "chunking_policy_version": settings.chunking_policy_version,
            "embedding_model": deps.embedder.model_id if final is VersionStatus.READY else None,
        }
        if deleted_at is not None:
            # Purged after indexing committed: the purge already removed this version's content
            # and marked it purged. Never activate it and never overwrite that state.
            raise SourcePurgedError
        if current_id is None or current_version < version.version:
            if current_id is not None:
                # A purged version stays purged when its source is re-uploaded (ADR-0016): the
                # run-side purge guard reads source_versions.status (runs.store).
                await session.execute(
                    text(
                        "UPDATE source_versions SET status = :st, updated_at = now() "
                        "WHERE id = :id AND status <> :purged"
                    ),
                    {
                        "id": current_id,
                        "st": VersionStatus.SUPERSEDED.value,
                        "purged": VersionStatus.PURGED.value,
                    },
                )
            await session.execute(
                text(
                    "UPDATE sources SET current_version_id = :v, updated_at = now() WHERE id = :s"
                ),
                {"v": version.id, "s": version.source_id},
            )
            await repo.set_status(session, version.id, final, ready_at=datetime.now(UTC), **common)
            corpus_version = await repo.bump_corpus_version(session, scope.workspace_id)
            await repo.audit(
                session,
                scope.workspace_id,
                ACTOR,
                "source_version.activated",
                f"{version.source_code}@v{version.version}",
                {
                    "status": final.value,
                    "corpus_version": corpus_version,
                    "superseded": current_version,
                },
            )
            await session.commit()
            return final.value
        # A newer version is already current: this one is superseded on arrival.
        await repo.set_status(session, version.id, VersionStatus.SUPERSEDED, **common)
        await session.commit()
        return VersionStatus.SUPERSEDED.value


async def _fail(
    deps: IngestionDeps,
    scope: WorkspaceScope,
    version: repo.VersionRow,
    code: str,
    message: str,
    timer: _Timer,
) -> str:
    timer.total()
    async with scoped_session(deps.session_factory, scope) as session:
        if not await repo.lock_live_source(session, version.source_id):
            return VersionStatus.PURGED.value  # the purge already removed content and set status
        await repo.delete_version_content(session, version.id)
        await repo.set_status(
            session,
            version.id,
            VersionStatus.FAILED,
            error_code=code,
            error_detail=message[:500],
            timings=timer.marks,
        )
        await repo.audit(
            session,
            scope.workspace_id,
            ACTOR,
            "source_version.failed",
            str(version.id),
            {"error_code": code},
        )
        await session.commit()
    return VersionStatus.FAILED.value
