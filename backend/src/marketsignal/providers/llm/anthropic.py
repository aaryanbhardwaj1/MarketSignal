"""Anthropic Messages API provider (plan §5, §19, §20; spec §6; ADR-0007).

Streams a single Messages call and maps it onto the provider contract in ``base``: text deltas
become :class:`LLMText`, the stream ends with exactly one :class:`LLMStop`. Thinking content is
never yielded (privacy, spec §6): only ``text_delta`` events inside ``text`` blocks reach the
caller.

**Retries are ours, not the SDK's.** The client is built with ``max_retries=0`` so the run
deadline stays in control. On 429, 529, other 5xx, an in-stream overloaded/api error, or a
connection/timeout error we retry *once*, after 0.5-1.5 s of jitter, and only if no text has
been yielded yet and enough of ``request.timeout_s`` remains. A failure after text was
yielded is never retried: the caller has already streamed a draft and must reset it. Every
other failure (other 4xx, malformed stream) raises :class:`LLMUnavailableError` at once, and
the run falls back to evidence-only.

``request.timeout_s`` is a per-call wall-clock budget covering the retry: it bounds the SDK
request timeout and each wait for the next stream event.

**Secrets.** The API key is handed to the SDK client and not kept on this object.
``__repr__`` omits it, and error messages are built from the error class, HTTP status and
request id only (never ``str(exc)``, never the request), raised ``from None`` so the SDK
exception (whose request carries auth headers) is not chained.

API assumptions the live spike (spec §12, "Live Anthropic check") must confirm:

1. ``output_config={"effort": ...}`` is accepted with ``low|medium|high|xhigh|max`` on the
   synthesis model (``claude-sonnet-5-5``), with and without thinking.
2. ``thinking={"type": "disabled"}`` and ``{"type": "adaptive", "display": "omitted"}`` are
   both accepted; with ``omitted`` no ``thinking_delta`` text arrives (we drop it anyway).
3. A ``cache_control: {"type": "ephemeral"}`` breakpoint on the single system text block
   yields ``cache_creation_input_tokens`` on the first call and ``cache_read_input_tokens`` on
   repeats (system prompt must exceed the model's minimum cacheable length).
4. ``message_start.message.usage`` carries input/cache counts and ``message_delta.usage`` is
   cumulative (``output_tokens`` final; input/cache fields may be null there).
5. ``stop_reason`` values seen in practice: ``end_turn``, ``max_tokens``, ``refusal``,
   ``stop_sequence`` (``pause_turn``/``model_context_window_exceeded`` passed through as-is).
6. Overload mid-stream arrives as an SSE ``error`` event (raised by the SDK as
   ``APIStatusError`` with the HTTP status of the stream, i.e. 200, and an
   ``overloaded_error`` body) and is classified as retryable here.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from typing import Any, Literal, Protocol, cast

import anthropic
from pydantic import SecretStr

from marketsignal.providers.llm.base import (
    LLMChunk,
    LLMRequest,
    LLMStop,
    LLMText,
    LLMUnavailableError,
    LLMUsage,
)
from marketsignal.telemetry.logging import get_logger

log = get_logger(__name__)

ThinkingMode = Literal["disabled", "adaptive"]

RETRYABLE_STATUS = frozenset({429, 529})
RETRYABLE_ERROR_TYPES = frozenset({"overloaded_error", "api_error", "rate_limit_error"})
JITTER_S = (0.5, 1.5)
DEFAULT_MIN_RETRY_BUDGET_S = 2.0  # don't retry unless this much budget is left after the sleep
DEFAULT_CLIENT_TIMEOUT_S = 60.0


class _EventStream(Protocol):
    """The slice of ``anthropic.AsyncStream[RawMessageStreamEvent]`` we use."""

    def __aiter__(self) -> AsyncIterator[Any]: ...

    async def close(self) -> None: ...


class _MessagesAPI(Protocol):
    def create(self, **kwargs: Any) -> Awaitable[_EventStream]: ...


class _ClientLike(Protocol):
    @property
    def messages(self) -> Any: ...


class _Retryable(Exception):  # noqa: N818 - internal control-flow signal, not a public error
    """A transient failure that may be retried if no text was yielded."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AnthropicProvider:
    """Streaming :class:`~marketsignal.providers.llm.base.LLMProvider` over ``AsyncAnthropic``."""

    def __init__(
        self,
        *,
        model: str,
        api_key: SecretStr | str | None = None,
        thinking: ThinkingMode = "disabled",
        client: _ClientLike | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
        min_retry_budget_s: float = DEFAULT_MIN_RETRY_BUDGET_S,
        client_timeout_s: float = DEFAULT_CLIENT_TIMEOUT_S,
    ) -> None:
        if thinking not in ("disabled", "adaptive"):
            raise ValueError(f"unsupported thinking mode: {thinking!r}")
        if client is None:
            key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
            if not key:
                raise ValueError("AnthropicProvider requires an API key")
            client = anthropic.AsyncAnthropic(api_key=key, max_retries=0, timeout=client_timeout_s)
        self._client = client
        self._model = model
        self._thinking: ThinkingMode = thinking
        self._sleep = sleep
        self._clock = clock
        self._rng = rng or random.Random()  # noqa: S311 - jitter, not security
        self._min_retry_budget_s = min_retry_budget_s

    def __repr__(self) -> str:
        return f"AnthropicProvider(model={self._model!r}, thinking={self._thinking!r})"

    @property
    def model_id(self) -> str:
        return self._model

    def thinking_param(self) -> dict[str, Any]:
        if self._thinking == "adaptive":
            return {"type": "adaptive", "display": "omitted"}
        return {"type": "disabled"}

    def build_params(self, request: LLMRequest, timeout_s: float) -> dict[str, Any]:
        """Keyword arguments for ``messages.create`` (``metadata`` is never sent)."""
        return {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "system": [
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": [dict(m) for m in request.messages],
            "output_config": {"effort": request.effort},
            "thinking": self.thinking_param(),
            "stream": True,
            "timeout": timeout_s,
        }

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        deadline = self._clock() + request.timeout_s
        for attempt in (1, 2):
            emitted = False
            try:
                async with aclosing(self._attempt(request, deadline)) as chunks:
                    async for chunk in chunks:
                        emitted = emitted or isinstance(chunk, LLMText)
                        yield chunk
                return
            except _Retryable as exc:
                if emitted:
                    raise LLMUnavailableError(
                        f"Anthropic stream failed after partial output ({exc.reason})"
                    ) from None
                delay = self._rng.uniform(*JITTER_S)
                remaining = deadline - self._clock() - delay
                if attempt == 2 or remaining < self._min_retry_budget_s:
                    raise LLMUnavailableError(
                        f"Anthropic unavailable after {attempt} attempt(s) ({exc.reason})"
                    ) from None
                log.warning(
                    "llm_retry", provider="anthropic", reason=exc.reason, delay_s=round(delay, 3)
                )
                await self._sleep(delay)

    async def _attempt(self, request: LLMRequest, deadline: float) -> AsyncGenerator[LLMChunk]:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise LLMUnavailableError("Anthropic call skipped: no time budget left")
        messages = cast(_MessagesAPI, self._client.messages)
        try:
            events = await asyncio.wait_for(
                messages.create(**self.build_params(request, remaining)), remaining
            )
        except Exception as exc:
            raise _classify(exc) from None
        try:
            async with aclosing(self._map_events(events, deadline)) as chunks:
                async for chunk in chunks:
                    yield chunk
        finally:
            await events.close()

    async def _map_events(self, events: _EventStream, deadline: float) -> AsyncGenerator[LLMChunk]:
        usage = _UsageAccumulator()
        model = self._model
        stop_reason: str | None = None
        text_blocks: set[int] = set()
        iterator = events.__aiter__()
        while True:
            try:
                event = await asyncio.wait_for(anext(iterator), deadline - self._clock())
            except StopAsyncIteration:
                break
            except Exception as exc:
                raise _classify(exc) from None
            etype = getattr(event, "type", None)
            if etype == "message_start":
                model = event.message.model or model
                usage.update(event.message.usage)
            elif etype == "content_block_start":
                if event.content_block.type == "text":
                    text_blocks.add(event.index)
            elif etype == "content_block_delta":
                delta = event.delta
                if delta.type == "text_delta" and event.index in text_blocks and delta.text:
                    yield LLMText(delta.text)
                # thinking_delta / signature_delta / others: never surfaced
            elif etype == "message_delta":
                stop_reason = event.delta.stop_reason or stop_reason
                usage.update(event.usage)
            elif etype == "message_stop":
                break
        if stop_reason is None:
            raise _Retryable("stream ended without a stop reason")
        yield LLMStop(stop_reason=stop_reason, usage=usage.freeze(), model=model)


class _UsageAccumulator:
    """Folds ``message_start`` usage and cumulative ``message_delta`` usage (nulls ignored)."""

    _FIELDS = (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    )

    def __init__(self) -> None:
        self._values = dict.fromkeys(self._FIELDS, 0)

    def update(self, source: Any) -> None:
        for name in self._FIELDS:
            value = getattr(source, name, None)
            if isinstance(value, int):
                self._values[name] = value

    def freeze(self) -> LLMUsage:
        return LLMUsage(**self._values)


def _classify(exc: BaseException) -> Exception:
    """Map an SDK/transport failure to a retryable signal or a terminal error (secret-free)."""
    if isinstance(exc, LLMUnavailableError | _Retryable):
        return exc
    if isinstance(exc, TimeoutError):
        return LLMUnavailableError("Anthropic call exceeded its time budget")
    if isinstance(exc, anthropic.APIStatusError):
        status = exc.status_code
        rid = f", request_id={exc.request_id}" if exc.request_id else ""
        reason = f"{type(exc).__name__} status={status}{rid}"
        if (
            status in RETRYABLE_STATUS
            or status >= 500
            or _body_error_type(exc.body) in (RETRYABLE_ERROR_TYPES)
        ):
            return _Retryable(reason)
        return LLMUnavailableError(f"Anthropic request rejected ({reason})")
    if isinstance(exc, anthropic.APIConnectionError):  # includes APITimeoutError
        return _Retryable(type(exc).__name__)
    return LLMUnavailableError(f"Anthropic call failed ({type(exc).__name__})")


def _body_error_type(body: object) -> str | None:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("type"), str):
            return cast(str, error["type"])
    return None
