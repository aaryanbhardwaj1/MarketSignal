"""Assemble the curated analyst brief and the named analyses (plan §5.4).

Every request re-resolves each quote (``insights.evidence``) and recomputes each analysis
(``insights.analyses``); nothing is written and no model is called. Metrics read only computed
analysis rows, and a derived metric (``diff``, ``pct_change``) exists only when all its inputs
were computed. Item integrity rolls up as: ``verified`` (all evidence verified and all metrics
computed), ``partial`` (at least one verified passage) or ``unverified``; an opportunity's
risk evidence counts towards its roll-up.

Schema v2 fields are always present in the response (``null`` / empty for a v1 fixture). Each
analysis also carries its ``summary`` and its ``interpretation`` only when it computed and every
number in them matches a computed figure (``insights.summary``; ``summary_status`` and
``interpretation_status`` say why one is ``null``), and ``used_by``: the signals and
opportunities that read it through a metric or link to it through ``related``.

A forecast is re-checked on every request, not only at load: an item (or risk) with a
``forecast`` claim whose cited projection (a supporting ``states_projection`` reference) no
longer verifies is ``unverified``, and the item's metric values are withheld.

Results are cached in process for :data:`CACHE_TTL_S`, keyed by workspace, fixture version and
a fingerprint of the referenced sources' current versions, so any upload, supersession or purge
of a referenced source invalidates the entry immediately.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Iterable
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
from marketsignal.insights.fixture import (
    ClaimText,
    EvidenceSpec,
    Fixture,
    MetricSpec,
    OpportunitySpec,
    Pick,
    Related,
    SignalSpec,
)
from marketsignal.insights.format import format_value
from marketsignal.insights.summary import SummaryStatus, check_summary, check_text

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


def _claim(claim: ClaimText | None) -> dict[str, Any] | None:
    return None if claim is None else {"text": claim.text, "claim_type": claim.claim_type}


def _projection_verified(evidence: list[dict[str, Any]]) -> bool:
    return any(
        e["role"] == "support" and e["states_projection"] and e["integrity"] == "verified"
        for e in evidence
    )


def _forecast_fails(claims: Iterable[str | None], evidence: list[dict[str, Any]]) -> bool:
    """A forecast claim whose cited projection does not verify on this request."""
    return "forecast" in claims and not _projection_verified(evidence)


def _withheld(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**m, "value": None, "display": None} for m in metrics]


def _related(related: Related) -> dict[str, list[str]]:
    return {
        "analyses": list(related.analyses),
        "opportunities": list(related.opportunities),
        "signals": list(related.signals),
    }


def _counts(evidence: list[dict[str, Any]]) -> dict[str, int]:
    verified = [e for e in evidence if e["integrity"] == "verified"]
    return {
        "support_count": sum(e["role"] == "support" for e in verified),
        "contradiction_count": sum(e["role"] == "contradict" for e in verified),
    }


def _analysis_ids(metrics: Iterable[MetricSpec], related: Related) -> set[str]:
    ids = set(related.analyses)
    for m in metrics:
        ids |= {p.analysis_id for p in ([m.pick] if m.pick else m.derive.of if m.derive else [])}
    return ids


def used_by_index(fixture: Fixture) -> dict[str, dict[str, list[str]]]:
    """Analysis id -> the signals and opportunities that read it (metric picks, derived inputs)
    or link to it (``related.analyses``), in fixture order."""
    signals = [(s.id, _analysis_ids(s.metrics, s.related)) for s in fixture.signals]
    opps = [(o.id, _analysis_ids(o.metrics, o.related)) for o in fixture.opportunities]
    return {
        a.id: {
            "signals": [i for i, ids in signals if a.id in ids],
            "opportunities": [i for i, ids in opps if a.id in ids],
        }
        for a in fixture.analyses
    }


class _Refs:
    """Resolves curated references and records the sources of any that did not verify."""

    def __init__(self, session: AsyncSession, scope: WorkspaceScope, drift: set[str]) -> None:
        self.session, self.scope, self.drift = session, scope, drift

    async def __call__(self, specs: Iterable[EvidenceSpec]) -> list[dict[str, Any]]:
        out = [await resolve_ref(self.session, self.scope, e) for e in specs]
        self.drift.update(r["source"]["code"] for r in out if r["integrity"] != "verified")
        return out


async def _signal(
    s: SignalSpec, fixture: Fixture, results: dict[str, Recomputed], refs: _Refs
) -> dict[str, Any]:
    evidence = await refs(s.evidence)
    metrics = [_metric(m, fixture, results) for m in s.metrics]
    integrity = _integrity(evidence, metrics)
    claims = (s.claim_type, s.implication.claim_type if s.implication else None)
    if _forecast_fails(claims, evidence):
        integrity, metrics = "unverified", _withheld(metrics)
    return {
        "id": s.id,
        "category": s.category,
        "title": s.title,
        "statement": s.statement,
        "integrity": integrity,
        "evidence": evidence,
        "metrics": metrics,
        "caveats": list(s.caveats),
        "kind": s.kind,
        "status": s.status,
        "claim_type": s.claim_type,
        "implication": _claim(s.implication),
        "gaps": list(s.gaps),
        "related": _related(s.related),
        **_counts(evidence),
    }


async def _opportunity(
    o: OpportunitySpec, fixture: Fixture, results: dict[str, Recomputed], refs: _Refs
) -> dict[str, Any]:
    evidence = await refs(o.evidence)
    metrics = [_metric(m, fixture, results) for m in o.metrics]
    risks: list[dict[str, Any]] = []
    for risk in o.risks:
        risk_refs = await refs(risk.evidence)
        risk_integrity = _integrity(risk_refs, [])
        if _forecast_fails((risk.claim_type,), risk_refs):
            risk_integrity = "unverified"
        risks.append(
            {
                "text": risk.text,
                "claim_type": risk.claim_type,
                "evidence": risk_refs,
                "integrity": risk_integrity,
            }
        )
    every_ref = evidence + [r for risk in risks for r in risk["evidence"]]
    integrity = _integrity(every_ref, metrics)
    claims = (o.thesis_claim_type, o.why_it_matters.claim_type if o.why_it_matters else None)
    if _forecast_fails(claims, evidence):
        integrity, metrics = "unverified", _withheld(metrics)
    return {
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
        "integrity": integrity,
        "thesis_claim_type": o.thesis_claim_type,
        "why_it_matters": _claim(o.why_it_matters),
        "risks": risks,
        "next_investigation": o.next_investigation,
        "related": _related(o.related),
        **_counts(evidence),
    }


def _interpretation(
    claim: ClaimText | None, payload: dict[str, Any]
) -> tuple[dict[str, Any] | None, SummaryStatus]:
    """Gated like the summary: withheld unless computed and every number is a computed figure."""
    text, status = check_text(claim.text if claim else None, payload)
    return (_claim(claim) if text is not None else None), status


def _analyses(fixture: Fixture, results: dict[str, Recomputed]) -> list[dict[str, Any]]:
    used_by = used_by_index(fixture)
    out = []
    for a in fixture.analyses:
        payload = results[a.id].payload
        summary, summary_status = check_summary(a.summary, payload)
        interpretation, interpretation_status = _interpretation(a.interpretation, payload)
        out.append(
            {
                **payload,
                "business_area": a.business_area,
                "summary": summary,
                "summary_status": summary_status,
                "interpretation": interpretation,
                "interpretation_status": interpretation_status,
                "used_by": used_by[a.id],
            }
        )
    return out


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
    refs = _Refs(session, scope, drift)
    signals = [await _signal(s, fixture, results, refs) for s in fixture.signals]
    opportunities = [await _opportunity(o, fixture, results, refs) for o in fixture.opportunities]
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
        "analyses": _analyses(fixture, results),
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
