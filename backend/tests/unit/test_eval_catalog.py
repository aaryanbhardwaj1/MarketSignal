"""Evaluation catalog (E11): provenance integrity, pointer fidelity, safety, determinism.

The generated catalog lives in the package; the originals live in ``eval/``. Tests that need
``eval/`` skip when it is absent and fail instead under ``MS_REQUIRE_EVAL=1``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from marketsignal.devtools import eval_catalog

REPO = Path(__file__).resolve().parents[3]
EVAL = REPO / "eval"
BUILDER = REPO / "scripts" / "build_eval_catalog.py"
ITEM_PHASES = {"retrieval", "grounded", "research", "analytics"}
SECRET_PATTERNS = [
    re.compile(p)
    for p in (
        r"/Users/",
        r"/home/[a-z]",
        r"sk-ant-[A-Za-z0-9]",
        r"sk-[A-Za-z0-9]{20,}",
        r"AKIA[0-9A-Z]{16}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"postgres(ql)?(\+\w+)?://[^\s\"]*:[^\s\"]*@",
        r"(?i)api[_-]?key\"?\s*[:=]\s*\"[A-Za-z0-9]",
    )
]


def _require_eval() -> None:
    if not EVAL.is_dir():
        if os.environ.get("MS_REQUIRE_EVAL") == "1":
            pytest.fail("eval/ is required (MS_REQUIRE_EVAL=1) but missing")
        pytest.skip("eval/ not present")


def _catalog() -> dict[str, Any]:
    return eval_catalog.load_catalog().payload


def _resolve(doc: Any, pointer: str) -> Any:
    node = doc
    for raw in pointer.lstrip("/").split("/") if pointer else []:
        token = raw.replace("~1", "/").replace("~0", "~")
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


def _metrics(node: Any) -> Iterator[dict[str, Any]]:
    """Every EvalMetric anywhere in the catalog (objects with id, value, unit and source)."""
    if isinstance(node, dict):
        if {"id", "value", "unit", "source"} <= node.keys():
            yield node
            return
        for v in node.values():
            yield from _metrics(v)
    elif isinstance(node, list):
        for v in node:
            yield from _metrics(v)


def _sources(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if node.get("kind") in {"json", "report_md"} and "path" in node:
            yield node
        for v in node.values():
            yield from _sources(v)
    elif isinstance(node, list):
        for v in node:
            yield from _sources(v)


def test_catalog_shape_and_run_ids() -> None:
    cat = _catalog()
    assert cat["schema_version"] == 1
    for key in (
        "sources",
        "caveats",
        "overview",
        "retrieval",
        "grounded",
        "research_tradeoff",
        "analytics",
        "superseded",
        "failure_runs",
    ):
        assert key in cat
    assert {f["run_id"] for f in cat["failure_runs"]} == set(eval_catalog.EVAL_RUN_IDS)
    caveats = {c["id"] for c in cat["caveats"]}
    assert {
        "small-test-n",
        "v0-test-informed-default",
        "verifier-holdout-used-twice",
        "a3-not-run",
        "p5-holdout-routing",
    } <= caveats
    outcomes = {d["id"]: d["outcome"] for d in cat["retrieval"]["decisions"]}
    assert outcomes["hybrid-default"] == "adopted"
    assert outcomes["reranker-rejected"] == "rejected"


def test_contract_literal_values() -> None:
    """Values the TypeScript contract types as literal unions (JSON fixtures cannot check)."""
    cat = _catalog()
    units = {"ratio", "percent", "ms", "s", "usd", "count", "tokens"}
    assert all(m["unit"] in units for m in _metrics(cat))
    assert all(isinstance(m["value"], int | float | None) for m in _metrics(cat))
    outcomes = {d["outcome"] for d in cat["retrieval"]["decisions"]}
    assert outcomes <= {"adopted", "rejected", "not_adopted"}
    assert [v["split"] for v in cat["grounded"]["verifier"]] == ["dev", "holdout"]
    assert [r["split"] for r in cat["research_tradeoff"]] == ["dev", "test"]
    assert [a["split"] for a in cat["analytics"]] == ["dev", "holdout"]
    run_ids = set(eval_catalog.EVAL_RUN_IDS)
    assert {r["run_id"] for r in cat["retrieval"]["runs"]} <= run_ids
    assert {c["run_id"] for c in cat["retrieval"]["comparisons"]} <= run_ids
    for run in cat["retrieval"]["runs"]:
        assert sum(a["is_default"] for a in run["arms"]) == 1


def test_every_run_has_an_items_file_with_matching_counts() -> None:
    cat = _catalog()
    for fr in cat["failure_runs"]:
        page = eval_catalog.load_items(fr["run_id"], limit=50)
        assert page["total"] == fr["item_count"] > 0
        assert all(i["phase"] in ITEM_PHASES for i in page["items"])
        for b in fr["buckets"]:
            assert eval_catalog.load_items(fr["run_id"], bucket=b["id"])["total"] == b["n"]


def test_items_paging_and_limits() -> None:
    first = eval_catalog.load_items("p3-grounded-live", offset=0, limit=10)
    second = eval_catalog.load_items("p3-grounded-live", offset=10, limit=10)
    assert len(first["items"]) == 10
    assert first["items"][0]["item_id"] != second["items"][0]["item_id"]
    assert len(eval_catalog.load_items("p3-grounded-live", limit=999)["items"]) == 50
    assert eval_catalog.load_items("p3-grounded-live", bucket="no-such-bucket")["total"] == 0


@pytest.mark.parametrize("bad", ["..", "../catalog.v1", "p3-grounded-live/../x", "", "P2-TEST-C3"])
def test_unknown_run_ids_are_rejected(bad: str) -> None:
    assert not eval_catalog.is_known_run(bad)
    with pytest.raises(eval_catalog.UnknownEvalRunError):
        eval_catalog.load_items(bad)


def test_no_absolute_paths_or_secret_patterns() -> None:
    data_dir = eval_catalog.DATA_DIR
    files = [data_dir / "catalog.v1.json", *sorted((data_dir / "items").glob("*.json"))]
    assert len(files) == 1 + len(eval_catalog.EVAL_RUN_IDS)
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pat in SECRET_PATTERNS:
            assert not pat.search(text), f"{path.name} matches {pat.pattern}"


def test_sources_are_repo_relative_and_hashes_match() -> None:
    _require_eval()
    cat = _catalog()
    listed = {s["path"] for s in cat["sources"]}
    for src in cat["sources"]:
        assert not src["path"].startswith("/")
        assert ".." not in src["path"]
        data = (REPO / src["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == src["sha256"], src["path"]
        assert len(data) == src["bytes"]
    for ref in _sources(cat):
        assert ref["path"] in listed, ref["path"]


def test_every_metric_pointer_resolves_to_its_value() -> None:
    _require_eval()
    cat = _catalog()
    docs: dict[str, Any] = {}
    metrics = list(_metrics(cat))
    assert len(metrics) > 100
    for m in metrics:
        src = m["source"]
        assert src["kind"] == "json", m["id"]
        doc = docs.setdefault(src["path"], json.loads((REPO / src["path"]).read_text()))
        assert _resolve(doc, src["pointer"]) == m["value"], (m["id"], src["pointer"])


def test_report_anchors_exist() -> None:
    _require_eval()
    for ref in _sources(_catalog()):
        if ref["kind"] != "report_md":
            continue
        text = (REPO / ref["path"]).read_text(encoding="utf-8")
        headings = re.findall(r"^#+ (.+?)\s*$", text, re.M)
        slugs = {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}
        assert ref["anchor"] in slugs, ref


def test_hard_gate_sums_are_computed_from_items() -> None:
    _require_eval()
    gates = {g["id"]: g for g in _catalog()["grounded"]["hard_gates"]}
    items = json.loads((REPO / "eval/baselines/phase3/live-v0/results.json").read_text())["items"]
    cited = sum(i["checks"]["citations"] for i in items)
    assert gates["citation_resolvability"]["n"] == cited
    assert gates["citation_resolvability"]["k"] == sum(i["checks"]["resolvable"] for i in items)
    assert all(g["pass"] for g in gates.values())


def test_builder_is_deterministic_except_built_at(tmp_path: Path) -> None:
    _require_eval()
    out = tmp_path / "a"
    cmd = [
        sys.executable,
        str(BUILDER),
        "--out",
        str(out),
        "--built-at",
        "2000-01-01T00:00:00+00:00",
    ]
    subprocess.run(  # noqa: S603 - fixed argv
        cmd, check=True, capture_output=True, cwd=REPO
    )
    committed = eval_catalog.DATA_DIR
    for rel in ["catalog.v1.json", *(f"items/{rid}.json" for rid in eval_catalog.EVAL_RUN_IDS)]:
        fresh, shipped = (out / rel).read_text(), (committed / rel).read_text()
        if rel == "catalog.v1.json":
            fresh_doc, shipped_doc = json.loads(fresh), json.loads(shipped)
            fresh_doc.pop("built_at")
            shipped_doc.pop("built_at")
            assert fresh_doc == shipped_doc, "catalog drifted: rerun scripts/build_eval_catalog.py"
            line = re.compile(r'^ "built_at": .*$', re.M)
            assert line.sub("", fresh) == line.sub("", shipped)
        else:
            assert fresh == shipped, f"{rel} drifted: rerun scripts/build_eval_catalog.py"


def test_builder_refuses_to_write_under_eval() -> None:
    _require_eval()
    proc = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, str(BUILDER), "--out", str(EVAL / "x")], capture_output=True, cwd=REPO
    )
    assert proc.returncode != 0
    assert not (EVAL / "x").exists()
