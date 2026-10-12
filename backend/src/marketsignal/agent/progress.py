"""Deterministic progress events for research mode (plan §21; the Phase 4 SSE contract).

Events are built only from validated tool arguments and tool status, never from model prose
or thinking. Summaries are shown verbatim on the Ask page, so they use plain business words:
model-supplied text (queries, terms, filter values, compared levels) appears only as quoted
plain text, collapsed to one line and truncated to :data:`QUOTE_MAX_CHARS`; column names appear
unquoted but printable, quote-free, de-snake-cased and truncated to :data:`NAME_MAX_CHARS`;
dataset ids, function-call syntax and tool names never appear.

Analytics templates (kind ``analytics``): "Reviewing datasets", "Reviewing a dataset's
columns", "Computing the average NPS, by region, in a workspace dataset", 'Comparing the
average NPS between "Gen Z" and "Millennial" in a workspace dataset', "Listing up to 5
matching records in a workspace dataset".
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ValidationError

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
_OP_WORDS = {
    "eq": "is",
    "ne": "is not",
    "gt": "is above",
    "gte": "is at least",
    "lt": "is below",
    "lte": "is at most",
}
_FN_WORDS = {
    "count_distinct": "number of distinct",
    "sum": "total",
    "mean": "average",
    "median": "median",
    "min": "lowest",
    "max": "highest",
}
_ACRONYMS = frozenset({"nps", "csat", "aov", "sku", "roi", "ltv", "cac", "arr", "mrr", "id"})
_IN_DATASET = "in a workspace dataset"
INVALID_STEP = "A research step could not run"
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


def _column(text: Any) -> str:
    """A column name in plain words (``age_group`` -> ``age group``, ``nps`` -> ``NPS``)."""
    words = _name(str(text).replace("_", " ")).split(" ")
    return " ".join(w.upper() if w.lower() in _ACRONYMS else w for w in words)


def _condition(cond: dict[str, Any]) -> str:
    col, op = _column(cond.get("column", "")), str(cond.get("op", ""))
    if op in _OP_WORDS:
        return f"{col} {_OP_WORDS[op]} {quote(str(cond.get('value')))}"
    if op in ("is_null", "not_null"):
        return f"{col} {'is blank' if op == 'is_null' else 'is not blank'}"
    values = [quote(str(v)) for v in (cond.get("values") or [])]
    if op == "between" and len(values) == 2:
        return f"{col} is between {values[0]} and {values[1]}"
    shown = ", ".join(values[:_SHOWN_VALUES]) + (", …" if len(values) > _SHOWN_VALUES else "")
    return f"{col} {'is not one of' if op == 'not_in' else 'is one of'} {shown}"


def _metric(metric: dict[str, Any]) -> str:
    fn = str(metric.get("fn", ""))
    if metric.get("condition"):
        return f"the share where {_condition(metric['condition'])}"
    if fn == "count":
        return "the number of records"
    word = _FN_WORDS.get(fn, fn)
    return f"the {word} {_column(metric['column'])}" if metric.get("column") else f"the {word}"


def _joined(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _analytics(name: str, args: dict[str, Any]) -> str:
    if name == "describe_dataset":
        return "Reviewing a dataset's columns" if args.get("dataset") else "Reviewing datasets"
    if name == "aggregate":
        metrics = _joined([_metric(m) for m in args["metrics"]])
        groups = [_column(g) for g in args.get("group_by") or []]
        by = f", by {_joined(groups)}," if groups else ""
        return f"Computing {metrics}{by} {_IN_DATASET}"
    if name == "group_compare":
        a, b = quote(str(args["group_a"])), quote(str(args["group_b"]))
        return f"Comparing {_metric(args['metric'])} between {a} and {b} {_IN_DATASET}"
    limit = args.get("limit")
    rows = f"up to {limit} matching records" if limit else "matching records"
    return f"Listing {rows} {_IN_DATASET}"


def summarize(name: str, arguments: dict[str, Any]) -> str:
    """A fixed-template, plain-language summary of one call (shown on the Ask page)."""
    args = validated_args(name, arguments)
    if args is None:
        return INVALID_STEP
    if KINDS.get(name) == "analytics":
        return _analytics(name, args)
    if name == "search_evidence":
        return (
            f"Searching {_classes(args.get('source_classes'))} evidence for {quote(args['query'])}"
        )
    if name == "search_evidence_keyword":
        terms = ", ".join(quote(t) for t in args["terms"])
        return f"Searching for exact mentions of {terms}"
    if name == "get_evidence":
        count = len(args["handles"])
        return f"Opening {count} evidence passage{'s' if count != 1 else ''}"
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
