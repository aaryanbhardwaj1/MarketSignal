"""Build, summarise and write ``marketsignal.ragas-results`` artifacts (format_version 1)."""

import json
import math
import shutil
import subprocess
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ms_ragas_runner import telemetry
from ms_ragas_runner.registry import METRICS, not_run_reason, registry_json
from ms_ragas_runner.report import render_report
from ms_ragas_runner.samples import Sample, SamplesFile

RESULTS_FORMAT = "marketsignal.ragas-results"
RESULTS_FORMAT_VERSION = 1
HISTOGRAM_BINS = 10

Scores = dict[str, float | None]
ScoreFn = Callable[[Sample], Scores]


class OutputExistsError(FileExistsError):
    """The output directory already exists; recorded artifacts are never overwritten."""


def clean_score(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def to_json_safe(value: Any) -> Any:
    """Replace NaN/inf with ``None`` recursively so the JSON is strict."""
    if isinstance(value, float):
        return clean_score(value)
    if isinstance(value, dict):
        return {k: to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_json_safe(v) for v in value]
    return value


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile (numpy's default method)."""
    position = (len(sorted_values) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    fraction = position - low
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * fraction


def _histogram(values: Sequence[float]) -> list[dict[str, Any]]:
    width = 1.0 / HISTOGRAM_BINS
    counts = [0] * HISTOGRAM_BINS
    for value in values:
        counts[min(int(value / width), HISTOGRAM_BINS - 1)] += 1
    return [
        {"lo": round(i * width, 10), "hi": round((i + 1) * width, 10), "n": counts[i]}
        for i in range(HISTOGRAM_BINS)
    ]


def summarize(raw: Iterable[float | None]) -> dict[str, Any]:
    """Summary statistics over the defined scores; undefined scores are only counted."""
    cleaned = [clean_score(v) for v in raw]
    values = sorted(v for v in cleaned if v is not None)
    n_nan = len(cleaned) - len(values)
    if not values:
        empty: dict[str, Any] = dict.fromkeys(("mean", "median", "p25", "p75", "min", "max"))
        return {**empty, "n": 0, "n_nan": n_nan, "histogram": _histogram([])}
    return {
        "mean": sum(values) / len(values),
        "median": _percentile(values, 0.5),
        "p25": _percentile(values, 0.25),
        "p75": _percentile(values, 0.75),
        "min": values[0],
        "max": values[-1],
        "n": len(values),
        "n_nan": n_nan,
        "histogram": _histogram(values),
    }


def git_sha() -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no user input
            [git, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=True
        )
    except (subprocess.SubprocessError, OSError):
        return None
    sha = completed.stdout.strip()
    return sha or None


def _repo_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def display_path(path: Path) -> str:
    """A repo-relative path when possible; never an absolute local path in an artifact."""
    resolved = path.resolve()
    cwd = Path.cwd().resolve()
    for base in (_repo_root(cwd), cwd):
        if base is not None and resolved.is_relative_to(base):
            return resolved.relative_to(base).as_posix()
    return path.name


def _groups(files: Sequence[SamplesFile]) -> list[tuple[SamplesFile, str]]:
    seen: set[tuple[str, str]] = set()
    groups = []
    for samples_file in files:
        for configuration in samples_file.configurations:
            key = (samples_file.run_id, configuration)
            if key in seen:
                raise ValueError(
                    f"run {key[0]!r} configuration {key[1]!r} appears more than once in the inputs"
                )
            seen.add(key)
            groups.append((samples_file, configuration))
    return groups


def _run_entry(
    samples_file: SamplesFile, configuration: str, score_fn: ScoreFn, computed: set[str]
) -> dict[str, Any]:
    scorable = samples_file.scorable(configuration)
    items: list[dict[str, Any]] = []
    for sample in scorable:
        scores = score_fn(sample)
        items.append(
            {
                "item_id": sample.item_id,
                "category": sample.category,
                "configuration": configuration,
                "scores": {k: clean_score(scores.get(k)) for k in sorted(computed)},
            }
        )
    summary: dict[str, Any] = {}
    for metric in METRICS:
        if metric.key in computed:
            values = [item["scores"][metric.key] for item in items]
            summary[metric.key] = {"status": "computed", **summarize(values)}
        else:
            summary[metric.key] = {"status": "not_run", "not_run_reason": not_run_reason(metric)}
    return {
        "run_id": samples_file.run_id,
        "configuration": configuration,
        "n_samples": len(scorable),
        "n_excluded": samples_file.excluded_count(configuration),
        "summary": summary,
        "items": items,
    }


def build_results(
    files: Sequence[SamplesFile], score_fn: ScoreFn, computed: set[str], *, mode: str
) -> dict[str, Any]:
    groups = _groups(files)
    results = {
        "format": RESULTS_FORMAT,
        "format_version": RESULTS_FORMAT_VERSION,
        "mode": mode,
        "ragas_version": telemetry.ragas_version(),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "inputs": [
            {"path": display_path(f.path), "sha256": f.sha256, "run_id": f.run_id} for f in files
        ],
        "telemetry_disabled": telemetry.telemetry_disabled(),
        "metrics": registry_json(),
        "runs": [_run_entry(f, c, score_fn, computed) for f, c in groups],
    }
    return to_json_safe(results)  # type: ignore[no-any-return]


def write_artifacts(out_dir: Path, results: dict[str, Any]) -> None:
    """Write ``results.json`` and ``report.md`` into a directory that must not exist yet."""
    if out_dir.exists():
        raise OutputExistsError(f"refusing to overwrite existing output directory: {out_dir}")
    body = json.dumps(results, indent=2, allow_nan=False, ensure_ascii=False) + "\n"
    report = render_report(results)
    out_dir.mkdir(parents=True)
    (out_dir / "results.json").write_text(body, encoding="utf-8")
    (out_dir / "report.md").write_text(report, encoding="utf-8")


def ensure_out_dir_free(out_dir: Path) -> None:
    if out_dir.exists():
        raise OutputExistsError(f"refusing to overwrite existing output directory: {out_dir}")
