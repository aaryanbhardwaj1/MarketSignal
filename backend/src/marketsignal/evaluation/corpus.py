"""Corpus and ledger identity: the hashes a frozen dataset is pinned to.

``corpus_sha256`` covers every generated seed file (workspace, source code, version, filename,
sha256 from the generated manifest) - change one byte of the corpus and the hash changes.
``ledger_sha256`` is the hash of the fact-ledger file bytes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
SEED_DIR = REPO_ROOT / "seed_data"
MANIFEST = SEED_DIR / "generated" / "manifest.json"
LEDGER = SEED_DIR / "fact_ledger.json"
EVAL_DIR = REPO_ROOT / "eval"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def corpus_sha256(manifest_path: Path = MANIFEST) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = sorted(
        (u["workspace_code"], u["source_code"], int(u["version"]), u["filename"], u["sha256"])
        for u in manifest["uploads"]
    )
    return sha256_bytes(canonical_json(entries).encode())


def ledger_sha256(ledger_path: Path = LEDGER) -> str:
    return sha256_bytes(ledger_path.read_bytes())


def load_ledger(ledger_path: Path = LEDGER) -> dict[str, Any]:
    ledger: dict[str, Any] = json.loads(ledger_path.read_text(encoding="utf-8"))
    return ledger


def related_fact_pairs(ledger: dict[str, Any]) -> list[tuple[str, str]]:
    """Contradiction, superseded and distractor pairs: facts that must share a split."""
    pairs = [(c["a"], c["b"]) for c in ledger.get("contradictions", [])]
    pairs += [(s["old"], s["new"]) for s in ledger.get("superseded", [])]
    pairs += [(d["fact_id"], d["distractor_of"]) for d in ledger.get("distractors", [])]
    return pairs


def config_hash(config: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(config).encode())[:16]
