"""Evaluation catalog, RAGAS section (E13): pointer fidelity, not-run honesty, item files, and
proof that adding the section changed no pre-existing catalog value or item file.

Tests that need ``eval/`` skip when it is absent and fail instead under ``MS_REQUIRE_EVAL=1``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from marketsignal.devtools import eval_catalog

REPO = Path(__file__).resolve().parents[3]
EVAL = REPO / "eval"
BUILDER = REPO / "scripts" / "build_eval_catalog.py"
SUMMARY_FIELDS = ("mean", "median", "p25", "p75", "min", "max", "n", "n_nan", "histogram")

# sha256 of ``json.dumps(section, sort_keys=True, ensure_ascii=False)`` for every top-level
# section of the catalog committed before the RAGAS section existed (git 3b5ed59), computed from
# ``git show 3b5ed59:backend/src/marketsignal/devtools/eval_catalog_data/catalog.v1.json``.
# ``built_at`` is excluded; ``sources`` is hashed after dropping the new RAGAS source entries.
PRE_RAGAS_SECTION_SHA256 = {
    "schema_version": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "sources": "97d502bff44897706a6d0cb7974baa47a72bd0a30f17f46b36f8d6422b49924b",
    "caveats": "53f0dd0af1a912e756e17e7ccf14971c622ec97fb9ec0a6f2758a0085c7691d9",
    "overview": "1e7e1e4e81e90eecaddff126d51daaafbd7ba8a45670a810c4ae62517dffe26e",
    "retrieval": "24d3c43b10dec18c15afc346348e8b92b7144362dc853f91a9141f550b3dfcf4",
    "grounded": "aca9cf50f7b261675321cb06c7197a761801143faa64a35f70ef6b04c1e54058",
    "research_tradeoff": "400b3a4108f0e99a899e7436c05a406fd13b0a7ec668077406ace86603202712",
    "analytics": "e30d3e125118cb5ce92003be0f7e76b580377c0be28e5810b65def18e28c7eda",
    "superseded": "98b775ed2701f8521f74d2c91db9f2578fb6bfbff29695da22740146cfa30667",
    "failure_runs": "612a4b78d48feee201cd70fcc8b9918644e7a86f2133244b484bf3372b4b1052",
}
# sha256 of the item files as committed at 3b5ed59 (byte-identical after the RAGAS change).
PRE_RAGAS_ITEM_SHA256 = {
    "p2-dev-final": "a691353f4fa53c14829e6895066913c4cd96bf5418baa9de8715602212d0b18c",
    "p2-test-c3": "c8bf9ad5c0bacae1a8b8c2dea60f347942072e3e9cf2e123322a08b56d6c898a",
    "p3-grounded-live": "0e8fab77df9bb31029555f389d400483108932b079b71f1004d94f100234de9d",
    "p4-research-dev": "f0680704322e7d2a75ffb9f52787383851a8232a6ff6209976f373fc0598bd99",
    "p4-research-test": "3821686e2b9bffd6197a367a06b84c4c9f765bf9177ac1495592455393a571d3",
    "p5-analytics-dev": "364568c88ac267495c06320bbc3ef5040f15a8cf501bed26953855691ae5e7b8",
    "p5-analytics-holdout": "da1bff34dde74b4560a74fe9cf2b12dea4309a8baf2976afb5a16357c4727485",
}
RAGAS_SOURCE_PREFIX = "eval/baselines/ragas/"


def _require_eval() -> None:
    if not EVAL.is_dir():
        if os.environ.get("MS_REQUIRE_EVAL") == "1":
            pytest.fail("eval/ is required (MS_REQUIRE_EVAL=1) but missing")
        pytest.skip("eval/ not present")


def _catalog() -> dict[str, Any]:
    return eval_catalog.load_catalog().payload


def _ragas() -> dict[str, Any]:
    section: dict[str, Any] = _catalog()["ragas"]
    return section


def _resolve(doc: Any, pointer: str) -> Any:
    node = doc
    for raw in pointer.lstrip("/").split("/") if pointer else []:
        token = raw.replace("~1", "/").replace("~0", "~")
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


def _canonical_sha(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _metrics() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    return [
        (run["id"], cfg, m)
        for run in _ragas()["runs"]
        for cfg in run["configurations"]
        for m in cfg["metrics"]
    ]


def test_section_shape_and_run_ids() -> None:
    ragas = _ragas()
    assert ragas["telemetry_disabled"] is True
    assert ragas["ragas_version"]
    assert [r["id"] for r in ragas["runs"]] == list(eval_catalog.RAGAS_RUN_IDS)
    assert set(eval_catalog.RAGAS_RUN_IDS) <= set(eval_catalog.EVAL_RUN_IDS)
    known = {f["run_id"] for f in _catalog()["failure_runs"]}
    assert {r["source_run"] for r in ragas["runs"]} <= known
    families = {d["family"] for d in ragas["definitions"]}
    assert families == {"ragas_non_llm", "ragas_llm_judge"}
    keys = {d["key"] for d in ragas["definitions"]}
    for _, _, m in _metrics():
        assert m["key"] in keys
        assert m["status"] in {"computed", "not_run"}
    assert {c["id"] for c in ragas["caveats"]} == {
        "ragas-heuristics-not-truth",
        "ragas-id-recall-counts-alternates",
        "ragas-llm-metrics-not-run",
        "ragas-offline-persisted-outputs",
    }


def test_llm_metrics_are_not_run_and_carry_no_numbers() -> None:
    llm = {d["key"] for d in _ragas()["definitions"] if d["needs_llm"]}
    assert llm
    for _, cfg, m in _metrics():
        if m["key"] in llm:
            assert m["status"] == "not_run"
        if m["status"] == "not_run":
            assert m["summary"] is None
            assert m["not_run_reason"] in {"model_credits_unavailable", "no_reference_answers"}
        else:
            assert m["not_run_reason"] is None
            assert set(m["summary"]) == set(SUMMARY_FIELDS)
            assert m["summary"]["n"] + m["summary"]["n_nan"] == cfg["n_samples"]


def test_every_ragas_number_resolves_to_its_source() -> None:
    _require_eval()
    docs: dict[str, Any] = {}
    computed = 0
    for _, _, m in _metrics():
        src = m["source"]
        assert src["kind"] == "json"
        assert src["path"].startswith(RAGAS_SOURCE_PREFIX)
        doc = docs.setdefault(src["path"], json.loads((REPO / src["path"]).read_text()))
        block = _resolve(doc, src["pointer"])
        assert block["status"] == m["status"]
        if m["status"] == "computed":
            computed += 1
            for field in SUMMARY_FIELDS:
                value = _resolve(doc, f"{src['pointer']}/{field}")
                assert value == m["summary"][field], (src["pointer"], field)
        else:
            assert not set(SUMMARY_FIELDS) & set(block)
    assert computed == 6 * 3  # six model-free metrics x three run configurations


def test_reconciliation_metrics_point_at_ragas_and_compare_json() -> None:
    _require_eval()
    caveat = next(c for c in _ragas()["caveats"] if c["id"] == "ragas-id-recall-counts-alternates")
    paths = {m["source"]["path"] for m in caveat["metrics"]}
    assert paths == {
        "eval/baselines/ragas/p4-research-test-nonllm/results.json",
        "eval/baselines/phase4/research-v0-test-live/compare.json",
    }
    for m in caveat["metrics"]:
        doc = json.loads((REPO / m["source"]["path"]).read_text())
        assert _resolve(doc, m["source"]["pointer"]) == m["value"]
        assert m["n"] == 30
    by_id = {m["id"]: m["value"] for m in caveat["metrics"]}
    for cfg in ("standard", "research"):
        ragas_id = by_id[f"ragas.p4.test.{cfg}.id_context_recall_pack"]
        historical = by_id[f"p4.test.gold_handle_recall.{cfg}"]
        assert ragas_id < historical  # alternates counted: the definitional gap


def test_excluded_reasons_add_up() -> None:
    for run in _ragas()["runs"]:
        for cfg in run["configurations"]:
            assert sum(r["n"] for r in cfg["excluded_reasons"]) == cfg["n_excluded"]


def test_ragas_items_pages_and_configuration_filter() -> None:
    for run in _ragas()["runs"]:
        rid = run["id"]
        total = sum(c["n_samples"] for c in run["configurations"])
        assert eval_catalog.load_items(rid, limit=50)["total"] == total
        for cfg in run["configurations"]:
            page = eval_catalog.load_items(rid, bucket=cfg["name"], limit=50)
            assert page["total"] == cfg["n_samples"]
            for item in page["items"]:
                assert item["phase"] == "ragas"
                assert item["configuration"] == cfg["name"]
                assert item["question"]
                for v in item["scores"].values():
                    assert v is None or (isinstance(v, float) and not math.isnan(v))


def test_pre_existing_sections_are_unchanged() -> None:
    cat = _catalog()
    assert set(cat) == {"built_at", "ragas", *PRE_RAGAS_SECTION_SHA256}
    for key, expected in PRE_RAGAS_SECTION_SHA256.items():
        value = cat[key]
        if key == "sources":
            value = [s for s in value if not s["path"].startswith(RAGAS_SOURCE_PREFIX)]
        assert _canonical_sha(value) == expected, f"pre-existing section {key!r} changed"


def test_pre_existing_item_files_are_byte_identical() -> None:
    for rid, expected in PRE_RAGAS_ITEM_SHA256.items():
        data = (eval_catalog.DATA_DIR / "items" / f"{rid}.json").read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, rid


def test_frontend_fixture_is_a_copy_of_the_catalog() -> None:
    fixture = REPO / "frontend/src/lib/api/__fixtures__/evaluation-catalog.json"
    if not fixture.is_file():
        pytest.skip("frontend/ not present")
    assert fixture.read_bytes() == eval_catalog.CATALOG_FILE.read_bytes()


def test_fresh_build_keeps_pre_existing_sections(tmp_path: Path) -> None:
    _require_eval()
    out = tmp_path / "fresh"
    subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, str(BUILDER), "--out", str(out), "--built-at", "2000-01-01T00:00:00Z"],
        check=True,
        capture_output=True,
        cwd=REPO,
    )
    fresh = json.loads((out / "catalog.v1.json").read_text())
    for key, expected in PRE_RAGAS_SECTION_SHA256.items():
        value = fresh[key]
        if key == "sources":
            value = [s for s in value if not s["path"].startswith(RAGAS_SOURCE_PREFIX)]
        assert _canonical_sha(value) == expected, key
    for rid, expected in PRE_RAGAS_ITEM_SHA256.items():
        data = (out / "items" / f"{rid}.json").read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, rid
