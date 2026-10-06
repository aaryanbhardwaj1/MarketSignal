"""The governed tool contract (plan §17-18; ADR-0006): the one interface shared by the tool
registry, both transports (in-process and MCP Streamable HTTP) and the research agent.

Ownership: this module is the frozen boundary between the tool layer and the agent. Neither
side changes it unilaterally; changes go through the integrator so the in-process and HTTP
paths can never drift apart.

Rules that every implementation must keep:

* **No context in schemas.** No input model has a workspace, user, persona, path or SQL field.
  The workspace comes only from the verified capability token (``credential``) and becomes a
  ``ToolContext`` server-side. A model-supplied ``workspace_id`` (or any unknown field) is a
  ``VALIDATION_ERROR``: every input model forbids extra fields.
* **Bounded.** Every list and string (including each list item) has a server-side limit, and
  no string input may contain control characters other than tab/newline/carriage return
  (``VALIDATION_ERROR``); outputs are capped and say so (``truncated`` plus ``TRUNCATED``).
* **Class claim.** A capability token may carry ``source_classes``; the tools intersect any
  requested classes with it (never widen) and ``get_evidence`` treats other classes as absent.
* **Explicit failure.** A call never raises to the agent: it returns ``ToolResult(ok=False,
  error=ToolError(code, message))`` with a normalized code and a safe message.
* **Two views of one result.** ``output`` is the full typed result for the runtime (the
  evidence pool needs handles and anchor spans); ``observation`` is the compact, bounded text
  the model sees. Document-derived text in both is untrusted data, never instructions.
* **Production retrieval.** ``search_evidence`` is the production hybrid pipeline (dense +
  lexical, parent-level RRF, reranker **off**, the Phase 2 decision); it never enables the
  experimental reranker.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from marketsignal.domain.enums import SourceClass, SourceType

ToolName = Literal[
    "search_evidence",
    "search_evidence_keyword",
    "get_evidence",
    "list_sources",
    "aggregate",
    "describe_dataset",
    "filter_rows",
    "group_compare",
]
TOOL_NAMES: tuple[ToolName, ...] = (
    "aggregate",
    "describe_dataset",
    "filter_rows",
    "get_evidence",
    "group_compare",
    "list_sources",
    "search_evidence",
    "search_evidence_keyword",
)  # sorted: the model-facing tool array is ordered by name for prompt-cache stability

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "POLICY_DENIED",
    "NOT_FOUND",
    "TIMEOUT",
    "UNAVAILABLE",
    "INTERNAL",
    "UNAUTHENTICATED",
]
Transport = Literal["inprocess", "http"]

TRUNCATED = "TRUNCATED"  # warning: the output was capped (items or characters)
# warning: the requested classes and the token's class claim do not intersect (no hits)
SOURCE_CLASS_FILTERED = "SOURCE_CLASS_FILTERED"
# warning on an UNAVAILABLE result: the transport itself failed (no tool ran); set only by the
# HTTP transport on connection failures, so a fallback transport may safely re-run the call
TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
# warning: the call was re-run through the fallback (in-process) transport
TOOLS_TRANSPORT_FALLBACK = "TOOLS_TRANSPORT_FALLBACK"
SNIPPET_MAX_CHARS = 280
HANDLE_MAX_CHARS = 200
SOURCE_CODE_MAX_CHARS = 64
TERM_MAX_CHARS = 60

_ALLOWED_CONTROL = frozenset("\t\n\r")

Handle = Annotated[str, StringConstraints(min_length=1, max_length=HANDLE_MAX_CHARS)]
SourceCode = Annotated[str, StringConstraints(min_length=1, max_length=SOURCE_CODE_MAX_CHARS)]
Term = Annotated[str, StringConstraints(min_length=1, max_length=TERM_MAX_CHARS)]


def has_control_chars(value: str) -> bool:
    """Control (Cc, other than tab/newline/CR) or surrogate (Cs) characters: NUL breaks jsonb
    writes and escape sequences have no place in a search argument."""
    return any(
        unicodedata.category(ch) in ("Cc", "Cs") and ch not in _ALLOWED_CONTROL for ch in value
    )


def _check_strings(value: Any) -> Any:
    items = value if isinstance(value, list) else [value]
    if any(isinstance(v, str) and has_control_chars(v) for v in items):
        raise ValueError("control characters are not allowed")
    return value


class _In(BaseModel):
    """Tool inputs: strict, closed (no extra fields), so context can never be smuggled in.
    Every string (and every string list item) is bounded and free of control characters."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def _no_control_chars(cls, value: Any) -> Any:
        return _check_strings(value)


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- retrieval -------------------------------------------------------------------------------


class SearchEvidenceIn(_In):
    """``search_evidence``: the full production hybrid pipeline over the run's workspace."""

    query: str = Field(min_length=2, max_length=400)
    source_classes: list[SourceClass] | None = Field(default=None, max_length=5)
    source_codes: list[SourceCode] | None = Field(default=None, max_length=10)
    top_k: int | None = Field(default=None, ge=1, le=12)  # default 8


class KeywordSearchIn(_In):
    """``search_evidence_keyword``: exact matching with exhaustive counts (identifiers,
    names, quoted phrases)."""

    terms: list[Term] = Field(min_length=1, max_length=6)  # each 1..60 non-blank chars
    match: Literal["all", "any", "phrase"] | None = None  # default "all"
    source_classes: list[SourceClass] | None = Field(default=None, max_length=5)
    source_codes: list[SourceCode] | None = Field(default=None, max_length=10)
    limit: int | None = Field(default=None, ge=1, le=20)  # default 10


class GetEvidenceIn(_In):
    """``get_evidence``: resolve up to 8 canonical handles (malformed ones reported per item)."""

    handles: list[Handle] = Field(min_length=1, max_length=8)


class ListSourcesIn(_In):
    """``list_sources``: the workspace catalogue (optionally by class)."""

    source_classes: list[SourceClass] | None = Field(default=None, max_length=5)


class EvidenceHit(_Out):
    """One parent-level hit. ``anchor_*`` carry the D1 anchor (ADR-0003) into the evidence
    pool so the pack and citation cards keep the exact supporting span."""

    handle: str
    source_code: str
    source_title: str
    source_class: SourceClass
    locator_label: str
    snippet: str = Field(max_length=SNIPPET_MAX_CHARS)  # untrusted document text
    anchor_child_id: str
    anchor_char_start: int = Field(ge=0)
    anchor_char_end: int = Field(ge=0)
    dense_rank: int | None = None
    lexical_rank: int | None = None
    fused_rank: int = Field(ge=1)


class SearchEvidenceOut(_Out):
    hits: list[EvidenceHit]
    classes_found: dict[str, int]
    warnings: list[str] = Field(default_factory=list)


class KeywordSearchOut(_Out):
    total_matches: int = Field(ge=0)  # exhaustive count over the workspace (not capped)
    matches_by_source: dict[str, int]
    hits: list[EvidenceHit]
    warnings: list[str] = Field(default_factory=list)


class ResolvedEvidence(_Out):
    handle: str
    found: bool
    miss_reason: Literal["MALFORMED", "NOT_FOUND", "SOURCE_DELETED"] | None = None
    text: str | None = None  # truncated observation text; the pack re-resolves full text
    locator_label: str | None = None
    source_title: str | None = None
    source_class: SourceClass | None = None


class GetEvidenceOut(_Out):
    items: list[ResolvedEvidence]
    warnings: list[str] = Field(default_factory=list)


class SourceCard(_Out):
    source_code: str
    title: str
    source_class: SourceClass
    source_type: SourceType
    version: int
    parent_count: int


class ListSourcesOut(_Out):
    sources: list[SourceCard]
    warnings: list[str] = Field(default_factory=list)


# Phase 5 analytics tools (frozen contract in ``analytics_contracts``, which builds on ``_In`` /
# ``_Out`` above; ``marketsignal.tools.__init__`` imports this module first so the cycle resolves).
from marketsignal.tools.analytics_contracts import (  # noqa: E402
    ANALYTICS_INPUT_MODELS,
    ANALYTICS_OUTPUT_MODELS,
)

INPUT_MODELS: dict[str, type[_In]] = {
    "search_evidence": SearchEvidenceIn,
    "search_evidence_keyword": KeywordSearchIn,
    "get_evidence": GetEvidenceIn,
    "list_sources": ListSourcesIn,
    **ANALYTICS_INPUT_MODELS,
}
OUTPUT_MODELS: dict[str, type[_Out]] = {
    "search_evidence": SearchEvidenceOut,
    "search_evidence_keyword": KeywordSearchOut,
    "get_evidence": GetEvidenceOut,
    "list_sources": ListSourcesOut,
    **ANALYTICS_OUTPUT_MODELS,
}


# --- calls, results, transports --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One model tool_use block. ``step``/``call_index`` are runtime metadata for the audit
    row and deterministic ordering; they are never model-visible arguments."""

    call_id: str  # the model's tool_use id
    name: str
    arguments: dict[str, Any]
    step: int = 0
    call_index: int = 0


@dataclass(frozen=True, slots=True)
class ToolError:
    code: ErrorCode
    message: str  # safe for the model and logs: no SQL, paths, tokens or stack traces


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    name: str
    ok: bool
    output: dict[str, Any] | None  # the validated output model, dumped (runtime view)
    observation: str  # compact, bounded, model-visible text (obs_max_tokens)
    error: ToolError | None = None
    truncated: bool = False
    warnings: tuple[str, ...] = ()
    duration_ms: float = 0.0
    transport: Transport = "inprocess"

    def handles(self) -> tuple[str, ...]:
        """Evidence handles returned (search hits and found resolutions), in output order."""
        if not self.ok or not self.output:
            return ()
        hits = self.output.get("hits") or []
        items = [i for i in self.output.get("items") or [] if i.get("found")]
        return tuple(str(h["handle"]) for h in [*hits, *items])


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A model-facing tool definition (already adapted for Anthropic strict mode)."""

    name: str
    description: str
    input_schema: dict[str, Any]
    strict: bool = True

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "strict": self.strict,
        }


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Built server-side from verified capability claims only (never from arguments)."""

    workspace_id: str
    workspace_code: str
    run_id: str | None
    principal: str
    persona: str
    tools: frozenset[str]
    max_confidentiality: str
    extra: dict[str, Any] = field(default_factory=dict)
    # the token's ``classes`` claim (SourceClass values); empty = every class
    source_classes: frozenset[str] = frozenset()


class ToolTransport(Protocol):
    """How the agent reaches the governed tools. Both implementations run the *same*
    registry and governance pipeline; only the wire differs (parity is tested)."""

    @property
    def transport(self) -> Transport: ...

    async def list_tools(self) -> list[ToolSpec]: ...

    async def call(self, call: ToolCall, *, credential: str) -> ToolResult:
        """Execute one call under the capability token ``credential``. Never raises for tool,
        validation, auth or policy failures: they come back as ``ToolResult(ok=False)``."""
        ...
