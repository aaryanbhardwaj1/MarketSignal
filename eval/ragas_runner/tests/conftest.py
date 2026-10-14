"""Tiny inline samples whose ID-based scores can be computed by hand."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

PASSAGE_A = "Northstar grew enterprise revenue twelve percent year over year in the west region."
PASSAGE_B = "Churn among mid-market accounts rose after the pricing change in the second quarter."
PASSAGE_C = "The competitor launched a bundled analytics tier aimed at regional banks."
PASSAGE_D = "Support ticket volume fell after the onboarding redesign shipped."
PASSAGE_E = "Partner-sourced pipeline doubled across the APAC channel program this year."
PASSAGE_X = "Gross margin held at sixty-one percent despite higher cloud hosting costs."


def _sample(
    item_id: str,
    *,
    configuration: str = "standard",
    pack: list[tuple[str, str]],
    cited: list[tuple[str, str]],
    gold: list[tuple[str, str]],
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "category": "answerable_fact",
        "configuration": configuration,
        "user_input": f"Question for {item_id}?",
        "response": f"Answer for {item_id}.",
        "reference": None,
        "retrieved_context_ids": [h for h, _ in pack],
        "cited_context_ids": [h for h, _ in cited],
        "reference_context_ids": [h for h, _ in gold],
        "retrieved_contexts": [t for _, t in pack],
        "cited_contexts": [t for _, t in cited],
        "reference_contexts": [t for _, t in gold],
        "excluded": None,
    }


def make_samples_payload() -> dict[str, Any]:
    a, b, c, d = ("h:a", PASSAGE_A), ("h:b", PASSAGE_B), ("h:c", PASSAGE_C), ("h:d", PASSAGE_D)
    e, x = ("h:e", PASSAGE_E), ("h:x", PASSAGE_X)
    return {
        "format": "marketsignal.ragas-samples",
        "format_version": 1,
        "run": {
            "id": "unit-run",
            "title": "Unit run",
            "results_path": "eval/baselines/unit/results.json",
            "results_sha256": "0" * 64,
            "dataset_path": "eval/datasets/unit/items.json",
            "dataset_sha256": "1" * 64,
            "split": "test",
            "configurations": ["standard"],
        },
        "created_at": "2026-10-14T00:00:00Z",
        "git_sha": "abc123",
        "corpus": {"workspace": "NORTHSTAR", "texts_sha256": "2" * 64},
        "samples": [
            # pack recall 1/2, pack precision 1/4, cited recall 1/2, cited precision 1/1
            _sample("U-001", pack=[a, b, c, d], cited=[a], gold=[a, e]),
            # pack recall 1/1, pack precision 1/1, cited recall 0/1, cited precision undefined
            _sample("U-002", pack=[x], cited=[], gold=[x]),
        ],
        "excluded": [
            {"item_id": "U-003", "configuration": "standard", "reason": "no_gold_handles"},
        ],
    }


@pytest.fixture
def samples_payload() -> dict[str, Any]:
    return copy.deepcopy(make_samples_payload())


@pytest.fixture
def samples_file(tmp_path: Path, samples_payload: dict[str, Any]) -> Path:
    path = tmp_path / "unit-run.samples.json"
    path.write_text(json.dumps(samples_payload), encoding="utf-8")
    return path


def write_payload(tmp_path: Path, payload: dict[str, Any], name: str = "s.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
