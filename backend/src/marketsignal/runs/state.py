"""Run request and per-run state shared by the executor, synthesis and finalization."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from marketsignal.db.scope import WorkspaceScope
from marketsignal.generation.types import EvidencePack, VerificationReport
from marketsignal.providers.llm.base import LLMStop, LLMUsage


class _ToolFailureError(Exception):
    """A pipeline tool failed in a way the run reports (warning ``code``) rather than crashes."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


class _SourceWithheldError(Exception):
    """The store withheld this run's draft text: a pack source was purged mid-generation."""


@dataclass(frozen=True, slots=True)
class RunRequest:
    run_id: uuid.UUID
    scope: WorkspaceScope
    conversation_id: uuid.UUID
    question: str
    persona: str
    mode: str = "standard"
    source_classes: tuple[str, ...] = ()
    route: dict[str, Any] | None = None  # the router's decision (runs.router.RouteDecision)


@dataclass(frozen=True, slots=True)
class _Answer:
    """What the pipeline decided to publish; finalized outside the deadline scope."""

    content: str
    sections: dict[str, Any]
    citations: list[dict[str, Any]]
    report: VerificationReport | None
    pack: EvidencePack


@dataclass(frozen=True, slots=True)
class _Outcome:
    status: str = "completed"
    error: str | None = None
    notice: tuple[str, dict[str, Any]] | None = None  # warning/error emitted before done
    cancelled: bool = False


@dataclass
class _Attempt:
    raw: str = ""
    stop: LLMStop | None = None
    first_token_ms: float | None = None
    duration_ms: float = 0.0


@dataclass
class _RunState:
    flags: list[str] = field(default_factory=list)
    states: set[str] = field(default_factory=set)
    usage: dict[str, int] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    model: str | None = None

    def flag(self, code: str) -> None:
        if code not in self.flags:
            self.flags.append(code)

    def count(self, key: str) -> None:
        self.usage[key] = self.usage.get(key, 0) + 1

    def add_usage(self, usage: LLMUsage) -> None:
        for key, value in usage.as_dict().items():
            self.usage[key] = self.usage.get(key, 0) + value
