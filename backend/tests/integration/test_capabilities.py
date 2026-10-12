# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""Provider gating (final productization phase): ``GET /api/capabilities`` and the 503
``PROVIDER_UNAVAILABLE`` pre-check on ``POST …/runs``. No test here can reach a provider: a
refused run is refused before any row or call, and nothing posts a run with the real provider
seam installed while generation is available."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import anthropic
import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.providers.llm import availability
from marketsignal.providers.llm.anthropic import _classify
from marketsignal.providers.llm.base import LLMUnavailableError
from marketsignal.providers.llm.fake import FakeLLM
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_runs_api import GOOD, _install, _scoped, _stream

pytestmark = pytest.mark.integration

PROVIDER_CANARY = "Your credit balance is too low CANARY-PROVIDER-8812"
REQUEST_ID_CANARY = "req_CANARY0000provider"


@pytest.fixture(autouse=True)
def _clean_latch() -> Iterator[None]:
    availability.PROVIDER_LATCH.clear()
    yield
    availability.PROVIDER_LATCH.clear()


def _app(h: Harness) -> Any:
    return h.client._transport.app  # type: ignore[attr-defined]


def _configure(h: Harness, **update: Any) -> None:
    """Swap the settings the request handlers read (the provider seam is left as built)."""
    app = _app(h)
    app.state.settings = app.state.settings.model_copy(update=update)


def _rejection(error_type: str = "billing_error", status: int = 400) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://provider.invalid/v1/messages")
    response = httpx.Response(status, request=request, headers={"request-id": REQUEST_ID_CANARY})
    body = {"type": "error", "error": {"type": error_type, "message": PROVIDER_CANARY}}
    return anthropic.BadRequestError(PROVIDER_CANARY, response=response, body=body)


async def _conversation(h: Harness, ws: str) -> str:
    created = await h.client.post(f"/api/workspaces/{ws}/conversations", json={})
    assert created.status_code == 201, created.text
    conversation: str = created.json()["conversation_id"]
    return conversation


async def _post_run(h: Harness, ws: str, conversation: str) -> httpx.Response:
    return await h.client.post(
        f"/api/workspaces/{ws}/conversations/{conversation}/runs",
        json={"question": "What share of Gen Z buyers name fit as their top frustration?"},
    )


async def _run_rows(engine: AsyncEngine, ws: str) -> int:
    async with engine.connect() as conn:
        await _scoped(conn, ws)
        return int((await conn.execute(text("SELECT count(*) FROM query_runs"))).scalar_one())


async def _capabilities(h: Harness) -> dict[str, Any]:
    response = await h.client.get("/api/capabilities")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _assert_refused(response: httpx.Response, reason: str) -> None:
    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert error == {
        "code": "PROVIDER_UNAVAILABLE",
        "message": "Answer generation is unavailable; saved runs remain browsable.",
        "reason": reason,
        "retryable": False,
    }
    assert PROVIDER_CANARY not in response.text
    assert REQUEST_ID_CANARY not in response.text


async def test_disabled_refuses_runs_before_any_row(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    ws = await harness.create_workspace()
    conversation = await _conversation(harness, ws)  # created while generation was available
    _configure(harness, llm_enabled=False)
    assert await _capabilities(harness) == {
        "generation": {"available": False, "reason": "DISABLED"}
    }
    _assert_refused(await _post_run(harness, ws, conversation), "DISABLED")
    assert await _run_rows(app_engine, ws) == 0
    async with app_engine.connect() as conn:
        await _scoped(conn, ws)
        messages = (await conn.execute(text("SELECT count(*) FROM messages"))).scalar_one()
    assert messages == 0  # the user message is not written either


async def test_disabled_wins_even_over_a_scripted_provider(harness: Harness) -> None:
    _install(harness, FakeLLM([GOOD]))
    ws = await harness.create_workspace()
    conversation = await _conversation(harness, ws)
    _configure(harness, llm_enabled=False)
    _assert_refused(await _post_run(harness, ws, conversation), "DISABLED")


async def test_missing_key_refuses_runs(harness: Harness, app_engine: AsyncEngine) -> None:
    ws = await harness.create_workspace()
    conversation = await _conversation(harness, ws)
    _configure(harness, llm_provider="anthropic", anthropic_api_key=None)
    assert await _capabilities(harness) == {
        "generation": {"available": False, "reason": "NOT_CONFIGURED"}
    }
    _assert_refused(await _post_run(harness, ws, conversation), "NOT_CONFIGURED")
    assert await _run_rows(app_engine, ws) == 0


async def test_disabled_refuses_new_conversations_before_any_row(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    ws = await harness.create_workspace()
    _configure(harness, llm_enabled=False)
    response = await harness.client.post(
        f"/api/workspaces/{ws}/conversations", json={"title": "What frustrates Gen Z buyers?"}
    )
    _assert_refused(response, "DISABLED")
    async with app_engine.connect() as conn:
        await _scoped(conn, ws)
        count = (await conn.execute(text("SELECT count(*) FROM conversations"))).scalar_one()
    assert count == 0  # no empty conversation is left behind


async def test_unknown_conversation_is_still_404(harness: Harness) -> None:
    _configure(harness, llm_enabled=False)
    ws = await harness.create_workspace()
    response = await _post_run(harness, ws, "00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


async def test_classified_rejection_latches_until_ttl(
    harness: Harness, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A configured (fake) key with the real provider seam: the pre-check never builds it.
    _configure(
        harness,
        llm_provider="anthropic",
        anthropic_api_key=SecretStr("not-a-real-key"),
        provider_latch_ttl_s=600,
    )
    clock = [1000.0]
    monkeypatch.setattr(availability, "_now", lambda: clock[0])
    assert await _capabilities(harness) == {"generation": {"available": True, "reason": None}}
    ws = await harness.create_workspace()
    conversation = await _conversation(harness, ws)

    classified = _classify(_rejection("billing_error"))
    assert isinstance(classified, LLMUnavailableError)
    assert availability.PROVIDER_LATCH.error_type() == "billing_error"

    body = await _capabilities(harness)
    assert body == {"generation": {"available": False, "reason": "PROVIDER_REJECTED"}}
    _assert_refused(await _post_run(harness, ws, conversation), "PROVIDER_REJECTED")
    assert await _run_rows(app_engine, ws) == 0

    clock[0] += 599
    assert (await _capabilities(harness))["generation"]["available"] is False
    clock[0] += 2  # past the TTL: available again (checked without posting a live run)
    assert await _capabilities(harness) == {"generation": {"available": True, "reason": None}}


@pytest.mark.parametrize(
    ("error_type", "status", "latched"),
    [
        ("authentication_error", 401, True),
        ("permission_error", 403, True),
        ("invalid_request_error", 400, True),  # the canary message names the credit balance
        ("not_found_error", 404, False),
        ("overloaded_error", 529, False),  # retryable: never latched
    ],
)
def test_latch_types(error_type: str, status: int, latched: bool) -> None:
    _classify(_rejection(error_type, status))
    assert (availability.PROVIDER_LATCH.error_type() == error_type) is latched


@pytest.mark.parametrize(
    ("message", "latched"),
    [
        ("prompt is too long: 210000 tokens > 200000 maximum", False),
        ("messages.3: tool_use ids were found without tool_result blocks", False),
        ("Your credit balance is too low to access the Anthropic API.", True),
    ],
)
def test_invalid_request_latches_only_for_account_level_messages(
    message: str, latched: bool
) -> None:
    request = httpx.Request("POST", "https://provider.invalid/v1/messages")
    response = httpx.Response(400, request=request)
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": message}}
    _classify(anthropic.BadRequestError(message, response=response, body=body))
    state = availability.PROVIDER_LATCH._state
    assert (state is not None) is latched
    assert message not in repr(state)  # the message is never stored


def test_latch_keeps_only_the_error_type() -> None:
    _classify(_rejection("billing_error"))
    state = availability.PROVIDER_LATCH._state
    assert state is not None
    assert PROVIDER_CANARY not in repr(state)
    assert REQUEST_ID_CANARY not in repr(state)


async def test_fake_provider_is_unaffected_by_key_and_latch(harness: Harness) -> None:
    _configure(harness, llm_provider="fake", anthropic_api_key=None)
    availability.latch("billing_error")
    assert await _capabilities(harness) == {"generation": {"available": True, "reason": None}}


async def test_scripted_provider_seam_runs_normally(harness: Harness) -> None:
    """Tests (and offline stand-ins) replace the provider seam: the key check does not apply."""
    _install(harness, FakeLLM([GOOD]))
    _configure(harness, llm_provider="anthropic", anthropic_api_key=None)
    availability.latch("billing_error")
    ws = await harness.create_workspace()
    conversation = await _conversation(harness, ws)
    response = await _post_run(harness, ws, conversation)
    assert response.status_code == 202, response.text
    events = await _stream(harness, response.json()["stream_url"])
    assert events[-1]["event"] == "done"


async def test_capabilities_exposes_only_generation(harness: Harness) -> None:
    body = await _capabilities(harness)
    assert set(body) == {"generation"}
    assert set(body["generation"]) == {"available", "reason"}
