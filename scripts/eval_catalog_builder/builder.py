"""Assembles the catalog and per-run item files from the section mixins."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .analytics import AnalyticsSections
from .common import Sources
from .grounded import GroundedSections
from .items import ItemSections
from .research import ResearchSections
from .retrieval import RetrievalSections
from .summary import SummarySections


class Builder(
    RetrievalSections,
    GroundedSections,
    ResearchSections,
    AnalyticsSections,
    SummarySections,
    ItemSections,
):
    """All catalog sections; each mixin owns one area of the catalog."""


def build(root: Path, built_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    src = Sources(root)
    b = Builder(src)
    retrieval = b.retrieval()
    grounded = b.grounded()
    research = b.research()
    analytics = b.analytics()
    superseded = b.superseded()
    caveats = b.caveats()
    items, failure_runs = b.items_and_failures()
    catalog = {
        "schema_version": 1,
        "built_at": built_at,
        "sources": src.listing(),
        "caveats": caveats,
        "overview": b.overview(retrieval, grounded, analytics),
        "retrieval": retrieval,
        "grounded": grounded,
        "research_tradeoff": research,
        "analytics": analytics,
        "superseded": superseded,
        "failure_runs": failure_runs,
    }
    files = {rid: {"run_id": rid, "items": rows} for rid, rows in items.items()}
    return catalog, files


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"
