"""Analytics-engine section."""

from __future__ import annotations

from typing import Any

from .base import BuilderBase
from .common import DS, P5


class AnalyticsSections(BuilderBase):
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
