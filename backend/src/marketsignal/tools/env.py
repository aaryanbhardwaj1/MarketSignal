"""What a tool implementation receives: trusted context only (never model arguments)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory
from marketsignal.domain.enums import Confidentiality
from marketsignal.retrieval.pipeline import RetrievalService
from marketsignal.tools.contracts import ToolContext


@dataclass(frozen=True)
class ToolEnv:
    """``factory`` opens sessions whose every transaction carries ``SET LOCAL
    statement_timeout``; ``scope`` is built from the verified claims."""

    ctx: ToolContext
    scope: WorkspaceScope
    factory: SessionFactory
    retrieval: RetrievalService
    settings: Settings

    @property
    def max_confidentiality(self) -> Confidentiality:
        return Confidentiality(self.ctx.max_confidentiality)


def scope_from(ctx: ToolContext) -> WorkspaceScope:
    return WorkspaceScope(uuid.UUID(ctx.workspace_id), ctx.workspace_code)


class ToolInputError(ValueError):
    """Arguments that pass the schema but not a semantic check (reported as VALIDATION_ERROR)."""
