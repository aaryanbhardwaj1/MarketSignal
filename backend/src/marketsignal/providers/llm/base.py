"""LLM provider interface (plan §5: providers/llm/{base, anthropic, fake}).

Generation streams text deltas and ends with exactly one :class:`LLMStop` carrying the stop
reason and token usage. Providers never expose model reasoning: thinking content, if any, is
not yielded. Failures surface as :class:`LLMUnavailableError` (the run falls back to
evidence-only); refusals and truncation are stop reasons, handled by the caller.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMUnavailableError(RuntimeError):
    """The model could not be reached or returned an error after the retry policy."""


@dataclass(frozen=True, slots=True)
class LLMRequest:
    system: str  # static, byte-stable system prompt (prompt-cached)
    messages: tuple[dict[str, Any], ...]  # Anthropic-style [{"role", "content"}]
    max_tokens: int
    effort: str  # low | medium | high | xhigh | max
    timeout_s: float
    metadata: dict[str, Any] = field(default_factory=dict)  # never sent to the provider


@dataclass(frozen=True, slots=True)
class LLMText:
    text: str


@dataclass(frozen=True, slots=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
        }


@dataclass(frozen=True, slots=True)
class LLMStop:
    stop_reason: str  # end_turn | max_tokens | refusal | stop_sequence | ...
    usage: LLMUsage
    model: str


LLMChunk = LLMText | LLMStop


class LLMProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]: ...


# --- one non-streamed agent step with tools (Phase 4, research mode; ADR-0007) ----------------


@dataclass(frozen=True, slots=True)
class AgentLLMRequest:
    """One agent step. ``messages`` is the append-only transcript (assistant ``content`` resent
    verbatim, thinking blocks included); ``tools`` are Anthropic tool definitions. Tool choice
    is always ``auto`` (forced choice is rejected by Claude 5.x)."""

    system: str
    messages: tuple[dict[str, Any], ...]
    tools: tuple[dict[str, Any], ...]
    max_tokens: int
    effort: str
    timeout_s: float


@dataclass(frozen=True, slots=True)
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AgentTurn:
    """The model's reply to one step. ``content`` holds the raw assistant blocks exactly as
    returned (thinking/redacted_thinking with signatures, text, tool_use) and must be resent
    unchanged; it is never streamed, logged or persisted. ``tool_uses`` is the parsed view of
    the tool_use blocks in block order."""

    content: tuple[dict[str, Any], ...]
    tool_uses: tuple[ToolUse, ...]
    stop_reason: str
    usage: LLMUsage
    model: str


class AgentLLM(Protocol):
    """A provider that can run one tool-using agent step (non-streamed)."""

    @property
    def model_id(self) -> str: ...

    async def step(self, request: AgentLLMRequest) -> AgentTurn:
        """Raises :class:`LLMUnavailableError` on failure (after the retry policy)."""
        ...


def tool_uses_of(content: tuple[dict[str, Any], ...]) -> tuple[ToolUse, ...]:
    """The tool_use blocks of an assistant ``content`` in block order."""
    return tuple(
        ToolUse(id=str(b["id"]), name=str(b["name"]), input=dict(b.get("input") or {}))
        for b in content
        if b.get("type") == "tool_use"
    )
