"""Production retrieval through the API, against real ingestion, as ``ms_app`` under RLS.

Uses the deterministic hash embedder and a keyword reranker (the real ONNX models are measured by
the evaluation harness); what is tested here is the contract: isolation, active versions only,
filters, determinism, anchors that resolve to valid highlights, graceful degradation, traces.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.providers.embeddings import FailingEmbedder, HashEmbedder
from marketsignal.providers.rerankers import FailingReranker, KeywordReranker
from marketsignal.retrieval.pipeline import LEXICAL_FALLBACK, RetrievalService
from marketsignal.retrieval.rerank import RERANKER_UNAVAILABLE, RerankExecutor
from marketsignal.retrieval.types import RetrievalConfig
from tests.fixtures.factories import make_csv, make_docx
from tests.integration.test_ingestion_api import Harness, harness  # noqa: F401 - fixture

pytestmark = pytest.mark.integration

CANARY_A = "Zephyrine lattice stitching reduced seam failures by 31 percent."
CANARY_B = "Quorvex tread compound lowered outsole wear by 44 percent."


def _install(h: Harness, *, reranker: Any = None, embedder: Any = None) -> None:
    app = h.client._transport.app  # type: ignore[attr-defined]
    app.state.query_embedder = lambda: embedder or HashEmbedder(model_id="hash-test")
    previous: RerankExecutor = app.state.rerank_executor
    app.state.rerank_executor = RerankExecutor(reranker or KeywordReranker())
    previous.shutdown()  # the app lifespan shuts down whichever executor is installed last
    app.state.retrieval_service = RetrievalService(
        RetrievalConfig(embed_model_id="hash-test"),
        embedder=lambda: app.state.query_embedder(),
        rerank_executor=app.state.rerank_executor,
    )


async def _search(h: Harness, ws: str, q: str, **params: Any) -> dict[str, Any]:
    response = await h.client.get(f"/api/workspaces/{ws}/search", params={"q": q, **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _md(*paragraphs: str) -> bytes:
    return ("# Notes\n\n" + "\n\n".join(paragraphs) + "\n").encode()


async def _seed(h: Harness, ws: str, canary: str) -> None:
    await h.upload(ws, "memo.md", _md("Background on stores.", canary), source_code="MEMO")
    await h.upload(
        ws,
        "survey.csv",
        make_csv(
            [
                ["id", "segment", "comment"],
                ["S1", "Gen Z", "The leggings run small and the tees run large."],
                ["S2", "Gen Z", "Delivery took too long for my custom pair."],
            ]
        ),
        source_code="SURVEY",
    )
    await h.drain()


async def test_search_is_workspace_isolated_and_traces_are_scoped(
    harness: Harness,  # noqa: F811
    app_engine: AsyncEngine,
) -> None:
    _install(harness)
    a, b = await harness.create_workspace(), await harness.create_workspace()
    await _seed(harness, a, CANARY_A)
    await _seed(harness, b, CANARY_B)
    for mode in ("full", "hybrid", "dense", "lexical"):
        for q in ("Quorvex tread compound outsole", "Zephyrine lattice stitching seam"):
            body = await _search(harness, a, q, mode=mode, k=50)
            assert all(i["handle"].startswith(f"{a}/") for i in body["items"]), (mode, q)
    own = await _search(harness, a, "Zephyrine lattice stitching seam failures", mode="lexical")
    assert own["items"][0]["handle"].startswith(f"{a}/MEMO@v1:")
    foreign = await _search(harness, a, "Quorvex tread compound outsole wear", mode="lexical")
    assert foreign["items"] == []
    trace_id = own["trace_id"]
    assert trace_id
    async with app_engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT set_config('app.workspace_id', "
                "(SELECT id::text FROM workspaces WHERE code = :c), true)"
            ),
            {"c": b},
        )
        visible = (
            await conn.execute(
                text("SELECT count(*) FROM retrieval_traces WHERE id = CAST(:id AS uuid)"),
                {"id": trace_id},
            )
        ).scalar_one()
    assert visible == 0  # B cannot read A's trace


async def test_trace_records_every_stage(harness: Harness, app_engine: AsyncEngine) -> None:  # noqa: F811
    _install(harness)
    ws = await harness.create_workspace()
    await _seed(harness, ws, CANARY_A)
    body = await _search(harness, ws, "Zephyrine lattice stitching")
    async with app_engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT set_config('app.workspace_id', "
                "(SELECT id::text FROM workspaces WHERE code = :c), true)"
            ),
            {"c": ws},
        )
        row = (
            await conn.execute(
                text(
                    "SELECT stages, timings, flags, result_handles, origin "
                    "FROM retrieval_traces WHERE id = CAST(:id AS uuid)"
                ),
                {"id": body["trace_id"]},
            )
        ).one()
    stages, timings, flags, handles, origin = row
    assert {"dense", "lexical", "lexical_query", "fused", "pool", "rerank", "final"} <= set(stages)
    assert {"embed_ms", "dense_ms", "lexical_ms", "fusion_ms", "rerank_ms", "total_ms"} <= set(
        timings
    )
    assert flags == []
    assert origin == "api"
    assert handles[0] == body["items"][0]["handle"]
    final = stages["final"][0]
    assert final["anchor"]["child_id"] == body["items"][0]["anchor"]["child_id"]


async def test_every_returned_anchor_resolves_to_a_valid_highlight(harness: Harness) -> None:  # noqa: F811
    _install(harness)
    ws = await harness.create_workspace()
    await _seed(harness, ws, CANARY_A)
    body = await _search(harness, ws, "leggings tees custom pair delivery stores", k=20)
    assert body["items"]
    for item in body["items"]:
        evidence = (
            await harness.client.get(
                f"/api/workspaces/{ws}/evidence/{item['handle']}",
                params={"child_id": item["anchor"]["child_id"]},
            )
        ).json()
        hl = evidence["highlight"]
        assert hl["child_id"] == item["anchor"]["child_id"]
        assert (hl["char_start"], hl["char_end"]) == (
            item["anchor"]["char_start"],
            item["anchor"]["char_end"],
        )
        assert evidence["text"][hl["char_start"] : hl["char_end"]] == hl["text"]
        snippet = item["snippet"]
        marked = snippet["text"][snippet["mark_start"] : snippet["mark_end"]]
        assert marked
        assert marked in hl["text"]


async def test_only_active_versions_are_searched(harness: Harness) -> None:  # noqa: F811
    _install(harness)
    ws = await harness.create_workspace()
    await harness.upload(
        ws, "memo.md", _md("Old figure: Vexlar churn was 12 percent."), source_code="M"
    )
    await harness.drain()
    await harness.upload(
        ws, "memo.md", _md("New figure: Draxim churn is 9 percent."), source_code="M"
    )
    await harness.drain()
    old = await _search(harness, ws, "Vexlar churn", mode="lexical")
    new = await _search(harness, ws, "Draxim churn", mode="lexical")
    assert old["items"] == []
    assert [i["handle"] for i in new["items"]] == [f"{ws}/M@v2:S1.B1"]
    source_id = (await harness.client.get(f"/api/workspaces/{ws}/sources")).json()[0]["source_id"]
    assert (
        await harness.client.delete(f"/api/workspaces/{ws}/sources/{source_id}")
    ).status_code == 200
    for mode in ("full", "dense", "lexical"):
        assert (await _search(harness, ws, "Draxim churn", mode=mode))["items"] == []


async def test_filters_and_determinism(harness: Harness) -> None:  # noqa: F811
    _install(harness)
    ws = await harness.create_workspace()
    await harness.upload(
        ws,
        "memo.md",
        _md("Competitor Pace sells leggings at 38 dollars."),
        source_code="PACE",
        source_class="competitor",
        confidentiality="public",
    )
    await harness.upload(
        ws,
        "plan.md",
        _md("Our leggings plan targets 42 dollars."),
        source_code="PLAN",
        source_class="internal",
        confidentiality="restricted",
    )
    await harness.drain()
    q = "leggings dollars"
    both = await _search(harness, ws, q, k=10)
    assert {i["source_code"] for i in both["items"]} == {"PACE", "PLAN"}
    again = await _search(harness, ws, q, k=10)
    assert [i["handle"] for i in again["items"]] == [i["handle"] for i in both["items"]]
    by_class = await _search(harness, ws, q, source_class="competitor")
    assert {i["source_code"] for i in by_class["items"]} == {"PACE"}
    by_source = await _search(harness, ws, q, source="PLAN")
    assert {i["source_code"] for i in by_source["items"]} == {"PLAN"}
    public_only = await _search(harness, ws, q, max_confidentiality="internal")
    assert {i["source_code"] for i in public_only["items"]} == {"PACE"}
    two_classes = await _search(harness, ws, q, source_class=["competitor", "internal"])
    assert {i["source_code"] for i in two_classes["items"]} == {"PACE", "PLAN"}


async def test_reranker_outage_degrades_to_fused_order(harness: Harness) -> None:  # noqa: F811
    ws = await harness.create_workspace()
    _install(harness)
    await _seed(harness, ws, CANARY_A)
    hybrid = await _search(harness, ws, "leggings delivery stores", mode="hybrid", k=20)
    _install(harness, reranker=FailingReranker())
    degraded = await _search(harness, ws, "leggings delivery stores", mode="full", k=20)
    assert RERANKER_UNAVAILABLE in degraded["flags"]
    assert [i["handle"] for i in degraded["items"]] == [i["handle"] for i in hybrid["items"]]


async def test_embedder_outage_falls_back_to_lexical(harness: Harness) -> None:  # noqa: F811
    _install(harness)
    ws = await harness.create_workspace()
    await _seed(harness, ws, CANARY_A)
    _install(harness, embedder=FailingEmbedder())
    body = await _search(harness, ws, "Zephyrine lattice stitching")
    assert LEXICAL_FALLBACK in body["flags"]
    assert body["items"][0]["handle"].startswith(f"{ws}/MEMO@v1:")


@pytest.mark.parametrize(
    "query",
    ["gen z", "$129", "ratio:3", "(x", "& |", "O'Brien", "the and of", '"unterminated', "!!!"],
)
async def test_adversarial_lexical_input_never_errors(harness: Harness, query: str) -> None:  # noqa: F811
    _install(harness)
    ws = await harness.create_workspace()
    await _seed(harness, ws, CANARY_A)
    first = await _search(harness, ws, query, mode="lexical")
    second = await _search(harness, ws, query, mode="lexical")
    assert first["items"] == second["items"]


async def test_heading_flood_and_keyword_stuffing_do_not_beat_the_relevant_child(
    harness: Harness,  # noqa: F811
) -> None:
    """IDF over body text + heading-damped tiebreak (plan §11 tests)."""
    _install(harness)
    ws = await harness.create_workspace()
    flooded = "# Return Rate Return Rate\n\n" + "\n\n".join(
        f"Store {i} opened on schedule." for i in range(6)
    )
    await harness.upload(ws, "flood.md", flooded.encode(), source_code="FLOOD")
    await harness.upload(
        ws,
        "stuffed.md",
        _md("rate rate rate rate rate rate rate rate rate rate"),
        source_code="STUFF",
    )
    await harness.upload(
        ws,
        "real.md",
        _md("The Knit Runner 2 return rate was 16.8 percent in August."),
        source_code="REAL",
    )
    await harness.drain()
    body = await _search(harness, ws, "Knit Runner return rate", mode="lexical")
    assert body["items"][0]["source_code"] == "REAL"


async def test_search_concurrent_with_purge_never_errors(harness: Harness) -> None:  # noqa: F811
    _install(harness)
    ws = await harness.create_workspace()
    await _seed(harness, ws, CANARY_A)
    source_id = next(
        s["source_id"]
        for s in (await harness.client.get(f"/api/workspaces/{ws}/sources")).json()
        if s["source_code"] == "MEMO"
    )
    searches = [_search(harness, ws, "Zephyrine lattice stitching") for _ in range(5)]
    purge = harness.client.delete(f"/api/workspaces/{ws}/sources/{source_id}")
    *results, purged = await asyncio.gather(*searches, purge)
    assert purged.status_code == 200
    after = await _search(harness, ws, "Zephyrine lattice stitching")
    assert all(not i["handle"].startswith(f"{ws}/MEMO") for i in after["items"])
    assert len(results) == 5


async def test_docx_and_rows_are_searchable(harness: Harness) -> None:  # noqa: F811
    _install(harness)
    ws = await harness.create_workspace()
    await harness.upload(
        ws,
        "interviews.docx",
        make_docx(
            [("h1", "Interview 1"), ("p", "Q: Biggest issue?"), ("p", "A: Seams split early.")]
        ),
        source_code="INT",
    )
    await _seed(harness, ws, CANARY_A)
    body = await _search(harness, ws, "seams split", mode="lexical")
    assert body["items"][0]["source_code"] == "INT"
    rows = await _search(harness, ws, "leggings run small tees", mode="lexical")
    assert rows["items"][0]["handle"] == f"{ws}/SURVEY@v1:R2"


async def test_rankings_are_identical_across_re_ingestion(harness: Harness) -> None:  # noqa: F811
    """Ties break on parent handle + child ordinal, not on random child ids: the same corpus
    ingested twice (two workspaces, different ids) must rank identically in every mode."""
    _install(harness)
    rows = [["id", "segment", "comment"]] + [
        [f"S{i}", "Gen Z", f"Sizing runs small on the leggings, said shopper {name}."]
        for i, name in enumerate(["ana", "ben", "cal", "dee", "eli", "fay", "gus", "hal"], 1)
    ]
    ws_a, ws_b = await harness.create_workspace(), await harness.create_workspace()
    for ws in (ws_a, ws_b):
        await harness.upload(ws, "survey.csv", make_csv(rows), source_code="SURVEY")
        await harness.upload(
            ws, "memo.md", _md("Sizing notes: leggings run small."), source_code="M"
        )
        await harness.drain()
    for mode in ("lexical", "dense", "hybrid", "full"):
        a = await _search(harness, ws_a, "leggings sizing small", mode=mode, k=20)
        b = await _search(harness, ws_b, "leggings sizing small", mode=mode, k=20)
        strip = lambda body, ws: [i["handle"].removeprefix(f"{ws}/") for i in body["items"]]  # noqa: E731
        assert strip(a, ws_a) == strip(b, ws_b), mode
