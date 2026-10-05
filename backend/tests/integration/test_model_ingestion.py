"""Real-model ingestion: the ONNX bge-small embedder and its own WordPiece tokenizer.

Covers what the deterministic test doubles cannot: child windows cut on real subword token
offsets still satisfy the span contract in the database, vectors are the model's 384-d
normalised embeddings, and a *paraphrased* query finds the planted passage by dense search.
The model (~70 MB) is cached under ``.cache/models`` (CI restores it with actions/cache).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.api.app import create_app
from marketsignal.config import Settings
from marketsignal.db.engine import create_engine, create_session_factory
from marketsignal.ingestion.pipeline import IngestionDeps
from marketsignal.ingestion.tokenizer import HuggingFaceTokenizer
from marketsignal.providers.embeddings import FastEmbedEmbedder
from marketsignal.worker import app as worker
from tests.fixtures.factories import make_pdf
from tests.integration.conftest import new_workspace_code, purge_workspace

pytestmark = [pytest.mark.integration, pytest.mark.model]

PLANTED = (
    "Shoppers aged 18 to 24 told us that inconsistent sizing between our running shoes and "
    "our apparel is the main reason they return online orders."
)
DISTRACTORS = [
    "Store traffic in the northeast region was flat compared with the prior quarter.",
    "The finance team expects gross margin to improve by forty basis points next year.",
    "Our sustainability report now covers recycled packaging across all distribution centers.",
]


@pytest.fixture
async def client(
    settings: Settings, owner_engine: AsyncEngine
) -> AsyncIterator[tuple[AsyncClient, str]]:
    embedder = FastEmbedEmbedder(
        settings.embed_model_id,
        settings.embed_model_name,
        settings.embed_dimensions,
        settings.model_cache_dir,
    )
    worker.set_deps(
        IngestionDeps(
            session_factory=create_session_factory(create_engine(settings)),
            settings=settings,
            embedder=embedder,
            tokenizer=HuggingFaceTokenizer(embedder.tokenizer),
        )
    )
    app = create_app(settings)
    app.state.query_embedder = lambda: embedder
    code = new_workspace_code()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
    ):
        assert (
            await http.post("/api/workspaces", json={"code": code, "name": code})
        ).status_code == 201
        yield http, code
    worker.set_deps(None)
    async with owner_engine.connect() as conn:
        workspace_id = (
            await conn.execute(text("SELECT id FROM workspaces WHERE code = :c"), {"c": code})
        ).scalar_one()
    await purge_workspace(owner_engine, workspace_id)


async def test_real_model_spans_and_paraphrase_retrieval(
    client: tuple[AsyncClient, str], app_engine: AsyncEngine
) -> None:
    http, ws = client
    long_tail = " ".join(
        f"Background detail number {i} about regional assortment planning." for i in range(60)
    )
    pdf = make_pdf(
        [
            [
                ("h1", "Customer Research"),
                ("p", DISTRACTORS[0]),
                ("p", PLANTED),
                ("p", DISTRACTORS[1]),
            ],
            [("p", DISTRACTORS[2]), ("p", long_tail[:1500])],
        ]
    )
    uploaded = await http.post(
        f"/api/workspaces/{ws}/sources",
        files={"file": ("research.pdf", pdf)},
        data={"source_class": "customer", "source_code": "RESEARCH"},
    )
    assert uploaded.status_code == 202, uploaded.text
    async with worker.app.open_async():
        await worker.run_pending_jobs()
    source = (await http.get(f"/api/workspaces/{ws}/sources/{uploaded.json()['source_id']}")).json()
    (version,) = source["versions"]
    assert version["status"] == "ready", version
    assert version["embedding_model"] == "bge-small-en-v1.5"

    # Paraphrase: no shared distinctive words with the planted sentence.
    query = "why do young customers send back the things they bought on the website"
    hits = (
        await http.get(f"/api/workspaces/{ws}/dev/search", params={"q": query, "mode": "dense"})
    ).json()["hits"]
    assert hits
    top = hits[0]
    evidence = (
        await http.get(
            f"/api/workspaces/{ws}/evidence/{top['handle']}", params={"child_id": top["child_id"]}
        )
    ).json()
    assert PLANTED in evidence["text"]
    highlight = evidence["highlight"]
    assert evidence["text"][highlight["char_start"] : highlight["char_end"]] == highlight["text"]

    # Span contract with real WordPiece offsets, checked in the database for every window.
    async with app_engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT set_config('app.workspace_id', (SELECT id::text FROM workspaces WHERE code = :c), true)"
            ),
            {"c": ws},
        )
        mismatches = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM child_chunks c JOIN parent_chunks p ON p.id = c.parent_id "
                    "WHERE c.kind = 'window' AND substr(p.text, c.char_start + 1, "
                    "c.char_end - c.char_start) <> c.text"
                )
            )
        ).scalar_one()
        dims = (
            (
                await conn.execute(
                    text("SELECT DISTINCT vector_dims(embedding) FROM chunk_embeddings")
                )
            )
            .scalars()
            .all()
        )
    assert mismatches == 0
    assert dims == [384]
