"""Rebuild live grounded-eval runs for failure analysis (Phase 3).

For each item id, find its run from the live-v0 evaluation window, split the stored ``token``
events into one draft per attempt (``draft_reset`` boundaries), rebuild the evidence pack
through the production retrieval and pack code (and check it equals the stored pack_handles),
then re-run the deterministic verifier on every draft. Writes one Markdown file per item.
The cases and their classification are in eval/baselines/phase3/live-v0/FAILURE_ANALYSIS.md.
No model is called.

    uv --directory backend run python ../scripts/phase3_inspect_run.py OUT_DIR G-R0-055 [...]
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

from marketsignal.api.app import create_app
from marketsignal.config import get_settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import scoped_session, unscoped_session
from marketsignal.generation.pack import PackLimits, build_pack
from marketsignal.generation.verifier import verify_answer
from marketsignal.retrieval.types import RetrievalFilters
from marketsignal.runs import store

ROOT = Path(__file__).resolve().parents[1]
RESULTS = json.loads((ROOT / "eval/baselines/phase3/live-v0/results.json").read_text())
DATASET = json.loads((ROOT / "eval/datasets/grounded-v0/items.json").read_text())
ITEMS = {i["id"]: i for i in DATASET["items"]}
END = datetime.fromisoformat(RESULTS["run"]["at"]) + timedelta(seconds=5)
START = END - timedelta(seconds=RESULTS["elapsed_s"] + 10)


def _drafts(events: list[store.StoredEvent]) -> list[str]:
    drafts: list[str] = []
    current: list[str] = []
    for event in events:
        if event.type == "token":
            current.append(str(event.payload.get("text", "")))
        elif event.type == "draft_reset":
            drafts.append("".join(current))
            current = []
    if current:
        drafts.append("".join(current))
    return drafts


async def _find_run(app: Any, item: dict[str, Any]) -> tuple[WorkspaceScope, Any, list[str]]:
    factory = app.state.session_factory
    async with unscoped_session(factory) as session:
        ws_id = (
            await session.execute(
                text("SELECT id FROM workspaces WHERE code = :c"), {"c": item["workspace"]}
            )
        ).scalar_one()
    scope = WorkspaceScope(ws_id, item["workspace"])
    async with scoped_session(factory, scope) as session:
        run_id, pack_handles = (
            await session.execute(
                text(
                    "SELECT id, pack_handles FROM query_runs WHERE workspace_id = :ws "
                    "AND original_query = :q AND created_at BETWEEN :a AND :b "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"ws": ws_id, "q": item["question"], "a": START, "b": END},
            )
        ).one()
    return scope, run_id, list(pack_handles or [])


async def inspect(app: Any, item_id: str, out_dir: Path) -> None:
    settings = get_settings()
    factory = app.state.session_factory
    item = ITEMS[item_id]
    scope, run_id, stored_pack = await _find_run(app, item)
    events = await store.load_events(factory, scope, run_id, 0)
    max_conf = await app.state.run_executor()._llm_max_confidentiality(scope)
    filters = RetrievalFilters.of(item.get("source_classes") or (), (), max_conf)
    result = await app.state.retrieval_service.search(
        factory, scope, item["question"], filters, top_k=settings.pack_candidates
    )
    limits = PackLimits(
        settings.pack_max_items,
        settings.pack_max_tokens,
        settings.pack_item_max_tokens,
        settings.pack_candidates,
    )
    pack = await build_pack(factory, scope, result.parents, limits)
    same = list(pack.handles()) == stored_pack
    lines = [
        f"# {item_id} ({item['category']}, expect={item['expect']})",
        f"Question: {item['question']}",
        f"Gold: {json.dumps(item.get('gold_facts'))[:1500]}",
        f"Pack reconstructed identical to stored: {same}",
        "",
        "## Pack",
    ]
    for it in pack.items:
        lines.append(f"### {it.alias} {it.handle} [{it.source_class}] {it.locator_label}")
        lines.append(f"{it.text}\n")
    drafts = _drafts(events)
    for n, draft in enumerate(drafts, 1):
        verified = verify_answer(draft, pack, pack_truncated=pack.truncated)
        lines += [
            f"## Attempt {n} draft (streamed text)",
            draft,
            "",
            f"### Verifier re-run: ok={verified.ok}",
            json.dumps(verified.report.as_dict(), indent=1, default=str),
        ]
    final = next((e.payload for e in events if e.type == "final"), {})
    lines += ["## Stored final content", str(final.get("content", ""))]
    _write(out_dir / f"{item_id}.md", "\n".join(lines) + "\n")
    print(item_id, "pack_same=", same, "attempts=", len(drafts))


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


async def main(out_dir: Path, ids: list[str]) -> int:
    app = create_app(get_settings())
    async with app.router.lifespan_context(app):
        for item_id in ids:
            await inspect(app, item_id, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(Path(sys.argv[1]), sys.argv[2:])))
