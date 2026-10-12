# ruff: noqa: F811  (the imported `harness` fixture is re-bound as a test parameter)
"""Analytics browsing (final productization phase): datasets after a CSV upload, unknown and
malformed ids 404, the persisted-results list (paging, filters, test-run exclusion), purge and
workspace isolation."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.providers.llm.fake import FakeLLM
from marketsignal.tools.analytics_contracts import AnalyticsResult
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture
from tests.integration.test_runs_api import GOOD, _ask, _install, _scoped, _stream

pytestmark = pytest.mark.integration

CSV = b"segment,nps_score,orders_count\nGen Z,9,3\nMillennial,6,5\nGen Z,7,2\n"


async def _dataset_ws(h: Harness) -> tuple[str, str]:
    ws = await h.create_workspace()
    response = await h.upload(ws, "survey.csv", CSV, source_code="SURVEY-T")
    assert response.status_code in (200, 202), response.text
    await h.drain()
    source_id: str = response.json()["source_id"]
    return ws, source_id


def _result(ws: str, result_id: uuid.UUID) -> dict[str, Any]:
    metric = {
        "fn": "count",
        "key": "count(*)",
        "unit": "count",
        "exact": "3",
        "scale": "",
        "value": 3,
        "column": None,
        "numerator": None,
        "denominator": 3,
    }
    raw = {
        "result_id": str(result_id),
        "workspace": ws,
        "dataset": "SURVEY-T:1",
        "source_code": "SURVEY-T",
        "source_version": 1,
        "table": "survey",
        "operation": "aggregate",
        "spec": {"dataset": "SURVEY-T:1", "metrics": [{"fn": "count", "key": "count(*)"}]},
        "rows": [{"group": {}, "handle": None, "metrics": [metric], "row_number": None}],
        "rows_scanned": 3,
        "rows_matched": 3,
        "rounding": "half_even",
        "difference": None,
        "warnings": [],
    }
    return AnalyticsResult.model_validate(raw).model_dump(mode="json")


async def _insert_result(
    engine: AsyncEngine, ws: str, *, tool: str = "aggregate", run_id: str | None = None
) -> str:
    result_id = uuid.uuid4()
    body = _result(ws, result_id)
    async with engine.connect() as conn:
        await _scoped(conn, ws)
        await conn.execute(
            text(
                "INSERT INTO analytics_results (id, workspace_id, query_run_id, "
                "source_version_id, table_id, tool, spec, result) "
                "SELECT :id, workspace_id, :run, source_version_id, id, :tool, "
                "CAST(:spec AS jsonb), CAST(:result AS jsonb) FROM dataset_tables LIMIT 1"
            ),
            {
                "id": result_id,
                "run": run_id,
                "tool": tool,
                "spec": json.dumps(body["spec"]),
                "result": json.dumps(body),
            },
        )
        await conn.commit()
    return str(result_id)


async def test_datasets_list_and_detail(harness: Harness) -> None:
    ws, _ = await _dataset_ws(harness)
    listed = await harness.client.get(f"/api/workspaces/{ws}/analytics/datasets")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["truncated"] is False
    [info] = body["datasets"]
    assert info["dataset"] == "SURVEY-T:1"
    assert info["source_code"] == "SURVEY-T"
    assert info["source_version"] == 1
    assert info["row_count"] == 3
    assert info["columns"] == []
    assert set(info) == {
        "dataset",
        "source_code",
        "source_version",
        "title",
        "table",
        "source_class",
        "row_count",
        "columns",
    }

    detail = await harness.client.get(f"/api/workspaces/{ws}/analytics/datasets/SURVEY-T:1")
    assert detail.status_code == 200, detail.text
    columns = {c["name"]: c for c in detail.json()["columns"]}
    assert set(columns) == {"segment", "nps_score", "orders_count"}
    assert set(columns["nps_score"]) == {"name", "type", "unit", "scale", "levels", "non_empty"}
    assert columns["nps_score"]["unit"] == "rating"
    assert columns["orders_count"]["unit"] == "count"


async def test_unknown_malformed_and_foreign_datasets_are_404(harness: Harness) -> None:
    ws, _ = await _dataset_ws(harness)
    other = await harness.create_workspace()
    for code, dataset in (
        (ws, "NOPE:1"),
        (ws, "SURVEY-T:2"),
        (ws, "x';DROP TABLE sources;--"),
        (ws, "SURVEY-T"),
        (other, "SURVEY-T:1"),
    ):
        response = await harness.client.get(f"/api/workspaces/{code}/analytics/datasets/{dataset}")
        assert response.status_code == 404, dataset
        assert response.json()["error"]["code"] == "DATASET_NOT_FOUND"
    empty = await harness.client.get(f"/api/workspaces/{other}/analytics/datasets")
    assert empty.json() == {"datasets": [], "truncated": False}


async def test_results_list_paging_filters_and_test_runs(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    ws, _ = await _dataset_ws(harness)
    _install(harness, FakeLLM([GOOD], repeat_last=True))
    conversation, run = await _ask(harness, ws, "nps by segment", mode="standard")
    await _stream(harness, run["stream_url"])
    plain = [await _insert_result(app_engine, ws) for _ in range(3)]
    compare = await _insert_result(app_engine, ws, tool="group_compare")
    harness_result = await _insert_result(app_engine, ws, run_id=run["run_id"])

    url = f"/api/workspaces/{ws}/analytics/results"
    default = (await harness.client.get(url)).json()
    ids = [i["result_id"] for i in default["items"]]
    assert set(ids) == {*plain, compare}  # the harness (fake-llm) run's result is hidden
    assert default["next_cursor"] is None
    item = default["items"][0]
    assert set(item) == {
        "result_id",
        "tool",
        "dataset",
        "source_code",
        "source_version",
        "summary",
        "metrics",
        "query_run_id",
        "conversation_id",
        "created_at",
    }
    assert item["dataset"] == "SURVEY-T:1"
    assert item["metrics"] == ["count(*)"]
    assert isinstance(item["summary"], str)
    assert item["summary"]

    with_tests = (await harness.client.get(url, params={"include_test_runs": "true"})).json()
    linked = next(i for i in with_tests["items"] if i["result_id"] == harness_result)
    assert linked["query_run_id"] == run["run_id"]
    assert linked["conversation_id"] == conversation
    by_run = await harness.client.get(
        url, params={"run_id": run["run_id"], "include_test_runs": "true"}
    )
    assert [i["result_id"] for i in by_run.json()["items"]] == [harness_result]
    by_tool = (await harness.client.get(url, params={"tool": "group_compare"})).json()
    assert [i["result_id"] for i in by_tool["items"]] == [compare]

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params: dict[str, Any] = {"limit": 2, "include_test_runs": "true"}
        if cursor:
            params["cursor"] = cursor
        page = (await harness.client.get(url, params=params)).json()
        seen += [i["result_id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [i["result_id"] for i in with_tests["items"]]
    assert len(set(seen)) == 5

    bad = await harness.client.get(url, params={"tool": "drop_table"})
    assert bad.status_code == 422


async def test_results_isolated_and_removed_by_purge(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    ws, source_id = await _dataset_ws(harness)
    other = await harness.create_workspace()
    await _insert_result(app_engine, ws)
    other_list = await harness.client.get(f"/api/workspaces/{other}/analytics/results")
    assert other_list.json() == {"items": [], "next_cursor": None}

    purge = await harness.client.delete(f"/api/workspaces/{ws}/sources/{source_id}")
    assert purge.status_code in (200, 202), purge.text
    await harness.drain()
    after = await harness.client.get(f"/api/workspaces/{ws}/analytics/results")
    assert after.json()["items"] == []
    datasets = await harness.client.get(f"/api/workspaces/{ws}/analytics/datasets")
    assert datasets.json()["datasets"] == []
