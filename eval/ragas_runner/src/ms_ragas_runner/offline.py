"""Model-free RAGAS scoring with the real ragas legacy metric classes."""

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ms_ragas_runner import telemetry
from ms_ragas_runner.registry import OFFLINE_KEYS
from ms_ragas_runner.results import (
    Scores,
    build_results,
    clean_score,
    ensure_out_dir_free,
    write_artifacts,
)
from ms_ragas_runner.samples import Sample, load_samples

logger = logging.getLogger(__name__)

NONLLM_THRESHOLD = 0.5


def offline_metric_instances() -> dict[str, Any]:
    classes = telemetry.legacy_offline_metric_classes()
    return {
        "id_recall": classes["IDBasedContextRecall"](),
        "id_precision": classes["IDBasedContextPrecision"](),
        "text_recall": classes["NonLLMContextRecall"](threshold=NONLLM_THRESHOLD),
        "text_precision": classes["NonLLMContextPrecisionWithReference"](
            threshold=NONLLM_THRESHOLD
        ),
    }


async def _ascore(metric: Any, row: Any) -> float | None:
    """One ragas score; a metric that cannot be computed for this row yields ``None``."""
    try:
        value = await metric.single_turn_ascore(row)
    except (AssertionError, ValueError, ZeroDivisionError) as exc:
        logger.debug("metric %s undefined for row: %s", type(metric).__name__, exc)
        return None
    return clean_score(float(value))


async def _score(sample: Sample, metrics: dict[str, Any]) -> Scores:
    row_cls = telemetry.single_turn_sample_class()
    gold_ids = list(sample.reference_context_ids)
    pack_ids = row_cls(
        retrieved_context_ids=list(sample.retrieved_context_ids), reference_context_ids=gold_ids
    )
    cited_ids = row_cls(
        retrieved_context_ids=list(sample.cited_context_ids), reference_context_ids=gold_ids
    )
    pack_texts = row_cls(
        retrieved_contexts=list(sample.retrieved_contexts),
        reference_contexts=list(sample.reference_contexts),
    )
    return {
        "id_context_recall_pack": await _ascore(metrics["id_recall"], pack_ids),
        "id_context_precision_pack": await _ascore(metrics["id_precision"], pack_ids),
        "id_context_recall_cited": await _ascore(metrics["id_recall"], cited_ids),
        "id_context_precision_cited": await _ascore(metrics["id_precision"], cited_ids),
        "nonllm_context_recall_pack": await _ascore(metrics["text_recall"], pack_texts),
        "nonllm_context_precision_pack": await _ascore(metrics["text_precision"], pack_texts),
    }


def score_sample_offline(sample: Sample, metrics: dict[str, Any] | None = None) -> Scores:
    return asyncio.run(_score(sample, metrics or offline_metric_instances()))


def run_offline(sample_paths: Sequence[Path], out_dir: Path) -> dict[str, Any]:
    """Score every configuration of every samples file and write the artifacts."""
    ensure_out_dir_free(out_dir)
    files = [load_samples(p) for p in sample_paths]
    metrics = offline_metric_instances()
    results = build_results(
        files,
        lambda sample: score_sample_offline(sample, metrics),
        set(OFFLINE_KEYS),
        mode="offline",
    )
    write_artifacts(out_dir, results)
    return results
