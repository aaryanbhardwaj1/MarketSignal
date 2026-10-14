"""The LLM path is wired and gated; these tests never reach a model."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from ms_ragas_runner import llm
from ms_ragas_runner.samples import load_samples

ACK = True
OPEN_ENV = {"MS_LIVE_LLM": "1", "ANTHROPIC_API_KEY": "sk-test-not-a-real-key"}


class _ClientConstructedError(AssertionError):
    pass


@pytest.fixture
def forbid_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise _ClientConstructedError("an Anthropic client must not be constructed")

    monkeypatch.setattr(llm, "AsyncAnthropic", _raise)


@pytest.mark.parametrize(
    ("acknowledged", "environ", "missing"),
    [
        (False, OPEN_ENV, "--i-understand-this-calls-the-model"),
        (ACK, {"ANTHROPIC_API_KEY": "sk-test"}, "MS_LIVE_LLM=1"),
        (ACK, {"MS_LIVE_LLM": "true", "ANTHROPIC_API_KEY": "sk-test"}, "MS_LIVE_LLM=1"),
        (ACK, {"MS_LIVE_LLM": "1"}, "ANTHROPIC_API_KEY"),
        (ACK, {"MS_LIVE_LLM": "1", "ANTHROPIC_API_KEY": "  "}, "ANTHROPIC_API_KEY"),
        (False, {}, "MS_LIVE_LLM=1"),
    ],
)
def test_every_gate_refuses_without_constructing_a_client(
    forbid_client: None,
    tmp_path: Path,
    samples_file: Path,
    acknowledged: bool,
    environ: dict[str, str],
    missing: str,
) -> None:
    with pytest.raises(llm.GateError, match=missing):
        llm.run_llm(
            [samples_file],
            tmp_path / "out",
            acknowledged=acknowledged,
            confirm_cost=True,
            environ=environ,
        )
    assert not (tmp_path / "out").exists()


def test_gate_message_never_echoes_the_key() -> None:
    with pytest.raises(llm.GateError) as info:
        llm.check_gates(acknowledged=False, environ={"ANTHROPIC_API_KEY": "sk-secret-value"})
    assert "sk-secret-value" not in str(info.value)


def test_open_gates_without_confirm_cost_only_print_estimate(
    forbid_client: None, tmp_path: Path, samples_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = llm.run_llm(
        [samples_file], tmp_path / "out", acknowledged=True, confirm_cost=False, environ=OPEN_ENV
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "Estimated" in out
    assert "--confirm-cost" in out
    assert not (tmp_path / "out").exists()


def test_cost_estimate_arithmetic(samples_file: Path) -> None:
    files = [load_samples(samples_file)]
    estimate = llm.estimate_cost(
        files,
        ("faithfulness", "answer_relevancy"),
        price_input_per_mtok=2.0,
        price_output_per_mtok=10.0,
    )
    # 2 samples x (2 faithfulness calls + 3 answer-relevancy calls)
    assert estimate.calls == 10
    assert estimate.output_tokens == 10 * llm.OUTPUT_TOKENS_PER_CALL
    assert estimate.input_tokens > 10 * llm.PROMPT_OVERHEAD_TOKENS
    expected = estimate.input_tokens * 2.0 / 1e6 + estimate.output_tokens * 10.0 / 1e6
    assert estimate.usd == pytest.approx(expected)


def test_reference_metrics_are_skipped_without_reference_answers(samples_file: Path) -> None:
    files = [load_samples(samples_file)]
    assert llm.runnable_llm_keys(files) == ("faithfulness", "answer_relevancy")


def test_judge_llm_drops_top_p_with_a_dummy_key() -> None:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key="test")  # no request is made by construction
    judge = llm.build_judge_llm("claude-sonnet-5-5", client)
    assert "top_p" not in judge.model_args
    assert "temperature" in judge.model_args


def test_fastembed_adapter_uses_injected_model() -> None:
    class _FakeModel:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def embed(self, documents: list[str]) -> list[list[float]]:
            self.calls.append(list(documents))
            return [[float(len(d)), 1.0] for d in documents]

    fake = _FakeModel()
    adapter = llm.FastEmbedEmbedding(model_factory=lambda _name: fake)
    assert adapter.embed_text("abc") == [3.0, 1.0]
    assert asyncio.run(adapter.aembed_text("abcd")) == [4.0, 1.0]
    assert adapter.embed_texts(["a", "bb"]) == [[1.0, 1.0], [2.0, 1.0]]
    assert isinstance(adapter, llm.telemetry.base_embedding_class())


def test_llm_module_never_uses_legacy_evaluate() -> None:
    source = Path(llm.__file__).read_text(encoding="utf-8")
    assert "evaluate(" not in source
    assert "import ragas" not in source
    assert "from ragas" not in source


def test_judge_metrics_construct_and_kwargs_match_signatures(samples_file: Path) -> None:
    import inspect

    from anthropic import AsyncAnthropic

    judge = llm.build_judge_llm("claude-sonnet-5-5", AsyncAnthropic(api_key="test"))
    metrics = llm._judge_metrics(llm.LLM_KEYS, judge)  # construction only; nothing is scored
    sample = load_samples(samples_file).samples[0]
    for key, metric in metrics.items():
        params = set(inspect.signature(metric.ascore).parameters)
        assert set(llm._metric_kwargs(key, sample)) == params, key
