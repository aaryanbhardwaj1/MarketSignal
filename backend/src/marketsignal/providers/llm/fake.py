"""Scripted, deterministic LLM provider for tests (plan §5: providers/llm/fake).

Tests need two things from a model stand-in: control over what comes back (text, chunking,
stop reason, usage, failures, pacing) and a record of exactly what would have been sent. The
second matters for trust boundaries: the restricted-canary test (spec §6) asserts on
:attr:`FakeLLM.requests`, so recording happens when :meth:`FakeLLM.stream` is *called*, even
if the caller never iterates the stream.

Each call consumes the next :class:`ScriptedResponse`. Running out of script is a test bug and
raises :class:`AssertionError` unless ``repeat_last`` is set. Nothing here is random.
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from marketsignal.providers.llm.base import (
    AgentLLMRequest,
    AgentTurn,
    LLMChunk,
    LLMRequest,
    LLMStop,
    LLMText,
    LLMUsage,
    tool_uses_of,
)

DEFAULT_CHUNK_SIZE = 16
_CHARS_PER_TOKEN = 4  # crude, deterministic token estimate for default usage


@dataclass(frozen=True, slots=True)
class ScriptedResponse:
    """One scripted model reply.

    ``chunks`` (explicit deltas) wins over ``text`` + ``chunk_size``; giving both requires them
    to agree. ``error`` is raised instead of finishing: before any text by default, or after
    ``fail_after_chunks`` text chunks (a mid-stream failure). ``delay_s`` is awaited before
    each chunk so tests can exercise cancellation and timeouts.
    """

    text: str = ""
    stop_reason: str = "end_turn"
    usage: LLMUsage | None = None
    chunk_size: int | None = None
    chunks: tuple[str, ...] | None = None
    error: BaseException | None = None
    fail_after_chunks: int = 0
    delay_s: float = 0.0

    def __post_init__(self) -> None:
        if self.chunks is not None and self.text and "".join(self.chunks) != self.text:
            raise ValueError("ScriptedResponse: chunks do not join to text")
        if self.chunk_size is not None and self.chunk_size < 1:
            raise ValueError("ScriptedResponse: chunk_size must be >= 1")
        if self.fail_after_chunks < 0 or self.delay_s < 0:
            raise ValueError("ScriptedResponse: fail_after_chunks and delay_s must be >= 0")

    @property
    def full_text(self) -> str:
        return "".join(self.chunks) if self.chunks is not None else self.text

    def split(self) -> tuple[str, ...]:
        if self.chunks is not None:
            return tuple(c for c in self.chunks if c)
        size = self.chunk_size or DEFAULT_CHUNK_SIZE
        return tuple(self.text[i : i + size] for i in range(0, len(self.text), size))


def request_text(request: LLMRequest) -> str:
    """Everything in a request that would reach the model, as one string (for leak checks).

    ``metadata`` is excluded on purpose: it is never sent to the provider.
    """
    return request.system + "\n" + json.dumps(list(request.messages), default=str, sort_keys=True)


class FakeLLM:
    """:class:`~marketsignal.providers.llm.base.LLMProvider` that replays a script."""

    def __init__(
        self,
        responses: Sequence[ScriptedResponse | str],
        *,
        model: str = "fake-llm",
        repeat_last: bool = False,
    ) -> None:
        self._script = tuple(
            r if isinstance(r, ScriptedResponse) else ScriptedResponse(text=r) for r in responses
        )
        self._model = model
        self._repeat_last = repeat_last
        self._requests: list[LLMRequest] = []

    def __repr__(self) -> str:
        return f"FakeLLM(model={self._model!r}, scripted={len(self._script)})"

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def requests(self) -> tuple[LLMRequest, ...]:
        """Every request received, in call order."""
        return tuple(self._requests)

    @property
    def calls(self) -> int:
        return len(self._requests)

    @property
    def remaining(self) -> int:
        """Scripted responses not yet consumed (``repeat_last`` never runs out)."""
        return max(len(self._script) - len(self._requests), 0)

    def sent_text(self) -> str:
        """All recorded request text joined, for "this string never reached the model" checks."""
        return "\n".join(request_text(r) for r in self._requests)

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        index = len(self._requests)
        self._requests.append(request)
        if index < len(self._script):
            scripted = self._script[index]
        elif self._repeat_last and self._script:
            scripted = self._script[-1]
        else:
            raise AssertionError(
                f"FakeLLM script exhausted: call {index + 1} but only {len(self._script)} scripted"
            )
        return self._play(request, scripted)

    async def _play(
        self, request: LLMRequest, scripted: ScriptedResponse
    ) -> AsyncIterator[LLMChunk]:
        chunks = scripted.split()
        for i, chunk in enumerate(chunks):
            if scripted.error is not None and i == scripted.fail_after_chunks:
                raise scripted.error
            if scripted.delay_s:
                await asyncio.sleep(scripted.delay_s)
            yield LLMText(chunk)
        if scripted.error is not None:
            raise scripted.error
        usage = scripted.usage or LLMUsage(
            input_tokens=max(len(request_text(request)) // _CHARS_PER_TOKEN, 1),
            output_tokens=max(len(scripted.full_text) // _CHARS_PER_TOKEN, 1),
        )
        yield LLMStop(stop_reason=scripted.stop_reason, usage=usage, model=self._model)


# --- scripted agent steps (Phase 4) -----------------------------------------------------------


def tool_use_block(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": call_id, "name": name, "input": dict(arguments)}


def thinking_block(thinking: str = "", signature: str = "sig-synthetic") -> dict[str, Any]:
    return {"type": "thinking", "thinking": thinking, "signature": signature}


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


@dataclass(frozen=True, slots=True)
class ScriptedTurn:
    """One scripted agent step. ``stop_reason`` defaults to ``tool_use`` when ``content`` has
    tool_use blocks, else ``end_turn``. ``error`` is raised instead of replying; ``delay_s`` is
    awaited first (cancellation and timeout tests)."""

    content: tuple[dict[str, Any], ...] = ()
    stop_reason: str | None = None
    usage: LLMUsage | None = None
    error: BaseException | None = None
    delay_s: float = 0.0
    model: str = field(default="fake-agent-llm")

    def resolved_stop_reason(self) -> str:
        if self.stop_reason is not None:
            return self.stop_reason
        return "tool_use" if any(b.get("type") == "tool_use" for b in self.content) else "end_turn"


def agent_request_json(request: AgentLLMRequest) -> str:
    """Everything an agent step would send to the model, as one canonical string."""
    return json.dumps(
        {
            "system": request.system,
            "messages": list(request.messages),
            "tools": list(request.tools),
        },
        sort_keys=True,
        default=str,
    )


Responder = Callable[[AgentLLMRequest, int], ScriptedTurn]


class FakeAgentLLM:
    """:class:`~marketsignal.providers.llm.base.AgentLLM` replaying scripted turns (or a
    ``responder(request, index)`` callable). Records each request and a JSON snapshot of it
    *at call time*, so tests can prove the transcript is append-only and byte-stable."""

    def __init__(
        self,
        script: Sequence[ScriptedTurn] | Responder,
        *,
        model: str = "fake-agent-llm",
    ) -> None:
        self._script = script
        self._model = model
        self._requests: list[AgentLLMRequest] = []
        self._snapshots: list[str] = []

    def __repr__(self) -> str:
        return f"FakeAgentLLM(model={self._model!r})"

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def requests(self) -> tuple[AgentLLMRequest, ...]:
        return tuple(self._requests)

    @property
    def snapshots(self) -> tuple[str, ...]:
        return tuple(self._snapshots)

    @property
    def calls(self) -> int:
        return len(self._requests)

    async def step(self, request: AgentLLMRequest) -> AgentTurn:
        index = len(self._requests)
        self._requests.append(request)
        self._snapshots.append(agent_request_json(request))
        if callable(self._script):
            scripted = self._script(request, index)
        elif index < len(self._script):
            scripted = self._script[index]
        else:
            raise AssertionError(f"FakeAgentLLM script exhausted at call {index + 1}")
        if scripted.delay_s:
            await asyncio.sleep(scripted.delay_s)
        if scripted.error is not None:
            raise scripted.error
        content = tuple(copy.deepcopy(b) for b in scripted.content)
        usage = scripted.usage or LLMUsage(
            input_tokens=max(len(agent_request_json(request)) // _CHARS_PER_TOKEN, 1),
            output_tokens=max(len(json.dumps(list(content))) // _CHARS_PER_TOKEN, 1),
        )
        return AgentTurn(
            content=content,
            tool_uses=tool_uses_of(content),
            stop_reason=scripted.resolved_stop_reason(),
            usage=usage,
            model=self._model,
        )
