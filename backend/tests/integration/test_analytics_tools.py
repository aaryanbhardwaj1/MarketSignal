"""Governed analytics tools end to end: correctness, persistence, isolation and adversarial input.

Workspaces come from the harness: A holds SALES (CSV), SIZING (restricted XLSX, 2 sheets),
RETURNS and PURGEME; B holds its own SALES (canary values) and ONLYB."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound

from marketsignal.db.session import scoped_session
from marketsignal.tools.contracts import ToolCall, ToolResult
from marketsignal.tools.inprocess import InProcessToolTransport
from tests.fixtures.factories import make_xlsx
from tests.integration.test_ingestion_api import harness  # noqa: F401 - fixture
from tests.integration.test_tools_governance import World, world  # noqa: F401 - fixture

pytestmark = pytest.mark.integration

SALES_A = (
    "order_id,segment,region,rating,spend_usd,discount_pct,order_date,units\n"
    "O1,Gen Z,North,5,10.005,12.25,2026-01-03,1\n"
    "O2,Gen Z,South,4,20,12.35,2026-02-01,2\n"
    "O3,Millennial,North,,30,,2026-01-15,3\n"
    "O4,Millennial,West,3,15.5,10,2026-02-20,1\n"
    "O5,Gen X,East,5,0.125,20,2025-12-31,4\n"
    "O6,Gen Z,North,2,2,5,2026-03-01,2\n"
)
SALES_B = (
    "order_id,segment,region,rating,spend_usd,discount_pct,order_date,units\n"
    "B1,Gen Z,North,1,999,99,2026-01-03,9\n"
    "B2,Gen X,South,1,999,99,2026-01-04,9\n"
)
SALES_V2 = SALES_A + "O7,Gen X,West,1,100,0,2026-03-05,5\n"
SQLI = "x'; DROP TABLE dataset_rows;--"


@dataclass
class AW:
    w: World
    source_ids: dict[str, str]

    async def call(
        self, name: str, args: dict[str, Any], *, credential: str | None = None, idx: int = 0
    ) -> ToolResult:
        return await InProcessToolTransport(self.w.governor).call(
            ToolCall(f"a{idx}", name, args, step=1, call_index=idx),
            credential=self.w.token() if credential is None else credential,
        )

    async def ok(self, name: str, args: dict[str, Any], **kw: Any) -> dict[str, Any]:
        r = await self.call(name, args, **kw)
        assert r.ok, (r.error, r.observation)
        assert r.output is not None
        return r.output

    async def code(self, name: str, args: dict[str, Any], **kw: Any) -> str:
        r = await self.call(name, args, **kw)
        return "OK" if r.ok else (r.error.code if r.error else "?")

    async def stored(self, result_id: str) -> dict[str, Any]:
        async with scoped_session(self.w.factory, self.w.ws_a) as session:
            row = (
                await session.execute(
                    text(
                        "SELECT r.query_run_id, r.tool, r.spec, r.result, v.version, t.name "
                        "FROM analytics_results r "
                        "JOIN source_versions v ON v.id = r.source_version_id "
                        "JOIN dataset_tables t ON t.id = r.table_id WHERE r.id = :id"
                    ),
                    {"id": uuid.UUID(result_id)},
                )
            ).one()
        return dict(row._mapping)


async def _up(w: World, ws: str, name: str, data: bytes, **form: str) -> str:
    response = await w.h.upload(ws, name, data, **form)
    assert response.status_code in (200, 202), response.text
    return str(response.json()["source_id"])


@pytest.fixture
async def aw(world: World) -> AW:  # noqa: F811
    a, b = world.ws_a.workspace_code, world.ws_b.workspace_code
    xlsx = make_xlsx(
        {
            "Market": [
                ["market", "year", "value_usd_bn"],
                ["US", 2023, 15.1],
                ["US", 2024, 16.2],
                ["EU", 2023, 9.9],
            ],
            "Growth": [["market", "yoy_growth_pct"], ["US", 7.3], ["EU", 4.1]],
        }
    )
    ids = {
        "SALES": await _up(world, a, "sales.csv", SALES_A.encode(), source_code="SALES"),
        "SIZING": await _up(
            world,
            a,
            "sizing.xlsx",
            xlsx,
            source_code="SIZING",
            source_class="market",
            confidentiality="restricted",
        ),
        "PURGEME": await _up(world, a, "p.csv", b"k,v\nA,1\nB,2\n", source_code="PURGEME"),
        "SALES_B": await _up(world, b, "sales.csv", SALES_B.encode(), source_code="SALES"),
        "ONLYB": await _up(world, b, "only.csv", b"k,v\nA,1\nB,2\n", source_code="ONLYB"),
    }
    await world.h.drain()
    return AW(world, ids)


MEAN_RATING = {"fn": "mean", "column": "rating"}
GEN_Z_SHARE = {"fn": "share", "condition": {"column": "segment", "op": "eq", "value": "Gen Z"}}


async def test_describe_lists_only_visible_datasets(aw: AW) -> None:
    out = await aw.ok("describe_dataset", {}, credential=aw.w.token(max_conf="restricted"))
    ids = [d["dataset"] for d in out["datasets"]]
    assert ids == ["PURGEME:1", "RETURNS:1", "SALES:1", "SIZING:1", "SIZING:2"]
    assert all(d["columns"] == [] for d in out["datasets"])
    one = (await aw.ok("describe_dataset", {"dataset": "SALES:1"}))["datasets"][0]
    units = {c["name"]: (c["type"], c["unit"]) for c in one["columns"]}
    assert units["rating"] == ("numeric", "rating")
    assert units["spend_usd"] == ("numeric", "currency_usd")
    assert units["discount_pct"] == ("numeric", "percent")
    assert units["order_date"] == ("date", "date")
    assert units["units"] == ("numeric", "count")
    seg = next(c for c in one["columns"] if c["name"] == "segment")
    assert sorted(seg["levels"]) == ["Gen X", "Gen Z", "Millennial"]
    assert one["row_count"] == 6
    assert one["source_version"] == 1
    sizing = await aw.ok(
        "describe_dataset", {"dataset": "SIZING:2"}, credential=aw.w.token(max_conf="restricted")
    )
    assert sizing["datasets"][0]["table"] == "Growth"


async def test_aggregate_correct_and_persisted_identically(aw: AW) -> None:
    out = await aw.ok(
        "aggregate",
        {
            "dataset": "SALES:1",
            "metrics": [
                {"fn": "count"},
                MEAN_RATING,
                GEN_Z_SHARE,
                {"fn": "sum", "column": "spend_usd"},
            ],
        },
    )
    result = out["result"]
    values = {m["key"]: m for m in result["rows"][0]["metrics"]}
    assert values["count(*)"]["value"] == 6
    assert (values["mean(rating)"]["value"], values["mean(rating)"]["denominator"]) == (3.8, 5)
    assert values["share(segment=Gen Z)"]["value"] == 50.0
    assert values["sum(spend_usd)"]["value"] == 77.63
    assert values["sum(spend_usd)"]["unit"] == "currency_usd"
    assert result["warnings"] == ["NULLS_EXCLUDED"] == out["warnings"]
    assert result["workspace"] == aw.w.ws_a.workspace_code
    stored = await aw.stored(result["result_id"])
    assert stored["result"] == result  # the stored JSON is the returned JSON
    assert stored["spec"] == result["spec"]
    assert stored["tool"] == "aggregate"
    assert stored["query_run_id"] == aw.w.runs[aw.w.ws_a.workspace_id]
    assert (stored["version"], stored["name"]) == (1, result["table"])
    audit = [r for r in await aw.w.audit() if r["tool"] == "aggregate"]
    assert audit[-1]["status"] == "ok"
    assert audit[-1]["args"]["dataset"] == "SALES:1"


async def test_grouped_top_n_group_compare_and_filter_rows(aw: AW) -> None:
    top = await aw.ok(
        "aggregate",
        {
            "dataset": "SALES:1",
            "metrics": [{"fn": "sum", "column": "units"}],
            "group_by": ["region"],
            "order": {"by": "value", "direction": "desc"},
            "limit": 2,
        },
    )
    rows = top["result"]["rows"]
    assert [(r["group"]["region"], r["metrics"][0]["value"]) for r in rows] == [
        ("North", 6),
        ("East", 4),
    ]
    cmp = await aw.ok(
        "group_compare",
        {
            "dataset": "SALES:1",
            "metric": MEAN_RATING,
            "compare_column": "segment",
            "group_a": "Gen Z",
            "group_b": "Millennial",
        },
    )
    diff = cmp["result"]["difference"]
    assert diff["value"] == round(11 / 3 - 3, 2)  # 3.666... - 3 = 0.67
    assert diff["unit"] == "rating"
    listed = await aw.ok(
        "filter_rows",
        {
            "dataset": "SALES:1",
            "filters": [{"column": "order_date", "op": "gte", "value": "2026-02"}],
            "columns": ["order_id", "spend_usd"],
            "order_by": "spend_usd",
            "direction": "desc",
        },
    )
    got = listed["result"]["rows"]
    assert [r["group"]["order_id"] for r in got] == ["O2", "O4", "O6"]
    handles = [r["handle"] for r in got]
    assert all(isinstance(r["row_number"], int) and "@handle" not in r["group"] for r in got)
    resolved = await aw.ok("get_evidence", {"handles": handles})
    assert all(i["found"] for i in resolved["items"])  # rows are citable evidence


async def test_sql_like_and_malformed_payloads_never_reach_sql(aw: AW) -> None:
    cases: list[tuple[dict[str, Any], str]] = [
        ({"dataset": SQLI, "metrics": [{"fn": "count"}]}, "NOT_FOUND"),
        ({"dataset": "values->>'a'", "metrics": [{"fn": "count"}]}, "NOT_FOUND"),
        ({"dataset": "SALES:1 OR 1=1", "metrics": [{"fn": "count"}]}, "NOT_FOUND"),
        ({"dataset": "SALES:1", "metrics": [{"fn": "sum", "column": SQLI}]}, "VALIDATION_ERROR"),
        (
            {"dataset": "SALES:1", "metrics": [{"fn": "count"}], "group_by": ["values->>'a'"]},
            "VALIDATION_ERROR",
        ),
        (
            {
                "dataset": "SALES:1",
                "metrics": [{"fn": "count"}],
                "filters": [{"column": "1=1", "op": "is_null"}],
            },
            "VALIDATION_ERROR",
        ),
        (
            {
                "dataset": "SALES:1",
                "metrics": [{"fn": "count"}],
                "filters": [{"column": "segment", "op": "eq", "value": SQLI}],
            },
            "VALIDATION_ERROR",
        ),
        (
            {
                "dataset": "SALES:1",
                "metrics": [{"fn": "count"}],
                "filters": [{"column": "order_id", "op": "in", "values": [SQLI, "1=1"]}],
            },
            "OK",
        ),
        (
            {
                "dataset": "SALES:1",
                "metrics": [{"fn": "count"}],
                "filters": [{"column": "order_id", "op": "eq", "value": "O1\x00"}],
            },
            "VALIDATION_ERROR",
        ),
        (
            {"dataset": "SALES:1", "metrics": [{"fn": "median", "column": "segment"}]},
            "VALIDATION_ERROR",
        ),
        (
            {"dataset": "SALES:1", "metrics": [{"fn": "variance", "column": "rating"}]},
            "VALIDATION_ERROR",
        ),
        (
            {
                "dataset": "SALES:1",
                "metrics": [{"fn": "count"}],
                "filters": [{"column": "rating", "op": "in", "values": list(range(21))}],
            },
            "VALIDATION_ERROR",
        ),
        ({"dataset": "SALES:1", "metrics": [{"fn": "count"}] * 5}, "VALIDATION_ERROR"),
        (
            {
                "dataset": "SALES:1",
                "metrics": [{"fn": "count"}],
                "group_by": ["segment", "region", "order_id"],
            },
            "VALIDATION_ERROR",
        ),
        (
            {
                "dataset": "SALES:1",
                "metrics": [{"fn": "count"}],
                "filters": [{"column": "rating", "op": "is_null"}] * 6,
            },
            "VALIDATION_ERROR",
        ),
        (
            {"dataset": "SALES:1", "metrics": [{"fn": "count"}], "workspace_id": "x"},
            "VALIDATION_ERROR",
        ),
    ]
    for i, (args, expected) in enumerate(cases):
        assert await aw.code("aggregate", args, idx=i) == expected, args
    empty = await aw.ok("aggregate", cases[7][0])
    assert empty["result"]["warnings"] == ["EMPTY_SELECTION"]
    assert empty["result"]["rows"][0]["metrics"][0]["value"] == 0
    still = await aw.ok("aggregate", {"dataset": "SALES:1", "metrics": [{"fn": "count"}]})
    assert still["result"]["rows"][0]["metrics"][0]["value"] == 6  # table intact


async def test_foreign_workspace_datasets_are_not_found(aw: AW) -> None:
    assert await aw.code("aggregate", {"dataset": "ONLYB:1", "metrics": [{"fn": "count"}]}) == (
        "NOT_FOUND"
    )
    assert await aw.code("describe_dataset", {"dataset": "ONLYB:1"}) == "NOT_FOUND"
    assert await aw.code("filter_rows", {"dataset": "ONLYB:1"}) == "NOT_FOUND"
    a = await aw.call("filter_rows", {"dataset": "SALES:1"})
    assert "999" not in a.observation
    b = await aw.ok(
        "aggregate",
        {"dataset": "SALES:1", "metrics": [{"fn": "max", "column": "spend_usd"}]},
        credential=aw.w.token(aw.w.ws_b),
    )
    assert b["result"]["rows"][0]["metrics"][0]["value"] == 999
    assert b["result"]["workspace"] == aw.w.ws_b.workspace_code


async def test_class_claim_and_confidentiality_hide_datasets(aw: AW) -> None:
    fin = aw.w.token(source_classes=["financial"])
    assert (await aw.ok("describe_dataset", {}, credential=fin))["datasets"] == []
    count = {"dataset": "SALES:1", "metrics": [{"fn": "count"}]}
    assert await aw.code("aggregate", count, credential=fin) == "NOT_FOUND"
    listed = await aw.ok("describe_dataset", {})  # max_conf confidential < restricted
    assert [d["dataset"] for d in listed["datasets"]] == ["PURGEME:1", "RETURNS:1", "SALES:1"]
    sizing = {"dataset": "SIZING:1", "metrics": [{"fn": "sum", "column": "value_usd_bn"}]}
    assert await aw.code("aggregate", sizing) == "NOT_FOUND"
    restricted = aw.w.token(max_conf="restricted")
    out = await aw.ok("aggregate", sizing, credential=restricted)
    metric = out["result"]["rows"][0]["metrics"][0]
    assert (metric["value"], metric["unit"], metric["scale"]) == (41.2, "currency_usd", "billion")
    market = aw.w.token(max_conf="restricted", source_classes=["market"])
    assert await aw.code("aggregate", sizing, credential=market) == "OK"
    assert await aw.code("aggregate", count, credential=market) == "NOT_FOUND"


async def test_superseded_version_is_not_used(aw: AW) -> None:
    a = aw.w.ws_a.workspace_code
    await _up(aw.w, a, "sales.csv", SALES_V2.encode(), source_code="SALES")
    await aw.w.h.drain()
    out = await aw.ok("aggregate", {"dataset": "SALES:1", "metrics": [{"fn": "count"}]})
    assert out["result"]["source_version"] == 2
    assert out["result"]["rows"][0]["metrics"][0]["value"] == 7


async def test_purged_version_is_not_analysable(aw: AW) -> None:
    a = aw.w.ws_a.workspace_code
    deleted = await aw.w.h.client.delete(f"/api/workspaces/{a}/sources/{aw.source_ids['PURGEME']}")
    assert deleted.status_code == 200
    assert await aw.code("filter_rows", {"dataset": "PURGEME:1"}) == "NOT_FOUND"
    listed = await aw.ok("describe_dataset", {})
    assert "PURGEME:1" not in [d["dataset"] for d in listed["datasets"]]


async def test_purge_after_analytics_removes_results(aw: AW) -> None:
    out = await aw.ok("aggregate", {"dataset": "PURGEME:1", "metrics": [{"fn": "count"}]})
    a = aw.w.ws_a.workspace_code
    deleted = await aw.w.h.client.delete(f"/api/workspaces/{a}/sources/{aw.source_ids['PURGEME']}")
    assert deleted.status_code == 200
    with pytest.raises(NoResultFound):
        await aw.stored(out["result"]["result_id"])


async def test_configured_limits_and_timeout(aw: AW) -> None:
    tight = aw.w.governor_with(analytics_max_metrics=1, analytics_max_filter_values=2)
    transport = InProcessToolTransport(tight)
    two = {"dataset": "SALES:1", "metrics": [{"fn": "count"}, MEAN_RATING]}
    r = await transport.call(ToolCall("t1", "aggregate", two), credential=aw.w.token())
    assert r.error is not None
    assert r.error.code == "VALIDATION_ERROR"
    slow = aw.w.governor_with(analytics_timeout_s=1e-9)
    r = await InProcessToolTransport(slow).call(
        ToolCall("t2", "aggregate", {"dataset": "SALES:1", "metrics": [{"fn": "count"}]}),
        credential=aw.w.token(),
    )
    assert r.error is not None
    assert r.error.code == "TIMEOUT"
