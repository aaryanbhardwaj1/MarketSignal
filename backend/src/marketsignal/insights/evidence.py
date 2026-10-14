"""Re-resolve a curated quote against current evidence (plan §5.4 step 1).

* ``verified``  - the passage resolves in the workspace scope, its version is the source's
  current ready version, and the whitespace-collapsed quote is a substring of the
  whitespace-collapsed passage. The match is mapped back to raw passage offsets and to the
  child chunk that contains its start, so the evidence drawer can highlight it.
* ``stale``     - the passage resolves but the version is superseded or the quote is gone.
* ``withdrawn`` - the passage no longer exists in this workspace, or its source was purged.

Only a verified reference carries the quote; the others never show text. ``states_projection``
echoes the curated flag: the quoted passage itself states a forward projection (a forecast).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.db.scope import WorkspaceScope
from marketsignal.evidence.handles import parse_handle
from marketsignal.evidence.resolver import (
    EvidenceDeletedError,
    EvidenceNotFoundError,
    ResolvedEvidence,
    resolve_evidence,
)
from marketsignal.insights.fixture import EvidenceSpec

Integrity = Literal["verified", "stale", "withdrawn"]
READY = frozenset({"ready", "ready_degraded"})


@dataclass(frozen=True, slots=True)
class Match:
    start: int
    end: int


def collapse(text: str) -> tuple[str, list[int]]:
    """``text`` with each whitespace run (and leading/trailing runs) collapsed to one space,
    plus, for every collapsed character, its index in ``text``."""
    out: list[str] = []
    index: list[int] = []
    in_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if not in_space:
                out.append(" ")
                index.append(i)
            in_space = True
            continue
        in_space = False
        out.append(ch)
        index.append(i)
    return "".join(out), index


def find_quote(passage: str, quote: str) -> Match | None:
    """Raw ``[start, end)`` offsets in ``passage`` of the whitespace-collapsed ``quote``."""
    needle, _ = collapse(quote.strip())
    haystack, index = collapse(passage)
    pos = haystack.find(needle) if needle else -1
    if pos < 0:
        return None
    return Match(index[pos], index[pos + len(needle) - 1] + 1)


def _source(
    code: str, title: str, source_type: str, source_class: str, version: int
) -> dict[str, Any]:
    return {
        "code": code,
        "title": title,
        "source_type": source_type,
        "source_class": source_class,
        "version": version,
    }


def _ref(spec: EvidenceSpec, integrity: Integrity, **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "handle": spec.handle,
        "integrity": integrity,
        "role": spec.role,
        "quote": None,
        "char_start": None,
        "char_end": None,
        "child_id": None,
        "locator_label": "",
        "note": spec.note,
        "states_projection": spec.states_projection,
    }
    return {**base, **fields}


def _child_at(resolved: ResolvedEvidence, offset: int) -> str | None:
    child = next((c for c in resolved.children if c.char_start <= offset < c.char_end), None)
    return str(child.child_id) if child is not None else None


def _from_resolved(spec: EvidenceSpec, resolved: ResolvedEvidence) -> dict[str, Any]:
    src = resolved.source
    source = _source(
        src["source_code"],
        src["title"],
        src["source_type"],
        src["source_class"],
        int(src["version"]),
    )
    current = bool(src["is_latest"]) and src["version_status"] in READY
    match = find_quote(resolved.text, spec.quote) if current else None
    if match is None:
        return _ref(spec, "stale", source=source, locator_label=resolved.locator_label)
    return _ref(
        spec,
        "verified",
        source=source,
        locator_label=resolved.locator_label,
        quote=spec.quote,
        char_start=match.start,
        char_end=match.end,
        child_id=_child_at(resolved, match.start),
    )


async def resolve_ref(
    session: AsyncSession, scope: WorkspaceScope, spec: EvidenceSpec
) -> dict[str, Any]:
    """One curated reference as a contract ``EvidenceRef``."""
    handle = parse_handle(spec.handle)
    try:
        resolved = await resolve_evidence(session, scope, spec.handle)
    except EvidenceDeletedError as exc:
        t = exc.tombstone
        return _ref(spec, "withdrawn", source=_source(t.source_code, t.title, "", "", t.version))
    except EvidenceNotFoundError:
        return _ref(
            spec, "withdrawn", source=_source(handle.source_code, "", "", "", handle.version)
        )
    return _from_resolved(spec, resolved)
