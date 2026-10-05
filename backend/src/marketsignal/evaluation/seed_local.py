"""Seed the corpus through the REAL upload API and ingestion pipeline, in one process.

Same path as ``scripts/seed.py`` (HTTP upload -> transactional job -> worker pipeline), but the
API runs in-process over an ASGI transport and the Procrastinate worker is drained in-process,
so CI needs no running server. Uses the production embedder with its file cache, and the
model's own tokenizer.
"""

from __future__ import annotations

import json
import time
from typing import Any

from httpx import ASGITransport, AsyncClient

from marketsignal.api.app import create_app
from marketsignal.config import Settings
from marketsignal.evaluation.corpus import SEED_DIR
from marketsignal.worker import app as worker

GENERATED = SEED_DIR / "generated"
TERMINAL_OK = {"ready", "superseded"}


async def seed_in_process(settings: Settings) -> dict[str, Any]:
    manifest = json.loads((GENERATED / "manifest.json").read_text(encoding="utf-8"))
    worker.set_deps(worker.default_deps(settings))
    app = create_app(settings)
    started = time.perf_counter()
    uploads: list[dict[str, Any]] = []
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://seed") as client,
        ):
            for ws in manifest["workspaces"]:
                response = await client.post(
                    "/api/workspaces",
                    json={"code": ws["code"], "name": ws["name"], "description": ws["description"]},
                )
                if response.status_code not in (201, 409):
                    raise RuntimeError(f"workspace {ws['code']}: {response.text}")
            for item in sorted(manifest["uploads"], key=lambda u: u["upload_order"]):
                path = GENERATED / item["filename"]
                response = await client.post(
                    f"/api/workspaces/{item['workspace_code']}/sources",
                    files={"file": (path.name, path.read_bytes())},
                    data={
                        "source_class": item["source_class"],
                        "confidentiality": item["confidentiality"],
                        "title": item["title"],
                        "source_code": item["source_code"],
                    },
                )
                if response.status_code not in (200, 202):
                    raise RuntimeError(f"upload {path.name}: {response.text}")
                uploads.append({**item, **response.json()})
                # Drain after each upload: versions of one source must activate in order.
                async with worker.app.open_async():
                    await worker.run_pending_jobs()
            statuses = []
            for u in uploads:
                body = (
                    await client.get(
                        f"/api/workspaces/{u['workspace_code']}/sources/{u['source_id']}"
                    )
                ).json()
                statuses += [
                    (u["source_code"], v["version"], v["status"]) for v in body["versions"]
                ]
    finally:
        worker.set_deps(None)
    bad = sorted({s for s in statuses if s[2] not in TERMINAL_OK})
    return {
        "uploads": len(uploads),
        "seconds": round(time.perf_counter() - started, 1),
        "not_ready": bad,
    }
