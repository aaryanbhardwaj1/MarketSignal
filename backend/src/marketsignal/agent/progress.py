"""Deterministic progress events for research mode (plan §21; the Phase 4 SSE contract).

Events are built only from validated tool arguments and tool status, never from model prose
or thinking. Model-supplied text (queries, terms) appears only as quoted plain text, collapsed
to one line and truncated to :data:`QUOTE_MAX_CHARS`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ValidationError

from marketsignal.tools.contracts import INPUT_MODELS, TOOL_NAMES

QUOTE_MAX_CHARS = 80
ToolKind = Literal["search", "keyword", "lookup", "catalog"]
ToolStatus = Literal["ok", "error", "denied", "timeout"]

KINDS: dict[str, ToolKind] = {
    "search_evidence": "search",
    "search_evidence_keyword": "keyword",
    "get_evidence": "lookup",
    "list_sources": "catalog",
}

STATUS_PLANNING = {"phase": "planning", "message": "Planning the research"}
STATUS_SEARCHING = {"phase": "searching", "message": "Searching workspace evidence"}


def tool_label(name: str) -> str:
    """The tool name as shown to clients: a known tool name, never model text."""
    return name if name in TOOL_NAMES else "unknown"


def quote(text: str) -> str:
    flat = " ".join(str(text).replace('"', "'").split())
    if len(flat) > QUOTE_MAX_CHARS:
        flat = flat[: QUOTE_MAX_CHARS - 1].rstrip() + "…"
    return f'"{flat}"'


def _classes(values: list[Any] | None) -> str:
    names = [str(getattr(v, "value", v)) for v in values or []]
    if not names:
        return "all"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def validated_args(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """The arguments after contract validation (JSON-dumped, nulls dropped), or ``None``."""
    model = INPUT_MODELS.get(name)
    if model is None:
        return None
    try:
        return model.model_validate(arguments).model_dump(mode="json", exclude_none=True)
    except ValidationError:
        return None


def summarize(name: str, arguments: dict[str, Any]) -> str:
    """A fixed-template, human-readable summary of one call."""
    args = validated_args(name, arguments)
    if args is None:
        return "Running a tool call with invalid arguments"
    if name == "search_evidence":
        return (
            f"Searching {_classes(args.get('source_classes'))} evidence for {quote(args['query'])}"
        )
    if name == "search_evidence_keyword":
        terms = ", ".join(quote(t) for t in args["terms"])
        return f"Checking exact identifiers: {terms}"
    if name == "get_evidence":
        count = len(args["handles"])
        return f"Opening {count} evidence item{'s' if count != 1 else ''}"
    return f"Listing {_classes(args.get('source_classes'))} sources"


def tool_started(
    step: int, call_index: int, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    return {
        "step": step,
        "call_index": call_index,
        "tool": tool_label(name),
        "kind": KINDS.get(name, "lookup"),
        "summary": summarize(name, arguments),
    }


def tool_completed(
    step: int,
    call_index: int,
    name: str,
    status: ToolStatus,
    result_count: int,
    duration_ms: int,
    error_code: str | None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "step": step,
        "call_index": call_index,
        "tool": tool_label(name),
        "status": status,
        "result_count": result_count,
        "duration_ms": duration_ms,
    }
    if error_code is not None:
        event["error_code"] = error_code
    return event
