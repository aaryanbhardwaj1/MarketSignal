"""Shared logic for the offline demo snapshot scripts (export, import, reset).

The snapshot (``seed_data/demo/northstar-demo-snapshot.json``) stores saved conversations and
their run rows with *logical keys* in place of corpus UUIDs, because a fresh ``make seed``
assigns new random ids to source versions, dataset tables and chunks:

* an evidence anchor (``anchor_child_id`` / ``child_id``) becomes ``child:<handle>#<start>-<end>``
  (the child chunk of that parent passage with that character span);
* an analytics result's ``source_version_id`` / ``table_id`` become a ``dataset_ref``
  ``{source_code, version, sheet_ordinal, table}``;
* ``workspace_id`` is dropped everywhere.

Run, conversation, message, result, trace, tool-run and verification ids are kept: answer text
embeds ``[[result:<uuid>]]`` and event payloads embed run and trace ids.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from marketsignal.demo.featured import featured_ids

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = REPO_ROOT / "seed_data" / "demo" / "northstar-demo-snapshot.json"
DENYLIST_FILE = REPO_ROOT / "scripts" / "safety-denylist.local"

SNAPSHOT_FORMAT = "marketsignal.demo-snapshot"
SNAPSHOT_FORMAT_VERSION = 1

# Featured NORTHSTAR conversations, in display order (one saved run each). Read from the API's
# own featured.v1.json so the export and the featured list can never diverge.
FEATURED_NORTHSTAR: tuple[str, ...] = tuple(str(i) for i in featured_ids("NORTHSTAR"))

# Test-harness workspace codes (tests/integration/conftest.py: "T" + 10 upper-case hex).
TEST_WORKSPACE_CODE = re.compile(r"^T[0-9A-F]{10}$")

# Corpus states an imported run may point at (the API also treats ``ready_degraded`` as ready);
# ``purged`` (or anything else) means drift.
LIVE_VERSION_STATUSES = frozenset({"ready", "ready_degraded", "superseded"})

# Patterns that must never appear in a committed snapshot. Mixed case on purpose: env-var names
# are matched exactly, everything else case-insensitively.
BASE_DENY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"/Users/"),
    re.compile(r"/private/tmp/"),
    re.compile(r"/home/runner/"),
    re.compile(r"sk-ant", re.IGNORECASE),
    re.compile(r"api_key", re.IGNORECASE),
    re.compile(r"ANTHROPIC"),
    re.compile(r"postgres(?:ql)?(?:\+\w+)?://", re.IGNORECASE),
    re.compile(r"PRIVATE KEY"),
)

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
CHILD_REF_PREFIX = "child:"
_CHILD_KEYS = ("anchor_child_id", "child_id")


class SnapshotError(RuntimeError):
    """The snapshot cannot be exported or imported safely (denylist hit, corpus drift, ...)."""


# ── handles ──────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class HandleKey:
    workspace: str
    source_code: str
    version: int


def parse_handle(handle: str) -> HandleKey | None:
    """``WS/CODE@vN[:LOCATOR]`` -> key; ``None`` for anything else (mirrors runs.store SQL)."""
    match = re.fullmatch(r"([^/]+)/([^@/]+)@v(\d+)(?::.*)?", handle)
    if match is None:
        return None
    return HandleKey(match.group(1), match.group(2), int(match.group(3)))


def child_ref(handle: str, start: int, end: int) -> str:
    return f"{CHILD_REF_PREFIX}{handle}#{int(start)}-{int(end)}"


def parse_child_ref(ref: str) -> tuple[str, int, int]:
    if not ref.startswith(CHILD_REF_PREFIX):
        raise SnapshotError(f"not a child reference: {ref!r}")
    handle, sep, span = ref[len(CHILD_REF_PREFIX) :].rpartition("#")
    start, dash, end = span.partition("-")
    if not sep or not dash or not start.isdigit() or not end.isdigit():
        raise SnapshotError(f"malformed child reference: {ref!r}")
    return handle, int(start), int(end)


# ── anchors: UUID <-> logical key ───────────────────────────────────────────────────────────


def _anchor_of(node: dict[str, Any], key: str) -> tuple[str, int, int] | None:
    """The (handle, start, end) that identifies the child chunk named by ``node[key]``."""
    handle = node.get("handle")
    if key == "anchor_child_id" and {"char_start", "char_end"} <= node.keys():
        return (handle, node["char_start"], node["char_end"]) if handle else None
    if key == "child_id" and isinstance(node.get("span"), list) and len(node["span"]) == 2:
        return (handle, node["span"][0], node["span"][1]) if handle else None
    return None


def _walk(
    obj: Any, visit: Callable[[dict[str, Any], dict[str, Any] | None], dict[str, Any]]
) -> Any:
    """Rebuild ``obj``; ``visit(node, parent_dict)`` may return a replacement for each dict."""

    def rec(value: Any, parent: dict[str, Any] | None) -> Any:
        if isinstance(value, dict):
            rebuilt = {k: rec(v, value) for k, v in value.items()}
            return visit(rebuilt, parent)
        if isinstance(value, list):
            return [rec(v, parent) for v in value]
        return value

    return rec(obj, None)


def logicalize_children(obj: Any) -> Any:
    """Replace every child-chunk UUID with ``child:<handle>#<start>-<end>``.

    Citations carry ``handle`` + ``char_start``/``char_end`` next to ``anchor_child_id``; trace
    lanes carry ``handle`` + ``span`` next to ``child_id``; fused/final trace items carry the
    handle on the item and ``{child_id, span}`` in its ``anchor``."""

    def visit(node: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
        out = dict(node)
        for key in _CHILD_KEYS:
            value = node.get(key)
            if not isinstance(value, str) or not UUID_RE.fullmatch(value):
                continue
            probe = node if "handle" in node else {**node, "handle": (parent or {}).get("handle")}
            anchor = _anchor_of(probe, key)
            if anchor is None:
                raise SnapshotError(f"cannot derive a logical key for {key}={value}")
            out[key] = child_ref(*anchor)
        return out

    return _walk(obj, visit)


def child_refs_in(obj: Any) -> set[str]:
    refs: set[str] = set()

    def visit(node: dict[str, Any], _parent: dict[str, Any] | None) -> dict[str, Any]:
        for key in _CHILD_KEYS:
            value = node.get(key)
            if isinstance(value, str) and value.startswith(CHILD_REF_PREFIX):
                refs.add(value)
        return node

    _walk(obj, visit)
    return refs


def resolve_children(obj: Any, lookup: dict[str, str]) -> Any:
    """Inverse of :func:`logicalize_children`, given ``child ref -> live child UUID``."""

    def visit(node: dict[str, Any], _parent: dict[str, Any] | None) -> dict[str, Any]:
        out = dict(node)
        for key in _CHILD_KEYS:
            value = node.get(key)
            if isinstance(value, str) and value.startswith(CHILD_REF_PREFIX):
                if value not in lookup:
                    raise SnapshotError(f"corpus drift: no child chunk for {value}")
                out[key] = lookup[value]
        return out

    return _walk(obj, visit)


# ── safety scans ─────────────────────────────────────────────────────────────────────────────


def load_denylist(path: Path = DENYLIST_FILE) -> tuple[re.Pattern[str], ...]:
    """Base patterns plus one regex per non-comment line of the untracked local denylist."""
    extra: list[re.Pattern[str]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = line.strip()
            if entry and not entry.startswith("#"):
                extra.append(re.compile(entry, re.IGNORECASE))
    return BASE_DENY_PATTERNS + tuple(extra)


def iter_strings(obj: Any, path: str = "$") -> Iterator[tuple[str, str]]:
    """Every string (keys included) in a JSON-like value, with its JSON path."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield f"{path}.{key}", str(key)
            yield from iter_strings(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from iter_strings(value, f"{path}[{index}]")
    elif isinstance(obj, str):
        yield path, obj


def denylist_hits(obj: Any, patterns: Iterable[re.Pattern[str]]) -> list[str]:
    """JSON paths of strings matching any pattern. Never echoes the matched text or pattern
    (local denylist entries are private)."""
    compiled = tuple(patterns)
    return sorted(
        {path for path, value in iter_strings(obj) if any(p.search(value) for p in compiled)}
    )


def foreign_uuids(obj: Any, own_ids: set[str]) -> list[str]:
    """JSON paths holding a UUID that is not one of the snapshot's own row ids."""
    return sorted(
        {
            path
            for path, value in iter_strings(obj)
            if any(u not in own_ids for u in UUID_RE.findall(value))
        }
    )


def is_test_workspace_code(code: str) -> bool:
    return bool(TEST_WORKSPACE_CODE.fullmatch(code))


# ── database helpers (owner connection; FORCE RLS applies, so scope every transaction) ──────


async def workspace_id(conn: AsyncConnection, code: str) -> str:
    row = await conn.execute(text("SELECT id::text FROM workspaces WHERE code = :c"), {"c": code})
    found = row.scalar_one_or_none()
    if found is None:
        raise SnapshotError(f"workspace {code} does not exist")
    return str(found)


async def assert_rls_applies(conn: AsyncConnection) -> None:
    """Refuse to run as a superuser or BYPASSRLS role: under such a role FORCE RLS is ignored
    and an unscoped statement would reach every workspace."""
    row = await conn.execute(
        text("SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname = current_user")
    )
    if row.scalar_one_or_none() is not True:
        raise SnapshotError(
            "refusing to run as a superuser or BYPASSRLS role: workspace isolation relies on "
            "row-level security (use the schema-owner role from MS_MIGRATIONS_DATABASE_URL)"
        )


async def scope_to(conn: AsyncConnection, ws_id: str) -> None:
    """Check the role is subject to RLS, then scope the transaction to one workspace."""
    await assert_rls_applies(conn)
    await conn.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws_id})


async def child_lookup(conn: AsyncConnection, refs: Iterable[str]) -> dict[str, str]:
    """``child ref -> child UUID`` for the refs that resolve in the scoped workspace."""
    wanted = {ref: parse_child_ref(ref) for ref in refs}
    if not wanted:
        return {}
    rows = await conn.execute(
        text(
            "SELECT p.handle, c.char_start, c.char_end, c.id::text FROM parent_chunks p "
            "JOIN child_chunks c ON c.parent_id = p.id WHERE p.handle = ANY(:handles) "
            "AND p.workspace_id = CAST(current_setting('app.workspace_id', true) AS uuid)"
        ),
        {"handles": sorted({handle for handle, _, _ in wanted.values()})},
    )
    by_key: dict[str, list[str]] = {}
    for handle, start, end, child in rows.all():
        by_key.setdefault(child_ref(handle, start, end), []).append(str(child))
    ambiguous = sorted(ref for ref in wanted if len(by_key.get(ref, [])) > 1)
    if ambiguous:
        raise SnapshotError(f"ambiguous child references: {ambiguous[:3]}")
    return {ref: by_key[ref][0] for ref in wanted if ref in by_key}
