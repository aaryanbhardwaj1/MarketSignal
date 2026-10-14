"""Definitions of every RAGAS metric this runner knows about, computed or not."""

from dataclasses import asdict, dataclass
from typing import Any, Literal

Family = Literal["ragas_non_llm", "ragas_llm_judge"]

NOT_RUN_NO_REFERENCE_ANSWERS = "no_reference_answers"
NOT_RUN_MODEL_CREDITS_UNAVAILABLE = "model_credits_unavailable"


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    family: Family
    ragas_class: str
    needs_llm: bool
    needs_reference_answer: bool
    inputs: tuple[str, ...]
    what_it_measures: str

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["inputs"] = list(self.inputs)
        return data


_PACK = "retrieved_context_ids (evidence pack handles)"
_CITED = "cited_context_ids (handles cited in the answer)"
_GOLD = "reference_context_ids (gold handles)"
_PACK_TEXT = "retrieved_contexts (evidence pack passage texts)"
_GOLD_TEXT = "reference_contexts (gold passage texts)"

METRICS: tuple[MetricDef, ...] = (
    MetricDef(
        "id_context_recall_pack",
        "Context recall (IDs, evidence pack)",
        "ragas_non_llm",
        "IDBasedContextRecall",
        False,
        False,
        (_PACK, _GOLD),
        "Share of distinct gold passage handles that appear in the evidence pack.",
    ),
    MetricDef(
        "id_context_precision_pack",
        "Context precision (IDs, evidence pack)",
        "ragas_non_llm",
        "IDBasedContextPrecision",
        False,
        False,
        (_PACK, _GOLD),
        "Share of distinct evidence-pack handles that are gold handles. Undefined for an empty "
        "pack.",
    ),
    MetricDef(
        "id_context_recall_cited",
        "Context recall (IDs, cited passages)",
        "ragas_non_llm",
        "IDBasedContextRecall",
        False,
        False,
        (_CITED, _GOLD),
        "Share of distinct gold passage handles that the answer actually cites.",
    ),
    MetricDef(
        "id_context_precision_cited",
        "Context precision (IDs, cited passages)",
        "ragas_non_llm",
        "IDBasedContextPrecision",
        False,
        False,
        (_CITED, _GOLD),
        "Share of distinct cited handles that are gold handles. Undefined when the answer cites "
        "nothing.",
    ),
    MetricDef(
        "nonllm_context_recall_pack",
        "Context recall (text similarity, evidence pack)",
        "ragas_non_llm",
        "NonLLMContextRecall",
        False,
        False,
        (_PACK_TEXT, _GOLD_TEXT),
        "Share of gold passages whose best normalised string similarity to any pack passage "
        "exceeds 0.5. A lexical heuristic, not a judgement of meaning.",
    ),
    MetricDef(
        "nonllm_context_precision_pack",
        "Context precision (text similarity, evidence pack)",
        "ragas_non_llm",
        "NonLLMContextPrecisionWithReference",
        False,
        False,
        (_PACK_TEXT, _GOLD_TEXT),
        "Rank-weighted average precision of pack passages, where a pack passage counts as "
        "relevant when its best string similarity to a gold passage is at least 0.5.",
    ),
    MetricDef(
        "faithfulness",
        "Faithfulness (model-judged)",
        "ragas_llm_judge",
        "Faithfulness",
        True,
        False,
        ("user_input", "response", _PACK_TEXT),
        "Share of the answer's claims that a judge model finds supported by the evidence pack.",
    ),
    MetricDef(
        "answer_relevancy",
        "Answer relevancy (model-judged)",
        "ragas_llm_judge",
        "AnswerRelevancy",
        True,
        False,
        ("user_input", "response"),
        "Mean embedding similarity between the question and questions a judge model generates "
        "from the answer; zero when the answer is non-committal.",
    ),
    MetricDef(
        "llm_context_precision_with_reference",
        "Context precision vs reference (model-judged)",
        "ragas_llm_judge",
        "ContextPrecisionWithReference",
        True,
        True,
        ("user_input", "reference", _PACK_TEXT),
        "Rank-weighted precision of pack passages judged useful for an authored reference answer.",
    ),
    MetricDef(
        "llm_context_recall",
        "Context recall vs reference (model-judged)",
        "ragas_llm_judge",
        "ContextRecall",
        True,
        True,
        ("user_input", "reference", _PACK_TEXT),
        "Share of an authored reference answer's statements that a judge model attributes to "
        "the evidence pack.",
    ),
    MetricDef(
        "factual_correctness",
        "Factual correctness vs reference (model-judged)",
        "ragas_llm_judge",
        "FactualCorrectness",
        True,
        True,
        ("response", "reference"),
        "Claim-level F1 between the answer and an authored reference answer, as judged by a model.",
    ),
)

METRICS_BY_KEY: dict[str, MetricDef] = {m.key: m for m in METRICS}
OFFLINE_KEYS: tuple[str, ...] = tuple(m.key for m in METRICS if not m.needs_llm)
LLM_KEYS: tuple[str, ...] = tuple(m.key for m in METRICS if m.needs_llm)


def not_run_reason(metric: MetricDef) -> str:
    """Why an LLM-judged metric was not computed in a run that did not call the model."""
    if metric.needs_reference_answer:
        return NOT_RUN_NO_REFERENCE_ANSWERS
    return NOT_RUN_MODEL_CREDITS_UNAVAILABLE


def registry_json() -> list[dict[str, Any]]:
    return [m.to_json() for m in METRICS]
