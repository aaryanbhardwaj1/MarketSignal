"""Build the developer evaluation catalog from committed evaluation artifacts (stdlib only).

Reads an allowlist of files under ``eval/`` (and two phase reports, for prose-only decisions)
read-only, and writes ``backend/src/marketsignal/devtools/eval_catalog_data/catalog.v1.json``
plus ``items/<EvalRunId>.json``. Nothing is computed per request and nothing under ``eval/``
is ever written.

Rules (see the frozen contract ``frontend/src/lib/api/contracts.ts``, E11):
- every number is an ``EvalMetric`` whose ``source.pointer`` (RFC 6901) resolves, in the
  original file, to exactly ``value``;
- aggregate hard gates (for example 256/256 resolvable citations) are summed here from
  ``items[].checks`` and point at the ``/items`` array;
- prose-only decisions carry ``kind: "report_md"`` with a heading anchor, and their numbers
  stay inside ``text`` (numbers are never parsed out of prose).

Usage:
    uv --directory backend run python ../scripts/build_eval_catalog.py [--out DIR] [--built-at ISO]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "backend" / "src" / "marketsignal" / "devtools" / "eval_catalog_data"

P2 = "eval/baselines/phase2"
P2_SUMMARY = f"{P2}/summary.json"
P2_ELIGIBLE = f"{P2}/summary-eligible.json"
P2_REPORT = "docs/phase-reports/phase-2.md"
P3 = "eval/baselines/phase3/live-v0"
P4 = "eval/baselines/phase4"
P5 = "eval/baselines/phase5"
P5_REPORT = "docs/phase-reports/phase-5.md"
VERIFIER_SUMMARY = f"{P4}/verifier/SUMMARY.md"
DS = "eval/datasets"

RETRIEVAL_RUNS = {"p2-dev-final": "06-final-dev", "p2-test-c3": "07-test-milestone-c3"}
ARMS = [
    ("dense", "Dense (vector only)"),
    ("lexical", "Lexical (full-text only)"),
    ("hybrid", "Hybrid (production default)"),
    ("hybrid-rerank", "Hybrid + reranker (experimental)"),
]
DEFAULT_ARM = "hybrid"
RETRIEVAL_METRICS = [
    ("hit@1", "Hit@1"),
    ("hit@10", "Hit@10"),
    ("recall@10", "Recall@10"),
    ("recall@20", "Recall@20"),
    ("mrr", "MRR"),
]
BUCKET_PAIR = "dense|hybrid"


# ── sources and pointers ─────────────────────────────────────────────────────────────────────


class Sources:
    """Read-only access to repo files; records sha256/bytes of everything read."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._json: dict[str, Any] = {}
        self._text: dict[str, str] = {}
        self.manifest: dict[str, dict[str, Any]] = {}

    def _read(self, rel: str) -> bytes:
        with (self.root / rel).open("rb") as fh:  # read-only by construction
            data = fh.read()
        self.manifest[rel] = {
            "path": rel,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
        return data

    def json(self, rel: str) -> Any:
        if rel not in self._json:
            self._json[rel] = json.loads(self._read(rel))
        return self._json[rel]

    def text(self, rel: str) -> str:
        if rel not in self._text:
            self._text[rel] = self._read(rel).decode("utf-8")
        return self._text[rel]

    def sha(self, rel: str) -> str:
        if rel not in self.manifest:
            self._read(rel)
        return str(self.manifest[rel]["sha256"])

    def listing(self) -> list[dict[str, Any]]:
        return [self.manifest[k] for k in sorted(self.manifest)]


def escape(token: str | int) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def ptr(*tokens: str | int) -> str:
    return "".join("/" + escape(t) for t in tokens)


def resolve(doc: Any, pointer: str) -> Any:
    if pointer == "":
        return doc
    node = doc
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


def slug(heading: str) -> str:
    """GitHub-style heading anchor."""
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return s.replace(" ", "-")


class Builder:
    def __init__(self, src: Sources) -> None:
        self.src = src

    # metric helpers -----------------------------------------------------------------------
    def metric(
        self,
        mid: str,
        label: str,
        path: str,
        pointer: str,
        unit: str,
        *,
        ci: tuple[str, str] | None = None,
        n: int | str | None = None,
        k: int | str | None = None,
    ) -> dict[str, Any]:
        doc = self.src.json(path)
        value = resolve(doc, pointer)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int | float)):
            raise TypeError(f"{path}#{pointer} is not a number: {value!r}")
        out: dict[str, Any] = {"id": mid, "label": label, "value": value, "unit": unit}
        if ci is not None:
            out["ci_low"] = resolve(doc, ci[0])
            out["ci_high"] = resolve(doc, ci[1])
        for key, spec in (("n", n), ("k", k)):
            if spec is not None:
                out[key] = resolve(doc, spec) if isinstance(spec, str) else spec
        out["source"] = {"kind": "json", "path": path, "pointer": pointer}
        return out

    def est(
        self, mid: str, label: str, path: str, base: str, unit: str = "ratio", **kw: Any
    ) -> dict[str, Any]:
        """Metric from an ``{estimate, low, high}`` block."""
        return self.metric(
            mid, label, path, base + "/estimate", unit, ci=(base + "/low", base + "/high"), **kw
        )

    def md(self, path: str, heading: str) -> dict[str, Any]:
        text = self.src.text(path)
        if not re.search(r"^#+ " + re.escape(heading) + r"\s*$", text, re.M):
            raise KeyError(f"heading {heading!r} not found in {path}")
        return {"kind": "report_md", "path": path, "anchor": slug(heading)}

    # provenance -----------------------------------------------------------------------------
    def provenance(
        self,
        path: str,
        *,
        split: str | None,
        dataset: dict[str, Any],
        model_key: str | None = "model",
    ) -> dict[str, Any]:
        run = self.src.json(path)["run"]
        return {
            "path": path,
            "git": run.get("git"),
            "at": run.get("at"),
            "model": run.get(model_key) if model_key else None,
            "split": split,
            "config_hash": run.get("config_hash") or run.get("retrieval_config_hash"),
            "dataset": dataset,
        }

    def file_dataset(self, name: str, rel: str) -> dict[str, Any]:
        doc = self.src.json(rel)
        return {"name": name, "version": doc.get("dataset_version"), "sha256": self.src.sha(rel)}

    # sections ------------------------------------------------------------------------------
    def row_index(self, rows: list[dict[str, Any]], run: str, arm: str) -> int:
        for i, row in enumerate(rows):
            if row["run"] == run and row["arm"] == arm:
                return i
        raise KeyError(f"no row for {run}/{arm}")

    def retrieval(self) -> dict[str, Any]:
        summary = self.src.json(P2_SUMMARY)
        eligible = self.src.json(P2_ELIGIBLE)
        runs = []
        for run_id, run in RETRIEVAL_RUNS.items():
            res_path = f"{P2}/{run}/results.json"
            res = self.src.json(res_path)
            ds = res["dataset"]
            arms = []
            n = n_eligible = 0
            for arm, label in ARMS:
                ia = self.row_index(summary, run, arm)
                ie = self.row_index(eligible["rows"], run, arm)
                n, n_eligible = summary[ia]["n"], eligible["rows"][ie]["n_eligible"]
                all_m = {
                    key: self.est(
                        f"{run_id}.{arm}.all.{key}", name, P2_SUMMARY, ptr(ia, key), n=ptr(ia, "n")
                    )
                    for key, name in RETRIEVAL_METRICS
                }
                elig_m = {
                    key: self.est(
                        f"{run_id}.{arm}.eligible.{key}",
                        f"{name} (retrieval-eligible)",
                        P2_ELIGIBLE,
                        ptr("rows", ie, key),
                        n=ptr("rows", ie, "n_eligible"),
                    )
                    for key, name in RETRIEVAL_METRICS
                }
                lat = summary[ia]["latency_total_ms"]
                arms.append(
                    {
                        "arm": arm,
                        "label": label,
                        "is_default": arm == DEFAULT_ARM,
                        "all": all_m,
                        "eligible": elig_m,
                        "latency_ms": {"p50": lat["p50"], "p95": lat["p95"]},
                    }
                )
            runs.append(
                {
                    "run_id": run_id,
                    "label": f"{'Dev' if res['split'] == 'dev' else 'Test'} split, run {run}",
                    "provenance": self.provenance(
                        res_path,
                        split=res["split"],
                        model_key=None,
                        dataset={
                            "name": "retrieval-v0",
                            "version": ds["dataset_version"],
                            "sha256": ds["items_sha256"],
                        },
                    ),
                    "n": n,
                    "n_eligible": n_eligible,
                    "arms": arms,
                }
            )
        return {"runs": runs, "comparisons": self.comparisons(), "decisions": self.decisions()}

    def comparisons(self) -> list[dict[str, Any]]:
        eligible = self.src.json(P2_ELIGIBLE)
        by_run = {v: k for k, v in RETRIEVAL_RUNS.items()}
        out = []
        for i, c in enumerate(eligible["comparisons"]):
            if c["run"] not in by_run:
                continue
            run_id = by_run[c["run"]]
            base = f"{run_id}.{c['a']}->{c['b']}"
            out.append(
                {
                    "run_id": run_id,
                    "a": c["a"],
                    "b": c["b"],
                    "n": c["n"],
                    "metrics": [
                        self.est(
                            f"{base}.d_recall@10",
                            "Δ Recall@10 (eligible)",
                            P2_ELIGIBLE,
                            ptr("comparisons", i, "d_recall@10"),
                            n=ptr("comparisons", i, "n"),
                        ),
                        self.est(
                            f"{base}.d_mrr",
                            "Δ MRR (eligible)",
                            P2_ELIGIBLE,
                            ptr("comparisons", i, "d_mrr"),
                            n=ptr("comparisons", i, "n"),
                        ),
                    ],
                    "hit_at_10": {
                        "gains": c["hit@10"]["b_gains"],
                        "losses": c["hit@10"]["b_losses"],
                        "p": c["hit@10"].get("p"),
                    },
                }
            )
        return out

    def _cmp_index(self, run: str, a: str, b: str) -> int:
        for i, c in enumerate(self.src.json(P2_ELIGIBLE)["comparisons"]):
            if (c["run"], c["a"], c["b"]) == (run, a, b):
                return i
        raise KeyError((run, a, b))

    def decisions(self) -> list[dict[str, Any]]:
        summary = self.src.json(P2_SUMMARY)
        addendum = self.md(P2_REPORT, "Addendum: review decisions (2026-10-05, after approval)")
        iterations = self.md(P2_REPORT, "Measured iterations (dev)")
        t_dh = self._cmp_index("07-test-milestone-c3", "dense", "hybrid")
        t_hr = self._cmp_index("07-test-milestone-c3", "hybrid", "hybrid-rerank")
        d_hr = self._cmp_index("06-final-dev", "hybrid", "hybrid-rerank")

        def cmp_metric(i: int, key: str, mid: str, label: str) -> dict[str, Any]:
            return self.est(
                mid, label, P2_ELIGIBLE, ptr("comparisons", i, key), n=ptr("comparisons", i, "n")
            )

        def row_metric(run: str, arm: str, key: str, label: str) -> dict[str, Any]:
            i = self.row_index(summary, run, arm)
            return self.est(f"{run}.{arm}.{key}", label, P2_SUMMARY, ptr(i, key), n=ptr(i, "n"))

        return [
            {
                "id": "hybrid-default",
                "title": "Hybrid retrieval (dense + lexical, RRF) is the production default",
                "outcome": "adopted",
                "text": "Production default: hybrid RRF without the reranker. On the "
                "retrieval-eligible "
                "test items, hybrid beats dense on hit@10 (+6 / -0, p = 0.031). On dev the "
                "difference is not distinguishable.",
                "metrics": [
                    cmp_metric(
                        t_dh,
                        "d_recall@10",
                        "decision.hybrid.test.d_recall@10",
                        "Δ Recall@10, dense → hybrid (test, eligible)",
                    ),
                ],
                "source": addendum,
            },
            {
                "id": "reranker-rejected",
                "title": "Cross-encoder reranker rejected on held-out data",
                "outcome": "rejected",
                "text": "Negative finding: the reranker looked better on dev (MRR), but on "
                "the held-out "
                "test split it lowered Recall@10 against hybrid. It stays experimental behind "
                "MS_RERANK_ENABLED; future reranker experiments need new dev questions and a newly "
                "frozen holdout.",
                "metrics": [
                    cmp_metric(
                        t_hr,
                        "d_recall@10",
                        "decision.rerank.test.d_recall@10",
                        "Δ Recall@10, hybrid → hybrid + rerank (test, eligible)",
                    ),
                    cmp_metric(
                        d_hr,
                        "d_mrr",
                        "decision.rerank.dev.d_mrr",
                        "Δ MRR, hybrid → hybrid + rerank (dev, eligible)",
                    ),
                ],
                "source": addendum,
            },
            {
                "id": "bge-query-instruction",
                "title": "BGE query instruction prefix",
                "outcome": "not_adopted",
                "text": (
                    "Dense hit@10 \u22123 / +0 (p = 0.25); reranked arm unchanged. Not "
                    "adopted (iteration 04)."
                ),
                "metrics": [
                    row_metric(
                        "04-bge-instruction-dev",
                        "dense+bge-instruction",
                        "hit@10",
                        "Dense + instruction Hit@10 (dev, all items)",
                    ),
                ],
                "source": iterations,
            },
            {
                "id": "source-balancing",
                "title": "Source balancing (per-source cap and pool cap)",
                "outcome": "not_adopted",
                "text": "hit@10 \u22121, hit@20 \u22122; the pool cap alone causes the drop. "
                "Built and left off "
                "(iteration 03).",
                "metrics": [
                    row_metric(
                        "03-balance-dev",
                        "hybrid-rerank",
                        "hit@10",
                        "Hybrid + rerank Hit@10 (dev, all items)",
                    ),
                    row_metric(
                        "03-balance-dev",
                        "hybrid-rerank-balance",
                        "hit@10",
                        "With balancing Hit@10 (dev, all items)",
                    ),
                    row_metric(
                        "03-balance-dev",
                        "hybrid-rerank",
                        "recall@20",
                        "Hybrid + rerank Recall@20 (dev, all items)",
                    ),
                    row_metric(
                        "03-balance-dev",
                        "hybrid-rerank-balance",
                        "recall@20",
                        "With balancing Recall@20 (dev, all items)",
                    ),
                ],
                "source": iterations,
            },
            {
                "id": "row-identifiers",
                "title": "Row identifiers in table-row passages (chunking c3)",
                "outcome": "adopted",
                "text": "Lexical RV-00655 rank 26 → 2, R0062 21 → 1; hybrid ΔMRR +0.046 "
                "[+0.007, +0.095]; "
                "no reranked regressions. Adopted as c3 (iteration 05). Recorded in the report "
                "only.",
                "metrics": [],
                "source": iterations,
            },
        ]

    def grounded(self) -> dict[str, Any]:
        path = f"{P3}/results.json"
        res = self.src.json(path)
        gold = {g["id"]: g for g in self.src.json(f"{DS}/grounded-v0/items.json")["items"]}
        items = res["items"]
        hg = res["summary"]["hard_gates"]
        arr = {"kind": "json", "path": path, "pointer": "/items"}
        cited = sum(i["checks"]["citations"] for i in items)
        no_leak = sum(
            1
            for i in items
            if not i["checks"]["foreign_citations"] and not i["checks"]["southpeak_marker_leak"]
        )
        needs_final = [i for i in items if gold[i["id"]]["expect"] != "abstain_no_llm"]
        empty = [i for i in items if gold[i["id"]]["expect"] == "abstain_no_llm"]

        def gate(gid: str, label: str, k: int, n: int) -> dict[str, Any]:
            passed = k == n
            if passed != hg[gid]["pass"]:
                raise ValueError(
                    f"hard gate {gid}: recomputed {k}/{n} disagrees with recorded pass"
                )
            return {"id": gid, "label": label, "k": k, "n": n, "pass": passed, "source": arr}

        gates = [
            gate(
                "citation_resolvability",
                "Citations resolve to a stored passage",
                sum(i["checks"]["resolvable"] for i in items),
                cited,
            ),
            gate(
                "citation_in_pack",
                "Citations point into the retrieved evidence pack",
                sum(i["checks"]["in_pack"] for i in items),
                cited,
            ),
            gate(
                "cross_workspace_leaks",
                "Runs with no cross-workspace citation or marker leak",
                no_leak,
                len(items),
            ),
            gate(
                "every_run_done",
                "Runs that emitted a done event",
                sum(1 for i in items if i["checks"]["has_done"]),
                len(items),
            ),
            gate(
                "answer_items_have_final",
                "Answer-expected runs with a final answer",
                sum(1 for i in needs_final if i["checks"]["has_final"]),
                len(needs_final),
            ),
            gate(
                "empty_pack_never_calls_llm",
                "Empty-pack runs that never call the model",
                sum(1 for i in empty if i["checks"]["pass_behaviour"]),
                len(empty),
            ),
        ]
        m, s, v, c = self.metric, "/summary", "/pipeline/verification", "/pipeline/cost_usd"
        nr = f"{P3}/numeric-recheck.json"
        metrics = [
            m(
                "p3.citation_resolvability",
                "Citation resolvability",
                path,
                "/summary/hard_gates/citation_resolvability/value",
                "ratio",
                k=gates[0]["k"],
                n=cited,
            ),
            m(
                "p3.cross_workspace_leaks",
                "Cross-workspace leaks",
                path,
                "/summary/hard_gates/cross_workspace_leaks/value",
                "count",
            ),
            m(
                "p3.insufficient_correct",
                "Insufficient-evidence items abstained correctly",
                path,
                f"{s}/insufficient_correct/k",
                "count",
                k=f"{s}/insufficient_correct/k",
                n=f"{s}/insufficient_correct/n",
            ),
            m(
                "p3.over_refusal",
                "Over-refusals on answerable items",
                path,
                f"{s}/over_refusal/k",
                "count",
                k=f"{s}/over_refusal/k",
                n=f"{s}/over_refusal/n",
            ),
            m(
                "p3.cited_units",
                "Cited answer units re-checked for numbers",
                nr,
                "/summary/cited_units",
                "count",
            ),
            m(
                "p3.cited_units_flagged",
                "Cited units flagged by the numeric re-check (all locator labels in G-R0-055)",
                nr,
                "/summary/cited_units_with_unsupported_numbers",
                "count",
                n="/summary/cited_units",
            ),
            m(
                "p3.uncited_numbers_absent",
                "Uncited units with a number absent from the pack",
                nr,
                "/summary/uncited_units_with_numbers_absent_from_pack",
                "count",
                n="/summary/uncited_units",
            ),
            m(
                "p3.regenerated",
                "Answers regenerated after verification",
                path,
                f"{v}/regenerated",
                "count",
            ),
            m(
                "p3.fallback_after_verification",
                "Evidence-only fallbacks after verification",
                path,
                f"{v}/fallback_after_verification",
                "count",
            ),
            m(
                "p3.repairs_total",
                "Verifier repairs (all runs)",
                path,
                f"{v}/repairs_total",
                "count",
            ),
            m(
                "p3.numeric_units_dropped",
                "Units dropped for unsupported numbers",
                path,
                f"{v}/numeric_units_dropped",
                "count",
            ),
            m(
                "p3.first_token_p50",
                "First token p50",
                path,
                f"{s}/latency_ms/first_token_p50",
                "ms",
            ),
            m(
                "p3.first_token_p95",
                "First token p95",
                path,
                f"{s}/latency_ms/first_token_p95",
                "ms",
            ),
            m("p3.total_p50", "End-to-end p50", path, f"{s}/latency_ms/total_p50", "ms"),
            m("p3.total_p95", "End-to-end p95", path, f"{s}/latency_ms/total_p95", "ms"),
            m(
                "p3.input_tokens_total",
                "Input tokens (all runs)",
                path,
                f"{s}/usage_total/input_tokens",
                "tokens",
            ),
            m(
                "p3.output_tokens_total",
                "Output tokens (all runs)",
                path,
                f"{s}/usage_total/output_tokens",
                "tokens",
            ),
            m(
                "p3.cache_read_tokens_total",
                "Cache-read tokens (all runs)",
                path,
                f"{s}/usage_total/cache_read_input_tokens",
                "tokens",
            ),
            m(
                "p3.input_tokens_mean",
                "Input tokens per model run (mean)",
                path,
                f"{s}/usage_per_llm_run_mean/input_tokens",
                "tokens",
            ),
            m(
                "p3.output_tokens_mean",
                "Output tokens per model run (mean)",
                path,
                f"{s}/usage_per_llm_run_mean/output_tokens",
                "tokens",
            ),
            m(
                "p3.cost_total",
                "Cost, all runs (as recorded by the eval harness)",
                path,
                f"{c}/total",
                "usd",
            ),
            m(
                "p3.cost_per_model_run",
                "Cost per model run (as recorded by the eval harness)",
                path,
                f"{c}/per_model_run",
                "usd",
            ),
        ]
        by_category = []
        for cat, block in res["summary"]["categories"].items():
            base = ptr("summary", "categories", cat)
            cm = [
                self.est(
                    f"p3.{cat}.behaviour",
                    "Behaviour pass rate",
                    path,
                    base + "/behaviour_ci",
                    n=base + "/n",
                )
            ]
            for key, label in (
                ("gold_coverage_mean", "Gold evidence coverage"),
                ("numeric_correct_mean", "Numeric correctness"),
            ):
                if block.get(key) is not None:
                    cm.append(
                        m(f"p3.{cat}.{key}", label, path, f"{base}/{key}", "ratio", n=base + "/n")
                    )
            by_category.append({"category": cat, "metrics": cm})
        return {
            "provenance": self.provenance(
                path,
                split=None,
                dataset=self.file_dataset("grounded-v0", f"{DS}/grounded-v0/items.json"),
            ),
            "hard_gates": gates,
            "metrics": metrics,
            "by_category": by_category,
            "verifier": self.verifier(),
        }

    def verifier(self) -> list[dict[str, Any]]:
        out = []
        keys = [
            ("false_positive_rejection_rate", "False-positive rejection rate", "supported_units"),
            (
                "false_negative_acceptance_rate",
                "False-negative acceptance rate",
                "unsupported_units",
            ),
            ("supported_retention", "Supported-unit retention", "supported_units"),
        ]
        for split in ("dev", "holdout"):
            sides = {}
            for side in ("before", "after"):
                path = f"{P4}/verifier/{split}-{side}.json"
                sides[side] = [
                    self.metric(
                        f"verifier.{split}.{side}.{k}",
                        label,
                        path,
                        f"/summary/{k}",
                        "ratio",
                        n=f"/summary/{nk}",
                    )
                    for k, label, nk in keys
                ]
            out.append({"split": split, "before": sides["before"], "after": sides["after"]})
        return out

    def research(self) -> list[dict[str, Any]]:
        rows_spec = [
            ("gold_handle_recall", "Gold evidence retrieved", "ratio"),
            ("gold_coverage", "Gold evidence cited", "ratio"),
            ("answer_completeness", "Gold values stated", "ratio"),
            ("behaviour_pass", "Expected behaviour", "ratio"),
            ("model_calls", "Model calls per run", "count"),
            ("tool_calls", "Tool calls per run", "count"),
            ("retrieval_calls", "Retrieval calls per run", "count"),
            ("tokens_total", "Tokens per run", "tokens"),
            ("cost_usd", "Cost per run (as recorded by the eval harness)", "usd"),
        ]
        out = []
        for split in ("dev", "test"):
            d = f"{P4}/research-v0-{split}-live"
            cpath = f"{d}/compare.json"
            cmp_doc = self.src.json(cpath)
            rows: list[dict[str, Any]] = []
            for key, label, unit in rows_spec:
                base = ptr("metrics", key)
                block = cmp_doc["metrics"][key]
                ci = (base + "/ci/low", base + "/ci/high") if "ci" in block else None
                rid = f"p4.{split}.{key}"
                rows.append(
                    {
                        "id": key,
                        "label": label,
                        "standard": self.metric(
                            rid + ".standard",
                            label,
                            cpath,
                            base + "/standard_mean",
                            unit,
                            n=base + "/n_pairs",
                        ),
                        "research": self.metric(
                            rid + ".research",
                            label,
                            cpath,
                            base + "/research_mean",
                            unit,
                            n=base + "/n_pairs",
                        ),
                        "delta": self.metric(
                            rid + ".delta",
                            f"Δ {label}",
                            cpath,
                            base + "/delta_mean",
                            unit,
                            ci=ci,
                            n=base + "/n_pairs",
                        ),
                    }
                )
            for q, label in (
                ("total_p50", "End-to-end latency p50"),
                ("total_p95", "End-to-end latency p95"),
            ):
                rows.append(
                    {
                        "id": f"latency_{q}",
                        "label": label,
                        "standard": self.metric(
                            f"p4.{split}.{q}.standard",
                            label,
                            f"{d}/results-standard.json",
                            f"/summary/latency_ms/{q}",
                            "ms",
                        ),
                        "research": self.metric(
                            f"p4.{split}.{q}.research",
                            label,
                            f"{d}/results-research.json",
                            f"/summary/latency_ms/{q}",
                            "ms",
                        ),
                        "delta": None,
                    }
                )
            run_path = f"{d}/results-research.json"
            out.append(
                {
                    "split": split,
                    "provenance": self.provenance(
                        run_path,
                        split=split,
                        dataset=self.file_dataset("research-v0", f"{DS}/research-v0/items.json"),
                    ),
                    "n_pairs": cmp_doc["n_pairs"],
                    "rows": rows,
                }
            )
        return out

    def analytics(self) -> list[dict[str, Any]]:
        out = []
        for split in ("dev", "holdout"):
            path = f"{P5}/analytics-v0-{split}-live/results.json"
            m, r, a, w, pf = (
                self.metric,
                "/summary/routing",
                "/summary/analytics",
                "/summary/answer",
                "/summary/performance",
            )
            pre = f"p5.{split}"
            metrics = [
                m(
                    f"{pre}.task_type_accuracy",
                    "Task-type routing accuracy",
                    path,
                    f"{r}/task_type_accuracy/rate",
                    "ratio",
                    ci=(f"{r}/task_type_accuracy/ci/low", f"{r}/task_type_accuracy/ci/high"),
                    k=f"{r}/task_type_accuracy/k",
                    n=f"{r}/task_type_accuracy/n",
                ),
                m(
                    f"{pre}.mixed_recognition",
                    "Mixed-question recognition",
                    path,
                    f"{r}/mixed_recognition/rate",
                    "ratio",
                    k=f"{r}/mixed_recognition/k",
                    n=f"{r}/mixed_recognition/n",
                ),
                m(
                    f"{pre}.items_all_values_matched",
                    "Items with every gold value matched",
                    path,
                    f"{a}/items_all_values_matched/rate",
                    "ratio",
                    ci=(
                        f"{a}/items_all_values_matched/ci/low",
                        f"{a}/items_all_values_matched/ci/high",
                    ),
                    k=f"{a}/items_all_values_matched/k",
                    n=f"{a}/items_all_values_matched/n",
                ),
                m(
                    f"{pre}.exact_result_accuracy_mean",
                    "Exact result accuracy (item mean)",
                    path,
                    f"{a}/exact_result_accuracy_mean",
                    "ratio",
                ),
                m(
                    f"{pre}.exact_result_accuracy_micro",
                    "Exact result accuracy (all gold values)",
                    path,
                    f"{a}/exact_result_accuracy_micro/rate",
                    "ratio",
                    k=f"{a}/exact_result_accuracy_micro/matched",
                    n=f"{a}/exact_result_accuracy_micro/gold_values",
                ),
                m(
                    f"{pre}.numeric_faithfulness",
                    "Numeric faithfulness of answers",
                    path,
                    f"{w}/numeric_faithfulness/rate",
                    "ratio",
                    k=f"{w}/numeric_faithfulness/supported",
                    n=f"{w}/numeric_faithfulness/numbers",
                ),
                m(
                    f"{pre}.unsupported_computed_claim_rate",
                    "Unsupported computed-claim rate",
                    path,
                    f"{w}/unsupported_computed_claim_rate/rate",
                    "ratio",
                    k=f"{w}/unsupported_computed_claim_rate/unsupported_units",
                    n=f"{w}/unsupported_computed_claim_rate/result_units",
                ),
                m(
                    f"{pre}.end_to_end_p50",
                    "End-to-end latency p50",
                    path,
                    f"{pf}/end_to_end_ms/p50",
                    "ms",
                    n=f"{pf}/end_to_end_ms/n",
                ),
                m(
                    f"{pre}.end_to_end_p95",
                    "End-to-end latency p95",
                    path,
                    f"{pf}/end_to_end_ms/p95",
                    "ms",
                    n=f"{pf}/end_to_end_ms/n",
                ),
                m(
                    f"{pre}.analytics_tool_p50",
                    "Analytics tool latency p50",
                    path,
                    f"{pf}/analytics_tool_ms/p50",
                    "ms",
                    n=f"{pf}/analytics_tool_ms/n",
                ),
                m(
                    f"{pre}.analytics_tool_p95",
                    "Analytics tool latency p95",
                    path,
                    f"{pf}/analytics_tool_ms/p95",
                    "ms",
                    n=f"{pf}/analytics_tool_ms/n",
                ),
                m(
                    f"{pre}.model_calls_per_run",
                    "Model calls per run",
                    path,
                    f"{pf}/model_calls_per_run",
                    "count",
                ),
                m(
                    f"{pre}.tool_calls_per_run",
                    "Tool calls per run",
                    path,
                    f"{pf}/tool_calls_per_run",
                    "count",
                ),
                m(
                    f"{pre}.tokens_per_run",
                    "Tokens per run",
                    path,
                    f"{pf}/tokens_per_run",
                    "tokens",
                ),
                m(
                    f"{pre}.cost_usd_per_run",
                    "Cost per run (as recorded by the eval harness)",
                    path,
                    f"{pf}/cost_usd_per_run",
                    "usd",
                ),
            ]
            out.append(
                {
                    "split": split,
                    "provenance": self.provenance(
                        path,
                        split=split,
                        dataset=self.file_dataset("analytics-v0", f"{DS}/analytics-v0/items.json"),
                    ),
                    "metrics": metrics,
                }
            )
        return out

    def superseded(self) -> list[dict[str, Any]]:
        self.md(P5_REPORT, "Live findings that changed the system (dev only)")
        self.md(P5_REPORT, "Phase 4 hardening outcomes")
        entries = [
            (
                f"{P5}/analytics-v0-dev-live-attempt1-strict-limit/results.json",
                "Analytics dev, attempt 1 (superseded)",
                "Strict-mode grammar limits: every agent step returned 400 and research runs fell "
                "back to "
                "standard. Fixed with non-strict analytics tools; kept for the record.",
            ),
            (
                f"{P5}/analytics-v0-dev-live-attempt2-verifier-fp/results.json",
                "Analytics dev, attempt 2 (superseded)",
                "Verifier false positives on computed results: correct answers fell back to "
                "evidence only. "
                "Fixed in the result re-check; kept for the record.",
            ),
            (
                f"{P5}/research-dev-p5-summary-off/results.json",
                "Research summary-off arm, A3 (incomplete)",
                "The A3 research-summary off/on comparison stopped when API credits ran out; the "
                "summary-on "
                "arm never ran, so no live before/after comparison exists.",
            ),
        ]
        for path, _, _ in entries:
            self.src.sha(path)
        return [{"path": p, "label": label, "reason": reason} for p, label, reason in entries]

    def caveats(self) -> list[dict[str, Any]]:
        self.src.text(VERIFIER_SUMMARY)
        return [
            {
                "id": "small-test-n",
                "applies_to": ["overview", "retrieval", "research_tradeoff"],
                "text": "Test splits are small (retrieval test: 21 items, 17 "
                "retrieval-eligible; Standard vs "
                "Research test: 34 pairs). Confidence intervals are wide; read point estimates "
                "with care.",
            },
            {
                "id": "v0-test-informed-default",
                "applies_to": ["overview", "retrieval"],
                "text": "The production default (hybrid without the reranker) was chosen "
                "after seeing v0 test "
                "results, so the v0 test split is no longer a clean holdout for that choice.",
            },
            {
                "id": "verifier-holdout-used-twice",
                "applies_to": ["overview", "grounded"],
                "text": "The verifier-v1 holdout was run twice: at the end of development and "
                "once more after "
                "the review safety fixes. No rule was tuned to holdout scores.",
            },
            {
                "id": "a3-not-run",
                "applies_to": ["overview", "analytics", "research_tradeoff"],
                "text": "The Phase 5 A3 research-summary on/off comparison was not run live "
                "because API "
                "credits ran out. The summary hand-off is implemented and tested offline only.",
            },
            {
                "id": "p5-holdout-routing",
                "applies_to": ["overview", "analytics"],
                "text": "Analytics routing generalised weakly: task-type accuracy was 36/36 "
                "on dev but 31/54 "
                "on the holdout split.",
            },
        ]

    def overview(
        self, retrieval: dict[str, Any], grounded: dict[str, Any], analytics: list[dict[str, Any]]
    ) -> dict[str, Any]:
        test = next(r for r in retrieval["runs"] if r["run_id"] == "p2-test-c3")
        hybrid = next(a for a in test["arms"] if a["arm"] == DEFAULT_ARM)
        headline = [
            {
                **hybrid["eligible"]["recall@10"],
                "id": "headline.test_hybrid_recall10",
                "label": "Recall@10, hybrid default (test, retrieval-eligible)",
            },
            {**grounded["metrics"][0], "id": "headline.citation_resolvability"},
            {**grounded["metrics"][1], "id": "headline.cross_workspace_leaks"},
        ]
        for block in analytics:
            nf = next(x for x in block["metrics"] if x["id"].endswith(".numeric_faithfulness"))
            headline.append(
                {
                    **nf,
                    "id": f"headline.analytics_numeric_faithfulness_{block['split']}",
                    "label": f"Analytics numeric faithfulness ({block['split']})",
                }
            )
        phases = [
            {
                "id": "retrieval",
                "title": "Phase 2: hybrid retrieval",
                "summary": (
                    "Dense, lexical, hybrid and reranked retrieval measured on the "
                    "frozen retrieval-v0 dataset (dev and a one-time test milestone)."
                ),
            },
            {
                "id": "grounded",
                "title": "Phase 3: grounded answers",
                "summary": (
                    "Live standard-mode answers with citation, abstention and "
                    "numeric-faithfulness gates; verifier precision before and after "
                    "Phase 4."
                ),
            },
            {
                "id": "research_tradeoff",
                "title": "Phase 4: standard vs research",
                "summary": (
                    "Paired comparison of single-pass answers and the bounded research "
                    "agent: quality gains against calls, tokens, cost and latency."
                ),
            },
            {
                "id": "analytics",
                "title": "Phase 5: structured analytics",
                "summary": (
                    "Deterministic analytics tools with routing; dev and a fresh "
                    "holdout split, plus superseded dev attempts kept for the record."
                ),
            },
        ]
        return {"headline": headline, "phases": phases}

    # items ---------------------------------------------------------------------------------
    def retrieval_items(self, run: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
        res = self.src.json(f"{P2}/{run}/results.json")
        frozen = {i["id"]: i for i in self.src.json(f"{DS}/retrieval-v0/frozen.json")["items"]}
        per_arm = {arm: {r["item_id"]: r for r in res["arms"][arm]["items"]} for arm, _ in ARMS}
        rows = []
        counts: dict[str, int] = {}
        for item_id in per_arm["dense"]:
            item = frozen[item_id]
            facts = [f["fact_id"] for f in item["required_facts"]]
            by_arm = {}
            for arm, _ in ARMS:
                r = per_arm[arm][item_id]
                ranks = [r["fact_ranks"].get(f) for f in facts]
                by_arm[arm] = {
                    "fact_ranks": ranks,
                    "hit_at_10": any(x is not None and x <= 10 for x in ranks),
                    "top": r["top"][:10],
                }
            hit_a, hit_b = by_arm["dense"]["hit_at_10"], by_arm[DEFAULT_ARM]["hit_at_10"]
            bucket = (
                None
                if hit_a and hit_b
                else "dense_only"
                if hit_a
                else f"{DEFAULT_ARM}_only"
                if hit_b
                else "both_miss"
            )
            if bucket:
                counts[bucket] = counts.get(bucket, 0) + 1
            handles = sorted(
                {
                    h
                    for f in item["required_facts"]
                    for h in f["satisfied_by"] + f.get("also_satisfied_by", [])
                }
            )
            rows.append(
                {
                    "buckets": [bucket] if bucket else [],
                    "item": {
                        "phase": "retrieval",
                        "item_id": item_id,
                        "question": item["question"],
                        "category": item["category"],
                        "bucket": bucket,
                        "expected_handles": handles,
                        "by_arm": by_arm,
                    },
                }
            )
        recorded = {b: v["count"] for b, v in res["failures"][BUCKET_PAIR].items()}
        if counts != recorded:
            raise ValueError(f"{run}: recomputed buckets {counts} != recorded {recorded}")
        return rows, recorded

    def grounded_items(self) -> list[dict[str, Any]]:
        res = self.src.json(f"{P3}/results.json")
        gold = {g["id"]: g for g in self.src.json(f"{DS}/grounded-v0/items.json")["items"]}
        failures = {f["id"]: f for f in self.src.json(f"{P3}/failure-analysis.json")}
        rows = []
        for it in res["items"]:
            fa = failures.get(it["id"])
            checks = {
                k: v
                for k, v in it["checks"].items()
                if v is None or isinstance(v, bool | int | float)
            }
            rows.append(
                {
                    "buckets": [fa["final_classification"]] if fa else [],
                    "item": {
                        "phase": "grounded",
                        "item_id": it["id"],
                        "question": it["question"],
                        "category": it["category"],
                        "answer_markdown": it["content"] or "",
                        "cited_handles": it["cited_handles"],
                        "gold_handles": sorted(
                            {h for f in gold[it["id"]]["gold_facts"] for h in f["handles"]}
                        ),
                        "checks": checks,
                        "termination_state": it["termination_state"],
                        "failure": None
                        if not fa
                        else {
                            "final_classification": fa["final_classification"],
                            "root_cause": fa["root_cause"],
                            "user_impact": fa["user_impact"],
                        },
                    },
                }
            )
        return rows

    def research_items(self, split: str) -> list[dict[str, Any]]:
        d = f"{P4}/research-v0-{split}-live"
        cmp_doc = self.src.json(f"{d}/compare.json")
        std = {i["id"]: i for i in self.src.json(f"{d}/results-standard.json")["items"]}
        rsr = {i["id"]: i for i in self.src.json(f"{d}/results-research.json")["items"]}

        def nums(block: dict[str, Any]) -> dict[str, Any]:
            return {
                k: (float(v) if isinstance(v, bool) else v)
                for k, v in block.items()
                if v is None or isinstance(v, bool | int | float)
            }

        rows = []
        for c in cmp_doc["items"]:
            r = rsr[c["id"]]
            agent = r.get("agent") or {}
            buckets = [
                f"{side}_behaviour_fail"
                for side in ("standard", "research")
                if c[side].get("behaviour_pass") is False
            ]
            rows.append(
                {
                    "buckets": buckets,
                    "item": {
                        "phase": "research",
                        "item_id": c["id"],
                        "question": r["question"],
                        "delta": nums(c["delta"]),
                        "standard": {
                            "answer_markdown": std[c["id"]]["content"] or "",
                            "metrics": nums(c["standard"]),
                        },
                        "research": {
                            "answer_markdown": r["content"] or "",
                            "stop_reason": agent.get("stop_reason") or "",
                            "tool_calls": int(c["research"].get("tool_calls") or 0),
                            "trace": [
                                {"step": t["step"], "tool": t["tool"], "status": t["status"]}
                                for t in agent.get("trace", [])
                            ],
                            "metrics": nums(c["research"]),
                        },
                    },
                }
            )
        return rows

    def analytics_items(self, split: str) -> list[dict[str, Any]]:
        res = self.src.json(f"{P5}/analytics-v0-{split}-live/results.json")
        gold = {g["id"]: g for g in self.src.json(f"{DS}/analytics-v0/items.json")["items"]}
        rows = []
        for it in res["items"]:
            ch = it["checks"]
            matched = ch.get("all_values_matched") if ch.get("gold_values") else None
            buckets = []
            if matched is False:
                buckets.append("values_mismatch")
            if ch.get("task_type_correct") is False:
                buckets.append("task_type_wrong")
            computed = [
                {k: v for k, v in r.items() if k != "result_id"} for r in it.get("results") or []
            ]
            rows.append(
                {
                    "buckets": buckets,
                    "item": {
                        "phase": "analytics",
                        "item_id": it["id"],
                        "question": it["question"],
                        "task_type": it["task_type"],
                        "routed_task_type": ch.get("route_task_type"),
                        "task_type_correct": bool(ch.get("task_type_correct")),
                        "values_matched": matched,
                        "exact_result_accuracy": ch.get("exact_result_accuracy")
                        if ch.get("gold_values")
                        else None,
                        "answer_markdown": it["content"] or "",
                        "gold_values": (gold[it["id"]].get("gold") or {}).get("analytics"),
                        "computed": computed,
                    },
                }
            )
        return rows

    def items_and_failures(self) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
        items: dict[str, list[dict[str, Any]]] = {}
        failure_runs = []

        def add(
            run_id: str, label: str, field: str, rows: list[dict[str, Any]], labels: dict[str, str]
        ) -> None:
            items[run_id] = rows
            counts: dict[str, int] = {}
            for r in rows:
                for b in r["buckets"]:
                    counts[b] = counts.get(b, 0) + 1
            failure_runs.append(
                {
                    "run_id": run_id,
                    "label": label,
                    "item_count": len(rows),
                    "bucket_field": field,
                    "buckets": [
                        {"id": b, "label": labels.get(b, b), "n": counts[b]} for b in sorted(counts)
                    ],
                }
            )

        retrieval_labels = {
            "both_miss": "Both dense and hybrid miss at hit@10",
            "dense_only": "Only dense hits at hit@10",
            "hybrid_only": "Only hybrid hits at hit@10",
        }
        for run_id, run in RETRIEVAL_RUNS.items():
            rows, _ = self.retrieval_items(run)
            split = "Dev" if run_id.startswith("p2-dev") else "Test"
            add(
                run_id,
                f"Retrieval, {split.lower()} ({run})",
                f"failures['{BUCKET_PAIR}']",
                rows,
                retrieval_labels,
            )
        add(
            "p3-grounded-live",
            "Grounded answers, live-v0",
            "failure-analysis.final_classification",
            self.grounded_items(),
            {"verifier_false_positive": "Verifier false positive", "mixed": "Mixed"},
        )
        research_labels = {
            "standard_behaviour_fail": "Standard run failed expected behaviour",
            "research_behaviour_fail": "Research run failed expected behaviour",
        }
        for split in ("dev", "test"):
            add(
                f"p4-research-{split}",
                f"Standard vs research, {split}",
                "behaviour_pass",
                self.research_items(split),
                research_labels,
            )
        analytics_labels = {
            "values_mismatch": "Not every gold value matched",
            "task_type_wrong": "Task type routed wrongly",
        }
        for split in ("dev", "holdout"):
            add(
                f"p5-analytics-{split}",
                f"Analytics, {split}",
                "checks.all_values_matched / checks.task_type_correct",
                self.analytics_items(split),
                analytics_labels,
            )
        self._check_analytics_buckets(failure_runs)
        return items, failure_runs

    def _check_analytics_buckets(self, failure_runs: list[dict[str, Any]]) -> None:
        for split in ("dev", "holdout"):
            s = self.src.json(f"{P5}/analytics-v0-{split}-live/results.json")["summary"]
            fr = next(f for f in failure_runs if f["run_id"] == f"p5-analytics-{split}")
            got = {b["id"]: b["n"] for b in fr["buckets"]}
            tta, vm = s["routing"]["task_type_accuracy"], s["analytics"]["items_all_values_matched"]
            if (
                got.get("task_type_wrong", 0) != tta["n"] - tta["k"]
                or got.get("values_mismatch", 0) != vm["n"] - vm["k"]
            ):
                raise ValueError(
                    f"analytics {split}: bucket counts disagree with the recorded summary"
                )


def build(root: Path, built_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    src = Sources(root)
    b = Builder(src)
    retrieval = b.retrieval()
    grounded = b.grounded()
    research = b.research()
    analytics = b.analytics()
    superseded = b.superseded()
    caveats = b.caveats()
    items, failure_runs = b.items_and_failures()
    catalog = {
        "schema_version": 1,
        "built_at": built_at,
        "sources": src.listing(),
        "caveats": caveats,
        "overview": b.overview(retrieval, grounded, analytics),
        "retrieval": retrieval,
        "grounded": grounded,
        "research_tradeoff": research,
        "analytics": analytics,
        "superseded": superseded,
        "failure_runs": failure_runs,
    }
    files = {rid: {"run_id": rid, "items": rows} for rid, rows in items.items()}
    return catalog, files


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--built-at", default=None, help="ISO timestamp (default: now, UTC)")
    args = parser.parse_args(argv)
    out: Path = args.out.resolve()
    if (REPO / "eval").resolve() in (out, *out.parents):
        raise SystemExit("refusing to write under eval/")
    built_at = args.built_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    catalog, files = build(REPO, built_at)
    (out / "items").mkdir(parents=True, exist_ok=True)
    (out / "catalog.v1.json").write_text(dump(catalog), encoding="utf-8")
    for rid, payload in files.items():
        (out / "items" / f"{rid}.json").write_text(dump(payload), encoding="utf-8")
    sizes = ", ".join(f"{rid} {len(dump(p)) // 1024} KB" for rid, p in files.items())
    n_src = len(catalog["sources"])
    sys.stdout.write(f"catalog {len(dump(catalog)) // 1024} KB, {n_src} sources; items: {sizes}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
