"""Independent numeric-faithfulness re-check of stored live answers (Phase 3).

The verifier reports what it dropped; this checks what it *kept*. For every stored answer in a
grounded-eval results file, each unit's canonical ``[[HANDLE]]`` citations are resolved through
the evidence API (the stored text, not the run's pack), and every number in the unit is checked
against the resolved parent texts with the same support rule the verifier uses. Units without
citations (``[inference]`` and gap statements) are reported separately and are checked against
the run's whole pack. Writes ``numeric-recheck.json`` next to the results file.

    uv --directory backend run python ../scripts/phase3_numeric_recheck.py \
        ../eval/baselines/phase3/live-v0/results.json
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient

from marketsignal.api.app import create_app
from marketsignal.config import get_settings
from marketsignal.generation import contract
from marketsignal.generation.types import CANONICAL_RE


async def _texts(client: AsyncClient, ws: str, handles: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for handle in sorted(handles):
        response = await client.get(f"/api/workspaces/{ws}/evidence/{handle}")
        if response.status_code == 200:
            out[handle] = str(response.json()["text"])
    return out


def _units(content: str) -> list[tuple[str, str]]:
    sections = contract.parse_sections(content)
    return [(name, unit) for name, body in sections.items() for unit in contract.split_units(body)]


async def recheck(client: AsyncClient, item: dict[str, Any], ws: str) -> dict[str, Any]:
    content = item.get("content") or ""
    pack = set(item.get("pack_handles") or [])
    cited_all = set(CANONICAL_RE.findall(content))
    texts = await _texts(client, ws, cited_all | pack)
    pack_values = contract.number_values(texts[h] for h in pack if h in texts)
    cited_units = uncited_units = 0
    unsupported: list[dict[str, Any]] = []
    for section, unit in _units(content):
        handles = set(CANONICAL_RE.findall(unit))
        if handles:
            cited_units += 1
            values = contract.number_values(texts[h] for h in handles if h in texts)
            scope = "cited"
        else:
            uncited_units += 1
            values = pack_values
            scope = "pack"
        missing = contract.unsupported_numbers(CANONICAL_RE.sub("", unit), values)
        if missing:
            unsupported.append(
                {
                    "section": section,
                    "scope": scope,
                    "numbers": [m.text for m in missing],
                    "unit": unit[:240],
                }
            )
    return {
        "id": item["id"],
        "cited_units": cited_units,
        "uncited_units": uncited_units,
        "unresolvable_citations": sorted(cited_all - set(texts)),
        "unsupported": unsupported,
    }


async def recheck_all(results: dict[str, Any], workspaces: dict[str, str]) -> list[dict[str, Any]]:
    app = create_app(get_settings())
    rows: list[dict[str, Any]] = []
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://recheck") as client,
    ):
        for item in results["items"]:
            if item.get("content"):
                rows.append(await recheck(client, item, workspaces[item["id"]]))
    return rows


def main(results_path: Path) -> int:
    results = json.loads(results_path.read_text())
    dataset = Path(__file__).resolve().parents[1] / "eval/datasets/grounded-v0/items.json"
    workspaces = {i["id"]: i["workspace"] for i in json.loads(dataset.read_text())["items"]}
    rows = asyncio.run(recheck_all(results, workspaces))
    summary = {
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
    out = results_path.parent / "numeric-recheck.json"
    out.write_text(json.dumps({"summary": summary, "items": rows}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
