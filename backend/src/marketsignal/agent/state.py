"""The research agent's explicit state machine and bounds (plan §19; ADR-0007).

::

    INIT ─▶ AGENT_STEP ──tool_use──▶ EXECUTE ─▶ OBSERVE ─┐
      │         ▲                                         │
      │         └──────── bounds / deadline checks ◀──────┘
      └──────────────┬─────────────┘
                     ▼
                   DONE  (stop gathering; the lead's executor runs BUILD_PACK and the tail)

Every edge into ``DONE`` carries a :data:`StopReason`. Transitions are validated against
:data:`TRANSITIONS`; :class:`StateMachine` records the history so tests can assert the path.
:func:`check_bounds` is the pure pre-step bound check; nothing loops without a bound: each
``AGENT_STEP`` is one model call and ``step_limit`` caps them.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from typing import Any, Literal

from marketsignal.agent.progress import validated_args
from marketsignal.config import Settings

StopReason = Literal[
    "finish_research",
    "end_turn",
    "step_limit",
    "tool_limit",
    "token_limit",
    "context_limit",
    "time_limit",
    "repeat_call",
    "tool_errors",
    "pool_full",
    "planner_unavailable",
    "no_successful_search",
    "llm_unavailable",
]

# Stop reason -> run flag (plan §19 names). Normal exits and ``pool_full`` carry no flag.
STOP_FLAGS: dict[str, str] = {
    "step_limit": "AGENT_STEP_BUDGET_EXHAUSTED",
    "tool_limit": "AGENT_STEP_BUDGET_EXHAUSTED",  # plan §19: same flag as the step limit
    "token_limit": "AGENT_TOKEN_BUDGET_EXHAUSTED",
    "context_limit": "AGENT_CONTEXT_LIMIT",
    "time_limit": "GATHER_TIMEOUT",
    "repeat_call": "AGENT_REPEAT_CALL_STOPPED",
    "tool_errors": "TOOL_CIRCUIT_OPEN",
    "planner_unavailable": "PLANNER_UNAVAILABLE_FALLBACK",
    "no_successful_search": "PLANNER_NO_TOOL_FALLBACK",
    "llm_unavailable": "AGENT_LLM_UNAVAILABLE",
}


class AgentState(enum.StrEnum):
    INIT = "INIT"
    AGENT_STEP = "AGENT_STEP"
    EXECUTE = "EXECUTE"
    OBSERVE = "OBSERVE"
    DONE = "DONE"


TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.INIT: frozenset({AgentState.AGENT_STEP, AgentState.DONE}),
    AgentState.AGENT_STEP: frozenset({AgentState.EXECUTE, AgentState.DONE}),
    AgentState.EXECUTE: frozenset({AgentState.OBSERVE}),
    AgentState.OBSERVE: frozenset({AgentState.AGENT_STEP, AgentState.DONE}),
    AgentState.DONE: frozenset(),
}


class InvalidTransitionError(RuntimeError):
    """A programming error: the loop tried an edge the diagram does not have."""


class StateMachine:
    def __init__(self) -> None:
        self._state = AgentState.INIT
        self._history: list[AgentState] = [AgentState.INIT]
        self.stop_reason: StopReason | None = None

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def history(self) -> tuple[AgentState, ...]:
        return tuple(self._history)

    def advance(self, to: AgentState) -> None:
        if to is AgentState.DONE:
            raise InvalidTransitionError("use stop(reason) to enter DONE")
        self._go(to)

    def stop(self, reason: StopReason) -> None:
        self._go(AgentState.DONE)
        self.stop_reason = reason

    def _go(self, to: AgentState) -> None:
        if to not in TRANSITIONS[self._state]:
            raise InvalidTransitionError(f"{self._state} -> {to}")
        self._state = to
        self._history.append(to)


@dataclass(frozen=True, slots=True)
class AgentBounds:
    step_limit: int = 4
    max_tool_calls: int = 10
    max_consecutive_tool_errors: int = 3
    max_context_tokens: int = 40_000
    max_output_tokens_total: int = 12_000
    max_tokens: int = 4_096
    effort: str = "low"
    gather_budget_s: float = 35.0
    pool_max: int = 40
    tool_timeout_s: float = 8.0
    obs_max_tokens: int = 1_000
    repeat_stop_at: int = 3  # 3rd identical call (the 2nd repeat) stops gathering

    @classmethod
    def from_settings(cls, settings: Settings) -> AgentBounds:
        return cls(
            step_limit=settings.agent_step_limit,
            max_tool_calls=settings.agent_max_tool_calls,
            max_consecutive_tool_errors=settings.agent_max_consecutive_tool_errors,
            max_context_tokens=settings.agent_max_context_tokens,
            max_output_tokens_total=settings.agent_max_output_tokens_total,
            max_tokens=settings.agent_max_tokens,
            effort=settings.agent_effort,
            gather_budget_s=settings.agent_gather_budget_s,
            pool_max=settings.evidence_pool_max,
            tool_timeout_s=settings.tool_timeout_s,
            obs_max_tokens=settings.obs_max_tokens,
        )


@dataclass(frozen=True, slots=True)
class Progress:
    """Counters read by :func:`check_bounds` (a snapshot, never mutated)."""

    steps: int = 0
    tool_calls: int = 0
    consecutive_tool_errors: int = 0
    output_tokens: int = 0
    context_tokens: int = 0  # estimated size of the next request
    pool_size: int = 0
    remaining_s: float = float("inf")


def check_bounds(progress: Progress, bounds: AgentBounds) -> StopReason | None:
    """The bound that stops gathering before the next model call, or ``None`` to continue.
    Order is fixed so the reported reason is deterministic when several bounds are hit."""
    if progress.remaining_s <= 0:
        return "time_limit"
    if progress.consecutive_tool_errors >= bounds.max_consecutive_tool_errors:
        return "tool_errors"
    if progress.pool_size >= bounds.pool_max:
        return "pool_full"
    if progress.steps >= bounds.step_limit:
        return "step_limit"
    if progress.tool_calls >= bounds.max_tool_calls:
        return "tool_limit"
    if progress.output_tokens >= bounds.max_output_tokens_total:
        return "token_limit"
    if progress.context_tokens >= bounds.max_context_tokens:
        return "context_limit"
    return None


# Tool defaults the implementations apply when an argument is omitted (tools/impl/*): filled in
# so an explicit default and an omitted one produce the same repeat key.
_TOOL_DEFAULTS: dict[str, dict[str, Any]] = {
    "search_evidence": {"top_k": 8},
    "search_evidence_keyword": {"match": "all", "limit": 10},
}
_SET_LISTS = ("source_classes", "source_codes", "handles", "terms")


def _flat(value: Any) -> str:
    return " ".join(str(value).split())


def canonical_args(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """The arguments as the tool will see them, or ``None`` when they do not validate.

    Contract-validated (whitespace stripped, nulls dropped), tool defaults filled, internal
    whitespace collapsed, set-like lists sorted and de-duplicated (empty lists dropped, which the
    tools treat as "no filter"). Keyword terms are case-folded because keyword matching is
    case-insensitive; a ``phrase`` match keeps its term order.
    """
    args = validated_args(name, arguments)
    if args is None:
        return None
    out: dict[str, Any] = {**_TOOL_DEFAULTS.get(name, {}), **args}
    if "query" in out:
        out["query"] = _flat(out["query"])
    for key in _SET_LISTS:
        if key not in out:
            continue
        values = [_flat(v) for v in out[key]]
        if key == "terms":
            values = [v.casefold() for v in values]
        if key == "terms" and out.get("match") == "phrase":
            values = list(dict.fromkeys(values))
        else:
            values = sorted(set(values))
        if values:
            out[key] = values
        else:
            del out[key]
    return out


def canonical_call_key(name: str, arguments: dict[str, Any]) -> str:
    """(tool, canonical args) for repeated-call detection. Built from :func:`canonical_args`, so
    whitespace, explicit defaults, list order and keyword case do not make a new key; arguments
    that fail validation fall back to their raw JSON (sorted keys)."""
    canonical = canonical_args(name, arguments)
    payload = arguments if canonical is None else canonical
    return name + ":" + json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
