"""RAGAS section (model-free heuristics over persisted outputs) and its per-item files.

Reads the RAGAS runner's ``results.json`` artifacts read-only. Every computed number keeps a
pointer to its summary block; not-run metrics carry no numbers. Exclusion reasons are
recomputed from the committed gold datasets (the exporter's samples file is local scratch) and
must add up to the recorded ``n_excluded``.
"""

from __future__ import annotations

import math
from typing import Any

from .base import BuilderBase
from .common import DS, P3, P4, ptr

RAGAS = "eval/baselines/ragas"
P4_TEST = f"{P4}/research-v0-test-live"
SUMMARY_FIELDS = ("mean", "median", "p25", "p75", "min", "max", "n", "n_nan", "histogram")
DEFINITION_FIELDS = (
    "key",
    "label",
    "family",
    "needs_llm",
    "needs_reference_answer",
    "what_it_measures",
    "ragas_class",
)
ABSTENTION_EXPECTS = frozenset({"insufficient", "abstain_no_llm"})
ID_RECALL = "id_context_recall_pack"

# (catalog run id, artifact dir, title, catalog run it measures, dataset, split,
#  {configuration: persisted results file})
RAGAS_RUNS: tuple[tuple[str, str, str, str, str, str | None, dict[str, str]], ...] = (
    (
        "ragas-p3-live-v0",
        f"{RAGAS}/p3-live-v0-nonllm",
        "RAGAS heuristics on grounded answers, live-v0",
        "p3-grounded-live",
        "grounded-v0",
        None,
        {"standard": f"{P3}/results.json"},
    ),
    (
        "ragas-p4-research-test",
        f"{RAGAS}/p4-research-test-nonllm",
        "RAGAS heuristics on Standard vs Research, test",
        "p4-research-test",
        "research-v0",
        "test",
        {
            "standard": f"{P4_TEST}/results-standard.json",
            "research": f"{P4_TEST}/results-research.json",
        },
    ),
)


def _gold_handles(item: dict[str, Any]) -> list[str]:
    seen = (h for f in item.get("gold_facts") or () for h in f.get("handles") or ())
    return list(dict.fromkeys(seen))


def _exclusion(item: dict[str, Any]) -> str | None:
    """Mirrors the exporter's gold-only rule (``ragas_export.pre_exclusion``)."""
    if item.get("expect") in ABSTENTION_EXPECTS:
        return "abstention_expected"
    if not _gold_handles(item):
        return "no_gold_handles"
    return None


class RagasSections(BuilderBase):
    def _ragas_doc(self, art: str) -> dict[str, Any]:
        doc: dict[str, Any] = self.src.json(f"{art}/results.json")
        if doc.get("format") != "marketsignal.ragas-results" or doc.get("format_version") != 1:
            raise ValueError(f"{art}: unexpected RAGAS results format")
        if doc.get("mode") != "offline" or doc.get("telemetry_disabled") is not True:
            raise ValueError(f"{art}: expected an offline run with ragas telemetry disabled")
        return doc

    def _ragas_metric(self, path: str, run_idx: int, key: str, block: dict[str, Any]) -> Any:
        pointer = ptr("runs", run_idx, "summary", key)
        source = {"kind": "json", "path": path, "pointer": pointer}
        if block["status"] == "not_run":
            if any(f in block for f in SUMMARY_FIELDS):
                raise ValueError(f"{path}#{pointer}: a not-run metric carries numbers")
            return {
                "key": key,
                "status": "not_run",
                "summary": None,
                "not_run_reason": block["not_run_reason"],
                "source": source,
            }
        if block["status"] != "computed":
            raise ValueError(f"{path}#{pointer}: unknown status {block['status']!r}")
        for f in SUMMARY_FIELDS[:-1]:
            v = block[f]
            if isinstance(v, bool) or not isinstance(v, int | float) or math.isnan(v):
                raise TypeError(f"{path}#{pointer}/{f} is not a number: {v!r}")
        return {
            "key": key,
            "status": "computed",
            "summary": {f: block[f] for f in SUMMARY_FIELDS},
            "not_run_reason": None,
            "source": source,
        }

    def _excluded(
        self, run_id: str, results_path: str, gold: dict[str, Any], run: dict[str, Any]
    ) -> list[dict[str, Any]]:
        persisted = [i["id"] for i in self.src.json(results_path)["items"]]
        scored = {i["item_id"] for i in run["items"]}
        if not scored <= set(persisted):
            raise ValueError(f"{run_id}: scored items missing from {results_path}")
        counts: dict[str, int] = {}
        for item_id in persisted:
            reason = _exclusion(gold[item_id])
            if (item_id in scored) == (reason is not None):
                raise ValueError(f"{run_id}/{item_id}: exclusion disagrees with the gold rule")
            if reason:
                counts[reason] = counts.get(reason, 0) + 1
        if sum(counts.values()) != run["n_excluded"]:
            raise ValueError(f"{run_id}: recomputed exclusions != recorded n_excluded")
        return [{"reason": r, "n": counts[r]} for r in sorted(counts)]

    def _ragas_run(self, spec: tuple[Any, ...]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rid, art, title, source_run, ds_name, split, results = spec
        path = f"{art}/results.json"
        doc = self._ragas_doc(art)
        ds_rel = f"{DS}/{ds_name}/items.json"
        gold = {g["id"]: g for g in self.src.json(ds_rel)["items"]}
        configurations: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        for i, run in enumerate(doc["runs"]):
            cfg = run["configuration"]
            metrics = [
                self._ragas_metric(path, i, d["key"], run["summary"][d["key"]])
                for d in doc["metrics"]
            ]
            configurations.append(
                {
                    "name": cfg,
                    "n_samples": run["n_samples"],
                    "n_excluded": run["n_excluded"],
                    "excluded_reasons": self._excluded(rid, results[cfg], gold, run),
                    "metrics": metrics,
                }
            )
            rows.extend(
                {
                    "buckets": [cfg],
                    "item": {
                        "phase": "ragas",
                        "item_id": it["item_id"],
                        "configuration": cfg,
                        "category": it["category"],
                        "question": gold[it["item_id"]]["question"],
                        "scores": dict(it["scores"]),
                    },
                }
                for it in run["items"]
            )
        if [c["name"] for c in configurations] != list(results):
            raise ValueError(f"{rid}: configurations differ from the expected set")
        out = {
            "id": rid,
            "title": title,
            "source_run": source_run,
            "dataset": self.file_dataset(ds_name, ds_rel),
            "split": split,
            "configurations": configurations,
            "created_at": doc["created_at"],
        }
        return out, rows

    def _reconciliation(self) -> list[dict[str, Any]]:
        """RAGAS ID recall vs the historical per-fact gold_handle_recall (p4 test), with the
        per-fact rule recomputed here over the same pack handles so the gap is explained."""
        path = f"{RAGAS}/p4-research-test-nonllm/results.json"
        doc = self.src.json(path)
        cpath = f"{P4_TEST}/compare.json"
        hist = self.src.json(cpath)["metrics"]["gold_handle_recall"]
        gold = {g["id"]: g for g in self.src.json(f"{DS}/research-v0/items.json")["items"]}
        out = []
        for i, run in enumerate(doc["runs"]):
            cfg = run["configuration"]
            res = {r["id"]: r for r in self.src.json(f"{P4_TEST}/results-{cfg}.json")["items"]}
            per_item = []
            for it in run["items"]:
                pack = set(res[it["item_id"]]["pack_handles"])
                facts = gold[it["item_id"]]["gold_facts"]
                per_item.append(
                    sum(any(h in pack for h in f["handles"]) for f in facts) / len(facts)
                )
            if round(sum(per_item) / len(per_item), 4) != hist[f"{cfg}_mean"]:
                raise ValueError(f"per-fact recall for {cfg} does not reproduce compare.json")
            if len(per_item) != hist["n_pairs"]:
                raise ValueError("RAGAS and compare.json score different item counts")
            out.append(
                self.metric(
                    f"ragas.p4.test.{cfg}.{ID_RECALL}",
                    f"RAGAS context recall (IDs, every gold handle), {cfg}",
                    path,
                    ptr("runs", i, "summary", ID_RECALL, "mean"),
                    "ratio",
                    n=ptr("runs", i, "summary", ID_RECALL, "n"),
                )
            )
            out.append(
                self.metric(
                    f"p4.test.gold_handle_recall.{cfg}",
                    f"Historical gold evidence retrieved (any accepted handle per fact), {cfg}",
                    cpath,
                    ptr("metrics", "gold_handle_recall", f"{cfg}_mean"),
                    "ratio",
                    n=ptr("metrics", "gold_handle_recall", "n_pairs"),
                )
            )
        return out

    def _ragas_caveats(self) -> list[dict[str, Any]]:
        p3_report = f"{RAGAS}/p3-live-v0-nonllm/report.md"
        p4_report = f"{RAGAS}/p4-research-test-nonllm/report.md"
        both = [rid for rid, *_ in RAGAS_RUNS]
        return [
            {
                "id": "ragas-heuristics-not-truth",
                "applies_to": both,
                "text": "RAGAS scores are heuristics computed by the ragas library, not objective "
                "truth. ID-based scores depend on the gold handles being complete; "
                "text-similarity scores are lexical and can miss paraphrases or reward surface "
                "overlap.",
                "metrics": [],
                "source": self.md(p3_report, "Caveat"),
            },
            {
                "id": "ragas-id-recall-counts-alternates",
                "applies_to": ["ragas-p4-research-test"],
                "text": "RAGAS ID-based context recall counts every distinct gold handle, "
                "alternates included, so it reads lower than the historical Standard vs "
                "Research figure, which counts a gold fact as found when any of its accepted "
                "handles was retrieved. Recomputing the per-fact rule over the same items "
                "reproduces the historical figures exactly; the gap is definitional.",
                "metrics": self._reconciliation(),
                "source": self.md(p4_report, "Reconciliation with historical metrics"),
            },
            {
                "id": "ragas-llm-metrics-not-run",
                "applies_to": both,
                "text": "Model-judged metrics (faithfulness, answer relevancy) are wired but were "
                "not run: no model credits were available. Reference-answer metrics need "
                "authored reference answers; the gold sets hold short gold facts and handles, "
                "so they are not runnable yet.",
                "metrics": [],
                "source": self.md(p4_report, "Not measured"),
            },
            {
                "id": "ragas-offline-persisted-outputs",
                "applies_to": both,
                "text": "Computed on persisted live outputs and the committed gold datasets: no "
                "new model calls, and nothing was tuned on these scores. The runs recorded the "
                "base commit while the working tree held uncommitted changes.",
                "metrics": [],
                "source": self.md(p4_report, "Provenance note"),
            },
        ]

    def ragas_section(self) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
        runs: list[dict[str, Any]] = []
        items: dict[str, list[dict[str, Any]]] = {}
        defs: list[dict[str, Any]] | None = None
        versions: set[str] = set()
        for spec in RAGAS_RUNS:
            run, rows = self._ragas_run(spec)
            runs.append(run)
            items[run["id"]] = rows
            doc = self.src.json(f"{spec[1]}/results.json")
            versions.add(doc["ragas_version"])
            these = [{f: m[f] for f in DEFINITION_FIELDS} for m in doc["metrics"]]
            if defs is not None and these != defs:
                raise ValueError("RAGAS metric definitions differ between runs")
            defs = these
        if len(versions) != 1:
            raise ValueError(f"RAGAS runs used different ragas versions: {sorted(versions)}")
        section = {
            "ragas_version": versions.pop(),
            "telemetry_disabled": True,
            "definitions": defs,
            "runs": runs,
            "caveats": self._ragas_caveats(),
        }
        return section, items
