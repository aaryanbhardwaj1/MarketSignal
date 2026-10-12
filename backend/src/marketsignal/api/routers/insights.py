"""Curated analyst brief (final productization phase): key signals, growth opportunities and
named analyses from a versioned fixture, re-resolved against current evidence and recomputed
deterministically on every request. Read-only; never persists analytics results.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/workspaces/{ws}", tags=["insights"])
