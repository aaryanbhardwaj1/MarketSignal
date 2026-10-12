"""Per-run item files and failure-run summaries."""

from __future__ import annotations

from typing import Any

from .base import BuilderBase
from .common import ARMS, BUCKET_PAIR, DEFAULT_ARM, DS, P2, P3, P4, P5, RETRIEVAL_RUNS


class ItemSections(BuilderBase):
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
