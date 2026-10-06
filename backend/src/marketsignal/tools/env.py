"""What a tool implementation receives: trusted context only (never model arguments)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
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

    def classes(self, requested: Iterable[str] | None) -> list[str] | None:
        """The source classes a call may read: the requested classes intersected with the
        token's class claim (the claim alone when none are requested; empty list = every
        class). ``None`` means the intersection is empty: the call returns no items with the
        ``SOURCE_CLASS_FILTERED`` warning instead of widening."""
        asked = {str(getattr(c, "value", c)) for c in requested or ()}
        claim = self.ctx.source_classes
        if not claim:
            return sorted(asked)
        if not asked:
            return sorted(claim)
        both = asked & claim
        return sorted(both) if both else None

    def class_allowed(self, source_class: str) -> bool:
        return not self.ctx.source_classes or source_class in self.ctx.source_classes


def scope_from(ctx: ToolContext) -> WorkspaceScope:
    return WorkspaceScope(uuid.UUID(ctx.workspace_id), ctx.workspace_code)


class ToolInputError(ValueError):
    """Arguments that pass the schema but not a semantic check (reported as VALIDATION_ERROR)."""


class ToolNotFoundError(LookupError):
    """A named object the call needs (e.g. an analytics dataset) is not visible to the token:
    absent, in another workspace, above ``max_conf``, outside the class claim, purged or
    superseded - indistinguishably (reported as ``NOT_FOUND``)."""
