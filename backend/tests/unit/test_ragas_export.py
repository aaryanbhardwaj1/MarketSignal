"""RAGAS sample exporter: pure pieces (markup stripping, gold handles, exclusions, assembly,
ordering, digests, output-path guard) over small inline fixtures. No database, no model."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from marketsignal.evaluation import corpus
from marketsignal.evaluation.ragas_export import (
    FORMAT,
    FORMAT_VERSION,
    RUNS,
    ExportError,
    assemble,
    build_document,
    check_out_path,
    default_out_path,
    gold_handles,
    handle_workspace,
    handles_to_resolve,
    pre_exclusion,
    sha256_file,
    strip_citations,
    texts_sha256,
)

A, B, C, D = (f"NS/DOC@v1:S1.B{n}" for n in range(1, 5))
TEXTS = {A: "alpha text", B: "beta text", C: "gamma text", D: "delta text"}


def _gold(item_id: str, *handle_sets: list[str], expect: str = "answer") -> dict[str, Any]:
    return {
        "id": item_id,
        "workspace": "NS",
        "category": "answerable_fact",
        "question": f"question {item_id}?",
        "expect": expect,
        "gold_facts": [{"fact_id": f"F{i}", "handles": hs} for i, hs in enumerate(handle_sets)],
    }


def _result(item_id: str, pack: list[str], cited: list[str], content: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "category": "answerable_fact",
        "question": f"question {item_id}?",
        "pack_handles": pack,
        "cited_handles": cited,
        "content": content,
    }


# --- strip_citations ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Sales rose [[NS/DOC@v1:S1.B1]].", "Sales rose."),
        ("Two [[NS/A@v1:P1]][[NS/B@v1:P2]], then more.", "Two, then more."),
        ("Total was 12 [[result:3f2a-9c]] units.", "Total was 12 units."),
        ("A claim [[NS/A@v1:P1]] [inference].", "A claim [inference]."),
        ("Value (see [[NS/A@v1:P1]]) here.", "Value (see) here."),
        ("Only ([[NS/A@v1:P1]]) cite.", "Only cite."),
        (
            "### Answer\n\nLine one [[NS/A@v1:P1]].  \n- item [[NS/B@v1:P2]]",
            "### Answer\n\nLine one.\n- item",
        ),
        ("No markup at all.", "No markup at all."),
    ],
)
def test_strip_citations(raw: str, clean: str) -> None:
    assert strip_citations(raw) == clean


def test_strip_citations_keeps_single_brackets_and_newlines() -> None:
    assert strip_citations("x [inference]\n\ny [[NS/A@v1:P1]]") == "x [inference]\n\ny"


# --- gold handles and pre-resolution exclusions ------------------------------------------


def test_gold_handles_dedup_in_order_over_alternates() -> None:
    item = _gold("G1", [B, A], [A], [C])
    assert gold_handles(item) == [B, A, C]


def test_gold_handles_empty_when_facts_have_none() -> None:
    assert gold_handles(_gold("G1", [])) == []
    assert gold_handles({"id": "G1", "gold_facts": []}) == []


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (_gold("G1", [A]), None),
        (_gold("G1", [A], expect="conflict"), None),
        (_gold("G1", [], expect="answer"), "no_gold_handles"),
        (_gold("G1", [], expect="conflict"), "no_gold_handles"),
        (_gold("G1", [], expect="insufficient"), "abstention_expected"),
        (_gold("G1", [A], expect="insufficient"), "abstention_expected"),
        (_gold("G1", [], expect="abstain_no_llm"), "abstention_expected"),
    ],
)
def test_pre_exclusion(item: dict[str, Any], reason: str | None) -> None:
    assert pre_exclusion(item) == reason


# --- assembly ------------------------------------------------------------------------------


def _dataset() -> list[dict[str, Any]]:
    return [
        _gold("G2", [B]),
        _gold("G1", [A], [D]),
        _gold("G3", [], expect="insufficient"),
        _gold("G4", []),
        _gold("G5", [C]),
    ]


def _results() -> list[dict[str, Any]]:
    return [
        _result("G2", [B, C], [B], "B said so [[NS/DOC@v1:S1.B2]]."),
        _result("G1", [A, B, A], [A], "A said so [[NS/DOC@v1:S1.B1]]."),
        _result("G3", [], [], "Not enough evidence."),
        _result("G4", [A], [A], "x"),
        _result("G5", ["XX/FOREIGN@v1:P1", C], [C], "y"),
    ]


def test_handles_to_resolve_skips_pre_excluded_and_foreign_in_sample_order() -> None:
    handles = handles_to_resolve(_dataset(), {"standard": _results()})
    assert handles == {"NS": [A, B, D, C]}  # G5 names XX/...: never requested anywhere


def test_handles_to_resolve_groups_by_item_workspace() -> None:
    other = {**_gold("G9", ["SP/DOC@v1:P1"]), "workspace": "SP"}
    results = [_result("G9", ["SP/DOC@v1:P1"], [], "z"), _results()[1]]
    assert handles_to_resolve([*_dataset(), other], {"standard": results}) == {
        "NS": [A, B, D],
        "SP": ["SP/DOC@v1:P1"],
    }


@pytest.mark.parametrize(
    ("handle", "ws"),
    [("NS/DOC@v1:S1.B1", "NS"), ("SOUTHPEAK/X@v2:P1", "SOUTHPEAK"), ("result:3f2a", None)],
)
def test_handle_workspace(handle: str, ws: str | None) -> None:
    assert handle_workspace(handle) == ws


def test_assemble_samples_and_exclusions() -> None:
    texts: dict[str, str | None] = {**TEXTS, "XX/FOREIGN@v1:P1": "must never be used"}
    samples, excluded = assemble(_dataset(), {"standard": _results()}, texts)
    assert [s["item_id"] for s in samples] == ["G1", "G2"]
    g1 = samples[0]
    assert g1 == {
        "item_id": "G1",
        "category": "answerable_fact",
        "configuration": "standard",
        "user_input": "question G1?",
        "response": "A said so.",
        "reference": None,
        "retrieved_context_ids": [A, B],
        "cited_context_ids": [A],
        "reference_context_ids": [A, D],
        "retrieved_contexts": ["alpha text", "beta text"],
        "cited_contexts": ["alpha text"],
        "reference_contexts": ["alpha text", "delta text"],
        "excluded": None,
    }
    assert excluded == [
        {"item_id": "G3", "configuration": "standard", "reason": "abstention_expected"},
        {"item_id": "G4", "configuration": "standard", "reason": "no_gold_handles"},
        {"item_id": "G5", "configuration": "standard", "reason": "foreign_handle"},
    ]


def test_assemble_missing_text_is_unresolvable() -> None:
    texts = {k: v for k, v in TEXTS.items() if k != D}
    samples, excluded = assemble(_dataset(), {"standard": _results()}, texts)
    assert [s["item_id"] for s in samples] == ["G2"]
    assert {"item_id": "G1", "configuration": "standard", "reason": "unresolvable_handle"} in (
        excluded
    )


def test_assemble_two_configurations_orders_by_configuration_then_id() -> None:
    research = [_result("G2", [C], [C], "r2"), _result("G1", [D], [D], "r1")]
    samples, _ = assemble(_dataset()[:2], {"standard": _results()[:2], "research": research}, TEXTS)
    assert [(s["configuration"], s["item_id"]) for s in samples] == [
        ("standard", "G1"),
        ("standard", "G2"),
        ("research", "G1"),
        ("research", "G2"),
    ]
    assert samples[2]["retrieved_contexts"] == ["delta text"]


def test_assemble_rejects_unknown_and_duplicate_items() -> None:
    with pytest.raises(ExportError, match="not in the dataset"):
        assemble(_dataset(), {"standard": [_result("ZZ", [], [], "")]}, TEXTS)
    dup = [_results()[0], _results()[0]]
    with pytest.raises(ExportError, match="duplicate"):
        assemble(_dataset(), {"standard": dup}, TEXTS)


# --- digests and document --------------------------------------------------------------------


def test_texts_sha256_over_contexts_in_sample_order() -> None:
    samples, _ = assemble(_dataset()[:2], {"standard": _results()[:2]}, TEXTS)
    expected = hashlib.sha256()
    for s in samples:
        for t in (*s["retrieved_contexts"], *s["cited_contexts"], *s["reference_contexts"]):
            expected.update(t.encode("utf-8") + b"\x00")
    assert texts_sha256(samples) == expected.hexdigest()
    assert texts_sha256(list(reversed(samples))) != texts_sha256(samples)


def test_sha256_file(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_bytes(b"abc")
    assert sha256_file(path) == hashlib.sha256(b"abc").hexdigest()


def test_build_document_shape() -> None:
    samples, excluded = assemble(_dataset(), {"standard": _results()}, TEXTS)
    doc = build_document(
        RUNS["p3-live-v0"],
        split="all",
        results_files=[("standard", "eval/r.json", "aa")],
        dataset_sha256="bb",
        samples=samples,
        excluded=excluded,
        created_at="2026-10-14T00:00:00+00:00",
        git_sha="abc1234",
        workspaces=["NORTHSTAR"],
    )
    assert doc["format"] == FORMAT == "marketsignal.ragas-samples"
    assert doc["format_version"] == FORMAT_VERSION == 1
    assert doc["run"]["id"] == "p3-live-v0"
    assert doc["run"]["results_path"] == "eval/r.json"
    assert doc["run"]["results_sha256"] == "aa"
    assert doc["run"]["results_files"] == [
        {"configuration": "standard", "path": "eval/r.json", "sha256": "aa"}
    ]
    assert doc["run"]["dataset_sha256"] == "bb"
    assert doc["run"]["configurations"] == ["standard"]
    assert doc["corpus"] == {
        "workspace": "NORTHSTAR",
        "workspaces": ["NORTHSTAR"],
        "texts_sha256": texts_sha256(samples),
    }
    assert doc["samples"] == samples
    assert doc["excluded"] == excluded
    json.dumps(doc)  # serialisable


def test_run_registry_points_at_committed_files() -> None:
    assert RUNS["p3-live-v0"].configurations == ("standard",)
    assert RUNS["p4-research-test"].configurations == ("standard", "research")
    for spec in RUNS.values():
        assert (corpus.REPO_ROOT / spec.dataset_path).is_file()
        for _, path in spec.results:
            assert (corpus.REPO_ROOT / path).is_file()
            assert not Path(path).is_absolute()


# --- output path guard ---------------------------------------------------------------------


def test_default_out_path() -> None:
    assert default_out_path("p3-live-v0") == (
        corpus.EVAL_DIR / "reports" / "ragas-inputs" / "p3-live-v0.samples.json"
    )


@pytest.mark.parametrize("sub", ["baselines/x.json", "datasets/grounded-v0/s.json", "baselines"])
def test_check_out_path_refuses_frozen_artifacts(sub: str) -> None:
    with pytest.raises(ExportError, match="refusing"):
        check_out_path(corpus.EVAL_DIR / sub)


def test_check_out_path_refuses_traversal_into_frozen_artifacts() -> None:
    with pytest.raises(ExportError):
        check_out_path(corpus.EVAL_DIR / "reports" / ".." / "baselines" / "s.json")


def test_check_out_path_allows_reports_and_tmp(tmp_path: Path) -> None:
    check_out_path(corpus.EVAL_DIR / "reports" / "ragas-inputs" / "x.json")
    check_out_path(tmp_path / "x.json")


def test_cli_refuses_frozen_output_before_touching_the_database(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from marketsignal.evaluation.cli import main

    out = corpus.EVAL_DIR / "baselines" / "ragas-should-not-exist.json"
    assert main(["ragas-export", "--run", "p3-live-v0", "--out", str(out)]) == 2
    assert "refusing" in capsys.readouterr().err
    assert not out.exists()
