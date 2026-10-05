"""Load the synthetic seed corpus through the REAL upload API (no database shortcut).

Creates the manifest's workspaces, uploads every file in manifest order with its declared
source code, class, confidentiality and title, then polls until every source version reaches
a terminal status. Requires a running API (``make api``) and worker (``make worker``).

    uv --directory backend run python ../scripts/seed.py [--api http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seed_data" / "generated"
TERMINAL = {"ready", "ready_degraded", "failed", "superseded", "purged"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument(
        "--timeout", type=float, default=1800.0, help="seconds to wait for ingestion"
    )
    args = parser.parse_args()
    manifest = json.loads((SEED / "manifest.json").read_text())
    client = httpx.Client(base_url=args.api, timeout=120)

    for ws in manifest["workspaces"]:
        response = client.post(
            "/api/workspaces",
            json={"code": ws["code"], "name": ws["name"], "description": ws["description"]},
        )
        if response.status_code not in (201, 409):
            print(
                f"workspace {ws['code']}: {response.status_code} {response.text}", file=sys.stderr
            )
            return 1
        print(f"workspace {ws['code']}: {'created' if response.status_code == 201 else 'exists'}")

    started = time.perf_counter()
    uploads: list[dict[str, Any]] = []
    for item in sorted(manifest["uploads"], key=lambda u: u["upload_order"]):
        path = SEED / item["filename"]
        response = client.post(
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
            print(f"upload {path.name}: {response.status_code} {response.text}", file=sys.stderr)
            return 1
        body = response.json()
        uploads.append({**item, **body})
        state = "queued" if body["created"] else f"unchanged ({body['status']})"
        print(f"  {item['workspace_code']}/{body['source_code']}@v{body['version']}: {state}")

    pending = {(u["workspace_code"], u["source_id"]) for u in uploads}
    deadline = time.monotonic() + args.timeout
    statuses: dict[tuple[str, str], list[dict[str, Any]]] = {}
    while pending and time.monotonic() < deadline:
        for ws, source_id in sorted(pending):
            versions = client.get(f"/api/workspaces/{ws}/sources/{source_id}").json()["versions"]
            statuses[(ws, source_id)] = versions
            if all(v["status"] in TERMINAL for v in versions):
                pending.discard((ws, source_id))
        if pending:
            time.sleep(2)
    elapsed = time.perf_counter() - started
    if pending:
        print(f"timed out with {len(pending)} sources still processing", file=sys.stderr)
        return 1

    failed = [
        (ws, v)
        for (ws, _), versions in statuses.items()
        for v in versions
        if v["status"] == "failed"
    ]
    print(f"\nseeded {len(uploads)} uploads in {elapsed:.1f}s; failed versions: {len(failed)}")
    for ws, version in failed:
        print(
            f"  FAILED {ws} v{version['version']}: "
            f"{version['error_code']} {version['error_detail']}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
