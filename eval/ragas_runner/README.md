# ms-ragas-runner

An isolated [ragas](https://github.com/explodinggradients/ragas) runner for MarketSignal. It has its
own `pyproject.toml` and `uv.lock` so that ragas and its langchain/openai/datasets dependency tree
never enter the backend lockfile, and it does not import the `marketsignal` package. Its only input
is a `marketsignal.ragas-samples` JSON file (format_version 1) produced by the backend exporter
(`python -m marketsignal.evaluation ragas-export ...`, written to `eval/reports/ragas-inputs/`).

ragas usage tracking is switched off: `ms_ragas_runner.telemetry` sets `RAGAS_DO_NOT_TRACK=true`
before ragas is first imported, and every ragas import in this package goes through that module.

## Setup

```bash
uv --directory eval/ragas_runner sync --locked
```

Supply-chain hygiene: everything resolves from releases published before
`exclude-newer = 2026-09-30` (see `pyproject.toml`); runtime pins are exact.

## Offline scoring (no model calls)

```bash
uv --directory eval/ragas_runner run ragas-eval offline \
  --samples ../reports/ragas-inputs/p4-research-test.samples.json \
  --out ../baselines/ragas/p4-research-test-nonllm
```

`--samples` is repeatable and paths are relative to `eval/ragas_runner` when using `--directory`.
The output directory must not exist; recorded artifacts are never overwritten. It receives:

- `results.json` (`marketsignal.ragas-results`, format_version 1): ragas version, git sha, input
  paths and sha256, the metric registry, and per run/configuration a summary per metric (mean,
  median, p25, p75, min, max, n, n_nan, ten-bin histogram on [0, 1]) plus per-item scores. A score
  that ragas cannot define (for example precision over an empty citation list) is `null` and
  counted in `n_nan`, never replaced by a number.
- `report.md`: what was measured, definitions, what was not measured and why, caveats.

Computed metrics (ragas legacy, non-LLM classes): ID-based context recall and precision over the
evidence pack and over the cited passages against gold handles, and text-similarity context recall
and precision (threshold 0.5) over the evidence pack.

## Model-judged metrics (gated, not run)

Faithfulness and answer relevancy (no reference needed) and context precision / context recall /
factual correctness against a reference (need authored reference answers, which the gold sets do not
have) are wired through `ragas.metrics.collections` with an explicit Anthropic judge and a local
fastembed embedding model. They are listed as not run in offline results.

```bash
MS_LIVE_LLM=1 ANTHROPIC_API_KEY=... uv --directory eval/ragas_runner run ragas-eval llm \
  --samples ... --out ... --i-understand-this-calls-the-model \
  [--model claude-sonnet-5-5] [--price-input-per-mtok 2] [--price-output-per-mtok 10] [--confirm-cost]
```

All three gates (flag, `MS_LIVE_LLM=1`, `ANTHROPIC_API_KEY`) are required. Without `--confirm-cost`
the command only prints a rough token and cost estimate (characters / 4 plus a fixed prompt
overhead per judge call, at the given USD-per-million-token prices) and exits without calling the
model.

## Development

```bash
uv --directory eval/ragas_runner run ruff check .
uv --directory eval/ragas_runner run ruff format --check .
uv --directory eval/ragas_runner run mypy
env -u ANTHROPIC_API_KEY -u MS_ANTHROPIC_API_KEY uv --directory eval/ragas_runner run pytest -q
```
