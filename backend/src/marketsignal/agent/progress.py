"""Deterministic progress events for research mode (plan §21; the Phase 4 SSE contract).

Events are built only from validated tool arguments and tool status, never from model prose
or thinking. Model-supplied text (queries, terms, filter values, compared levels) appears only
as quoted plain text, collapsed to one line and truncated to :data:`QUOTE_MAX_CHARS`; column
names appear unquoted but printable, quote-free and truncated to :data:`NAME_MAX_CHARS`; a
dataset id appears as is only when it is well-formed (``CODE:N``), otherwise quoted.

Analytics templates (kind ``analytics``): "Describing datasets", "Describing dataset
SURVEY-2026:1", "Computing mean(nps) by region on SURVEY-2026:1", 'Comparing mean(nps) between
"Gen Z" and "Millennial" on SURVEY-2026:1', "Listing up to 5 matching rows on SURVEY-2026:1".
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ValidationError

from marketsignal.analytics.schema import parse_dataset_id
from marketsignal.tools.contracts import INPUT_MODELS, TOOL_NAMES

QUOTE_MAX_CHARS = 80
NAME_MAX_CHARS = 40  # a model-supplied column name shown unquoted
ToolKind = Literal["search", "keyword", "lookup", "catalog", "analytics"]
ToolStatus = Literal["ok", "error", "denied", "timeout"]

KINDS: dict[str, ToolKind] = {
    "search_evidence": "search",
    "search_evidence_keyword": "keyword",
    "get_evidence": "lookup",
    "list_sources": "catalog",
    "describe_dataset": "analytics",
    "aggregate": "analytics",
    "group_compare": "analytics",
    "filter_rows": "analytics",
}
_SYMBOLS = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
_SHOWN_VALUES = 3

STATUS_PLANNING = {"phase": "planning", "message": "Planning the research"}
STATUS_SEARCHING = {"phase": "searching", "message": "Searching workspace evidence"}


def tool_label(name: str) -> str:
    """The tool name as shown to clients: a known tool name, never model text."""
    return name if name in TOOL_NAMES else "unknown"


def printable(text: str) -> str:
    """``text`` with every non-printable character (controls incl. NUL, format characters such
    as zero-width spaces, lone surrogates, private-use/unassigned code points) replaced by a
    space. A NUL or lone surrogate cannot be stored in jsonb (it would fail the event write and
    echo the text into database logs), so model text passes through here before it reaches a
    progress event, the agent trace or a log."""
    return "".join(c if c.isprintable() else " " for c in str(text))


def scrub(value: Any) -> Any:
    """:func:`printable` applied to every string (keys included) in a JSON-like value."""
    if isinstance(value, str):
        return printable(value)
    if isinstance(value, dict):
        return {printable(str(k)): scrub(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    return value


def quote(text: str) -> str:
    flat = " ".join(printable(text).replace('"', "'").split())
    if len(flat) > QUOTE_MAX_CHARS:
        flat = flat[: QUOTE_MAX_CHARS - 1].rstrip() + "…"
    return f'"{flat}"'


def _classes(values: list[Any] | None) -> str:
    names = [str(getattr(v, "value", v)) for v in values or []]
    if not names:
        return "all"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def validated_args(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """The arguments after contract validation (JSON-dumped, nulls dropped, non-printable
    characters replaced by :func:`scrub`), or ``None``."""
    model = INPUT_MODELS.get(name)
    if model is None:
        return None
    try:
        dumped = model.model_validate(arguments).model_dump(mode="json", exclude_none=True)
    except ValidationError:
        return None
    return dict(scrub(dumped))


def _name(text: Any) -> str:
    """A model-supplied column name: one printable line without quotes, bounded."""
    flat = " ".join(printable(str(text)).replace('"', "'").split())
    return flat if len(flat) <= NAME_MAX_CHARS else flat[: NAME_MAX_CHARS - 1].rstrip() + "…"


def _dataset(value: Any) -> str:
    """A well-formed dataset id as is (``CODE:N`` has no spaces or quotes); anything else
    quoted."""
    text = str(value)
    return text if parse_dataset_id(text) is not None else quote(text)


def _condition(cond: dict[str, Any]) -> str:
    col, op = _name(cond.get("column", "")), str(cond.get("op", ""))
    if op in _SYMBOLS:
        return f"{col} {_SYMBOLS[op]} {quote(str(cond.get('value')))}"
    if op in ("is_null", "not_null"):
        return f"{col} {'is null' if op == 'is_null' else 'is not null'}"
    values = [quote(str(v)) for v in (cond.get("values") or [])]
    shown = ", ".join(values[:_SHOWN_VALUES]) + (", …" if len(values) > _SHOWN_VALUES else "")
    return f"{col} {op.replace('_', ' ')} [{shown}]"


def _metric(metric: dict[str, Any]) -> str:
    fn = str(metric.get("fn", ""))
    if metric.get("condition"):
        return f"{fn}({_condition(metric['condition'])})"
    return f"{fn}({_name(metric['column'])})" if metric.get("column") else fn


def _analytics(name: str, args: dict[str, Any]) -> str:
    if name == "describe_dataset":
        ds = args.get("dataset")
        return f"Describing dataset {_dataset(ds)}" if ds else "Describing datasets"
    on = f" on {_dataset(args['dataset'])}"
    if name == "aggregate":
        metrics = ", ".join(_metric(m) for m in args["metrics"])
        groups = ", ".join(_name(g) for g in args.get("group_by") or [])
        return f"Computing {metrics}{' by ' + groups if groups else ''}{on}"
    if name == "group_compare":
        a, b = quote(str(args["group_a"])), quote(str(args["group_b"]))
        return f"Comparing {_metric(args['metric'])} between {a} and {b}{on}"
    limit = args.get("limit")
    return f"Listing up to {limit} matching rows{on}" if limit else f"Listing matching rows{on}"


def summarize(name: str, arguments: dict[str, Any]) -> str:
    """A fixed-template, human-readable summary of one call."""
    args = validated_args(name, arguments)
    if args is None:
        return "Running a tool call with invalid arguments"
    if KINDS.get(name) == "analytics":
        return _analytics(name, args)
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
