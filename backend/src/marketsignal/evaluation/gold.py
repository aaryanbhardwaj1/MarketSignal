"""``freeze-gold`` and gold integrity (plan §27).

Freeze: for every required fact, find the *active* parent that contains its planted anchor
(sentence anchors after whitespace normalisation; row anchors by key column + key value in the
named sheet), record its handle and content hash, compute overlap hardness and assign the
grouped split. Parents elsewhere that contain all of a fact's surface forms are written to a
separate review file - they are never added automatically, so distractors cannot be labelled
relevant; a reviewer moves genuine alternates into ``also_satisfied_by`` in ``items.json``.

Integrity: every handle resolves through the production resolver in its own workspace, the
parent still contains the anchor, the content hash is unchanged, the dataset is pinned to the
current corpus, ledger and items file, and no fact or parent leaks across dev/test.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import text

from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.db.session import SessionFactory, scoped_session, unscoped_session
from marketsignal.evaluation import corpus
from marketsignal.evaluation.dataset import Dataset, GoldItem, RequiredFact
from marketsignal.evaluation.overlap import overlap_bin, overlap_share
from marketsignal.evaluation.split import assign_splits, leakage_violations
from marketsignal.evidence.resolver import resolve_evidence

_WS = re.compile(r"\s+")

_ACTIVE_PARENTS = """
SELECT p.handle, p.text, p.content_hash, s.source_code, v.version
FROM parent_chunks p
JOIN source_versions v ON v.id = p.source_version_id
JOIN sources s ON s.id = v.source_id
WHERE s.deleted_at IS NULL AND s.current_version_id = v.id
  AND v.status IN ('ready', 'ready_degraded')
"""
_ACTIVE_ROWS = """
SELECT t.name, r.values, r.parent_handle, s.source_code
FROM dataset_rows r
JOIN dataset_tables t ON t.id = r.table_id
JOIN source_versions v ON v.id = t.source_version_id
JOIN sources s ON s.id = v.source_id
WHERE s.deleted_at IS NULL AND s.current_version_id = v.id
"""


class GoldFreezeError(RuntimeError):
    """An anchor could not be located exactly once in the active corpus."""


def norm(value: str) -> str:
    return _WS.sub(" ", value).strip()


@dataclass(frozen=True, slots=True)
class ActiveParent:
    handle: str
    text: str
    content_hash: str
    source_code: str
    version: int


@dataclass(frozen=True, slots=True)
class WorkspaceCorpus:
    scope: WorkspaceScope
    parents: dict[str, ActiveParent]
    rows: list[tuple[str, dict[str, Any], str, str]]


async def load_workspace(factory: SessionFactory, code: str) -> WorkspaceCorpus:
    async with unscoped_session(factory) as session:
        ws_id = (
            await session.execute(text("SELECT id FROM workspaces WHERE code = :c"), {"c": code})
        ).scalar_one()
    scope = WorkspaceScope(uuid.UUID(str(ws_id)), code)
    async with scoped_session(factory, scope) as session:
        parents = {
            r[0]: ActiveParent(r[0], r[1], r[2].strip(), r[3], int(r[4]))
            for r in (await session.execute(text(_ACTIVE_PARENTS))).all()
        }
        rows = [(r[0], r[1], r[2], r[3]) for r in (await session.execute(text(_ACTIVE_ROWS))).all()]
    return WorkspaceCorpus(scope, parents, rows)


def anchor_text(fact: dict[str, Any]) -> str:
    """The text a question is compared against for overlap hardness."""
    anchor = fact["anchor"]
    if anchor["type"] == "sentence":
        return str(anchor["text"])
    return f"{anchor['key_value']} {anchor['value_column'].replace('_', ' ')} {anchor['value']}"


def locate(fact: dict[str, Any], ws: WorkspaceCorpus) -> list[str]:
    anchor = fact["anchor"]
    if anchor["type"] == "sentence":
        target = norm(anchor["text"])
        return sorted(
            p.handle
            for p in ws.parents.values()
            if p.source_code == fact["source_code"] and target in norm(p.text)
        )
    return sorted(
        handle
        for sheet, values, handle, source_code in ws.rows
        if source_code == fact["source_code"]
        and (anchor.get("sheet") is None or sheet == anchor["sheet"])
        and str(values.get(anchor["key_column"])) == str(anchor["key_value"])
        and handle in ws.parents
    )


def parent_contains_anchor(fact: dict[str, Any], parent_text: str) -> bool:
    anchor = fact["anchor"]
    if anchor["type"] == "sentence":
        return norm(anchor["text"]) in norm(parent_text)
    key = f"{anchor['key_column']}: {anchor['key_value']}"
    return key in parent_text and f"{anchor['value_column']}:" in parent_text


def surface_form_candidates(
    fact: dict[str, Any], ws: WorkspaceCorpus, exclude: set[str]
) -> list[str]:
    forms = [str(f).lower() for f in fact.get("surface_forms") or [] if str(f).strip()]
    if not forms:
        return []
    return sorted(
        p.handle
        for p in ws.parents.values()
        if p.handle not in exclude and all(f in p.text.lower() for f in forms)
    )


async def freeze(
    items: Sequence[GoldItem],
    factory: SessionFactory,
    settings: Settings,
    *,
    items_sha256: str,
    ledger: dict[str, Any],
    decided: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[Dataset, dict[str, Any]]:
    """``decided``: (fact_id, handle) pairs already judged or prefiltered - not re-listed."""
    facts = {f["fact_id"]: f for f in ledger["facts"]}
    workspaces = {
        code: await load_workspace(factory, code) for code in {i.workspace for i in items}
    }
    frozen: list[GoldItem] = []
    review: dict[str, Any] = {}
    for item in items:
        ws = workspaces[item.workspace]
        resolved: list[RequiredFact] = []
        anchors: list[str] = []
        for required in item.required_facts:
            fact = facts.get(required.fact_id)
            if fact is None:
                raise GoldFreezeError(f"{item.id}: unknown fact {required.fact_id}")
            if fact["workspace_code"] != item.workspace:
                raise GoldFreezeError(f"{item.id}: {required.fact_id} is not in {item.workspace}")
            located = locate(fact, ws)
            if len(located) != 1:
                raise GoldFreezeError(f"{item.id}: {required.fact_id} located {len(located)}x")
            handle = located[0]
            resolved.append(
                replace(
                    required,
                    satisfied_by=(handle,),
                    parent_content_hashes=(ws.parents[handle].content_hash,),
                )
            )
            anchors.append(anchor_text(fact))
            alternates = [
                h
                for h in surface_form_candidates(fact, ws, {handle, *required.also_satisfied_by})
                if (required.fact_id, h) not in decided
            ]
            if alternates:
                review.setdefault(item.id, {})[required.fact_id] = {
                    "surface_forms": fact.get("surface_forms"),
                    "candidates": alternates,
                }
        negatives = sorted(
            {
                h
                for d in ledger.get("distractors", [])
                if d["distractor_of"] in item.fact_ids() and d["fact_id"] in facts
                for h in locate(facts[d["fact_id"]], ws)
            }
            - {h for r in resolved for h in r.handles()}
        )
        share = overlap_share(item.question, anchors)
        frozen.append(
            replace(
                item,
                required_facts=tuple(resolved),
                overlap=round(share, 3),
                overlap_bin=overlap_bin(share),
                hard_negatives=tuple(negatives),
            )
        )
    split = assign_splits(frozen, corpus.related_fact_pairs(ledger))
    manifest = {
        "dataset_version": "retrieval-v0",
        "items_sha256": items_sha256,
        "corpus_sha256": corpus.corpus_sha256(),
        "ledger_sha256": corpus.ledger_sha256(),
        "parser_version": settings.parser_version,
        "structure_version": settings.structure_version,
        "chunking_policy_version": settings.chunking_policy_version,
        "split_seed": "retrieval-v0",
        "test_fraction": 0.30,
        "counts": {
            "items": len(split),
            "dev": sum(1 for i in split if i.split == "dev"),
            "test": sum(1 for i in split if i.split == "test"),
            "groups": len({i.group for i in split}),
        },
    }
    return Dataset("retrieval-v0", tuple(split), manifest), review


async def integrity_problems(
    dataset: Dataset,
    factory: SessionFactory,
    *,
    items_sha256: str,
    ledger: dict[str, Any],
) -> list[str]:
    problems: list[str] = []
    manifest = dataset.manifest
    if manifest.get("corpus_sha256") != corpus.corpus_sha256():
        problems.append("corpus_sha256 does not match the current seed corpus")
    if manifest.get("ledger_sha256") != corpus.ledger_sha256():
        problems.append("ledger_sha256 does not match the current fact ledger")
    if manifest.get("items_sha256") != items_sha256:
        problems.append("items_sha256 does not match items.json (re-run freeze-gold)")
    problems += leakage_violations(dataset.items, corpus.related_fact_pairs(ledger))
    facts = {f["fact_id"]: f for f in ledger["facts"]}
    workspaces = {
        code: await load_workspace(factory, code) for code in {i.workspace for i in dataset.items}
    }
    for item in dataset.items:
        ws = workspaces[item.workspace]
        for required in item.required_facts:
            fact = facts[required.fact_id]
            if not required.satisfied_by:
                problems.append(f"{item.id}/{required.fact_id}: no satisfying handle")
            for handle, expected_hash in zip(
                required.satisfied_by, required.parent_content_hashes, strict=True
            ):
                async with scoped_session(factory, ws.scope) as session:
                    try:
                        evidence = await resolve_evidence(session, ws.scope, handle)
                    except Exception as exc:  # every failure is a finding
                        problems.append(f"{item.id}: {handle} does not resolve ({exc!r})")
                        continue
                body = evidence.as_dict()
                if body["content_hash"].strip() != expected_hash:
                    problems.append(f"{item.id}: {handle} content hash changed")
                if not parent_contains_anchor(fact, body["text"]):
                    problems.append(f"{item.id}: {handle} no longer contains the anchor")
            for handle in required.handles():
                if not handle.startswith(f"{item.workspace}/"):
                    problems.append(f"{item.id}: {handle} belongs to another workspace")
    return problems
