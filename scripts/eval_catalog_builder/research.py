"""Research-agent trade-off section."""

from __future__ import annotations

from typing import Any

from .base import BuilderBase
from .common import DS, P4, ptr


class ResearchSections(BuilderBase):
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
