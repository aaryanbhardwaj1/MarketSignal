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
