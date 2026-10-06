# Spike 0002: live Anthropic compatibility

| | |
|---|---|
| Date | 2026-10-06 (Phase 3) |
| SDK | `anthropic==1.11.0`, `max_retries=0` (retries are the adapter's) |
| Model | `claude-sonnet-5-5` (listed by `models.list`; effort `low`; no thinking) |
| Result | **Pass, after one adapter fix.** Claude 5.x rejects `thinking: {"type": "disabled"}`. The adapter now sends `{"type": "between_tools"}`, the model's no-thinking mode. The architecture is unchanged. Forced `tool_choice` returns 400, which the plan already assumed. |
| Executable record | `scripts/spike_anthropic.py` writes `docs/spikes/0002-anthropic-live.json` (non-secret results only) |

## Why

Phase 3 depends on six assumptions about the Anthropic API, listed in the module docstring of `backend/src/marketsignal/providers/llm/anthropic.py`. Phase 4 adds tool use and structured output. Each was checked against the live API with small, cheap requests before any evaluation ran.

## Verified behaviour

| # | Check | Finding |
|---|---|---|
| 1 | Configured model id is valid | `claude-sonnet-5-5` is in `models.list` |
| 2 | Authentication | The key loads from the gitignored `.env` as a `SecretStr`. Every authenticated call succeeded. |
| 3 | Streaming through our adapter | Answer contract followed (`### Answer`, `[E1]` cited). First text at **858 ms**, total 2,327 ms, `stop_reason=end_turn`. |
| 4a | Effort | `output_config.effort` accepts `low`, `medium`, `high`, `xhigh` and `max` |
| 4b | Thinking off | **Deviation.** `{"type": "disabled"}` returns 400: *"To turn thinking off on this model, send `{"type": "between_tools"}`."* With `between_tools` and no tools the response is one `text` block, with no thinking blocks. `llm_thinking="disabled"` now maps to `between_tools`. |
| 4c | Adaptive thinking | `{"type": "adaptive", "display": "omitted"}` with effort `medium` is accepted and streams no thinking text. First text at 3,214 ms, compared with 858 ms with thinking off. |
| 5a | Strict tool schema | `count_tokens` accepts a `strict: true` tool (382 input tokens). `tool_choice=auto` gives `stop_reason=tool_use`, with **parallel** `tool_use` blocks by default. |
| 5b | Forced tool choice | `tool_choice` `{"type":"tool"}` and `{"type":"any"}` return 400: *"type tool and any are not supported for this model"*. The thinking setting makes no difference. ARCHITECTURE_PLAN §19 already assumes `tool_choice=auto` plus a harness-local `finish_research` tool. Confirmed. |
| 5c | Structured output | `output_config.format = {type: json_schema, schema}` returns valid JSON that matches the schema |
| 6a | Timeout mapping | A 1 ms budget becomes our `LLMUnavailableError` (no hang, no crash) |
| 6b | Retry | A refused connection is retried **once** after jitter and then mapped to `LLMUnavailableError` (*"after 2 attempt(s) (APIConnectionError)"*, 820 ms). One `llm_retry` warning is logged, containing no secrets. |
| 6c | `stop_reason` | `max_tokens` is returned when the budget is tiny (16 tokens) |
| 7 | Usage | `message_start` and `message_delta` usage is parsed into `input_tokens`, `output_tokens`, `cache_read_input_tokens` and `cache_creation_input_tokens`. The SDK also returns `cache_creation`, `inference_geo`, `output_tokens_details` and `service_tier`, which we ignore. |
| 7b | Prompt cache | The static system prompt (658 tokens) is cached. The first call reports `cache_creation_input_tokens=658` and repeats report `cache_read_input_tokens=658`. |
| 8 | No secrets in logs | Everything (stdlib root and structlog) was captured at **DEBUG** during the spike: 31,734 bytes. Pattern scans for an Anthropic key shape, an `x-api-key` header value and a `Bearer` value all found **nothing**. The scan uses patterns only and never compares against the key value. |

## Changes made because of this spike

- `AnthropicProvider.thinking_param()` sends `{"type": "between_tools"}` for `llm_thinking="disabled"`. Test: `test_llm_providers.py`.
- Logging hardening, made before any live call (`telemetry/logging.py`):
  - the `httpx`, `httpcore` and `anthropic` loggers are pinned to WARNING;
  - redaction runs after tracebacks are formatted;
  - Anthropic key shapes, bearer values and JWTs are scrubbed by pattern.

## Facts recorded for Phase 4

- Use `tool_choice=auto` only, and expect parallel tool calls unless the prompt or harness limits them.
- With tools and `between_tools`, short updates between calls arrive as **thinking blocks**. The adapter must keep dropping every thinking delta and never stream or persist it.
- `output_config.format` json_schema works for planner and state outputs.

## Addendum (Phase 5): strict-mode grammar limits for the whole tool array

The first live analytics-v0 dev run failed on **every** research run: each agent step returned 400 and the run fell back to standard mode. The limits apply to the strict tool array **as a whole**, not to each tool:

| Limit | Live error (paraphrased) | Phase 5 strict array |
|---|---|---|
| ≤ 16 parameters with union types | *"Schemas contains too many parameters with union types (36 …, limit 16)"* | 36 (the analytics `Scalar` / optional fields) |
| ≤ 24 optional parameters | *"too many optional parameters (38 …, limit 24)"* (after making the unions non-nullable) | 38 |

Every per-tool schema test passed, because each tool alone is within both limits.

**Change.** The four analytics tools (`describe_dataset`, `aggregate`, `group_compare`, `filter_rows`) are offered with `strict: false` (`ToolEntry.strict`). The MCP HTTP client keeps the registry's flag. Retrieval tools and `finish_research` stay strict. The boundary does not move: every call still goes through server-side strict Pydantic validation in the governance pipeline (ADR-0006), so a malformed argument becomes `VALIDATION_ERROR` before the engine runs. Verified live: the model then called `describe_dataset` with a well-formed argument.

**Guard.** `test_strict_tool_array_stays_within_the_live_api_grammar_limits` counts union and optional parameters across every strict spec plus `finish_research`, and fails before the live API would.
