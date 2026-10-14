"""``generate_and_verify`` logs only the provider exception's type, never its text."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest

from marketsignal.providers.llm.base import LLMUnavailableError
from marketsignal.runs import synthesis
from marketsignal.runs.flags import LLM_SYNTHESIS_UNAVAILABLE
from marketsignal.runs.state import _RunState


class _Recorder:
    """Stands in for the module logger: structlog caches loggers on first use, so
    ``capture_logs`` misses events once another test has configured logging."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def warning(self, event: str, **fields: Any) -> None:
        self.entries.append({"event": event, **fields})

    def __getattr__(self, _name: str) -> Any:
        return lambda event, **fields: self.entries.append({"event": event, **fields})


class _Writer:
    async def emit(self, _event: str, _data: dict[str, Any]) -> None:
        return None


async def test_llm_unavailable_logs_error_type_not_provider_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        raise LLMUnavailableError("provider said: account 42 over quota, key sk-ant-xyz")

    monkeypatch.setattr(synthesis, "generate", unavailable)
    recorder = _Recorder()
    monkeypatch.setattr(synthesis, "log", recorder)
    state = _RunState()
    answer, _, code = await synthesis.generate_and_verify(
        cast(Any, None),
        cast(Any, None),
        cast(Any, SimpleNamespace(run_id=uuid.UUID(int=7))),
        cast(Any, _Writer()),
        state,
        cast(Any, None),
        "summary",
        (),
        0.0,
    )
    assert answer is None
    assert code == LLM_SYNTHESIS_UNAVAILABLE
    logs = recorder.entries
    [entry] = [e for e in logs if e["event"] == "llm_unavailable"]
    assert entry["error_type"] == "LLMUnavailableError"
    assert "reason" not in entry
    assert "over quota" not in repr(logs)
