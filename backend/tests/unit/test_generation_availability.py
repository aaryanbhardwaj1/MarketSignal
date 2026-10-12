"""``generation_status`` ordering and the provider latch (final productization phase)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from marketsignal.config import Settings
from marketsignal.providers.llm import availability
from marketsignal.providers.llm.availability import GenerationStatus, generation_status


@pytest.fixture(autouse=True)
def _clean_latch() -> Iterator[None]:
    availability.PROVIDER_LATCH.clear()
    yield
    availability.PROVIDER_LATCH.clear()


def _settings(**update: object) -> Settings:
    base = Settings(_env_file=None)  # type: ignore[call-arg]
    return base.model_copy(update=update)


KEY = SecretStr("not-a-real-key")


def test_order_disabled_first() -> None:
    availability.latch("billing_error")
    s = _settings(llm_enabled=False, llm_provider="anthropic", anthropic_api_key=None)
    assert generation_status(s) == GenerationStatus(False, "DISABLED")


def test_not_configured_before_latch() -> None:
    availability.latch("billing_error")
    s = _settings(llm_provider="anthropic", anthropic_api_key=None)
    assert generation_status(s) == GenerationStatus(False, "NOT_CONFIGURED")
    empty = _settings(llm_provider="anthropic", anthropic_api_key=SecretStr(""))
    assert generation_status(empty).reason == "NOT_CONFIGURED"


def test_latch_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [50.0]
    monkeypatch.setattr(availability, "_now", lambda: clock[0])
    s = _settings(llm_provider="anthropic", anthropic_api_key=KEY, provider_latch_ttl_s=10)
    assert generation_status(s) == availability.AVAILABLE
    assert availability.latch("authentication_error") is True
    assert generation_status(s) == GenerationStatus(False, "PROVIDER_REJECTED")
    clock[0] += 10
    assert generation_status(s) == availability.AVAILABLE


def test_only_non_retryable_types_latch() -> None:
    for error_type in ("rate_limit_error", "overloaded_error", "api_error", None, ""):
        assert availability.latch(error_type) is False
    assert availability.PROVIDER_LATCH.error_type() is None


def test_fake_and_replaced_seam_are_available() -> None:
    availability.latch("billing_error")
    assert generation_status(_settings(llm_provider="fake", anthropic_api_key=None)).available
    s = _settings(llm_provider="anthropic", anthropic_api_key=None)
    assert generation_status(s, uses_configured_provider=False).available


def test_status_dict_is_an_allowlist() -> None:
    assert GenerationStatus(False, "DISABLED").as_dict() == {
        "available": False,
        "reason": "DISABLED",
    }
