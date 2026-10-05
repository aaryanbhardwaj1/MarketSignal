"""End-to-end ingestion through the real API: upload -> Procrastinate job (deferred on the upload
transaction) -> in-process worker -> parents/children/embeddings -> evidence resolution.

Embeddings use a deterministic hash embedder and a regex tokenizer for speed; the real ONNX
model is exercised in ``test_model_ingestion.py`` and the seeded-corpus verification script.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from marketsignal.api.app import create_app
from marketsignal.config import Settings
from marketsignal.db.engine import create_engine, create_session_factory
from marketsignal.ingestion.pipeline import IngestionDeps
from marketsignal.ingestion.tokenizer import RegexTokenizer
from marketsignal.providers.embeddings import Embedder, FailingEmbedder, HashEmbedder
from marketsignal.worker import app as worker
from tests.fixtures.factories import make_csv, make_docx, make_pdf, make_pptx, make_xlsx
from tests.integration.conftest import new_workspace_code, purge_workspace

pytestmark = pytest.mark.integration

PLANTED = (
    "Fit inconsistency across categories is the top frustration for 27 percent of Gen Z buyers."
)


@dataclass
class Harness:
    client: AsyncClient
    settings: Settings
    workspaces: list[str]

    async def create_workspace(self) -> str:
        code = new_workspace_code()
        response = await self.client.post("/api/workspaces", json={"code": code, "name": code})
        assert response.status_code == 201, response.text
        self.workspaces.append(code)
        return code

    async def upload(
        self, ws: str, filename: str, data: bytes, *, source_class: str = "customer", **form: str
    ) -> Any:
        return await self.client.post(
            f"/api/workspaces/{ws}/sources",
            files={"file": (filename, data)},
            data={"source_class": source_class, **form},
        )

    async def drain(self) -> None:
        async with worker.app.open_async():
            await worker.run_pending_jobs()

    async def source(self, ws: str, source_id: str) -> dict[str, Any]:
        response = await self.client.get(f"/api/workspaces/{ws}/sources/{source_id}")
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body


def _deps(settings: Settings, embedder: Embedder) -> IngestionDeps:
    return IngestionDeps(
        session_factory=create_session_factory(create_engine(settings)),
        settings=settings,
        embedder=embedder,
        tokenizer=RegexTokenizer(),
    )


@pytest.fixture
async def harness(settings: Settings, owner_engine: AsyncEngine) -> AsyncIterator[Harness]:
    test_settings = settings.model_copy(update={"health_sample_size": 5})
    worker.set_deps(_deps(test_settings, HashEmbedder(model_id="hash-test")))
    app = create_app(test_settings)
    app.state.query_embedder = lambda: HashEmbedder(model_id="hash-test")
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        h = Harness(client, test_settings, [])
        yield h
    worker.set_deps(None)
    async with owner_engine.connect() as conn:
        ids = (
            (
                await conn.execute(
                    text("SELECT id FROM workspaces WHERE code = ANY(:c)"), {"c": h.workspaces}
                )
            )
            .scalars()
            .all()
        )
    for workspace_id in ids:
        await purge_workspace(owner_engine, workspace_id)


FORMATS = {
    "brief.pdf": lambda: make_pdf([[("h1", "Findings"), ("p", PLANTED), ("p", "Another point.")]]),
    "interviews.docx": lambda: make_docx(
        [("h1", "Interview 1"), ("p", "Q: Biggest issue?"), ("p", f"A: {PLANTED}")]
    ),
    "review.pptx": lambda: make_pptx(
        [{"title": "Pain points", "bullets": [PLANTED], "notes": "Speaker note."}]
    ),
    "data.xlsx": lambda: make_xlsx(
        {
            "Survey": [
                ["id", "segment", "comment"],
                ["S1", "Gen Z", PLANTED],
                ["S2", "Millennial", "Fine."],
            ]
        }
    ),
    "survey.csv": lambda: make_csv(
        [["id", "segment", "comment"], ["S1", "Gen Z", PLANTED], ["S2", "Millennial", "Fine."]],
        bom=True,
    ),
    "memo.md": lambda: f"# Memo\n\n{PLANTED}\n\n- item one\n- item two\n".encode(),
    "notes.txt": lambda: f"Call notes.\n\n{PLANTED}\n".encode(),
}


@pytest.mark.parametrize("filename", sorted(FORMATS))
async def test_every_format_ingests_and_resolves(harness: Harness, filename: str) -> None:
    ws = await harness.create_workspace()
    uploaded = await harness.upload(ws, filename, FORMATS[filename]())
    assert uploaded.status_code == 202, uploaded.text
    body = uploaded.json()
    assert body["status"] == "queued"
    assert body["created"] is True
    await harness.drain()

    source = await harness.source(ws, body["source_id"])
    (version,) = source["versions"]
    assert version["status"] == "ready", version
    assert version["parent_count"] > 0
    assert version["child_count"] > 0
    assert version["timings"]["total_ms"] > 0  # jsonb fields really persisted
    assert version["health"]["ok"] is True

    hits = (
        await harness.client.get(
            f"/api/workspaces/{ws}/dev/search", params={"q": "fit inconsistency categories"}
        )
    ).json()["hits"]
    assert hits, f"lexical smoke search found nothing for {filename}"
    top = hits[0]
    evidence = await harness.client.get(
        f"/api/workspaces/{ws}/evidence/{quote(top['handle'], safe='')}",
        params={"child_id": top["child_id"]},
    )
    assert evidence.status_code == 200, evidence.text
    payload = evidence.json()
    assert payload["handle"] == top["handle"]
    assert PLANTED in payload["text"]
    highlight = payload["highlight"]
    assert highlight is not None
    assert payload["text"][highlight["char_start"] : highlight["char_end"]] == highlight["text"]
    assert PLANTED[:30] in highlight["text"] or highlight["text"] in PLANTED
    assert payload["source"]["version_status"] == "ready"
    assert payload["provenance"]["parent_content_sha256"]


async def test_idempotent_reupload_and_duplicates(harness: Harness) -> None:
    ws = await harness.create_workspace()
    data = FORMATS["memo.md"]()
    first = (await harness.upload(ws, "memo.md", data, source_code="MEMO")).json()
    again = await harness.upload(ws, "memo.md", data, source_code="MEMO")
    assert again.status_code == 200
    assert again.json()["version_id"] == first["version_id"]
    assert again.json()["created"] is False
    duplicate = await harness.upload(ws, "copy-of-memo.md", data)
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate_of"] == "MEMO"
    await harness.drain()


async def test_version_update_supersedes_but_old_handles_still_resolve(harness: Harness) -> None:
    ws = await harness.create_workspace()
    v1 = (
        await harness.upload(
            ws,
            "trends.md",
            b"# Trends\n\nSocial commerce share was 17 percent.\n",
            source_code="TRENDS",
            source_class="market",
        )
    ).json()
    await harness.drain()
    v2 = (
        await harness.upload(
            ws,
            "trends.md",
            b"# Trends\n\nSocial commerce share is now 26 percent.\n",
            source_code="TRENDS",
            source_class="market",
        )
    ).json()
    assert v2["version"] == 2
    assert v2["created"] is True
    await harness.drain()
    versions = {
        v["version"]: v["status"] for v in (await harness.source(ws, v1["source_id"]))["versions"]
    }
    assert versions == {1: "superseded", 2: "ready"}

    old = (await harness.client.get(f"/api/workspaces/{ws}/evidence/{ws}/TRENDS@v1:S1.B1")).json()
    assert "17 percent" in old["text"]
    assert old["source"]["version_status"] == "superseded"
    assert old["source"]["latest_version"] == 2
    new = (await harness.client.get(f"/api/workspaces/{ws}/evidence/{ws}/TRENDS@v2:S1.B1")).json()
    assert "26 percent" in new["text"]
    # Search only sees the active version.
    hits = (
        await harness.client.get(
            f"/api/workspaces/{ws}/dev/search", params={"q": "social commerce"}
        )
    ).json()["hits"]
    assert {h["handle"].split(":")[0] for h in hits} == {f"{ws}/TRENDS@v2"}
    summary = (await harness.client.get(f"/api/workspaces/{ws}")).json()
    assert summary["corpus_version"] == 2


async def test_resolver_error_contract_and_purge(harness: Harness) -> None:
    ws = await harness.create_workspace()
    other = await harness.create_workspace()
    body = (await harness.upload(ws, "memo.md", FORMATS["memo.md"](), source_code="MEMO")).json()
    await harness.drain()
    handle = f"{ws}/MEMO@v1:S1.B1"
    assert (await harness.client.get(f"/api/workspaces/{ws}/evidence/{handle}")).status_code == 200

    malformed = await harness.client.get(f"/api/workspaces/{ws}/evidence/not-a-handle")
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "MALFORMED_HANDLE"
    assert (
        await harness.client.get(f"/api/workspaces/{ws}/evidence/{ws}/MEMO@v1:S9.B9")
    ).status_code == 404
    # Another workspace's handle through this workspace's route, and vice versa: both 404.
    foreign = await harness.client.get(f"/api/workspaces/{other}/evidence/{handle}")
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"
    cross = await harness.client.get(f"/api/workspaces/{other}/evidence/{other}/MEMO@v1:S1.B1")
    assert cross.status_code == 404
    assert (await harness.client.get(f"/api/workspaces/{other}/sources")).json() == []

    deleted = await harness.client.delete(f"/api/workspaces/{ws}/sources/{body['source_id']}")
    assert deleted.status_code == 200
    tomb = await harness.client.get(f"/api/workspaces/{ws}/evidence/{handle}")
    assert tomb.status_code == 410
    assert tomb.json()["error"]["tombstone"]["source_code"] == "MEMO"
    hits = (
        await harness.client.get(
            f"/api/workspaces/{ws}/dev/search", params={"q": "fit inconsistency"}
        )
    ).json()["hits"]
    assert hits == []


async def test_unknown_workspace_is_not_found(harness: Harness) -> None:
    response = await harness.client.get("/api/workspaces/NOPEXYZ123/sources")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


@pytest.mark.parametrize(
    ("filename", "data", "status", "code"),
    [
        ("virus.exe", b"MZ", 415, "UNSUPPORTED_TYPE"),
        ("locked.pdf", b"%PDF-1.7\ntrailer<</Encrypt 5 0 R>>", 422, "ENCRYPTED_DOCUMENT"),
        ("disguised.xlsx", None, 415, "UNSUPPORTED_TYPE"),
    ],
)
async def test_upload_rejections_persist_nothing(
    harness: Harness, filename: str, data: bytes | None, status: int, code: str
) -> None:
    ws = await harness.create_workspace()
    payload = data if data is not None else make_docx([("p", "x")])
    response = await harness.upload(ws, filename, payload)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert (await harness.client.get(f"/api/workspaces/{ws}/sources")).json() == []


async def test_source_type_mismatch(harness: Harness) -> None:
    ws = await harness.create_workspace()
    await harness.upload(ws, "memo.md", FORMATS["memo.md"](), source_code="MEMO")
    response = await harness.upload(ws, "memo.txt", b"different", source_code="MEMO")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOURCE_TYPE_MISMATCH"


async def test_embedder_outage_degrades_to_lexical_only(harness: Harness) -> None:
    worker.set_deps(_deps(harness.settings, FailingEmbedder()))
    ws = await harness.create_workspace()
    body = (await harness.upload(ws, "memo.md", FORMATS["memo.md"]())).json()
    await harness.drain()
    (version,) = (await harness.source(ws, body["source_id"]))["versions"]
    assert version["status"] == "ready_degraded"
    assert "EMBEDDER_UNAVAILABLE" in version["warnings"]
    hits = (
        await harness.client.get(
            f"/api/workspaces/{ws}/dev/search", params={"q": "fit inconsistency"}
        )
    ).json()["hits"]
    assert hits  # lexical still serves


async def test_parse_failure_is_visible_and_retryable(harness: Harness) -> None:
    ws = await harness.create_workspace()
    body = (await harness.upload(ws, "empty.md", b"   \n\n  \n")).json()
    await harness.drain()
    (version,) = (await harness.source(ws, body["source_id"]))["versions"]
    assert version["status"] == "failed"
    assert version["error_code"] == "EMPTY_DOCUMENT"
    retried = await harness.client.post(f"/api/workspaces/{ws}/sources/{body['source_id']}/retry")
    assert retried.status_code == 202
    await harness.drain()
    (version,) = (await harness.source(ws, body["source_id"]))["versions"]
    assert version["attempts"] == 2
    assert version["status"] == "failed"


async def test_failed_job_handoff_rolls_back_the_upload(
    harness: Harness, app_engine: AsyncEngine
) -> None:
    """The job is deferred on the upload transaction: if anything fails after deferral, the
    version row, blob AND job all roll back together (no dual-write)."""
    ws = await harness.create_workspace()
    app = harness.client._transport.app  # type: ignore[attr-defined]

    async def defer_then_fail(
        connection: Any, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> int:
        await worker.defer_ingestion(connection, workspace_id, version_id)
        raise RuntimeError("crash after enqueue")

    app.state.defer_job = defer_then_fail
    with pytest.raises(RuntimeError):
        await harness.upload(ws, "memo.md", FORMATS["memo.md"]())
    app.state.defer_job = worker.defer_ingestion
    assert (await harness.client.get(f"/api/workspaces/{ws}/sources")).json() == []
    async with app_engine.connect() as conn:
        jobs = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM procrastinate_jobs WHERE status = 'todo' "
                    "AND args->>'workspace_id' IN (SELECT id::text FROM workspaces WHERE code = :c)"
                ),
                {"c": ws},
            )
        ).scalar_one()
    assert jobs == 0
