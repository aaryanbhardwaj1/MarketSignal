"""Retrieval section: arm metrics, paired comparisons and decisions."""

from __future__ import annotations

from typing import Any

from .base import BuilderBase
from .common import (
    ARMS,
    DEFAULT_ARM,
    P2,
    P2_ELIGIBLE,
    P2_REPORT,
    P2_SUMMARY,
    RETRIEVAL_METRICS,
    RETRIEVAL_RUNS,
    ptr,
)


class RetrievalSections(BuilderBase):
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
