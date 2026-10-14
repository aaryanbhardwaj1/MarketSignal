"""Export persisted grounded-evaluation runs as RAGAS-ready samples (no ragas, no model).

``python -m marketsignal.evaluation ragas-export --run <id> [--out PATH]`` reads a committed
run's results plus its gold dataset (read-only), resolves every passage text read-only through
:func:`marketsignal.evidence.resolver.resolve_evidence` in the RLS scope of the item's own
workspace (the gold ``workspace`` field; one scoped session per workspace), and writes a
``marketsignal.ragas-samples`` (format_version 1) JSON for the isolated ragas runner.

Per (item, configuration), in configuration order then item id:

* ``abstention_expected`` - the dataset ``expect`` is an abstention (nothing to ground);
* ``no_gold_handles``     - no gold fact lists a handle (no reference contexts);
* ``foreign_handle``      - a pack, cited or gold handle names another workspace than the
  item's; it is never resolved (no cross-workspace reads);
* ``unresolvable_handle`` - a handle of the item's workspace does not resolve (malformed,
  missing or purged).

Everything else becomes a sample: the question, the answer with ``[[...]]`` citation markup
stripped, the pack / cited / gold handle ids and their texts in the same order. ``reference``
is null - the gold sets hold short gold facts, not authored reference answers.
``corpus.texts_sha256`` is sha256 over, for each sample in order, its retrieved, cited and
reference context texts (each UTF-8 encoded and NUL-terminated).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text as sql

from marketsignal.evaluation import corpus

FORMAT = "marketsignal.ragas-samples"
FORMAT_VERSION = 1
ABSTENTION_EXPECTS = frozenset({"insufficient", "abstain_no_llm"})
OUT_DIR = corpus.EVAL_DIR / "reports" / "ragas-inputs"
PROTECTED_DIRS = (corpus.EVAL_DIR / "baselines", corpus.EVAL_DIR / "datasets")

Item = Mapping[str, Any]


class ExportError(ValueError):
    """Inputs that cannot be exported faithfully, or a refused output path."""


@dataclass(frozen=True)
class RunSpec:
    id: str
    title: str
    dataset_path: str  # repo-relative
    results: tuple[tuple[str, str], ...]  # (configuration, repo-relative results path)

    @property
    def configurations(self) -> tuple[str, ...]:
        return tuple(c for c, _ in self.results)


_P4 = "eval/baselines/phase4/research-v0-test-live"
RUNS: dict[str, RunSpec] = {
    "p3-live-v0": RunSpec(
        "p3-live-v0",
        "Phase 3 grounded answers, live v0",
        "eval/datasets/grounded-v0/items.json",
        (("standard", "eval/baselines/phase3/live-v0/results.json"),),
    ),
    "p4-research-test": RunSpec(
        "p4-research-test",
        "Phase 4 standard vs research, test split (live)",
        "eval/datasets/research-v0/items.json",
        (
            ("standard", f"{_P4}/results-standard.json"),
            ("research", f"{_P4}/results-research.json"),
        ),
    ),
}

# ------------------------------------------------------------------------------------------
# Pure pieces
# ------------------------------------------------------------------------------------------

_CITATION = re.compile(r"\[\[[^\[\]\n]*\]\]")
_EMPTY_PARENS = re.compile(r"\(\s*\)")
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([.,;:!?)])")
_RUNS_OF_SPACE = re.compile(r"(?<=\S)[ \t]{2,}")
_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)


def strip_citations(content: str) -> str:
    """Remove ``[[HANDLE]]`` / ``[[result:<id>]]`` markup and tidy the spacing it leaves."""
    out = _CITATION.sub("", content)
    out = _EMPTY_PARENS.sub("", out)
    out = _SPACE_BEFORE_PUNCT.sub(r"\1", out)
    out = _RUNS_OF_SPACE.sub(" ", out)
    out = _TRAILING_SPACE.sub("", out)
    return out.strip()


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def gold_handles(item: Item) -> list[str]:
    """Every handle listed by the item's gold facts (alternates included), deduplicated in order."""
    return _unique(h for fact in item.get("gold_facts") or () for h in fact.get("handles") or ())


def pre_exclusion(item: Item) -> str | None:
    """Exclusion decided by the gold item alone (before any text is resolved)."""
    if item.get("expect") in ABSTENTION_EXPECTS:
        return "abstention_expected"
    if not gold_handles(item):
        return "no_gold_handles"
    return None


def handle_workspace(handle: str) -> str | None:
    """The workspace code a handle names (``WS/SOURCE@vN:...``); None when it names none."""
    return handle.split("/", 1)[0] if "/" in handle else None


def item_workspace(item: Item) -> str:
    workspace = item.get("workspace")
    if not workspace:
        raise ExportError(f"gold item {item.get('id')} has no workspace")
    return str(workspace)


def _is_foreign(workspace: str, handles: Iterable[str]) -> bool:
    return any(handle_workspace(h) not in (None, workspace) for h in handles)


def _joined(
    dataset: Sequence[Item], results: Mapping[str, Sequence[Item]]
) -> list[tuple[str, Item, Item]]:
    """(configuration, gold item, result item) in configuration order, then item id."""
    gold = {item["id"]: item for item in dataset}
    rows: list[tuple[str, Item, Item]] = []
    for configuration, items in results.items():
        seen: set[str] = set()
        for result in sorted(items, key=lambda r: str(r["id"])):
            item_id = str(result["id"])
            if item_id in seen:
                raise ExportError(f"duplicate item {item_id} in {configuration} results")
            seen.add(item_id)
            if item_id not in gold:
                raise ExportError(f"{configuration} result {item_id} is not in the dataset")
            rows.append((configuration, gold[item_id], result))
    return rows


def _ids(result: Item, gold: Item) -> tuple[list[str], list[str], list[str]]:
    return (
        _unique(result.get("pack_handles") or ()),
        _unique(result.get("cited_handles") or ()),
        gold_handles(gold),
    )


def handles_to_resolve(
    dataset: Sequence[Item], results: Mapping[str, Sequence[Item]]
) -> dict[str, list[str]]:
    """workspace -> handles of every candidate sample in it (not pre-excluded, no foreign
    handle), first-seen order. Only ever handles of the item's own workspace."""
    wanted: dict[str, list[str]] = {}
    for _, gold, result in _joined(dataset, results):
        workspace = item_workspace(gold)
        handles = [h for ids in _ids(result, gold) for h in ids]
        if pre_exclusion(gold) is None and not _is_foreign(workspace, handles):
            wanted.setdefault(workspace, []).extend(handles)
    return {ws: _unique(hs) for ws, hs in wanted.items()}


def assemble(
    dataset: Sequence[Item],
    results: Mapping[str, Sequence[Item]],
    texts: Mapping[str, str | None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Samples and exclusions; ``texts`` maps handle -> text (None or absent: unresolvable)."""
    samples: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for configuration, gold, result in _joined(dataset, results):
        item_id = str(result["id"])
        reason = pre_exclusion(gold)
        retrieved, cited, reference = _ids(result, gold)
        handles = (*retrieved, *cited, *reference)
        if reason is None and _is_foreign(item_workspace(gold), handles):
            reason = "foreign_handle"
        if reason is None and any(texts.get(h) is None for h in handles):
            reason = "unresolvable_handle"
        if reason is not None:
            excluded.append({"item_id": item_id, "configuration": configuration, "reason": reason})
            continue
        samples.append(
            {
                "item_id": item_id,
                "category": gold.get("category") or result.get("category"),
                "configuration": configuration,
                "user_input": result.get("question") or gold.get("question"),
                "response": strip_citations(str(result.get("content") or "")),
                "reference": None,
                "retrieved_context_ids": retrieved,
                "cited_context_ids": cited,
                "reference_context_ids": reference,
                "retrieved_contexts": [texts[h] for h in retrieved],
                "cited_contexts": [texts[h] for h in cited],
                "reference_contexts": [texts[h] for h in reference],
                "excluded": None,
            }
        )
    return samples, excluded


def texts_sha256(samples: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for sample in samples:
        for key in ("retrieved_contexts", "cited_contexts", "reference_contexts"):
            for passage in sample[key]:
                digest.update(passage.encode("utf-8") + b"\x00")
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_document(
    spec: RunSpec,
    *,
    split: str,
    results_files: Sequence[tuple[str, str, str]],
    dataset_sha256: str,
    samples: list[dict[str, Any]],
    excluded: list[dict[str, Any]],
    created_at: str,
    git_sha: str,
    workspaces: Sequence[str],
) -> dict[str, Any]:
    """The samples JSON. ``results_path``/``results_sha256`` name the first configuration's file;
    ``results_files`` (additive) lists every configuration's file and digest."""
    _, first_path, first_sha = results_files[0]
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "run": {
            "id": spec.id,
            "title": spec.title,
            "results_path": first_path,
            "results_sha256": first_sha,
            "results_files": [
                {"configuration": c, "path": p, "sha256": s} for c, p, s in results_files
            ],
            "dataset_path": spec.dataset_path,
            "dataset_sha256": dataset_sha256,
            "split": split,
            "configurations": list(spec.configurations),
        },
        "created_at": created_at,
        "git_sha": git_sha,
        "corpus": {
            # ``workspace`` kept for single-workspace consumers; None when several are used.
            "workspace": workspaces[0] if len(workspaces) == 1 else None,
            "workspaces": list(workspaces),
            "texts_sha256": texts_sha256(samples),
        },
        "samples": samples,
        "excluded": excluded,
    }


def default_out_path(run_id: str) -> Path:
    return OUT_DIR / f"{run_id}.samples.json"


def check_out_path(path: Path) -> None:
    """Refuse writing into the frozen evaluation artifacts (baselines, datasets)."""
    target = path.resolve()
    for protected in PROTECTED_DIRS:
        if target.is_relative_to(protected.resolve()):
            raise ExportError(f"refusing to write under eval/{protected.name}: {path}")


# ------------------------------------------------------------------------------------------
# Database (read-only) and orchestration
# ------------------------------------------------------------------------------------------


async def resolve_texts(
    factory: Any, workspace_code: str, handles: Sequence[str]
) -> dict[str, str | None]:
    """Resolve each handle's parent text inside ``workspace_code``'s RLS scope (read-only).
    Unresolvable handles (foreign workspace, malformed, missing, purged) map to None."""
    from marketsignal.db.scope import WorkspaceScope
    from marketsignal.db.session import scoped_session, unscoped_session
    from marketsignal.evidence.handles import MalformedHandleError
    from marketsignal.evidence.resolver import (
        EvidenceDeletedError,
        EvidenceNotFoundError,
        resolve_evidence,
    )

    async with unscoped_session(factory) as session:
        row = (
            await session.execute(
                sql("SELECT id, code FROM workspaces WHERE code = :c"), {"c": workspace_code}
            )
        ).one_or_none()
    if row is None:
        raise ExportError(f"workspace {workspace_code} not found")
    scope = WorkspaceScope(row[0], row[1])
    texts: dict[str, str | None] = {}
    async with scoped_session(factory, scope) as session:
        for handle in handles:
            try:
                texts[handle] = (await resolve_evidence(session, scope, handle)).text
            except (MalformedHandleError, EvidenceNotFoundError, EvidenceDeletedError):
                texts[handle] = None
    return texts


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


async def export(
    spec: RunSpec,
    factory: Any,
    *,
    created_at: str,
    git_sha: str,
    root: Path = corpus.REPO_ROOT,
) -> dict[str, Any]:
    """Build the samples document for ``spec`` (paths relative to ``root``)."""
    dataset = _load(root / spec.dataset_path)["items"]
    results: dict[str, list[Item]] = {}
    files: list[tuple[str, str, str]] = []
    splits: set[str] = set()
    for configuration, rel in spec.results:
        payload = _load(root / rel)
        results[configuration] = payload["items"]
        files.append((configuration, rel, sha256_file(root / rel)))
        splits.add(str((payload.get("run") or {}).get("split") or "all"))
    if len(splits) != 1:
        raise ExportError(f"configurations of {spec.id} disagree on split: {sorted(splits)}")
    texts: dict[str, str | None] = {}
    for workspace, handles in sorted(handles_to_resolve(dataset, results).items()):
        texts.update(await resolve_texts(factory, workspace, handles))
    samples, excluded = assemble(dataset, results, texts)
    gold = {item["id"]: item for item in dataset}
    workspaces = sorted({item_workspace(gold[s["item_id"]]) for s in samples})
    return build_document(
        spec,
        split=splits.pop(),
        results_files=files,
        dataset_sha256=sha256_file(root / spec.dataset_path),
        samples=samples,
        excluded=excluded,
        created_at=created_at,
        git_sha=git_sha,
        workspaces=workspaces,
    )


def write_document(document: Mapping[str, Any], out: Path) -> int:
    """Write the document (creating the directory); returns the byte size."""
    check_out_path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(document, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    out.write_bytes(data)
    return len(data)
