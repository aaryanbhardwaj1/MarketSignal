"""Run telemetry (final productization phase, developer tools): summary, runs and run detail
from persisted run records. Read-only, workspace-scoped; never exposes model reasoning or
answer content.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/workspaces/{ws}/telemetry", tags=["telemetry"])
