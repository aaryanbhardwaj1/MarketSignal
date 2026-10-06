"""Micro-benchmark: governed ``aggregate`` latency on the seeded NORTHSTAR REVIEWS (800 rows)
and SURVEY-2026 (600 rows) tables, uploaded read-only from ``seed_data`` into a harness
workspace. Prints p50/p95 (``-s`` to see them) and asserts a generous bound."""

from __future__ import annotations

import csv
import io
import statistics
import time
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

import pytest

from marketsignal.tools.contracts import ToolCall
from marketsignal.tools.inprocess import InProcessToolTransport
from tests.integration.test_ingestion_api import harness  # noqa: F401 - fixture
from tests.integration.test_tools_governance import World, world  # noqa: F401 - fixture

pytestmark = pytest.mark.integration

SEED = Path(__file__).resolve().parents[3] / "seed_data" / "generated" / "northstar"
RUNS = 25
P95_BOUND_MS = 1500.0

CASES: dict[str, dict[str, Any]] = {
    "REVIEWS": {
        "dataset": "REVIEWS:1",
        "metrics": [
            {"fn": "count"},
            {"fn": "mean", "column": "rating"},
            {"fn": "share", "condition": {"column": "rating", "op": "lte", "value": 2}},
        ],
        "group_by": ["category"],
        "order": {"by": "value", "metric_index": 1, "direction": "desc"},
    },
    "SURVEY-2026": {
        "dataset": "SURVEY-2026:1",
        "metrics": [{"fn": "count"}, {"fn": "mean", "column": "nps"}],
        "filters": [{"column": "nps", "op": "not_null"}],
        "group_by": ["segment", "region"],
    },
}
FILES = {
    "REVIEWS": "Northstar_Product_Reviews.csv",
    "SURVEY-2026": "Northstar_Customer_Survey_2026.csv",
}


async def test_aggregate_latency_on_seed_tables(world: World) -> None:  # noqa: F811
    if not SEED.exists():
        pytest.skip("seed data not generated")
    ws = world.ws_a.workspace_code
    for code, name in FILES.items():
        response = await world.h.upload(ws, name, (SEED / name).read_bytes(), source_code=code)
        assert response.status_code in (200, 202), response.text
    await world.h.drain()
    transport = InProcessToolTransport(world.governor)
    for code, args in CASES.items():
        timings = []
        for i in range(RUNS):
            start = time.perf_counter()
            r = await transport.call(ToolCall(f"p{i}", "aggregate", args), credential=world.token())
            timings.append((time.perf_counter() - start) * 1000)
            assert r.ok, (r.error, r.observation)
        assert r.output is not None
        scanned = r.output["result"]["rows_scanned"]
        p50 = statistics.median(timings)
        p95 = statistics.quantiles(timings, n=20)[18]
        print(f"\nanalytics aggregate {code}: rows={scanned} p50={p50:.1f}ms p95={p95:.1f}ms")
        assert p95 < P95_BOUND_MS
    # cross-check against an independent computation straight from the seed CSV
    text = (SEED / FILES["REVIEWS"]).read_text(encoding="utf-8-sig")
    by_cat: dict[str, list[Decimal]] = {}
    for rec in csv.DictReader(io.StringIO(text)):
        if rec["rating"].strip():
            by_cat.setdefault(rec["category"], []).append(Decimal(rec["rating"]))
    r = await transport.call(ToolCall("x", "aggregate", CASES["REVIEWS"]), credential=world.token())
    assert r.output is not None
    for row in r.output["result"]["rows"]:
        ratings = by_cat[row["group"]["category"]]
        expected = (sum(ratings) / len(ratings)).quantize(Decimal("0.01"), ROUND_HALF_EVEN)
        assert row["metrics"][0]["value"] == len(ratings)
        assert Decimal(str(row["metrics"][1]["value"])) == expected
