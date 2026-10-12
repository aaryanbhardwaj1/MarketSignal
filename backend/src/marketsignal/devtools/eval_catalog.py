"""Precomputed evaluation catalog (developer tools, E11).

The catalog and per-run item files are generated offline by ``scripts/build_eval_catalog.py``
from committed evaluation artifacts and shipped inside the package (the API image does not
contain ``eval/``). Nothing here computes metrics; it only loads, validates and pages.

Run ids are a closed set: a client-supplied id is looked up in ``EVAL_RUN_IDS`` and never used
to build a path, so traversal attempts (``..``, slashes, encoded separators) are simply
unknown ids.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

DATA_DIR: Final = Path(__file__).resolve().parent / "eval_catalog_data"
CATALOG_FILE: Final = DATA_DIR / "catalog.v1.json"

# Mirrors ``EvalRunId`` in frontend/src/lib/api/contracts.ts.
EVAL_RUN_IDS: Final[tuple[str, ...]] = (
    "p2-dev-final",
    "p2-test-c3",
    "p3-grounded-live",
    "p4-research-dev",
    "p4-research-test",
    "p5-analytics-dev",
    "p5-analytics-holdout",
)
_ITEM_FILES: Final[dict[str, Path]] = {
    rid: DATA_DIR / "items" / f"{rid}.json" for rid in EVAL_RUN_IDS
}

MAX_PAGE_SIZE: Final = 50


class EvalCatalogUnavailableError(RuntimeError):
    """The generated catalog is missing or unreadable (build not run)."""


class UnknownEvalRunError(KeyError):
    """The run id is not one of ``EVAL_RUN_IDS``."""


@dataclass(frozen=True)
class LoadedCatalog:
    payload: dict[str, Any]
    etag: str


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise EvalCatalogUnavailableError(f"evaluation catalog file missing: {path.name}") from exc


@lru_cache(maxsize=1)
def load_catalog() -> LoadedCatalog:
    raw = _read(CATALOG_FILE)
    payload = json.loads(raw)
    if payload.get("schema_version") != 1:
        raise EvalCatalogUnavailableError("unsupported evaluation catalog schema")
    return LoadedCatalog(payload=payload, etag=f'"{hashlib.sha256(raw).hexdigest()}"')


def is_known_run(run_id: str) -> bool:
    return run_id in _ITEM_FILES


@lru_cache(maxsize=len(EVAL_RUN_IDS))
def _load_rows(run_id: str) -> tuple[dict[str, Any], ...]:
    path = _ITEM_FILES.get(run_id)
    if path is None:
        raise UnknownEvalRunError(run_id)
    doc = json.loads(_read(path))
    if doc.get("run_id") != run_id:
        raise EvalCatalogUnavailableError(f"items file for {run_id} is inconsistent")
    return tuple(doc["items"])


def load_items(
    run_id: str, *, offset: int = 0, limit: int = 20, bucket: str | None = None
) -> dict[str, Any]:
    """One ``EvalItemsPage`` for ``run_id``, optionally filtered by a failure bucket id."""
    if not is_known_run(run_id):
        raise UnknownEvalRunError(run_id)
    rows = _load_rows(run_id)
    if bucket:
        rows = tuple(r for r in rows if bucket in r.get("buckets", ()))
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    return {
        "run_id": run_id,
        "total": len(rows),
        "items": [r["item"] for r in rows[offset : offset + limit]],
    }
