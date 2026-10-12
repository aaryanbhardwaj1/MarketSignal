"""Superseded runs, caveats and the overview headline."""

from __future__ import annotations

from typing import Any

from .base import BuilderBase
from .common import DEFAULT_ARM, P5, P5_REPORT, VERIFIER_SUMMARY


class SummarySections(BuilderBase):
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
                "Research summary-off arm (incomplete)",
                "The research-summary off/on comparison was stopped before the summary-on arm "
                "ran, so no live before/after comparison exists.",
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
                "text": "The citation verifier's holdout split was scored twice: at the end of "
                "development and again after safety fixes. No rule was tuned to holdout scores.",
            },
            {
                "id": "a3-not-run",
                "applies_to": ["overview", "analytics", "research_tradeoff"],
                "text": "The research-summary ablation was not measured live; the summary "
                "hand-off is tested offline only.",
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
