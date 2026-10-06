"""One turn's tool calls: plan (budget + repeat policy), run concurrently, record in order.

Each executed call goes through ``ToolTransport.call`` with the run's credential, so every
call gets its own independent capability check. Calls run concurrently in a ``TaskGroup``
(cancellation cancels them all, nothing is left running); results are always reported in the
model's tool_use block order, so ordering never depends on completion timing.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from marketsignal.agent.progress import ToolStatus
from marketsignal.providers.llm.base import ToolUse
from marketsignal.tools.contracts import ToolCall, ToolError, ToolResult, ToolTransport

Decision = Literal["run", "deny_budget", "deny_repeat"]

BUDGET_DENIED = "Tool-call budget for this research run is exhausted; this call was not run."
REPEAT_DENIED = (
    "Identical call already made in this run; this call was not run. Change the arguments "
    "or finish the research."
)
TIMEOUT_MESSAGE = "The tool call exceeded its time limit."
INTERNAL_MESSAGE = "The tool call failed unexpectedly."


@dataclass(frozen=True, slots=True)
class PlannedCall:
    call: ToolCall
    decision: Decision


@dataclass(frozen=True, slots=True)
class CallRecord:
    call: ToolCall
    decision: Decision
    result: ToolResult

    @property
    def executed(self) -> bool:
        return self.decision == "run"

    @property
    def status(self) -> ToolStatus:
        if self.result.ok:
            return "ok"
        code = self.result.error.code if self.result.error else "INTERNAL"
        if code == "POLICY_DENIED":
            return "denied"
        return "timeout" if code == "TIMEOUT" else "error"


def failed(call: ToolCall, code: str, message: str, duration_ms: float = 0.0) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        name=call.name,
        ok=False,
        output=None,
        observation=message,
        error=ToolError(code=code, message=message),  # type: ignore[arg-type]
        duration_ms=duration_ms,
    )


def to_call(use: ToolUse, step: int, call_index: int) -> ToolCall:
    return ToolCall(
        call_id=use.id, name=use.name, arguments=dict(use.input), step=step, call_index=call_index
    )


async def run_one(
    transport: ToolTransport, call: ToolCall, *, credential: str, timeout_s: float
) -> ToolResult:
    """Never raises for tool failures (timeouts and unexpected errors become results);
    ``CancelledError`` propagates."""
    start = time.perf_counter()
    try:
        return await asyncio.wait_for(
            transport.call(call, credential=credential), max(timeout_s, 0.001)
        )
    except TimeoutError:
        return failed(call, "TIMEOUT", TIMEOUT_MESSAGE, (time.perf_counter() - start) * 1000)
    except Exception:  # the transport contract says it never raises; be defensive anyway
        return failed(call, "INTERNAL", INTERNAL_MESSAGE, (time.perf_counter() - start) * 1000)


async def execute(
    transport: ToolTransport,
    planned: list[PlannedCall],
    *,
    credential: str,
    timeout_s: Callable[[], float],
) -> list[CallRecord]:
    """Run the ``run`` calls concurrently; denied calls get POLICY_DENIED without running."""
    tasks: dict[int, asyncio.Task[ToolResult]] = {}
    async with asyncio.TaskGroup() as group:
        for i, p in enumerate(planned):
            if p.decision == "run":
                coro = run_one(transport, p.call, credential=credential, timeout_s=timeout_s())
                tasks[i] = group.create_task(coro)
    records: list[CallRecord] = []
    for i, p in enumerate(planned):
        if p.decision == "run":
            result = tasks[i].result()
        else:
            message = REPEAT_DENIED if p.decision == "deny_repeat" else BUDGET_DENIED
            result = failed(p.call, "POLICY_DENIED", message)
        records.append(CallRecord(call=p.call, decision=p.decision, result=result))
    return records
