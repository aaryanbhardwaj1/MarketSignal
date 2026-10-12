"""Whether live answer generation is available (final productization phase).

``generation_status`` answers before any provider call, so ``POST …/runs`` can refuse a run with
``503 PROVIDER_UNAVAILABLE`` instead of starting one that can only degrade. Checks, in order:

1. ``DISABLED``: ``settings.llm_enabled`` is false (the offline demo).
2. ``llm_provider == "fake"``, or the app's provider seam was replaced (tests, offline stand-ins):
   always available; nothing here can reach a network.
3. ``NOT_CONFIGURED``: the Anthropic provider is configured without an API key.
4. ``PROVIDER_REJECTED``: the Anthropic provider recently rejected a request for an
   account-level reason (billing, authentication, permission, or an ``invalid_request_error``
   whose message says the credit balance is too low), latched for
   ``settings.provider_latch_ttl_s`` seconds.

The latch is process-global (it applies to every workspace), so it fires only on account-level
rejections. A request-specific ``invalid_request_error`` (for example "prompt is too long", or a
malformed tool-result pairing from our own bug) fails that one run and never refuses everyone
else's. The provider message is inspected in memory only; the latch stores just the error *type*
and a monotonic timestamp: never the message, the request id or anything else returned.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Final, Literal

from marketsignal.config import Settings

Reason = Literal["DISABLED", "NOT_CONFIGURED", "PROVIDER_REJECTED"]

LATCHED_ERROR_TYPES: Final = frozenset(
    {"billing_error", "authentication_error", "permission_error"}
)
# ``invalid_request_error`` is account-level only when the provider says so (low credit balance).
ACCOUNT_LEVEL_INVALID_REQUEST: Final = "invalid_request_error"
_ACCOUNT_MESSAGE = re.compile(r"credit|billing|balance", re.IGNORECASE)


def _now() -> float:
    """Monotonic clock (patched in tests to expire the latch)."""
    return time.monotonic()


@dataclass(frozen=True, slots=True)
class GenerationStatus:
    available: bool
    reason: Reason | None

    def as_dict(self) -> dict[str, object]:
        return {"available": self.available, "reason": self.reason}


AVAILABLE: Final = GenerationStatus(True, None)


@dataclass(frozen=True, slots=True)
class _LatchState:
    error_type: str
    at: float


class ProviderLatch:
    """The last non-retryable provider rejection: its error type and when it happened."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: _LatchState | None = None

    def set(self, error_type: str) -> None:
        with self._lock:
            self._state = _LatchState(error_type, _now())

    def clear(self) -> None:
        with self._lock:
            self._state = None

    def error_type(self) -> str | None:
        with self._lock:
            return self._state.error_type if self._state else None

    def active(self, ttl_s: float) -> bool:
        with self._lock:
            state = self._state
        return state is not None and (_now() - state.at) < ttl_s


PROVIDER_LATCH: Final = ProviderLatch()


def is_account_level(error_type: str | None, message: str | None = None) -> bool:
    """Whether a rejection is about the account (it would fail every request), not this one."""
    if error_type in LATCHED_ERROR_TYPES:
        return True
    return (
        error_type == ACCOUNT_LEVEL_INVALID_REQUEST
        and isinstance(message, str)
        and _ACCOUNT_MESSAGE.search(message) is not None
    )


def latch(error_type: str | None, message: str | None = None) -> bool:
    """Record a provider rejection if it is account-level (see :func:`is_account_level`).
    Returns whether the latch was set. Only the type string is kept; ``message`` is read here
    and never stored or logged."""
    if error_type is None or not is_account_level(error_type, message):
        return False
    PROVIDER_LATCH.set(error_type)
    return True


def generation_status(
    settings: Settings, *, uses_configured_provider: bool = True
) -> GenerationStatus:
    """See the module docstring. ``uses_configured_provider`` is false when the app's provider
    seam was replaced (a scripted or offline stand-in that never makes a network call)."""
    if not settings.llm_enabled:
        return GenerationStatus(False, "DISABLED")
    if settings.llm_provider == "fake" or not uses_configured_provider:
        return AVAILABLE
    if settings.anthropic_api_key is None or not settings.anthropic_api_key.get_secret_value():
        return GenerationStatus(False, "NOT_CONFIGURED")
    if PROVIDER_LATCH.active(settings.provider_latch_ttl_s):
        return GenerationStatus(False, "PROVIDER_REJECTED")
    return AVAILABLE
