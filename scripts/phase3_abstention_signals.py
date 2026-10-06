"""Retrieval-score diagnostics for the weak-evidence abstention question (Phase 3).

For every grounded-v0 item except the empty-pack ones, run the production retrieval path and
record the top dense cosine, the top lexical score and the query's maximum possible lexical
score (sum of term IDFs). Writes eval/baselines/phase3/abstention-signals.json (one row per
item) and abstention-signals.meta.json (retrieval config hash, corpus version, dataset).

The analysis in docs/GROUNDED_ANSWERING.md uses these rows to show that insufficient-evidence
questions are not separable from answerable ones by score, which is why score-based abstention
is deferred. Needs the seeded local database (``make up migrate seed``); no LLM is called.

    uv --directory backend run python ../scripts/phase3_abstention_signals.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from marketsignal.api.app import create_app
from marketsignal.config import get_settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import unscoped_session

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "eval" / "datasets" / "grounded-v0" / "items.json"
OUT = ROOT / "eval" / "baselines" / "phase3" / "abstention-signals.json"
META = OUT.with_suffix(".meta.json")


def _row(item: dict[str, Any], stages: dict[str, Any]) -> dict[str, Any]:
    dense = stages.get("dense") or []
    lexical = stages.get("lexical") or []
    query = stages.get("lexical_query") or {}
    return {
        "id": item["id"],
        "expect": item["expect"],
        "dense_top": dense[0]["score"] if dense else None,
        "lex_top": lexical[0]["score"] if lexical else None,
        "lex_max_possible": round(sum(query.get("idf") or []), 3),
    }


async def main() -> int:
    app = create_app(get_settings())
    items = json.loads(DATASET.read_text())["items"]
    rows: list[dict[str, Any]] = []
    config_hashes: set[str] = set()
    corpus_versions: dict[str, Any] = {}
    async with app.router.lifespan_context(app):
        factory = app.state.session_factory
        async with unscoped_session(factory) as session:
            result = await session.execute(text("SELECT id, code FROM workspaces"))
            workspaces = {str(code): ws_id for ws_id, code in result.all()}
        service = app.state.retrieval_service
        for item in items:
            if item["category"] == "empty_pack":
                continue
            scope = WorkspaceScope(workspaces[item["workspace"]], item["workspace"])
            found = await service.search(factory, scope, item["question"])
            rows.append(_row(item, found.trace.stages))
            config_hashes.add(found.trace.config_hash)
            corpus_versions[item["workspace"]] = found.trace.corpus_version
    OUT.write_text(json.dumps(rows, indent=1) + "\n")
    meta = {
        "dataset": "grounded-v0",
        "items": len(rows),
        "retrieval_config_hashes": sorted(config_hashes),
        "corpus_versions": corpus_versions,
        "generator": "scripts/phase3_abstention_signals.py",
    }
    META.write_text(json.dumps(meta, indent=1, default=str) + "\n")
    print(f"wrote {len(rows)} rows to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
