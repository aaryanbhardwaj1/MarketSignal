"""Whether live answer generation is available (final productization phase).

``generation_status`` answers before any provider call, so ``POST …/runs`` can refuse a run with
``503 PROVIDER_UNAVAILABLE`` instead of starting one that can only degrade. Checks, in order:

1. ``DISABLED``: ``settings.llm_enabled`` is false (the offline demo).
2. ``llm_provider == "fake"``, or the app's provider seam was replaced (tests, offline stand-ins):
   always available; nothing here can reach a network.
3. ``NOT_CONFIGURED``: the Anthropic provider is configured without an API key.
4. ``PROVIDER_REJECTED``: the Anthropic provider recently rejected a request with a
   non-retryable error type (billing, authentication, permission, invalid request), latched for
   ``settings.provider_latch_ttl_s`` seconds.

The latch is process-local and stores only the provider error *type* and a monotonic timestamp:
never the message, the request id or anything else the provider returned.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Final, Literal

from marketsignal.config import Settings

Reason = Literal["DISABLED", "NOT_CONFIGURED", "PROVIDER_REJECTED"]

LATCHED_ERROR_TYPES: Final = frozenset(
    {"invalid_request_error", "billing_error", "authentication_error", "permission_error"}
)


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


def latch(error_type: str | None) -> bool:
    """Record a provider rejection if its type is one that cannot recover on retry. Returns
    whether the latch was set. Only the type string is kept."""
    if error_type not in LATCHED_ERROR_TYPES:
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
