"""Shared fakes for the research-agent tests (no tests here): a scripted ToolTransport,
hit/result builders, a manual clock and a recording progress sink."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from marketsignal.agent.runtime import AgentContext, ResearchAgent
from marketsignal.agent.state import AgentBounds
from marketsignal.db.scope import WorkspaceScope
from marketsignal.providers.llm.base import LLMUsage
from marketsignal.providers.llm.fake import (
    FakeAgentLLM,
    ScriptedTurn,
    thinking_block,
    tool_use_block,
)
from marketsignal.tools.contracts import ToolCall, ToolError, ToolResult, ToolSpec, Transport

WS = "acme"
CREDENTIAL = "cap-token-synthetic"  # obviously synthetic, never a real token
SECRET_THOUGHT = "PRIVATE-REASONING-CANARY"
SECRET_PROSE = "AGENT-PROSE-CANARY"


def hit(n: int, *, rank: int = 1, code: str = "SRC", cls: str = "customer") -> dict[str, Any]:
    return {
        "handle": f"{WS}/{code}@v1:S{n}.B1",
        "source_code": code,
        "source_title": "Title",
        "source_class": cls,
        "locator_label": f"S{n}",
        "snippet": f"snippet {n}",
        "anchor_child_id": str(uuid.UUID(int=n)),
        "anchor_char_start": 0,
        "anchor_char_end": 10,
        "fused_rank": rank,
    }


def ok(call: ToolCall, output: dict[str, Any], observation: str = "obs") -> ToolResult:
    return ToolResult(call.call_id, call.name, True, output, observation)


def err(call: ToolCall, code: str = "UNAVAILABLE") -> ToolResult:
    return ToolResult(call.call_id, call.name, False, None, "failed", ToolError(code, "failed"))  # type: ignore[arg-type]


def search_ok(call: ToolCall) -> ToolResult:
    """Default handler: each distinct query returns two hits derived from the query text."""
    base = sum(map(ord, str(call.arguments.get("query") or call.arguments)))
    hits = [hit(base % 1000 + 1, rank=1), hit(base % 1000 + 2, rank=2)]
    return ok(call, {"hits": hits, "classes_found": {"customer": 2}, "warnings": []})


Handler = Callable[[ToolCall], ToolResult | Awaitable[ToolResult]]


@dataclass
class FakeTransport:
    handler: Handler = search_ok
    delay_s: float = 0.0
    calls: list[tuple[ToolCall, str]] = field(default_factory=list)
    running: int = 0
    max_running: int = 0
    cancelled: int = 0

    @property
    def transport(self) -> Transport:
        return "inprocess"

    async def list_tools(self) -> list[ToolSpec]:
        schema = {"type": "object", "properties": {}, "additionalProperties": False}
        return [
            ToolSpec(n, f"{n} tool", schema)
            for n in ("search_evidence", "list_sources", "get_evidence", "search_evidence_keyword")
        ]

    async def call(self, call: ToolCall, *, credential: str) -> ToolResult:
        self.calls.append((call, credential))
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            result = self.handler(call)
            if isinstance(result, Awaitable):
                result = await result
            return result
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.running -= 1


class ManualClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


@dataclass
class Sink:
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def __call__(self, name: str, data: dict[str, Any]) -> None:
        self.events.append((name, data))

    def named(self, name: str) -> list[dict[str, Any]]:
        return [d for n, d in self.events if n == name]


def search(call_id: str, query: str, **extra: Any) -> dict[str, Any]:
    return tool_use_block(call_id, "search_evidence", {"query": query, **extra})


def finish(
    call_id: str = "fin", sufficient: bool = True, gaps: Sequence[str] = ()
) -> dict[str, Any]:
    return tool_use_block(
        call_id, "finish_research", {"sufficient": sufficient, "gaps": list(gaps)}
    )


def turn(*blocks: dict[str, Any], thought: str | None = SECRET_THOUGHT, **kw: Any) -> ScriptedTurn:
    content = ((thinking_block(thought),) if thought is not None else ()) + tuple(blocks)
    return ScriptedTurn(content=content, **kw)


def usage(inp: int = 100, out: int = 50) -> LLMUsage:
    return LLMUsage(input_tokens=inp, output_tokens=out)


def make_ctx(sink: Sink | None = None, *, deadline: float = 10_000.0) -> AgentContext:
    return AgentContext(
        run_id=uuid.UUID(int=7),
        scope=WorkspaceScope(workspace_id=uuid.UUID(int=1), workspace_code=WS),
        question="What do Gen Z buyers say about fit?",
        persona="analyst",
        conversation_summary="",
        recent_questions=(),
        credential=CREDENTIAL,
        deadline=deadline,
        emit=sink or Sink(),
    )


def make_agent(
    llm: FakeAgentLLM,
    transport: FakeTransport | None = None,
    *,
    clock: ManualClock | None = None,
    **bounds: Any,
) -> tuple[ResearchAgent, FakeTransport]:
    t = transport or FakeTransport()
    agent = ResearchAgent(
        llm=llm, transport=t, bounds=AgentBounds(**bounds), clock=clock or ManualClock()
    )
    return agent, t
