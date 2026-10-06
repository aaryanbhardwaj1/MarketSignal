"""The one transport-agnostic governance registry (plan §17).

Each entry: input model, output model, implementation, result caps and the capability it
requires (its own name in ``claims.tools``). The timeout is ``settings.tool_timeout_s`` for
every tool. Both transports execute entries only through ``governance.ToolGovernor``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from marketsignal.tools.contracts import (
    INPUT_MODELS,
    OUTPUT_MODELS,
    TOOL_NAMES,
    ToolSpec,
)
from marketsignal.tools.env import ToolEnv
from marketsignal.tools.impl.evidence import get_evidence
from marketsignal.tools.impl.keyword import search_evidence_keyword
from marketsignal.tools.impl.search import search_evidence
from marketsignal.tools.impl.sources import MAX_SOURCES, list_sources
from marketsignal.tools.schema import to_anthropic_tool

Impl = Callable[[ToolEnv, Any], Awaitable[BaseModel]]
OUTPUT_MAX_CHARS = 32_000  # serialized runtime output, after the item cap


@dataclass(frozen=True)
class ToolEntry:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    impl: Impl
    items_key: str  # the output list that the item cap applies to
    max_items: int
    field_descriptions: dict[str, str] = field(default_factory=dict)

    @property
    def capability(self) -> str:
        return self.name

    def spec(self) -> ToolSpec:
        return to_anthropic_tool(
            self.name, self.description, self.input_model, self.field_descriptions
        )


_CLASSES = "Restrict to these source classes (null = all classes)."
_CODES = "Restrict to these source codes from list_sources (null = all sources)."

DEFAULT_ENTRIES: tuple[ToolEntry, ...] = (
    ToolEntry(
        name="get_evidence",
        description=(
            "Open up to 8 evidence handles returned by a search to read their fuller passage "
            "text. Unknown or malformed handles are reported per item."
        ),
        input_model=INPUT_MODELS["get_evidence"],
        output_model=OUTPUT_MODELS["get_evidence"],
        impl=get_evidence,
        items_key="items",
        max_items=8,
        field_descriptions={"handles": "Evidence handles exactly as returned by a search."},
    ),
    ToolEntry(
        name="list_sources",
        description=(
            "List the sources available in this workspace (code, title, class, type, version, "
            "passage count), optionally filtered by source class."
        ),
        input_model=INPUT_MODELS["list_sources"],
        output_model=OUTPUT_MODELS["list_sources"],
        impl=list_sources,
        items_key="sources",
        max_items=MAX_SOURCES,
        field_descriptions={"source_classes": _CLASSES},
    ),
    ToolEntry(
        name="search_evidence",
        description=(
            "Semantic + keyword hybrid search over the workspace's evidence. Returns the most "
            "relevant passages with handles to cite. Use for themes, questions and concepts."
        ),
        input_model=INPUT_MODELS["search_evidence"],
        output_model=OUTPUT_MODELS["search_evidence"],
        impl=search_evidence,
        items_key="hits",
        max_items=12,
        field_descriptions={
            "query": "What to search for, in natural language (2-400 characters).",
            "source_classes": _CLASSES,
            "source_codes": _CODES,
            "top_k": "Number of passages to return (1-12; null = 8).",
        },
    ),
    ToolEntry(
        name="search_evidence_keyword",
        description=(
            "Exact, case-insensitive matching for identifiers, names and quoted phrases, with "
            "exhaustive match counts per source. Use when exact strings matter (e.g. IDs)."
        ),
        input_model=INPUT_MODELS["search_evidence_keyword"],
        output_model=OUTPUT_MODELS["search_evidence_keyword"],
        impl=search_evidence_keyword,
        items_key="hits",
        max_items=20,
        field_descriptions={
            "terms": "1-6 exact terms (each 1-60 characters).",
            "match": "all = every term (default), any = at least one, phrase = terms in order.",
            "source_classes": _CLASSES,
            "source_codes": _CODES,
            "limit": "Number of passages to return (1-20; null = 10).",
        },
    ),
)


class ToolRegistry:
    def __init__(self, entries: tuple[ToolEntry, ...] = DEFAULT_ENTRIES) -> None:
        self._entries: Mapping[str, ToolEntry] = {e.name: e for e in entries}

    def get(self, name: str) -> ToolEntry | None:
        return self._entries.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def specs(self) -> list[ToolSpec]:
        """Model-facing specs, sorted by name (prompt-cache stability)."""
        return [self._entries[n].spec() for n in self.names()]

    def replace(self, entry: ToolEntry) -> ToolRegistry:
        """A copy with one entry swapped (tests: slow or oversized implementations)."""
        return ToolRegistry(tuple({**self._entries, entry.name: entry}.values()))


def default_registry() -> ToolRegistry:
    assert set(TOOL_NAMES) == {e.name for e in DEFAULT_ENTRIES}
    return ToolRegistry()
