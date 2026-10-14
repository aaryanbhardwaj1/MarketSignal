"""Model-judged RAGAS metrics: wired and gated, never run by default.

A live run requires ALL of: the ``--i-understand-this-calls-the-model`` flag, ``MS_LIVE_LLM=1`` and
``ANTHROPIC_API_KEY`` in the environment. Even then it only prints a token and cost estimate unless
``--confirm-cost`` is also given. The metrics come from ``ragas.metrics.collections`` with an
explicit judge llm; the legacy evaluation entry point is never used here because it silently falls
back to a default OpenAI judge.
"""

import asyncio
import logging
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from ms_ragas_runner import telemetry
from ms_ragas_runner.offline import offline_metric_instances, score_sample_offline
from ms_ragas_runner.registry import LLM_KEYS, METRICS_BY_KEY, OFFLINE_KEYS
from ms_ragas_runner.results import (
    Scores,
    build_results,
    clean_score,
    ensure_out_dir_free,
    write_artifacts,
)
from ms_ragas_runner.samples import Sample, SamplesFile, load_samples

logger = logging.getLogger(__name__)

ACK_FLAG = "--i-understand-this-calls-the-model"
LIVE_ENV_VAR = "MS_LIVE_LLM"
KEY_ENV_VAR = "ANTHROPIC_API_KEY"

DEFAULT_MODEL = "claude-sonnet-5-5"  # the backend's synthesis model
DEFAULT_PRICE_INPUT_PER_MTOK = 2.0  # USD, the backend's list price for DEFAULT_MODEL
DEFAULT_PRICE_OUTPUT_PER_MTOK = 10.0
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

# Rough estimation constants: ragas prompts carry instructions and few-shot examples, and judge
# outputs are short structured JSON. Treat the estimate as an order of magnitude, not a quote.
CHARS_PER_TOKEN = 4
PROMPT_OVERHEAD_TOKENS = 800
OUTPUT_TOKENS_PER_CALL = 300
ANSWER_RELEVANCY_STRICTNESS = 3


class GateError(RuntimeError):
    """A safety gate for live model calls is closed."""


def check_gates(*, acknowledged: bool, environ: Mapping[str, str]) -> None:
    """Raise :class:`GateError` naming every closed gate. Never echoes secret values."""
    closed = []
    if not acknowledged:
        closed.append(f"pass {ACK_FLAG}")
    if environ.get(LIVE_ENV_VAR) != "1":
        closed.append(f"set {LIVE_ENV_VAR}=1")
    if not environ.get(KEY_ENV_VAR, "").strip():
        closed.append(f"set {KEY_ENV_VAR}")
    if closed:
        raise GateError("live model run refused; to proceed: " + "; ".join(closed))


@dataclass(frozen=True)
class CostEstimate:
    calls: int
    input_tokens: int
    output_tokens: int
    usd: float


def _tokens(*texts: str) -> int:
    return PROMPT_OVERHEAD_TOKENS + sum(len(t) for t in texts) // CHARS_PER_TOKEN


def _calls_for(key: str, sample: Sample) -> list[int]:
    """Estimated input tokens for each judge call one metric makes on one sample."""
    contexts = "".join(sample.retrieved_contexts)
    reference = sample.reference or ""
    if key == "faithfulness":  # statement extraction, then verdicts against the contexts
        return [_tokens(sample.user_input, sample.response), _tokens(contexts, sample.response)]
    if key == "answer_relevancy":
        return [_tokens(sample.response)] * ANSWER_RELEVANCY_STRICTNESS
    if key == "llm_context_precision_with_reference":  # one verdict per retrieved context
        return [_tokens(sample.user_input, reference, c) for c in sample.retrieved_contexts]
    if key == "llm_context_recall":
        return [_tokens(sample.user_input, reference, contexts)]
    if key == "factual_correctness":  # claim decomposition and verification, both directions
        return [_tokens(sample.response, reference)] * 4
    raise KeyError(key)


def _scorable(files: Iterable[SamplesFile]) -> list[Sample]:
    return [s for f in files for c in f.configurations for s in f.scorable(c)]


def estimate_cost(
    files: Sequence[SamplesFile],
    keys: Sequence[str],
    *,
    price_input_per_mtok: float,
    price_output_per_mtok: float,
) -> CostEstimate:
    per_call = [t for s in _scorable(files) for k in keys for t in _calls_for(k, s)]
    calls = len(per_call)
    input_tokens = sum(per_call)
    output_tokens = calls * OUTPUT_TOKENS_PER_CALL
    usd = (input_tokens * price_input_per_mtok + output_tokens * price_output_per_mtok) / 1e6
    return CostEstimate(calls, input_tokens, output_tokens, usd)


def runnable_llm_keys(files: Sequence[SamplesFile]) -> tuple[str, ...]:
    """LLM metrics that the inputs support; reference-answer metrics need every reference."""
    samples = _scorable(files)
    have_references = bool(samples) and all(s.reference for s in samples)
    return tuple(
        k for k in LLM_KEYS if have_references or not METRICS_BY_KEY[k].needs_reference_answer
    )


def make_anthropic_client() -> Any:
    """The only place a model client is constructed; reached only after every gate is open."""
    return AsyncAnthropic()


def build_judge_llm(model: str, client: Any) -> Any:
    judge = telemetry.llm_factory()(model, provider="anthropic", client=client)
    # ragas defaults top_p alongside temperature; newer Anthropic models reject both together.
    judge.model_args.pop("top_p", None)
    return judge


_BaseEmbedding: Any = telemetry.base_embedding_class()


class FastEmbedEmbedding(_BaseEmbedding):  # type: ignore[misc]
    """A local fastembed model behind the ragas embedding interface (used by AnswerRelevancy)."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        model_factory: Callable[[str], Any] | None = None,
    ) -> None:
        super().__init__(cache=None)
        self._model_name = model_name
        self._model_factory = model_factory or _fastembed_model
        self._model: Any = None

    def _loaded(self) -> Any:
        if self._model is None:
            self._model = self._model_factory(self._model_name)
        return self._model

    def embed_texts(self, texts: list[str], **_kwargs: Any) -> list[list[float]]:
        return [[float(x) for x in vec] for vec in self._loaded().embed(list(texts))]

    def embed_text(self, text: str, **kwargs: Any) -> list[float]:
        return self.embed_texts([text], **kwargs)[0]

    async def aembed_text(self, text: str, **kwargs: Any) -> list[float]:
        return await asyncio.to_thread(self.embed_text, text, **kwargs)

    async def aembed_texts(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_texts, texts, **kwargs)


def _fastembed_model(name: str) -> Any:
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=name)


def _judge_metrics(keys: Sequence[str], judge: Any) -> dict[str, Any]:
    collections = telemetry.collections_module()
    factories: dict[str, Callable[[], Any]] = {
        "faithfulness": lambda: collections.Faithfulness(llm=judge),
        "answer_relevancy": lambda: collections.AnswerRelevancy(
            llm=judge, embeddings=FastEmbedEmbedding(), strictness=ANSWER_RELEVANCY_STRICTNESS
        ),
        "llm_context_precision_with_reference": lambda: collections.ContextPrecisionWithReference(
            llm=judge
        ),
        "llm_context_recall": lambda: collections.ContextRecall(llm=judge),
        "factual_correctness": lambda: collections.FactualCorrectness(llm=judge),
    }
    return {k: factories[k]() for k in keys}


def _metric_kwargs(key: str, sample: Sample) -> dict[str, Any]:
    contexts = list(sample.retrieved_contexts)
    kwargs: dict[str, dict[str, Any]] = {
        "faithfulness": {
            "user_input": sample.user_input,
            "response": sample.response,
            "retrieved_contexts": contexts,
        },
        "answer_relevancy": {"user_input": sample.user_input, "response": sample.response},
        "llm_context_precision_with_reference": {
            "user_input": sample.user_input,
            "reference": sample.reference,
            "retrieved_contexts": contexts,
        },
        "llm_context_recall": {
            "user_input": sample.user_input,
            "reference": sample.reference,
            "retrieved_contexts": contexts,
        },
        "factual_correctness": {"response": sample.response, "reference": sample.reference},
    }
    return kwargs[key]


async def _judge_sample(sample: Sample, metrics: Mapping[str, Any]) -> Scores:
    scores: Scores = {}
    for key, metric in metrics.items():
        try:
            result = await metric.ascore(**_metric_kwargs(key, sample))
        except ValueError as exc:  # e.g. an empty response; transport errors still abort
            logger.warning("%s undefined for %s: %s", key, sample.item_id, exc)
            scores[key] = None
            continue
        scores[key] = clean_score(float(result.value))
    return scores


def run_llm(
    sample_paths: Sequence[Path],
    out_dir: Path,
    *,
    acknowledged: bool,
    confirm_cost: bool,
    model: str = DEFAULT_MODEL,
    price_input_per_mtok: float = DEFAULT_PRICE_INPUT_PER_MTOK,
    price_output_per_mtok: float = DEFAULT_PRICE_OUTPUT_PER_MTOK,
    environ: Mapping[str, str] | None = None,
) -> int:
    check_gates(acknowledged=acknowledged, environ=os.environ if environ is None else environ)
    ensure_out_dir_free(out_dir)
    files = [load_samples(p) for p in sample_paths]
    keys = runnable_llm_keys(files)
    estimate = estimate_cost(
        files,
        keys,
        price_input_per_mtok=price_input_per_mtok,
        price_output_per_mtok=price_output_per_mtok,
    )
    print(
        f"Estimated {estimate.calls} judge calls to {model} for {', '.join(keys)}: "
        f"~{estimate.input_tokens:,} input + ~{estimate.output_tokens:,} output tokens, "
        f"~${estimate.usd:.2f} at ${price_input_per_mtok}/${price_output_per_mtok} per Mtok "
        f"(rough chars/{CHARS_PER_TOKEN} heuristic)."
    )
    if not confirm_cost:
        print("Nothing was sent. Re-run with --confirm-cost to make these calls.")
        return 0
    judge = build_judge_llm(model, make_anthropic_client())
    metrics = _judge_metrics(keys, judge)
    offline_metrics = offline_metric_instances()

    def score(sample: Sample) -> Scores:
        offline = score_sample_offline(sample, offline_metrics)
        return {**offline, **asyncio.run(_judge_sample(sample, metrics))}

    results = build_results(files, score, set(OFFLINE_KEYS) | set(keys), mode="llm")
    write_artifacts(out_dir, results)
    return 0
