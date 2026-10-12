"""Constants, the read-only source reader and RFC 6901 pointer helpers."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "backend" / "src" / "marketsignal" / "devtools" / "eval_catalog_data"

P2 = "eval/baselines/phase2"
P2_SUMMARY = f"{P2}/summary.json"
P2_ELIGIBLE = f"{P2}/summary-eligible.json"
P2_REPORT = "docs/phase-reports/phase-2.md"
P3 = "eval/baselines/phase3/live-v0"
P4 = "eval/baselines/phase4"
P5 = "eval/baselines/phase5"
P5_REPORT = "docs/phase-reports/phase-5.md"
VERIFIER_SUMMARY = f"{P4}/verifier/SUMMARY.md"
DS = "eval/datasets"

RETRIEVAL_RUNS = {"p2-dev-final": "06-final-dev", "p2-test-c3": "07-test-milestone-c3"}
ARMS = [
    ("dense", "Dense (vector only)"),
    ("lexical", "Lexical (full-text only)"),
    ("hybrid", "Hybrid (production default)"),
    ("hybrid-rerank", "Hybrid + reranker (experimental)"),
]
DEFAULT_ARM = "hybrid"
RETRIEVAL_METRICS = [
    ("hit@1", "Hit@1"),
    ("hit@10", "Hit@10"),
    ("recall@10", "Recall@10"),
    ("recall@20", "Recall@20"),
    ("mrr", "MRR"),
]
BUCKET_PAIR = "dense|hybrid"


# ── sources and pointers ─────────────────────────────────────────────────────────────────────


class Sources:
    """Read-only access to repo files; records sha256/bytes of everything read."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._json: dict[str, Any] = {}
        self._text: dict[str, str] = {}
        self.manifest: dict[str, dict[str, Any]] = {}

    def _read(self, rel: str) -> bytes:
        with (self.root / rel).open("rb") as fh:  # read-only by construction
            data = fh.read()
        self.manifest[rel] = {
            "path": rel,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
        return data

    def json(self, rel: str) -> Any:
        if rel not in self._json:
            self._json[rel] = json.loads(self._read(rel))
        return self._json[rel]

    def text(self, rel: str) -> str:
        if rel not in self._text:
            self._text[rel] = self._read(rel).decode("utf-8")
        return self._text[rel]

    def sha(self, rel: str) -> str:
        if rel not in self.manifest:
            self._read(rel)
        return str(self.manifest[rel]["sha256"])

    def listing(self) -> list[dict[str, Any]]:
        return [self.manifest[k] for k in sorted(self.manifest)]


def escape(token: str | int) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def ptr(*tokens: str | int) -> str:
    return "".join("/" + escape(t) for t in tokens)


def resolve(doc: Any, pointer: str) -> Any:
    if pointer == "":
        return doc
    node = doc
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


def slug(heading: str) -> str:
    """GitHub-style heading anchor."""
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return s.replace(" ", "-")
