"""Evaluation harness: metric definitions, statistics, grouped split and dataset validation."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from marketsignal.evaluation import corpus
from marketsignal.evaluation.dataset import DatasetError, GoldItem, RequiredFact, load_frozen
from marketsignal.evaluation.metrics import aggregate, dedupe_parents, score_item
from marketsignal.evaluation.overlap import content_stems, overlap_bin, overlap_share
from marketsignal.evaluation.split import assign_splits, leakage_groups, leakage_violations
from marketsignal.evaluation.stats import bootstrap_mean, mcnemar_exact, wilson

FROZEN = corpus.EVAL_DIR / "datasets" / "retrieval-v0" / "frozen.json"
ITEMS = corpus.EVAL_DIR / "datasets" / "retrieval-v0" / "items.json"


def _item(item_id: str, *facts: tuple[str, str], category: str = "single_source_fact") -> GoldItem:
    return GoldItem(
        id=item_id,
        question=f"question {item_id}",
        workspace="WS",
        category=category,
        required_facts=tuple(RequiredFact(f, satisfied_by=(h,)) for f, h in facts),
    )


# --- metrics ----------------------------------------------------------------------------------


def test_children_map_to_distinct_parents_in_first_occurrence_order() -> None:
    assert dedupe_parents(["WS/A@v1:P1", "WS/B@v1:P1", "WS/A@v1:P1", "WS/C@v1:P1"]) == [
        "WS/A@v1:P1",
        "WS/B@v1:P1",
        "WS/C@v1:P1",
    ]


def test_item_metrics_for_a_multi_fact_item() -> None:
    item = _item("x", ("F1", "WS/A@v1:P1"), ("F2", "WS/B@v1:P2"))
    score = score_item(item, ["WS/Z@v1:P9", "WS/B@v1:P2", "WS/Y@v1:P8", "WS/A@v1:P1"])
    assert score.fact_ranks == {"F1": 4, "F2": 2}
    assert score.recall_at(1) == 0.0
    assert score.recall_at(2) == 0.5
    assert score.recall_at(4) == 1.0
    assert score.hit_at(2)
    assert not score.hit_at(1)
    assert score.reciprocal_rank() == 0.5
    assert score.reciprocal_rank(cutoff=1) == 0.0


def test_alternate_handles_count_as_satisfying() -> None:
    fact = RequiredFact("F1", satisfied_by=("WS/A@v1:P1",), also_satisfied_by=("WS/B@v1:P3",))
    item = GoldItem("x", "q", "WS", "single_source_fact", (fact,))
    assert score_item(item, ["WS/B@v1:P3"]).fact_ranks == {"F1": 1}


def test_missing_fact_scores_zero() -> None:
    score = score_item(_item("x", ("F1", "WS/A@v1:P1")), ["WS/B@v1:P1"])
    assert score.fact_ranks == {"F1": None}
    assert score.reciprocal_rank() == 0.0
    agg = aggregate([score])
    assert agg["hit@10"] == 0.0
    assert agg["mrr"] == 0.0


# --- statistics -------------------------------------------------------------------------------


def test_wilson_interval_matches_reference_values() -> None:
    interval = wilson(8, 10)
    assert interval.estimate == 0.8
    assert math.isclose(interval.low, 0.4902, abs_tol=1e-3)
    assert math.isclose(interval.high, 0.9433, abs_tol=1e-3)
    assert wilson(0, 0).low == 0.0


def test_bootstrap_is_deterministic_and_brackets_the_mean() -> None:
    values = [0.0, 1.0, 1.0, 0.5, 0.25, 1.0, 0.0, 1.0]
    a, b = bootstrap_mean(values), bootstrap_mean(values)
    assert a == b
    assert a.low <= a.estimate <= a.high


def test_exact_mcnemar() -> None:
    a = [True] * 10 + [False] * 10
    b = [True] * 10 + [True] * 8 + [False] * 2
    result = mcnemar_exact(a, b)
    assert (result.only_a, result.only_b) == (0, 8)
    assert math.isclose(result.p_value, 2 / 2**8, rel_tol=1e-9)
    assert mcnemar_exact([True], [True]).p_value == 1.0


# --- overlap ----------------------------------------------------------------------------------


def test_overlap_is_retriever_independent_and_bounded() -> None:
    assert content_stems("The shoppers are returning shoes") == content_stems("shopper return shoe")
    assert "the" not in content_stems("The shoppers")
    assert overlap_share("returning shoes", ["shoe returns are high"]) == 1.0
    assert overlap_share("why do people leave", ["shoe returns are high"]) == 0.0
    assert [overlap_bin(x) for x in (0.1, 0.5, 0.9)] == ["low", "mid", "high"]


# --- split ------------------------------------------------------------------------------------


def test_paraphrases_and_related_facts_share_a_group() -> None:
    items = [
        _item("a", ("F1", "WS/A@v1:P1")),
        _item("b", ("F1", "WS/A@v1:P1")),  # paraphrase of the same fact
        _item("c", ("F2", "WS/B@v1:P1")),  # related to F1 via the ledger
        _item("d", ("F3", "WS/A@v1:P1")),  # different fact, same parent
        _item("e", ("F4", "WS/C@v1:P1")),
    ]
    groups = leakage_groups(items, [("F1", "F2")])
    assert groups["a"] == groups["b"] == groups["c"] == groups["d"]
    assert groups["e"] != groups["a"]


def test_split_is_deterministic_grouped_and_clean() -> None:
    items = [_item(f"i{n:02d}", (f"F{n}", f"WS/S@v1:P{n}")) for n in range(30)]
    items += [_item("dup", ("F3", "WS/S@v1:P3"))]
    first = assign_splits(items, test_fraction=0.3, seed="s")
    second = assign_splits(list(reversed(items)), test_fraction=0.3, seed="s")
    assert {i.id: i.split for i in first} == {i.id: i.split for i in second}
    assert leakage_violations(first) == []
    by_id = {i.id: i for i in first}
    assert by_id["dup"].split == by_id["i03"].split
    test_share = sum(1 for i in first if i.split == "test") / len(first)
    assert 0.2 <= test_share <= 0.4


def test_leakage_check_detects_a_shared_fact() -> None:
    items = assign_splits([_item("a", ("F1", "WS/A@v1:P1")), _item("b", ("F2", "WS/B@v1:P1"))])
    forced = [
        items[0].__class__(**{**_as_kwargs(items[0]), "split": "dev"}),
        items[1].__class__(
            **{**_as_kwargs(items[1]), "split": "test", "required_facts": items[0].required_facts}
        ),
    ]
    assert any("both splits" in p or "spans" in p for p in leakage_violations(forced))


def _as_kwargs(item: GoldItem) -> dict[str, object]:
    return {f: getattr(item, f) for f in item.__dataclass_fields__}


# --- dataset ----------------------------------------------------------------------------------


def test_items_in_the_wrong_workspace_are_rejected(tmp_path: Path) -> None:
    bad = {
        "items": [
            {
                "id": "x",
                "question": "q",
                "workspace": "NORTHSTAR",
                "category": "single_source_fact",
                "required_facts": [{"fact_id": "F", "satisfied_by": ["SOUTHPEAK/A@v1:P1"]}],
            }
        ],
        "manifest": {"dataset_version": "t"},
    }
    path = tmp_path / "frozen.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(DatasetError, match="not in workspace"):
        load_frozen(path)


@pytest.mark.skipif(not FROZEN.exists(), reason="dataset not frozen yet")
def test_committed_dataset_is_pinned_and_leak_free() -> None:
    """The offline half of gold integrity (the DB half runs in the retrieval-eval CI job)."""
    dataset = load_frozen(FROZEN)
    manifest = dataset.manifest
    assert manifest["corpus_sha256"] == corpus.corpus_sha256()
    assert manifest["ledger_sha256"] == corpus.ledger_sha256()
    assert manifest["items_sha256"] == corpus.sha256_bytes(ITEMS.read_bytes())
    ledger = corpus.load_ledger()
    assert leakage_violations(dataset.items, corpus.related_fact_pairs(ledger)) == []
    facts = {f["fact_id"]: f for f in ledger["facts"]}
    for item in dataset.items:
        for fact in item.required_facts:
            assert facts[fact.fact_id]["workspace_code"] == item.workspace
            assert fact.satisfied_by
            assert len(fact.satisfied_by) == len(fact.parent_content_hashes)
            for handle in fact.handles():
                assert handle.startswith(f"{item.workspace}/")
    counts = manifest["counts"]
    assert counts["dev"] + counts["test"] == counts["items"] == len(dataset.items)


def test_task_type_rule() -> None:
    from marketsignal.evaluation.task_types import item_task_type

    assert item_task_type({"F1": "retrieval", "F2": "retrieval"}) == "retrieval"
    assert item_task_type({"F1": "analytics"}) == "analytics"
    assert item_task_type({"F1": "retrieval", "F2": "analytics"}) == "multi_tool"


def test_committed_task_types_match_the_frozen_dataset() -> None:
    import json

    path = FROZEN.parent / "task-types.json"
    data = json.loads(path.read_text())
    dataset = load_frozen(FROZEN)
    assert data["items_sha256"] == dataset.manifest["items_sha256"]
    assert set(data["items"]) == {i.id for i in dataset.items}
    for item in dataset.items:
        assert set(data["items"][item.id]["facts"]) == set(item.fact_ids())
