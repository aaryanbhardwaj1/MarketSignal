"""Gold dataset schema.

Two files per dataset version under ``eval/datasets/<version>/``:

* ``items.json``  - the curated, human-reviewed items (question, workspace, category, required
  fact ids). Written once, reviewed, then frozen; never edited to suit a retriever.
* ``frozen.json`` - produced by ``freeze-gold`` from ``items.json`` + the ingested corpus: each
  required fact's satisfying parent handle(s) and content hash, the item's split and leakage
  group, its lexical-overlap hardness, and a manifest (dataset/corpus/ledger hashes, pipeline
  versions). The evaluation runner reads only ``frozen.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CATEGORIES = frozenset(
    {
        "single_source_fact",
        "exact_number",
        "named_entity",
        "customer_free_text",
        "cross_format",
        "keyword_sensitive",
        "semantic_paraphrase",
        "enumeration",
        "ambiguous_distractor",
        "versioning",
    }
)
SPLITS = frozenset({"dev", "test"})


class DatasetError(ValueError):
    """The dataset file is malformed or inconsistent."""


@dataclass(frozen=True, slots=True)
class RequiredFact:
    fact_id: str
    grade: int = 2  # 2 = required for a complete answer (plan §26); 1 reserved for partial
    satisfied_by: tuple[str, ...] = ()  # parent handles; filled by freeze-gold
    parent_content_hashes: tuple[str, ...] = ()
    also_satisfied_by: tuple[str, ...] = ()  # reviewed alternates (other parents stating the fact)

    def handles(self) -> frozenset[str]:
        return frozenset(self.satisfied_by) | frozenset(self.also_satisfied_by)


@dataclass(frozen=True, slots=True)
class GoldItem:
    id: str
    question: str
    workspace: str
    category: str
    required_facts: tuple[RequiredFact, ...]
    tags: tuple[str, ...] = ()
    provenance: str = "llm_draft_reviewed"
    rationale: str = ""
    split: str | None = None
    group: str | None = None
    overlap: float | None = None  # share of query content stems present in the anchors
    overlap_bin: str | None = None
    hard_negatives: tuple[str, ...] = ()  # parents of ledger distractors of the required facts

    def fact_ids(self) -> tuple[str, ...]:
        return tuple(f.fact_id for f in self.required_facts)


@dataclass(frozen=True, slots=True)
class Dataset:
    version: str
    items: tuple[GoldItem, ...]
    manifest: dict[str, Any] = field(default_factory=dict)

    def split(self, name: str) -> tuple[GoldItem, ...]:
        return tuple(i for i in self.items if i.split == name)


def _fact(raw: dict[str, Any]) -> RequiredFact:
    return RequiredFact(
        fact_id=str(raw["fact_id"]),
        grade=int(raw.get("grade", 2)),
        satisfied_by=tuple(raw.get("satisfied_by", ())),
        parent_content_hashes=tuple(raw.get("parent_content_hashes", ())),
        also_satisfied_by=tuple(raw.get("also_satisfied_by", ())),
    )


def _item(raw: dict[str, Any]) -> GoldItem:
    facts = raw.get("required_facts") or []
    item = GoldItem(
        id=str(raw["id"]),
        question=str(raw["question"]).strip(),
        workspace=str(raw["workspace"]),
        category=str(raw["category"]),
        required_facts=tuple(_fact(f if isinstance(f, dict) else {"fact_id": f}) for f in facts),
        tags=tuple(raw.get("tags", ())),
        provenance=str(raw.get("provenance", "llm_draft_reviewed")),
        rationale=str(raw.get("rationale", "")),
        split=raw.get("split"),
        group=raw.get("group"),
        overlap=raw.get("overlap"),
        overlap_bin=raw.get("overlap_bin"),
        hard_negatives=tuple(raw.get("hard_negatives", ())),
    )
    validate_item(item)
    return item


def validate_item(item: GoldItem) -> None:
    if not item.question:
        raise DatasetError(f"{item.id}: empty question")
    if item.category not in CATEGORIES:
        raise DatasetError(f"{item.id}: unknown category {item.category!r}")
    if not item.required_facts:
        raise DatasetError(f"{item.id}: no required facts")
    if len(set(item.fact_ids())) != len(item.fact_ids()):
        raise DatasetError(f"{item.id}: duplicate required fact")
    if item.split is not None and item.split not in SPLITS:
        raise DatasetError(f"{item.id}: unknown split {item.split!r}")
    prefix = f"{item.workspace}/"
    for fact in item.required_facts:
        for handle in fact.handles():
            if not handle.startswith(prefix):
                raise DatasetError(f"{item.id}: {handle} is not in workspace {item.workspace}")


def load_items(path: Path) -> list[GoldItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = [_item(r) for r in raw["items"]]
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        raise DatasetError("duplicate item ids")
    return items


def load_frozen(path: Path) -> Dataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = tuple(_item(r) for r in raw["items"])
    return Dataset(
        version=str(raw["manifest"]["dataset_version"]), items=items, manifest=raw["manifest"]
    )


def item_to_dict(item: GoldItem) -> dict[str, Any]:
    out = asdict(item)
    out["required_facts"] = [asdict(f) for f in item.required_facts]
    return out


def write_frozen(path: Path, dataset: Dataset) -> None:
    payload = {"manifest": dataset.manifest, "items": [item_to_dict(i) for i in dataset.items]}
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
