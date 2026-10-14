"""The single gateway to ragas.

ragas sends anonymous usage analytics unless ``RAGAS_DO_NOT_TRACK`` is true, and it reads that
variable once (behind ``functools.lru_cache``). This module sets it at import time, before any ragas
module can be imported, and every other module in this package obtains ragas objects through the
loader functions below rather than importing ragas directly.
"""

import os
import warnings
from types import ModuleType
from typing import Any

os.environ["RAGAS_DO_NOT_TRACK"] = "true"

TELEMETRY_ENV_VAR = "RAGAS_DO_NOT_TRACK"


def telemetry_disabled() -> bool:
    """True when ragas itself reports that usage tracking is off."""
    from ragas._analytics import do_not_track

    return bool(do_not_track())


def ragas_version() -> str:
    import ragas

    return str(ragas.__version__)


def legacy_offline_metric_classes() -> dict[str, Any]:
    """The legacy (non-LLM) ragas metric classes, imported with their deprecation warning muted."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from ragas.metrics import (
            IDBasedContextPrecision,
            IDBasedContextRecall,
            NonLLMContextPrecisionWithReference,
            NonLLMContextRecall,
        )
    return {
        "IDBasedContextRecall": IDBasedContextRecall,
        "IDBasedContextPrecision": IDBasedContextPrecision,
        "NonLLMContextRecall": NonLLMContextRecall,
        "NonLLMContextPrecisionWithReference": NonLLMContextPrecisionWithReference,
    }


def single_turn_sample_class() -> Any:
    from ragas.dataset_schema import SingleTurnSample

    return SingleTurnSample


def collections_module() -> ModuleType:
    """``ragas.metrics.collections``: the LLM metrics that take an explicit llm."""
    import ragas.metrics.collections as collections

    return collections


def llm_factory() -> Any:
    from ragas.llms import llm_factory as factory

    return factory


def base_embedding_class() -> Any:
    from ragas.embeddings.base import BaseRagasEmbedding

    return BaseRagasEmbedding
