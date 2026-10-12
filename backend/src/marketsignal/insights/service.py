"""Assemble the curated analyst brief and the named analyses (plan §5.4).

Every request re-resolves each quote (``insights.evidence``) and recomputes each analysis
(``insights.analyses``); nothing is written and no model is called. Metrics read only computed
analysis rows, and a derived metric (``diff``, ``pct_change``) exists only when all its inputs
were computed. Item integrity rolls up as: ``verified`` (all evidence verified and all metrics
computed), ``partial`` (at least one verified passage) or ``unverified``.

Results are cached in process for :data:`CACHE_TTL_S`, keyed by workspace, fixture version and
a fingerprint of the referenced sources' current versions, so any upload, supersession or purge
of a referenced source invalidates the entry immediately.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.analytics.rounding import round_value, to_decimal
from marketsignal.config import Settings
from marketsignal.db.scope import WorkspaceScope
from marketsignal.insights.analyses import FlatRow, Recomputed, pick_row, recompute
from marketsignal.insights.evidence import resolve_ref
from marketsignal.insights.fixture import Fixture, MetricSpec, Pick
from marketsignal.insights.format import format_value

LABEL = "Curated analyst brief"
CACHE_TTL_S = 300.0
CACHE_MAX = 32

_SOURCES = """
SELECT s.source_code, s.current_version_id, v.version, v.status, s.deleted_at IS NOT NULL
FROM sources s LEFT JOIN source_versions v ON v.id = s.current_version_id
WHERE s.workspace_id = :ws AND s.source_code = ANY(CAST(:codes AS text[]))
ORDER BY s.source_code
"""


@dataclass(frozen=True, slots=True)
class Bundle:
    brief: dict[str, Any]
    analyses: dict[str, Any]


_cache: dict[tuple[uuid.UUID, str, str], tuple[float, Bundle]] = {}


def clear_cache() -> None:
    _cache.clear()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def empty_brief() -> dict[str, Any]:
    return {
        "fixture_version": None,
        "label": LABEL,
        "computed_at": _now(),
        "corpus_check": {"status": "ok", "drifted_sources": []},
        "signals": [],
        "opportunities": [],
    }


def empty_analyses() -> dict[str, Any]:
    return {"fixture_version": None, "computed_at": _now(), "analyses": []}


async def _corpus_state(
    session: AsyncSession, scope: WorkspaceScope, fixture: Fixture
) -> tuple[str, list[str]]:
    """(fingerprint, sources whose current version differs from the pinned one)."""
    rows = (
        await session.execute(
            text(_SOURCES), {"ws": scope.workspace_id, "codes": sorted(fixture.corpus)}
        )
    ).all()
    seen = {r[0]: r for r in rows}
    drifted = sorted(
        code
        for code, pin in fixture.corpus.items()
        if code not in seen
        or seen[code][4]
        or seen[code][2] != pin.version
        or seen[code][3] not in ("ready", "ready_degraded")
    )
    digest = hashlib.sha256(repr([tuple(map(str, r)) for r in rows]).encode()).hexdigest()
    return digest, drifted


def _pick_value(pick: Pick, results: dict[str, Recomputed]) -> int | float | None:
    result = results.get(pick.analysis_id)
    if result is None or result.status != "computed":
        return None
    row: FlatRow | None = pick_row(result.rows, pick.group)
    if row is None:
        return None
    value = row.cells.get(pick.column) if pick.column else row.value
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _derive(op: str, a: int | float, b: int | float) -> int | float | None:
    da, db = to_decimal(a), to_decimal(b)
    if op == "diff":
        return round_value(da - db, None)
    if da == 0:
        return None
    return round_value((db - da) / da * Decimal(100), 1)


def _metric(m: MetricSpec, fixture: Fixture, results: dict[str, Recomputed]) -> dict[str, Any]:
    source_pick = m.pick or (m.derive.of[0] if m.derive else None)
    assert source_pick is not None
    spec = fixture.analysis(source_pick.analysis_id)
    assert spec is not None
    unit = m.unit or spec.unit
    derived: dict[str, Any] | None = None
    if m.derive is not None:
        inputs = [_pick_value(p, results) for p in m.derive.of]
        a, b = inputs
        value = _derive(m.derive.op, a, b) if a is not None and b is not None else None
        derived = {
            "op": m.derive.op,
            "of": [f"{p.analysis_id}:{'/'.join(p.group.values())}" for p in m.derive.of],
        }
        signed = m.derive.op == "pct_change"
        display = format_value(
            value, unit, places=-1 if m.derive.op == "diff" else None, signed=signed
        )
    else:
        assert m.pick is not None
        value = _pick_value(m.pick, results)
        display = format_value(value, unit)
    return {
        "analysis_id": source_pick.analysis_id,
        "label": m.label,
        "value": value,
        "display": display,
        "unit": unit,
        "denominator_label": m.denominator_label or spec.denominator_label,
        "derived": derived,
    }


def _integrity(evidence: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> str:
    verified = [e["integrity"] == "verified" for e in evidence]
    if all(verified) and all(m["value"] is not None for m in metrics):
        return "verified"
    return "partial" if any(verified) else "unverified"


async def _build(
    session: AsyncSession, scope: WorkspaceScope, settings: Settings, fixture: Fixture
) -> Bundle:
    computed_at = _now()
    results: dict[str, Recomputed] = {}
    for spec in fixture.analyses:
        code = spec.dataset.rpartition(":")[0]
        results[spec.id] = await recompute(
            session,
            scope,
            settings,
            spec,
            computed_at=computed_at,
            corpus_version=fixture.corpus[code].version,
        )
    _, drifted = await _corpus_state(session, scope, fixture)
    drift = set(drifted)

    async def refs(item_evidence: Any) -> list[dict[str, Any]]:
        out = [await resolve_ref(session, scope, e) for e in item_evidence]
        drift.update(r["source"]["code"] for r in out if r["integrity"] != "verified")
        return out

    signals = []
    for s in fixture.signals:
        evidence = await refs(s.evidence)
        metrics = [_metric(m, fixture, results) for m in s.metrics]
        signals.append(
            {
                "id": s.id,
                "category": s.category,
                "title": s.title,
                "statement": s.statement,
                "integrity": _integrity(evidence, metrics),
                "evidence": evidence,
                "metrics": metrics,
                "caveats": list(s.caveats),
            }
        )
    opportunities = []
    for o in fixture.opportunities:
        evidence = await refs(o.evidence)
        metrics = [_metric(m, fixture, results) for m in o.metrics]
        opportunities.append(
            {
                "id": o.id,
                "title": o.title,
                "status": o.status,
                "status_rationale": o.status_rationale,
                "thesis": o.thesis,
                "supporting": [e for e in evidence if e["role"] == "support"],
                "contradicting": [e for e in evidence if e["role"] == "contradict"],
                "metrics": metrics,
                "gaps": list(o.gaps),
                "next_step": o.next_step,
                "caveats": list(o.caveats),
                "integrity": _integrity(evidence, metrics),
            }
        )
    brief = {
        "fixture_version": fixture.fixture_version,
        "label": LABEL,
        "computed_at": computed_at,
        "corpus_check": {
            "status": "drift" if drift else "ok",
            "drifted_sources": sorted(drift),
        },
        "signals": signals,
        "opportunities": opportunities,
    }
    analyses = {
        "fixture_version": fixture.fixture_version,
        "computed_at": computed_at,
        "analyses": [results[a.id].payload for a in fixture.analyses],
    }
    return Bundle(brief, analyses)


async def build_bundle(
    session: AsyncSession, scope: WorkspaceScope, settings: Settings, fixture: Fixture
) -> Bundle:
    """The brief and the analyses for ``fixture``, from cache when the corpus is unchanged."""
    fingerprint, _ = await _corpus_state(session, scope, fixture)
    key = (scope.workspace_id, fixture.fixture_version, fingerprint)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    bundle = await _build(session, scope, settings, fixture)
    if len(_cache) >= CACHE_MAX:
        _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
    _cache[key] = (now + CACHE_TTL_S, bundle)
    return bundle
