"""Render the human-readable ``report.md`` that accompanies ``results.json``."""

from typing import Any

_REASON_TEXT = {
    "no_reference_answers": (
        "needs authored reference answers; the gold sets hold short gold facts and handles, "
        "not reference answers"
    ),
    "model_credits_unavailable": (
        "needs a judge model; it is wired but was not run (no model calls were made)"
    ),
}


def _fmt(value: Any) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _computed_table(run: dict[str, Any], labels: dict[str, str]) -> list[str]:
    lines = [
        "| Metric | Mean | Median | P25 | P75 | n | Undefined |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, entry in run["summary"].items():
        if entry["status"] != "computed":
            continue
        lines.append(
            f"| {labels[key]} | {_fmt(entry['mean'])} | {_fmt(entry['median'])} | "
            f"{_fmt(entry['p25'])} | {_fmt(entry['p75'])} | {entry['n']} | {entry['n_nan']} |"
        )
    return lines


def _caveat(mode: str) -> str:
    judged = (
        "The model-judged scores in this run reflect one judge model's opinions."
        if mode == "llm"
        else "No model was called for this run: every score here is a model-free heuristic."
    )
    return (
        f"{judged} RAGAS scores are proxies computed by the ragas library, not objective truth. "
        "ID-based scores depend on the gold handles being complete; text-similarity scores are "
        "lexical and can miss paraphrases or reward surface overlap."
    )


def render_report(results: dict[str, Any]) -> str:
    metrics = results["metrics"]
    labels = {m["key"]: m["label"] for m in metrics}
    computed_keys = {
        key
        for run in results["runs"]
        for key, entry in run["summary"].items()
        if entry["status"] == "computed"
    }
    lines = [
        "# RAGAS evaluation report",
        "",
        f"- ragas version: {results['ragas_version']}",
        f"- mode: {results['mode']}",
        f"- created: {results['created_at']}",
        f"- git sha: {results['git_sha'] or 'unknown'}",
        f"- ragas usage tracking disabled: {results['telemetry_disabled']}",
        "- inputs: " + ", ".join(f"`{i['path']}` ({i['run_id']})" for i in results["inputs"]),
        "",
        "## What was measured",
        "",
    ]
    for run in results["runs"]:
        lines += [
            f"### {run['run_id']} / {run['configuration']}",
            "",
            f"{run['n_samples']} scored samples, {run['n_excluded']} excluded by the exporter.",
            "",
            *_computed_table(run, labels),
            "",
        ]
    lines += ["## Definitions", ""]
    for metric in metrics:
        if metric["key"] in computed_keys:
            lines.append(
                f"- **{metric['label']}** (`{metric['key']}`, ragas `{metric['ragas_class']}`): "
                f"{metric['what_it_measures']}"
            )
    lines += ["", "## Not measured", ""]
    for metric in metrics:
        if metric["key"] in computed_keys:
            continue
        reason = (
            next(run["summary"][metric["key"]]["not_run_reason"] for run in results["runs"])
            if results["runs"]
            else "model_credits_unavailable"
        )
        lines.append(
            f"- **{metric['label']}** (`{metric['key']}`): not run, "
            f"{_REASON_TEXT.get(reason, reason)}."
        )
    lines += ["", "## Caveat", "", _caveat(results["mode"]), ""]
    return "\n".join(lines)
