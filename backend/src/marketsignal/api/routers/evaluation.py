"""Evaluation catalog (final productization phase, developer tools): validated evaluation
artifacts served from a precomputed catalog. Dev-only router (not mounted in prod).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/dev/eval", tags=["evaluation"])
