"""Live Anthropic compatibility spike (deferred from Phase 0; Phase 3 entry check).

Verifies, against the real API, the surface MarketSignal depends on and writes only non-secret
results to docs/spikes/0002-anthropic-live.json (the key is read through Settings as a
SecretStr and is never printed, logged or written). Small, cheap calls only.

    uv --directory backend run python ../scripts/spike_anthropic.py
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import anthropic

from marketsignal.config import get_settings
from marketsignal.generation.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from marketsignal.providers.llm.anthropic import AnthropicProvider
from marketsignal.providers.llm.base import LLMRequest, LLMStop, LLMText, LLMUnavailableError

OUT = Path(__file__).resolve().parents[1] / "docs" / "spikes" / "0002-anthropic-live.json"
USER = (
    '<evidence_items>\n<evidence alias="E1" class="customer" source="Survey" '
    'locator="Row 2">27 percent of Gen Z buyers name fit inconsistency as their top '
    "frustration.</evidence>\n</evidence_items>\n<question>What share of Gen Z buyers name fit "
    "inconsistency as their top frustration?</question>"
)


def _err(exc: BaseException) -> dict[str, Any]:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    kind = body.get("error", {}).get("type") if isinstance(body, dict) else None
    return {"error_class": type(exc).__name__, "status": status, "error_type": kind}


async def stream_once(
    provider: AnthropicProvider, *, max_tokens: int, effort: str
) -> dict[str, Any]:
    request = LLMRequest(
        system=SYSTEM_PROMPT,
        messages=({"role": "user", "content": USER},),
        max_tokens=max_tokens,
        effort=effort,
        timeout_s=60,
    )
    t0 = time.monotonic()
    first = None
    text = ""
    stop: LLMStop | None = None
    async for chunk in provider.stream(request):
        if isinstance(chunk, LLMText):
            first = first or round((time.monotonic() - t0) * 1000)
            text += chunk.text
        else:
            stop = chunk
    return {
        "first_token_ms": first,
        "total_ms": round((time.monotonic() - t0) * 1000),
        "stop_reason": stop.stop_reason if stop else None,
        "usage": stop.usage.as_dict() if stop else None,
        "model": stop.model if stop else None,
        "chars": len(text),
        "has_alias_citation": "[E1]" in text,
        "has_answer_heading": "### Answer" in text,
        "sample": text[:400],
    }


async def main() -> int:
    settings = get_settings()
    if settings.anthropic_api_key is None:
        print("ANTHROPIC_API_KEY is not configured")
        return 2
    key = settings.anthropic_api_key.get_secret_value()
    client = anthropic.AsyncAnthropic(api_key=key, max_retries=0)
    results: dict[str, Any] = {
        "sdk": anthropic.__version__,
        "model": settings.llm_model,
        "prompt_version": PROMPT_VERSION,
    }

    # 1. Configured model ids are served.
    try:
        listed = [m.id async for m in client.models.list(limit=100)]
        results["models_listed"] = sorted(m for m in listed if "claude" in m)[:40]
        results["configured_model_listed"] = settings.llm_model in listed
    except Exception as exc:
        results["models_list_error"] = _err(exc)

    # 2. Streaming through our adapter: effort low, thinking disabled (Phase 3 synthesis).
    disabled = AnthropicProvider(model=settings.llm_model, api_key=settings.anthropic_api_key)
    results["stream_effort_low_thinking_disabled"] = await stream_once(
        disabled, max_tokens=800, effort="low"
    )
    # 3. Second identical call: prompt-cache behaviour of the static system prompt.
    results["stream_repeat_for_cache"] = await stream_once(disabled, max_tokens=800, effort="low")
    # 4. Adaptive thinking with display omitted: nothing but answer text may reach our stream.
    adaptive = AnthropicProvider(
        model=settings.llm_model, api_key=settings.anthropic_api_key, thinking="adaptive"
    )
    try:
        results["stream_effort_medium_thinking_adaptive"] = await stream_once(
            adaptive, max_tokens=2000, effort="medium"
        )
    except LLMUnavailableError as exc:
        results["stream_thinking_adaptive_error"] = str(exc)
    # 5. stop_reason max_tokens.
    results["stop_reason_on_tiny_max_tokens"] = (
        await stream_once(disabled, max_tokens=16, effort="low")
    )["stop_reason"]
    # 6. Every documented effort value is accepted.
    efforts: dict[str, Any] = {}
    for effort in ("low", "medium", "high", "xhigh", "max"):
        try:
            message = await client.messages.create(
                model=settings.llm_model,
                max_tokens=64,
                messages=[{"role": "user", "content": "Reply with the single word: ok"}],
                output_config={"effort": effort},
            )
            efforts[effort] = {"ok": True, "stop_reason": message.stop_reason}
        except Exception as exc:
            efforts[effort] = {"ok": False, **_err(exc)}
    results["effort_values"] = efforts
    # 7. Timeout mapping (SDK retries off): an impossible deadline must become our
    #    LLMUnavailableError, never a hang or a crash.
    try:
        req = LLMRequest(
            system=SYSTEM_PROMPT,
            messages=({"role": "user", "content": USER},),
            max_tokens=200,
            effort="low",
            timeout_s=0.001,
        )
        async for _ in disabled.stream(req):
            pass
        results["timeout_mapping"] = "no error (unexpected)"
    except LLMUnavailableError:
        results["timeout_mapping"] = "LLMUnavailableError"
    # 8. Strict tool schema with count_tokens, and forced tool_choice (Phase 4 relevance).
    tool = {
        "name": "search_evidence",
        "description": "Search workspace evidence.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    }
    try:
        counted = await client.messages.count_tokens(
            model=settings.llm_model,
            messages=[{"role": "user", "content": "find fit complaints"}],
            tools=[tool],  # type: ignore[list-item]
        )
        results["count_tokens_strict_tool"] = {"ok": True, "input_tokens": counted.input_tokens}
    except Exception as exc:
        results["count_tokens_strict_tool"] = {"ok": False, **_err(exc)}
    for choice in ({"type": "auto"}, {"type": "tool", "name": "search_evidence"}):
        try:
            message = await client.messages.create(
                model=settings.llm_model,
                max_tokens=128,
                messages=[{"role": "user", "content": "find fit complaints"}],
                tools=[tool],  # type: ignore[list-item]
                tool_choice=choice,  # type: ignore[arg-type]
            )
            results[f"tool_choice_{choice['type']}"] = {
                "ok": True,
                "stop_reason": message.stop_reason,
                "blocks": [b.type for b in message.content],
            }
        except Exception as exc:
            results[f"tool_choice_{choice['type']}"] = {"ok": False, **_err(exc)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1, default=str) + "\n")
    print(
        json.dumps(
            {k: v for k, v in results.items() if k != "models_listed"}, indent=1, default=str
        )[:4000]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
