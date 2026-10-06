"""Independent numeric-faithfulness re-check of stored grounded-eval answers (Phase 3/4).

The verifier reports what it dropped; this checks what it *kept*. For every stored answer in a
grounded-eval results file (``results.json`` or a per-mode ``results-<mode>.json``), each unit's
canonical ``[[HANDLE]]`` citations are resolved through the evidence API and every number in the
unit is checked against the resolved parent texts with the verifier's support rule. Uncited units
(``[inference]`` and gap statements) are checked against the run's whole pack. The logic lives in
``marketsignal.evaluation.numeric_recheck`` (the grounded harness runs the cited-unit part inline
as ``unsupported_claim_rate``). Writes ``numeric-recheck[-<mode>].json`` next to each results file.

    uv --directory backend run python ../scripts/phase3_numeric_recheck.py \
        ../eval/baselines/phase3/live-v0/results.json [more results files] \
        [--items ../eval/datasets/research-v0/items.json]

Workspaces come from each stored item (``workspace``); older results files without it fall back
to ``--items`` (default grounded-v0).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient

from marketsignal.api.app import create_app
from marketsignal.config import get_settings
from marketsignal.evaluation.numeric_recheck import fetch_texts, recheck_content
from marketsignal.generation.types import CANONICAL_RE

DEFAULT_ITEMS = Path(__file__).resolve().parents[1] / "eval/datasets/grounded-v0/items.json"


async def recheck(client: AsyncClient, item: dict[str, Any], ws: str) -> dict[str, Any]:
    content = item.get("content") or ""
    pack = list(item.get("pack_handles") or [])
    texts = await fetch_texts(client, ws, set(CANONICAL_RE.findall(content)) | set(pack))
    return {"id": item["id"], **recheck_content(content, texts, pack=pack)}


async def recheck_all(
    results: list[dict[str, Any]], workspaces: dict[str, str]
) -> list[list[dict[str, Any]]]:
    app = create_app(get_settings())
    out: list[list[dict[str, Any]]] = []
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://recheck") as client,
    ):
        for result in results:
            rows = []
            for item in result["items"]:
                if item.get("content"):
                    ws = item.get("workspace") or workspaces[item["id"]]
                    rows.append(await recheck(client, item, ws))
            out.append(rows)
    return out


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "answers": len(rows),
        "cited_units": sum(r["cited_units"] for r in rows),
        "uncited_units": sum(r["uncited_units"] for r in rows),
        "cited_units_with_unsupported_numbers": sum(
            1 for r in rows for u in r["unsupported"] if u["scope"] == "cited"
        ),
        "uncited_units_with_numbers_absent_from_pack": sum(
            1 for r in rows for u in r["unsupported"] if u["scope"] == "pack"
        ),
        "unresolvable_citations": sum(len(r["unresolvable_citations"]) for r in rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    args = parser.parse_args(argv)
    dataset = json.loads(args.items.read_text())["items"]
    workspaces = {i["id"]: i["workspace"] for i in dataset}
    results = [json.loads(path.read_text()) for path in args.results]
    for path, rows in zip(args.results, asyncio.run(recheck_all(results, workspaces)), strict=True):
        summary = _summary(rows)
        suffix = path.stem.removeprefix("results")
        out = path.parent / f"numeric-recheck{suffix}.json"
        out.write_text(json.dumps({"summary": summary, "items": rows}, indent=1) + "\n")
        print(path.name, json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
