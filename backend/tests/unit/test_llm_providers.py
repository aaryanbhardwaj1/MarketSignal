"""LLM providers: the scripted FakeLLM and the Anthropic adapter against a fake SDK client.

The Anthropic tests never touch the network: a stand-in client exposes the same
``messages.create(stream=True)`` surface and replays real SDK event models
(``RawMessageStartEvent`` etc.) so the mapping is checked against the shapes the SDK emits.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any, cast

import anthropic
import httpx2
import pytest
from anthropic.types import (
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    RawContentBlockStopEvent,
    RawMessageDeltaEvent,
    RawMessageStartEvent,
    RawMessageStopEvent,
)
from pydantic import SecretStr

from marketsignal.providers.llm.anthropic import AnthropicProvider
from marketsignal.providers.llm.base import (
    LLMChunk,
    LLMRequest,
    LLMStop,
    LLMText,
    LLMUnavailableError,
    LLMUsage,
)
from marketsignal.providers.llm.fake import FakeLLM, ScriptedResponse

MODEL = "claude-sonnet-5-5"
API_KEY = "sk-ant-api03-SUPERSECRETKEY"
_URL = "https://api.anthropic.com/v1/messages"


def _request(**overrides: Any) -> LLMRequest:
    fields: dict[str, Any] = {
        "system": "You are a careful analyst.",
        "messages": ({"role": "user", "content": "What drives churn?"},),
        "max_tokens": 8000,
        "effort": "low",
        "timeout_s": 25.0,
        "metadata": {"run_id": "r1"},
    }
    fields.update(overrides)
    return LLMRequest(**fields)


async def _collect(stream: AsyncIterator[LLMChunk]) -> list[LLMChunk]:
    return [chunk async for chunk in stream]


async def _drain_into(stream: AsyncIterator[LLMChunk], seen: list[str]) -> None:
    """Consume a stream, recording text seen before any failure."""
    async for chunk in stream:
        if isinstance(chunk, LLMText):
            seen.append(chunk.text)


def _texts(chunks: Sequence[LLMChunk]) -> list[str]:
    return [c.text for c in chunks if isinstance(c, LLMText)]


# --------------------------------------------------------------------------- FakeLLM


async def test_fake_streams_scripted_chunks_then_one_stop() -> None:
    usage = LLMUsage(input_tokens=7, output_tokens=3)
    fake = FakeLLM(
        [ScriptedResponse(chunks=("Hel", "lo ", "[E1]"), usage=usage, stop_reason="max_tokens")],
        model="fake-1",
    )
    chunks = await _collect(fake.stream(_request()))
    assert _texts(chunks) == ["Hel", "lo ", "[E1]"]
    assert chunks[-1] == LLMStop(stop_reason="max_tokens", usage=usage, model="fake-1")
    assert sum(isinstance(c, LLMStop) for c in chunks) == 1
    assert fake.model_id == "fake-1"


async def test_fake_chunk_size_and_string_shorthand_are_deterministic() -> None:
    fake = FakeLLM([ScriptedResponse(text="abcdefg", chunk_size=3), "plain"])
    first = await _collect(fake.stream(_request()))
    second = await _collect(fake.stream(_request()))
    assert _texts(first) == ["abc", "def", "g"]
    assert "".join(_texts(second)) == "plain"
    stop = second[-1]
    assert isinstance(stop, LLMStop)
    assert stop.stop_reason == "end_turn"
    assert stop.usage.output_tokens >= 1


async def test_fake_records_requests_even_without_iteration() -> None:
    fake = FakeLLM(["a", "b"])
    req1 = _request(system="SYS ONE")
    req2 = _request(messages=({"role": "user", "content": "CANARY-OK"},))
    fake.stream(req1)  # never iterated
    await _collect(fake.stream(req2))
    assert fake.requests == (req1, req2)
    assert fake.calls == 2
    assert fake.remaining == 0
    assert "CANARY-OK" in fake.sent_text()
    assert "RESTRICTED-CANARY" not in fake.sent_text()
    assert "run_id" not in fake.sent_text()  # metadata is never "sent"


async def test_fake_exhaustion_raises_and_repeat_last_does_not() -> None:
    fake = FakeLLM(["only"])
    await _collect(fake.stream(_request()))
    with pytest.raises(AssertionError, match="exhausted"):
        fake.stream(_request())
    assert fake.calls == 2  # the over-call is still recorded

    repeating = FakeLLM(["again"], repeat_last=True)
    for _ in range(3):
        assert _texts(await _collect(repeating.stream(_request()))) == ["again"]


async def test_fake_raises_scripted_error_before_or_after_text() -> None:
    fake = FakeLLM(
        [
            ScriptedResponse(error=LLMUnavailableError("down")),
            ScriptedResponse(
                chunks=("a", "b", "c"), error=LLMUnavailableError("mid"), fail_after_chunks=2
            ),
        ]
    )
    with pytest.raises(LLMUnavailableError, match="down"):
        await _collect(fake.stream(_request()))
    seen: list[str] = []
    with pytest.raises(LLMUnavailableError, match="mid"):
        await _drain_into(fake.stream(_request()), seen)
    assert seen == ["a", "b"]


async def test_fake_delay_allows_cancellation() -> None:
    fake = FakeLLM([ScriptedResponse(text="slow text", chunk_size=1, delay_s=0.5)])
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await _collect(fake.stream(_request()))


def test_scripted_response_validates_inputs() -> None:
    with pytest.raises(ValueError, match="join"):
        ScriptedResponse(text="abc", chunks=("x",))
    with pytest.raises(ValueError, match="chunk_size"):
        ScriptedResponse(text="abc", chunk_size=0)


# --------------------------------------------------------------------------- SDK fakes


def _status_error(status: int, error_type: str = "api_error") -> anthropic.APIStatusError:
    response = httpx2.Response(
        status, request=httpx2.Request("POST", _URL), headers={"request-id": "req_123"}
    )
    body = {"type": "error", "error": {"type": error_type, "message": "nope"}}
    return anthropic.APIStatusError(f"Error code: {status}", response=response, body=body)


def _connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=httpx2.Request("POST", _URL))


def _message_start(input_tokens: int = 120, cache_read: int = 100, cache_create: int = 0) -> Any:
    return RawMessageStartEvent.model_validate(
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": MODEL,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": 1,
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": cache_create,
                },
            },
        }
    )


def _block_start(index: int, kind: str) -> Any:
    block: dict[str, Any] = (
        {"type": "text", "text": ""}
        if kind == "text"
        else {"type": "thinking", "thinking": "", "signature": ""}
    )
    return RawContentBlockStartEvent.model_validate(
        {"type": "content_block_start", "index": index, "content_block": block}
    )


def _text_delta(index: int, text: str) -> Any:
    return RawContentBlockDeltaEvent.model_validate(
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "text_delta", "text": text},
        }
    )


def _thinking_delta(index: int, text: str) -> Any:
    return RawContentBlockDeltaEvent.model_validate(
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "thinking_delta", "thinking": text},
        }
    )


def _block_stop(index: int) -> Any:
    return RawContentBlockStopEvent.model_validate({"type": "content_block_stop", "index": index})


def _message_delta(stop_reason: str, output_tokens: int) -> Any:
    return RawMessageDeltaEvent.model_validate(
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": output_tokens},
        }
    )


def _message_stop() -> Any:
    return RawMessageStopEvent.model_validate({"type": "message_stop"})


def _events(
    texts: Sequence[str], stop_reason: str = "end_turn", thinking: bool = False
) -> list[Any]:
    events: list[Any] = [_message_start()]
    index = 0
    if thinking:
        events += [
            _block_start(0, "thinking"),
            _thinking_delta(0, "SECRET REASONING"),
            _block_stop(0),
        ]
        index = 1
    events.append(_block_start(index, "text"))
    events += [_text_delta(index, t) for t in texts]
    events += [_block_stop(index), _message_delta(stop_reason, 42), _message_stop()]
    return events


class _FakeStream:
    """Replays events; an exception in the list is raised at that point."""

    def __init__(self, items: Sequence[Any], delay_s: float = 0.0) -> None:
        self._items = list(items)
        self._delay_s = delay_s
        self.closed = False

    async def _gen(self) -> AsyncIterator[Any]:
        for item in self._items:
            if self._delay_s:
                await asyncio.sleep(self._delay_s)
            if isinstance(item, BaseException):
                raise item
            yield item

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._gen()

    async def close(self) -> None:
        self.closed = True


class _FakeMessages:
    def __init__(self, script: Sequence[BaseException | _FakeStream]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.streams: list[_FakeStream] = []

    async def create(self, **kwargs: Any) -> _FakeStream:
        self.calls.append(kwargs)
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        self.streams.append(item)
        return item


class _FakeClient:
    def __init__(self, script: Sequence[BaseException | _FakeStream]) -> None:
        self.messages = _FakeMessages(script)


class _Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def _provider(
    script: Sequence[BaseException | _FakeStream], **kwargs: Any
) -> tuple[AnthropicProvider, _FakeClient, _Sleeps]:
    client = _FakeClient(script)
    sleeps = _Sleeps()
    provider = AnthropicProvider(
        model=MODEL, client=cast(Any, client), sleep=sleeps, clock=lambda: 1000.0, **kwargs
    )
    return provider, client, sleeps


# --------------------------------------------------------------------------- Anthropic


async def test_text_deltas_in_order_and_usage_stop_mapped() -> None:
    provider, client, _ = _provider([_FakeStream(_events(["Churn ", "is ", "driven [E1]."]))])
    chunks = await _collect(provider.stream(_request()))
    assert _texts(chunks) == ["Churn ", "is ", "driven [E1]."]
    assert chunks[-1] == LLMStop(
        stop_reason="end_turn",
        usage=LLMUsage(
            input_tokens=120,
            output_tokens=42,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=0,
        ),
        model=MODEL,
    )
    assert sum(isinstance(c, LLMStop) for c in chunks) == 1
    assert client.messages.streams[0].closed


async def test_thinking_deltas_are_never_yielded() -> None:
    provider, _, _ = _provider(
        [_FakeStream(_events(["visible"], thinking=True))], thinking="adaptive"
    )
    chunks = await _collect(provider.stream(_request()))
    assert _texts(chunks) == ["visible"]
    assert all("SECRET REASONING" not in repr(c) for c in chunks)


@pytest.mark.parametrize("reason", ["refusal", "max_tokens", "stop_sequence"])
async def test_stop_reasons_pass_through(reason: str) -> None:
    provider, _, _ = _provider([_FakeStream(_events(["partial"], stop_reason=reason))])
    chunks = await _collect(provider.stream(_request()))
    stop = chunks[-1]
    assert isinstance(stop, LLMStop)
    assert stop.stop_reason == reason


async def test_request_params_built_correctly() -> None:
    provider, client, _ = _provider([_FakeStream(_events(["ok"]))])
    request = _request(effort="medium", max_tokens=4096, timeout_s=12.5)
    await _collect(provider.stream(request))
    (sent,) = client.messages.calls
    assert sent["model"] == MODEL
    assert sent["max_tokens"] == 4096
    assert sent["stream"] is True
    assert sent["system"] == [
        {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
    ]
    assert sent["messages"] == [{"role": "user", "content": "What drives churn?"}]
    assert sent["output_config"] == {"effort": "medium"}
    # Claude 5.x rejects {"type": "disabled"}; "between_tools" is its spelling of "no thinking
    # before responding" (live spike, docs/spikes/0002-anthropic-live.md).
    assert sent["thinking"] == {"type": "between_tools"}
    assert sent["timeout"] == pytest.approx(12.5)
    assert "metadata" not in sent


async def test_adaptive_thinking_config_uses_omitted_display() -> None:
    provider, client, _ = _provider([_FakeStream(_events(["ok"]))], thinking="adaptive")
    await _collect(provider.stream(_request()))
    assert client.messages.calls[0]["thinking"] == {"type": "adaptive", "display": "omitted"}


async def test_retries_once_on_529_then_succeeds() -> None:
    provider, client, sleeps = _provider(
        [_status_error(529, "overloaded_error"), _FakeStream(_events(["after retry"]))]
    )
    chunks = await _collect(provider.stream(_request()))
    assert _texts(chunks) == ["after retry"]
    assert len(client.messages.calls) == 2
    assert len(sleeps.delays) == 1
    assert 0.5 <= sleeps.delays[0] <= 1.5


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_retryable_statuses_get_exactly_one_retry(status: int) -> None:
    provider, client, sleeps = _provider([_status_error(status), _status_error(status)])
    with pytest.raises(LLMUnavailableError, match=f"status={status}"):
        await _collect(provider.stream(_request()))
    assert len(client.messages.calls) == 2
    assert len(sleeps.delays) == 1


async def test_connection_error_is_retried() -> None:
    provider, client, _ = _provider([_connection_error(), _FakeStream(_events(["back"]))])
    assert _texts(await _collect(provider.stream(_request()))) == ["back"]
    assert len(client.messages.calls) == 2


async def test_timeout_error_from_sdk_is_retried() -> None:
    timeout = anthropic.APITimeoutError(request=httpx2.Request("POST", _URL))
    provider, client, _ = _provider([timeout, _FakeStream(_events(["back"]))])
    assert _texts(await _collect(provider.stream(_request()))) == ["back"]
    assert len(client.messages.calls) == 2


async def test_400_raises_without_retry() -> None:
    provider, client, sleeps = _provider([_status_error(400, "invalid_request_error")])
    with pytest.raises(LLMUnavailableError, match="status=400"):
        await _collect(provider.stream(_request()))
    assert len(client.messages.calls) == 1
    assert sleeps.delays == []


async def test_no_retry_after_text_was_yielded() -> None:
    events = _events(["first ", "second"])
    events.insert(3, _status_error(200, "overloaded_error"))  # mid-stream SSE error event
    stream = _FakeStream(events)
    provider, client, sleeps = _provider([stream, _FakeStream(_events(["never"]))])
    seen: list[str] = []
    with pytest.raises(LLMUnavailableError, match="partial output"):
        await _drain_into(provider.stream(_request()), seen)
    assert seen == ["first "]
    assert len(client.messages.calls) == 1
    assert sleeps.delays == []
    assert stream.closed


async def test_midstream_overload_before_text_is_retried() -> None:
    events = [_message_start(), _status_error(200, "overloaded_error")]
    provider, client, _ = _provider([_FakeStream(events), _FakeStream(_events(["ok"]))])
    assert _texts(await _collect(provider.stream(_request()))) == ["ok"]
    assert len(client.messages.calls) == 2


async def test_no_retry_when_budget_is_too_small() -> None:
    provider, client, sleeps = _provider([_status_error(529)], min_retry_budget_s=5.0)
    with pytest.raises(LLMUnavailableError, match="1 attempt"):
        await _collect(provider.stream(_request(timeout_s=3.0)))
    assert len(client.messages.calls) == 1
    assert sleeps.delays == []


async def test_stream_without_stop_reason_is_unavailable() -> None:
    truncated = [_message_start(), _block_start(0, "text"), _text_delta(0, "cut")]
    provider, _, _ = _provider([_FakeStream(truncated)])
    with pytest.raises(LLMUnavailableError, match="partial output"):
        await _collect(provider.stream(_request()))


async def test_slow_stream_hits_the_deadline() -> None:
    client = _FakeClient([_FakeStream(_events(["late"]), delay_s=1.0)])
    provider = AnthropicProvider(model=MODEL, client=cast(Any, client))
    with pytest.raises(LLMUnavailableError, match="time budget"):
        await _collect(provider.stream(_request(timeout_s=0.05)))
    assert client.messages.streams[0].closed


async def test_early_consumer_exit_closes_the_sdk_stream() -> None:
    provider, client, _ = _provider([_FakeStream(_events(["a", "b", "c"]))])
    stream = provider.stream(_request())
    assert isinstance(stream, AsyncIterator)
    async for _ in stream:
        break
    await cast(Any, stream).aclose()
    assert client.messages.streams[0].closed


async def test_errors_and_repr_never_contain_the_key() -> None:
    provider = AnthropicProvider(model=MODEL, api_key=SecretStr(API_KEY))
    assert API_KEY not in repr(provider)
    assert MODEL in repr(provider)
    assert not any(isinstance(v, str) and API_KEY in v for v in vars(provider).values())

    bad, _, _ = _provider([_status_error(401, "authentication_error")])
    with pytest.raises(LLMUnavailableError) as info:
        await _collect(bad.stream(_request()))
    assert API_KEY not in str(info.value)
    assert info.value.__cause__ is None
    assert "req_123" in str(info.value)


def test_real_client_is_built_without_sdk_retries() -> None:
    provider = AnthropicProvider(model=MODEL, api_key=API_KEY, client_timeout_s=30.0)
    client = cast(anthropic.AsyncAnthropic, vars(provider)["_client"])
    assert client.max_retries == 0
    assert client.timeout == 30.0
    with pytest.raises(ValueError, match="API key"):
        AnthropicProvider(model=MODEL, api_key=SecretStr(""))
