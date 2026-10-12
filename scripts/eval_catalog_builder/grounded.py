"""Grounded-answer and verifier sections."""

from __future__ import annotations

from typing import Any

from .base import BuilderBase
from .common import DS, P3, P4, ptr


class GroundedSections(BuilderBase):
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
