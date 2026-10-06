"""The append-only agent transcript (plan §19; ADR-0007).

Claude binds thinking blocks to the exact prefix, so nothing already sent is ever edited:
every assistant ``content`` (thinking/redacted_thinking incl. empty ones, text, tool_use) is
stored as a private deep copy and resent unchanged on every later step, and each step's
tool_result blocks follow in the model's tool_use block order. There is no trimming; when the
context bound is reached the agent stops gathering instead.

The transcript lives only for the duration of ``gather()``; it is never logged or persisted.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolResultBlock:
    tool_use_id: str
    content: str
    is_error: bool


class Transcript:
    def __init__(self, first_user_text: str) -> None:
        self._messages: list[dict[str, Any]] = [
            {"role": "user", "content": [{"type": "text", "text": first_user_text}]}
        ]

    @property
    def messages(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._messages)

    def __len__(self) -> int:
        return len(self._messages)

    def append_assistant(self, content: Sequence[dict[str, Any]]) -> None:
        if self._messages[-1]["role"] != "user":
            raise ValueError("assistant turn must follow a user turn")
        self._messages.append({"role": "assistant", "content": copy.deepcopy(list(content))})

    def append_tool_results(self, results: Sequence[ToolResultBlock]) -> None:
        if self._messages[-1]["role"] != "assistant" or not results:
            raise ValueError("tool results must follow an assistant turn")
        blocks = [
            {
                "type": "tool_result",
                "tool_use_id": r.tool_use_id,
                "content": r.content,
                **({"is_error": True} if r.is_error else {}),
            }
            for r in results
        ]
        self._messages.append({"role": "user", "content": blocks})
