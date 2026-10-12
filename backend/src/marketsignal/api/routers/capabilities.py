"""Capabilities (final productization phase): whether live answer generation is available, so
the UI can show a clean "Live model unavailable" state. Never makes a provider call.

The response is an allowlist (``{generation: {available, reason}}``): no settings, model names,
keys or provider text ever leave this endpoint.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from marketsignal.config import Settings
from marketsignal.providers.llm.availability import GenerationStatus, generation_status

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


def _uses_configured_provider(request: Request, settings: Settings) -> bool:
    """True when the app still uses the provider seam built from settings (``_lazy_llm``).

    Tests and offline stand-ins replace ``app.state.llm_provider`` with a scripted provider that
    never reaches a network; generation is then available whatever the key says. The check
    compares code objects only: it never builds a provider."""
    from marketsignal.api.app import _lazy_llm  # local: app imports this router

    seam = getattr(request.app.state, "llm_provider", None)
    default_code = _lazy_llm(settings).__code__
    return getattr(seam, "__code__", None) is default_code


def current_generation_status(request: Request) -> GenerationStatus:
    settings: Settings = request.app.state.settings
    return generation_status(
        settings, uses_configured_provider=_uses_configured_provider(request, settings)
    )


@router.get("")
async def get_capabilities(request: Request) -> dict[str, Any]:
    return {"generation": current_generation_status(request).as_dict()}
