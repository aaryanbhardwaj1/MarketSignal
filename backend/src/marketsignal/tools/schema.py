"""Model-facing tool schemas: the ``to_anthropic_tool()`` adapter (plan §17).

Anthropic strict tool use supports a JSON Schema subset, so the adapter, starting from the
contract's Pydantic input model:

* inlines ``$ref``/``$defs`` and drops ``title``/``default``;
* strips keywords strict mode does not support (length, range and item-count bounds);
* turns ``oneOf`` into ``anyOf`` and drops ``discriminator``;
* sets ``additionalProperties: false`` on every object;
* marks every property required; optional fields stay nullable (``anyOf [..., null]``).

Server-side Pydantic validation stays the security boundary: the bounds stripped here are still
enforced on every call. The tool array is sorted by name for prompt-cache stability.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from marketsignal.tools.contracts import ToolSpec

_STRIPPED = frozenset(
    {
        "title",
        "default",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
        "uniqueItems",
        "multipleOf",
        "discriminator",
        "examples",
    }
)


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a new strict-mode-compatible schema (the input is not modified)."""
    defs: dict[str, Any] = schema.get("$defs", {})
    root = {k: v for k, v in schema.items() if k != "$defs"}
    adapted: dict[str, Any] = _adapt(root, defs)
    return adapted


def _adapt(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_adapt(n, defs) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        target = defs[str(node["$ref"]).rsplit("/", 1)[-1]]
        extra = {k: v for k, v in node.items() if k != "$ref"}
        return _adapt({**target, **extra}, defs)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _STRIPPED:
            continue
        name = "anyOf" if key == "oneOf" else key
        if key == "properties":
            out[name] = {p: _adapt(v, defs) for p, v in value.items()}
        else:
            out[name] = _adapt(value, defs)
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        out["required"] = sorted(out.get("properties", {}))
    return out


def to_anthropic_tool(
    name: str,
    description: str,
    model: type[BaseModel],
    field_descriptions: dict[str, str] | None = None,
) -> ToolSpec:
    """Adapt one tool's input model into a strict ``ToolSpec`` (no context fields exist)."""
    schema = strict_schema(model.model_json_schema())
    props = schema.get("properties", {})
    for field, text in (field_descriptions or {}).items():
        if field in props:
            props[field] = {**props[field], "description": text}
    return ToolSpec(name=name, description=description, input_schema=schema, strict=True)
