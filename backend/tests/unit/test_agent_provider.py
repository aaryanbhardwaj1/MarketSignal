"""Tool-using agent step on the providers: AnthropicProvider.step and FakeAgentLLM (no live API)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from marketsignal.providers.llm.anthropic import AnthropicProvider
from marketsignal.providers.llm.base import AgentLLMRequest, LLMUnavailableError, LLMUsage
from marketsignal.providers.llm.fake import (
    FakeAgentLLM,
    ScriptedTurn,
    thinking_block,
    tool_use_block,
)

MODEL = "claude-test-model"
API_KEY = "sk-ant-test-synthetic-0000"  # obviously synthetic
_URL = "https://api.anthropic.com/v1/messages"


def _message(stop_reason: str = "tool_use") -> anthropic.types.Message:
    return anthropic.types.Message.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": MODEL,
            "content": [
                {"type": "thinking", "thinking": "", "signature": "sig-a"},
                {"type": "redacted_thinking", "data": "opaque"},
                {"type": "text", "text": "Let me search."},
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "search_evidence",
                    "input": {"query": "fit"},
                },
                {"type": "tool_use", "id": "tu_2", "name": "list_sources", "input": {}},
            ],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 120,
                "output_tokens": 40,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 0,
            },
        }
    )


def _status_error(status: int, error_type: str = "api_error") -> anthropic.APIStatusError:
    response = httpx2.Response(
        status, request=httpx2.Request("POST", _URL), headers={"request-id": "req_9"}
    )
    body = {"type": "error", "error": {"type": error_type, "message": "nope"}}
    return anthropic.APIStatusError(f"Error code: {status}", response=response, body=body)


class _Messages:
    def __init__(self, script: Sequence[Any]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _Client:
    def __init__(self, script: Sequence[Any]) -> None:
        self.messages = _Messages(script)


def _provider(script: Sequence[Any], **kw: Any) -> tuple[AnthropicProvider, _Client, list[float]]:
    client = _Client(script)
    sleeps: list[float] = []

    async def sleep(d: float) -> None:
        sleeps.append(d)

    provider = AnthropicProvider(
        model=MODEL, client=cast(Any, client), sleep=sleep, clock=lambda: 1000.0, **kw
    )
    return provider, client, sleeps


def _req(**kw: Any) -> AgentLLMRequest:
    base: dict[str, Any] = {
        "system": "SYSTEM",
        "messages": ({"role": "user", "content": [{"type": "text", "text": "q"}]},),
        "tools": (
            {
                "name": "search_evidence",
                "description": "d",
                "input_schema": {"type": "object"},
                "strict": True,
            },
        ),
        "max_tokens": 4096,
        "effort": "low",
        "timeout_s": 30.0,
    }
    return AgentLLMRequest(**{**base, **kw})


async def test_step_maps_blocks_verbatim_and_parses_tool_uses() -> None:
    provider, _, _ = _provider([_message()])
    turn = await provider.step(_req())
    assert turn.content[0] == {"type": "thinking", "thinking": "", "signature": "sig-a"}
    assert turn.content[1] == {"type": "redacted_thinking", "data": "opaque"}
    assert turn.content[2] == {"type": "text", "text": "Let me search."}
    assert [(u.id, u.name, u.input) for u in turn.tool_uses] == [
        ("tu_1", "search_evidence", {"query": "fit"}),
        ("tu_2", "list_sources", {}),
    ]
    assert turn.stop_reason == "tool_use"
    assert turn.model == MODEL
    assert turn.usage == LLMUsage(120, 40, 100, 0)


async def test_step_params_auto_tool_choice_between_tools_thinking_cached_system() -> None:
    provider, client, _ = _provider([_message()])
    await provider.step(_req())
    params = client.messages.calls[0]
    assert params["tool_choice"] == {"type": "auto"}
    assert params["thinking"] == {"type": "between_tools"}
    assert params["system"] == [
        {"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}
    ]
    assert params["tools"][0]["name"] == "search_evidence"
    assert params["tools"][0]["strict"] is True
    assert params["output_config"] == {"effort": "low"}
    assert params["max_tokens"] == 4096
    assert "stream" not in params
    assert params["timeout"] == 30.0


async def test_step_adaptive_thinking_is_omitted_display() -> None:
    provider, client, _ = _provider([_message()], thinking="adaptive")
    await provider.step(_req())
    assert client.messages.calls[0]["thinking"] == {"type": "adaptive", "display": "omitted"}


@pytest.mark.parametrize("status", [429, 529, 500])
async def test_step_retries_once_on_retryable_status(status: int) -> None:
    provider, client, sleeps = _provider([_status_error(status), _message()])
    turn = await provider.step(_req())
    assert len(client.messages.calls) == 2
    assert len(sleeps) == 1
    assert turn.tool_uses


async def test_step_gives_up_after_the_second_failure() -> None:
    provider, client, _ = _provider([_status_error(529), _status_error(529)])
    with pytest.raises(LLMUnavailableError):
        await provider.step(_req())
    assert len(client.messages.calls) == 2


async def test_step_400_is_not_retried_and_never_leaks_the_key() -> None:
    provider, client, _ = _provider([_status_error(400, "invalid_request_error")])
    with pytest.raises(LLMUnavailableError) as info:
        await provider.step(_req())
    assert len(client.messages.calls) == 1
    assert API_KEY not in str(info.value)
    assert info.value.__cause__ is None
    assert "req_9" in str(info.value)


async def test_step_no_retry_without_budget() -> None:
    provider, client, _ = _provider([_status_error(529), _message()])
    with pytest.raises(LLMUnavailableError):
        await provider.step(_req(timeout_s=1.0))
    assert len(client.messages.calls) == 1


async def test_step_malformed_message_is_unavailable() -> None:
    provider, _, _ = _provider([object()])
    with pytest.raises(LLMUnavailableError):
        await provider.step(_req())


def test_repr_has_no_key() -> None:
    provider = AnthropicProvider(model=MODEL, api_key=SecretStr(API_KEY))
    assert API_KEY not in repr(provider)


async def test_fake_agent_llm_records_snapshots_and_defaults_stop_reason() -> None:
    llm = FakeAgentLLM(
        [
            ScriptedTurn(
                content=(
                    thinking_block("t"),
                    tool_use_block("a", "search_evidence", {"query": "x"}),
                )
            ),
            ScriptedTurn(content=()),
            ScriptedTurn(error=LLMUnavailableError("down")),
        ]
    )
    first = await llm.step(_req())
    assert first.stop_reason == "tool_use"
    assert first.tool_uses[0].name == "search_evidence"
    first.content[0]["thinking"] = "mutated"  # returned content is a copy of the script
    assert (await llm.step(_req())).stop_reason == "end_turn"
    with pytest.raises(LLMUnavailableError):
        await llm.step(_req())
    assert llm.calls == 3
    assert len(llm.snapshots) == 3
    with pytest.raises(AssertionError):
        await llm.step(_req())
