"""RAGAS exporter against a real database: each item's passage texts resolve read-only inside
its own workspace's RLS scope only; a handle naming another workspace is never resolved."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.db.engine import create_session_factory
from marketsignal.evaluation.ragas_export import (
    ExportError,
    RunSpec,
    export,
    resolve_texts,
    texts_sha256,
)
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401

pytestmark = pytest.mark.integration

FIT = "Fit inconsistency is the top frustration for young shoppers in this study."
OTHER = "Delivery speed complaints doubled in the third quarter of the year."


async def _seed(h: Harness, ws: str, body: str) -> None:
    response = await h.upload(ws, "memo.md", f"# Notes\n\n{body}\n".encode(), source_code="MEMO")
    assert response.status_code in (200, 202), response.text
    await h.drain()


async def _handle(engine: AsyncEngine, ws: str, needle: str) -> tuple[str, str]:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT set_config('app.workspace_id', "
                "(SELECT id::text FROM workspaces WHERE code = :c), true)"
            ),
            {"c": ws},
        )
        rows = (await conn.execute(text("SELECT handle, text FROM parent_chunks"))).all()
    hits = [(str(h), str(t)) for h, t in rows if needle in re.sub(r"\s+", " ", t)]
    assert len(hits) == 1, rows
    return hits[0]


@pytest.fixture
async def seeded(harness: Harness, app_engine: AsyncEngine) -> tuple[str, str, str, str]:  # noqa: F811
    ws, other = await harness.create_workspace(), await harness.create_workspace()
    await _seed(harness, ws, FIT)
    await _seed(harness, other, OTHER)
    handle, passage = await _handle(app_engine, ws, FIT)
    foreign, _ = await _handle(app_engine, other, OTHER)
    return ws, handle, passage, foreign


async def test_resolve_texts_is_workspace_scoped(
    seeded: tuple[str, str, str, str], app_engine: AsyncEngine
) -> None:
    ws, handle, passage, foreign = seeded
    factory = create_session_factory(app_engine)
    texts = await resolve_texts(
        factory, ws, [handle, foreign, "not a handle", f"{ws}/NOPE@v1:S1.B1"]
    )
    assert texts == {
        handle: passage,
        foreign: None,
        "not a handle": None,
        f"{ws}/NOPE@v1:S1.B1": None,
    }
    with pytest.raises(ExportError, match="not found"):
        await resolve_texts(factory, "NO-SUCH-WS", [handle])


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


async def test_export_resolves_each_item_in_its_own_workspace(
    seeded: tuple[str, str, str, str], app_engine: AsyncEngine, tmp_path: Path
) -> None:
    ws, handle, passage, foreign = seeded
    other = foreign.split("/", 1)[0]
    missing = f"{ws}/NOPE@v1:S1.B1"

    def item(item_id: str, workspace: str, gold: list[str], expect: str = "answer") -> Any:
        return {
            "id": item_id,
            "workspace": workspace,
            "category": "fact",
            "question": f"{item_id}?",
            "expect": expect,
            "gold_facts": [{"handles": gold}],
        }

    def result(item_id: str, pack: list[str]) -> Any:
        return {
            "id": item_id,
            "question": f"{item_id}?",
            "pack_handles": pack,
            "cited_handles": pack[:1],
            "content": f"Answer {item_id} [[{pack[0]}]].",
        }

    gold = [
        item("I1", ws, [handle]),
        item("I2", ws, [foreign]),  # cross-workspace gold handle
        item("I3", ws, [], expect="insufficient"),
        item("I4", other, [foreign]),  # resolved in its own workspace
        item("I5", ws, [missing]),
        item("I6", other, [foreign]),  # pack names the other workspace's passage
    ]
    results = [
        result("I1", [handle]),
        result("I2", [handle]),
        result("I3", [handle]),
        result("I4", [foreign]),
        result("I5", [handle]),
        result("I6", [foreign, handle]),
    ]
    _write(tmp_path / "eval/datasets/x/items.json", {"items": gold})
    _write(tmp_path / "eval/baselines/x/results.json", {"items": results[::-1], "run": {}})
    spec = RunSpec(
        "x", "X", "eval/datasets/x/items.json", (("standard", "eval/baselines/x/results.json"),)
    )

    doc = await export(
        spec,
        create_session_factory(app_engine),
        created_at="2026-10-14T00:00:00+00:00",
        git_sha="abc1234",
        root=tmp_path,
    )

    assert doc["run"]["split"] == "all"
    assert [s["item_id"] for s in doc["samples"]] == ["I1", "I4"]
    i1, i4 = doc["samples"]
    assert i1["response"] == "Answer I1."
    assert i1["retrieved_contexts"] == i1["reference_contexts"] == [passage]
    assert OTHER in i4["retrieved_contexts"][0]
    assert doc["excluded"] == [
        {"item_id": "I2", "configuration": "standard", "reason": "foreign_handle"},
        {"item_id": "I3", "configuration": "standard", "reason": "abstention_expected"},
        {"item_id": "I5", "configuration": "standard", "reason": "unresolvable_handle"},
        {"item_id": "I6", "configuration": "standard", "reason": "foreign_handle"},
    ]
    assert doc["corpus"] == {
        "workspace": None,
        "workspaces": sorted([ws, other]),
        "texts_sha256": texts_sha256(doc["samples"]),
    }
