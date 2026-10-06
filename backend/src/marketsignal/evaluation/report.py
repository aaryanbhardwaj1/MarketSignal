"""Evaluation report: JSON (machine-readable, complete) and Markdown (for people).

For each arm: overall metrics with 95% intervals (Wilson for hit rates, percentile bootstrap
for recall and MRR), breakdowns by category, source format and overlap bin (cells with n < 10
shown as k/n), and latency p50/p95 per stage. For each arm against the reference arm: exact
McNemar on hit@k and paired-bootstrap intervals on MRR / recall@10 differences, plus failure
buckets with concrete examples (found by one arm only, missed by both, distractor outranking).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from marketsignal.evaluation.metrics import DEFAULT_KS, aggregate
from marketsignal.evaluation.runner import ItemRun
from marketsignal.evaluation.stats import (
    bootstrap_mean,
    mcnemar_exact,
    paired_bootstrap_diff,
    percentile,
    wilson,
)

SMALL_CELL = 10
EXAMPLES_PER_BUCKET = 6


def item_formats(run: ItemRun, fact_formats: Mapping[str, str]) -> list[str]:
    return sorted({fact_formats.get(f, "?") for f in run.item.fact_ids()})


def format_key(run: ItemRun, fact_formats: Mapping[str, str]) -> str:
    formats = item_formats(run, fact_formats)
    return formats[0] if len(formats) == 1 else "multi:" + "+".join(formats)


def summarize(runs: Sequence[ItemRun]) -> dict[str, Any]:
    scores = [r.score for r in runs]
    out: dict[str, Any] = {"metrics": aggregate(scores)}
    n = len(scores)
    intervals: dict[str, Any] = {}
    for k in (1, 5, 10, 20):
        hits = sum(1 for s in scores if s.hit_at(k))
        intervals[f"hit@{k}"] = wilson(hits, n).as_dict()
        intervals[f"recall@{k}"] = bootstrap_mean([s.recall_at(k) for s in scores]).as_dict()
    intervals["mrr"] = bootstrap_mean([s.reciprocal_rank() for s in scores]).as_dict()
    out["intervals"] = intervals
    stages: dict[str, list[float]] = defaultdict(list)
    for r in runs:
        for key, value in r.timings_ms.items():
            stages[key].append(value)
    out["latency_ms"] = {
        key: {"p50": round(percentile(v, 0.5), 2), "p95": round(percentile(v, 0.95), 2)}
        for key, v in sorted(stages.items())
    }
    flags: dict[str, int] = defaultdict(int)
    for r in runs:
        for flag in r.flags:
            flags[flag] += 1
    out["flags"] = dict(flags)
    return out


def breakdown(
    runs: Sequence[ItemRun], key_of: Any, ks: Sequence[int] = (1, 5, 10)
) -> dict[str, Any]:
    groups: dict[str, list[ItemRun]] = defaultdict(list)
    for r in runs:
        for key in key_of(r):
            groups[key].append(r)
    out: dict[str, Any] = {}
    for key, members in sorted(groups.items()):
        scores = [m.score for m in members]
        cell: dict[str, Any] = {"n": len(scores)}
        for k in ks:
            cell[f"hit@{k}"] = sum(1 for s in scores if s.hit_at(k))
            cell[f"recall@{k}"] = round(sum(s.recall_at(k) for s in scores) / len(scores), 3)
        cell["mrr"] = round(sum(s.reciprocal_rank() for s in scores) / len(scores), 3)
        out[key] = cell
    return out


def compare(reference: Sequence[ItemRun], other: Sequence[ItemRun]) -> dict[str, Any]:
    by_id = {r.item.id: r for r in reference}
    pairs = [(by_id[o.item.id], o) for o in other if o.item.id in by_id]
    ref_scores = [a.score for a, _ in pairs]
    oth_scores = [b.score for _, b in pairs]
    out: dict[str, Any] = {"n": len(pairs)}
    for k in (1, 5, 10, 20):
        test = mcnemar_exact([s.hit_at(k) for s in ref_scores], [s.hit_at(k) for s in oth_scores])
        out[f"hit@{k}"] = {
            "only_reference": test.only_a,
            "only_other": test.only_b,
            "p_value": round(test.p_value, 4),
        }
    out["mrr_diff"] = paired_bootstrap_diff(
        [s.reciprocal_rank() for s in ref_scores], [s.reciprocal_rank() for s in oth_scores]
    ).as_dict()
    out["recall@10_diff"] = paired_bootstrap_diff(
        [s.recall_at(10) for s in ref_scores], [s.recall_at(10) for s in oth_scores]
    ).as_dict()
    return out


def _first_rank(run: ItemRun) -> int | None:
    ranks = [r for r in run.score.fact_ranks.values() if r is not None]
    return min(ranks) if ranks else None


def _example(run_by_arm: Mapping[str, ItemRun], item_id: str) -> dict[str, Any]:
    any_run = next(iter(run_by_arm.values()))
    item = any_run.item
    return {
        "item_id": item_id,
        "question": item.question,
        "category": item.category,
        "overlap": item.overlap,
        "expected": sorted({h for f in item.required_facts for h in f.handles()}),
        "ranks": {arm: dict(r.score.fact_ranks) for arm, r in run_by_arm.items()},
        "top3": {arm: r.parents[:3] for arm, r in run_by_arm.items()},
    }


def failure_buckets(
    arms: Mapping[str, Sequence[ItemRun]], a: str, b: str, k: int = 10
) -> dict[str, Any]:
    ra = {r.item.id: r for r in arms[a]}
    rb = {r.item.id: r for r in arms[b]}
    buckets: dict[str, list[str]] = defaultdict(list)
    for item_id in ra:
        hit_a, hit_b = ra[item_id].score.hit_at(k), rb[item_id].score.hit_at(k)
        if hit_a and not hit_b:
            buckets[f"{a}_only"].append(item_id)
        elif hit_b and not hit_a:
            buckets[f"{b}_only"].append(item_id)
        elif not hit_a and not hit_b:
            buckets["both_miss"].append(item_id)
    out: dict[str, Any] = {}
    for name, ids in buckets.items():
        out[name] = {
            "count": len(ids),
            "examples": [_example({a: ra[i], b: rb[i]}, i) for i in ids[:EXAMPLES_PER_BUCKET]],
            "all_ids": ids,
        }
    return out


def distractor_outranking(runs: Sequence[ItemRun]) -> list[dict[str, Any]]:
    """Items whose ledger distractor parent ranks above the true parent (or true is missing)."""
    out = []
    for r in runs:
        if not r.item.hard_negatives:
            continue
        position = {h: i for i, h in enumerate(r.parents, start=1)}
        neg = [position[h] for h in r.item.hard_negatives if h in position]
        true_rank = _first_rank(r)
        best_neg = min(neg) if neg else None
        out.append(
            {
                "item_id": r.item.id,
                "question": r.item.question,
                "true_rank": true_rank,
                "best_distractor_rank": best_neg,
                "distractor_wins": best_neg is not None
                and (true_rank is None or best_neg < true_rank),
            }
        )
    return out


def build_report(
    arms: Mapping[str, Sequence[ItemRun]],
    *,
    split: str,
    reference: str,
    fact_formats: Mapping[str, str],
    manifest: Mapping[str, Any],
    arm_configs: Mapping[str, Any],
    run_info: Mapping[str, Any],
    task_types: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """``task_types`` (item id -> retrieval | analytics | multi_tool): when given, every arm also
    reports a ``retrieval_eligible`` summary over ``retrieval`` items (the retrieval-quality
    denominator) and a per-task-type breakdown; full-set metrics are always kept."""
    task_types = task_types or {}
    report: dict[str, Any] = {
        "run": dict(run_info),
        "split": split,
        "dataset": {
            k: manifest.get(k)
            for k in ("dataset_version", "corpus_sha256", "ledger_sha256", "items_sha256")
        },
        "arms": {},
        "comparisons": {},
        "failures": {},
    }
    for name, runs in arms.items():
        entry = summarize(runs)
        entry["config"] = arm_configs[name]
        entry["by_category"] = breakdown(runs, lambda r: [r.item.category])
        entry["by_format"] = breakdown(runs, lambda r: item_formats(r, fact_formats))
        entry["by_overlap_bin"] = breakdown(runs, lambda r: [r.item.overlap_bin or "?"])
        entry["distractors"] = distractor_outranking(runs)
        if task_types:
            eligible = [r for r in runs if task_types.get(r.item.id) == "retrieval"]
            entry["retrieval_eligible"] = summarize(eligible)
            entry["by_task_type"] = breakdown(
                runs, lambda r: [task_types.get(r.item.id, "unclassified")]
            )
        entry["items"] = [r.as_dict() for r in runs]
        report["arms"][name] = entry
    if task_types:
        report["task_composition"] = dict(
            Counter(task_types.get(r.item.id, "unclassified") for r in next(iter(arms.values())))
        )
    for name in arms:
        if name != reference:
            report["comparisons"][f"{reference}->{name}"] = compare(arms[reference], arms[name])
            if task_types:
                keep = {i for i, t in task_types.items() if t == "retrieval"}
                report["comparisons"][f"{reference}->{name} [retrieval-eligible]"] = compare(
                    [r for r in arms[reference] if r.item.id in keep],
                    [r for r in arms[name] if r.item.id in keep],
                )
            report["failures"][f"{reference}|{name}"] = failure_buckets(arms, reference, name)
    return report


def _pct(x: float) -> str:
    return f"{100 * x:.1f}"


def _ci(interval: Mapping[str, float]) -> str:
    return f"{_pct(interval['estimate'])} [{_pct(interval['low'])}, {_pct(interval['high'])}]"


def _cell(cell: Mapping[str, Any], metric: str) -> str:
    n = cell["n"]
    if metric.startswith("hit@"):
        return f"{cell[metric]}/{n}" if n < SMALL_CELL else f"{_pct(cell[metric] / n)}%"
    return f"{cell[metric]:.2f}"


def _diff(interval: Mapping[str, float]) -> str:
    return f"{interval['estimate']:+.3f} [{interval['low']:+.3f}, {interval['high']:+.3f}]"


def render_markdown(report: Mapping[str, Any], title: str) -> str:
    lines = [f"# {title}", ""]
    ds = report["dataset"]
    run = report["run"]
    n_items = next(iter(report["arms"].values()))["metrics"]["n"]
    lines += [
        f"- Split: **{report['split']}**, items: {n_items}",
        f"- Dataset: `{ds['dataset_version']}` · corpus `{ds['corpus_sha256'][:12]}`"
        f" · ledger `{ds['ledger_sha256'][:12]}`",
        f"- Run: {', '.join(f'{k}={v}' for k, v in run.items())}",
        "",
        "## Overall (95% CI: Wilson for hit, bootstrap for recall/MRR)",
        "",
        "| Arm | hit@1 | hit@5 | hit@10 | recall@10 | recall@20 (pool) | MRR | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, arm in report["arms"].items():
        iv = arm["intervals"]
        lat = arm["latency_ms"].get("total_ms", {"p50": 0, "p95": 0})
        lines.append(
            f"| {name} | {_ci(iv['hit@1'])} | {_ci(iv['hit@5'])} | {_ci(iv['hit@10'])} | "
            f"{_ci(iv['recall@10'])} | {_ci(iv['recall@20'])} | {_ci(iv['mrr'])} | "
            f"{lat['p50']} | {lat['p95']} |"
        )
    if "task_composition" in report:
        lines += [
            "",
            "## Retrieval-eligible items (task_type = retrieval)",
            "",
            f"Task composition of this split: {report['task_composition']}. Analytics-only and "
            "multi-tool items stay in the dataset but are outside the retrieval denominator.",
            "",
            "| Arm | n | hit@1 | hit@10 | recall@10 | recall@20 (pool) | MRR |",
            "|---|---|---|---|---|---|---|",
        ]
        for name, arm in report["arms"].items():
            el = arm["retrieval_eligible"]
            iv = el["intervals"]
            lines.append(
                f"| {name} | {el['metrics']['n']} | {_ci(iv['hit@1'])} | {_ci(iv['hit@10'])} | "
                f"{_ci(iv['recall@10'])} | {_ci(iv['recall@20'])} | {_ci(iv['mrr'])} |"
            )
    lines += ["", "## Latency by stage (ms, p50 / p95)", ""]
    for name, arm in report["arms"].items():
        stages = ", ".join(f"{k} {v['p50']}/{v['p95']}" for k, v in arm["latency_ms"].items())
        lines.append(f"- **{name}**: {stages}")
        if arm["flags"]:
            lines.append(f"  - flags: {arm['flags']}")
    for title_, key in (
        ("category", "by_category"),
        ("source format", "by_format"),
        ("overlap bin", "by_overlap_bin"),
    ):
        lines += [
            "",
            f"## By {title_} (hit@1 · hit@10 · MRR; cells with n < {SMALL_CELL} as k/n)",
            "",
        ]
        names = list(report["arms"])
        lines.append("| " + title_ + " | n | " + " | ".join(names) + " |")
        lines.append("|---|---|" + "---|" * len(names))
        keys = sorted({k for a in report["arms"].values() for k in a[key]})
        for k in keys:
            cells = []
            n = 0
            for a in names:
                c = report["arms"][a][key].get(k)
                if c is None:
                    cells.append("-")
                    continue
                n = c["n"]
                cells.append(f"{_cell(c, 'hit@1')} · {_cell(c, 'hit@10')} · {_cell(c, 'mrr')}")
            lines.append(f"| {k} | {n} | " + " | ".join(cells) + " |")
    if report["comparisons"]:
        lines += ["", "## Paired comparisons (same items)", ""]
        lines.append(
            "| Comparison | hit@1 (only ref / only other, p) | hit@10 (…) "
            "| ΔMRR [95% CI] | Δrecall@10 [95% CI] |"
        )
        lines.append("|---|---|---|---|---|")
        for name, c in report["comparisons"].items():
            h1, h10 = c["hit@1"], c["hit@10"]
            lines.append(
                f"| {name} | {h1['only_reference']} / {h1['only_other']}, p={h1['p_value']} | "
                f"{h10['only_reference']} / {h10['only_other']}, p={h10['p_value']} | "
                f"{_diff(c['mrr_diff'])} | {_diff(c['recall@10_diff'])} |"
            )
    for pair, buckets in report["failures"].items():
        lines += ["", f"## Failure buckets at k=10: {pair}", ""]
        for bucket, data in buckets.items():
            lines.append(f"### {bucket} ({data['count']})")
            lines.append("")
            for ex in data["examples"]:
                ranks = "; ".join(f"{arm}: {r}" for arm, r in ex["ranks"].items())
                head = f"- **{ex['item_id']}** ({ex['category']}, overlap {ex['overlap']})"
                lines.append(f"{head}: {ex['question']}")
                lines.append(f"  - expected {ex['expected']} · ranks {ranks}")
                for arm, top in ex["top3"].items():
                    lines.append(f"  - {arm} top-3: {top}")
            lines.append("")
    lines += ["", "## Distractor outranking", ""]
    for name, arm in report["arms"].items():
        rows = arm["distractors"]
        wins = [r for r in rows if r["distractor_wins"]]
        lines.append(
            f"- **{name}**: a ledger distractor ranked above the item's best-ranked required"
            f" parent in {len(wins)}/{len(rows)} items with a distractor (multi-fact items are"
            " compared with their best fact, not per fact)"
        )
        for r in wins:
            lines.append(
                f"  - {r['item_id']}: true rank {r['true_rank']},"
                f" distractor rank {r['best_distractor_rank']} — {r['question']}"
            )
    return "\n".join(lines) + "\n"


def write_report(report: Mapping[str, Any], out_dir: Path, title: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(render_markdown(report, title), encoding="utf-8")


__all__ = ["DEFAULT_KS", "build_report", "format_key", "write_report"]
