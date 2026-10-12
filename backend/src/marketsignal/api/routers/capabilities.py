"""Capabilities (final productization phase): whether live answer generation is available, so
the UI can show a clean "Live model unavailable" state. Never makes a provider call.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])
