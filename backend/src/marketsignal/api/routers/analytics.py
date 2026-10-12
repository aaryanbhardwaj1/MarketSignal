"""Analytics browsing (final productization phase): datasets and persisted computed results.

Read-only, workspace-scoped (forced RLS). Owned by the core-API workstream.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/workspaces/{ws}/analytics", tags=["analytics"])
