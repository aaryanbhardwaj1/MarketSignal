"""The curated brief fixture: strict schema and loader.

One hand-authored JSON file per workspace (``fixtures/<WORKSPACE>.v<N>.json``). Every quote is
an exact sentence of an evidence passage, and every number is a named analysis that the
deterministic engine recomputes on request. Loading fails closed: an unknown field, a handle
outside the fixture's workspace, a superseded or planted handle, or a metric that points at a
value the fixture does not pin, is a :class:`FixtureError`.

Schema v2 adds claim types, signal kinds and statuses, opportunity risks and ``related`` links,
and analysis summaries. Its fields default for a v1 file (which may not carry them) and are
required in a v2 file, where every claim is checked against its grounding (:func:`check_claim`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from marketsignal.analytics.schema import parse_dataset_id
from marketsignal.evidence.handles import parse_handle
from marketsignal.tools.analytics_contracts import AggregateIn, FilterRowsIn, GroupCompareIn

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SCHEMA_VERSION = 2
# Handles a fixture must never cite: planted prompt-injection blocks and a superseded report.
BANNED_HANDLE_PREFIXES = (
    "NORTHSTAR/KINETIC-WEB@v1:S1.B12",
    "NORTHSTAR/REVIEWS@v1:R578",
    "NORTHSTAR/GENZ-TRENDS@v1",
)

Op = Literal["aggregate", "filter_rows", "group_compare"]
AnalysisUnit = Literal["percent", "count", "usd", "score", "ratio"]
Category = Literal["customer", "product", "channel", "pricing"]
OpportunityStatus = Literal["supported", "mixed_evidence", "emerging", "needs_research"]
ClaimType = Literal["observed", "derived", "inference", "hypothesis", "forecast"]
SignalKind = Literal[
    "emerging_signal", "risk_blocker", "competitor_finding", "optimization", "future_outlook"
]
SignalStatus = Literal["strong_evidence", "emerging", "mixed_evidence", "needs_validation"]
BusinessArea = Literal[
    "Customer friction",
    "Willingness to pay",
    "Customer satisfaction",
    "Product performance",
    "Channels and growth",
]
INTERPRETIVE = frozenset({"inference", "hypothesis", "forecast"})
SPEC_MODELS: dict[str, type[AggregateIn] | type[FilterRowsIn] | type[GroupCompareIn]] = {
    "aggregate": AggregateIn,
    "filter_rows": FilterRowsIn,
    "group_compare": GroupCompareIn,
}


class FixtureError(ValueError):
    """The fixture file is malformed or breaks a curation rule."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Part(_Model):
    """One engine call of a named analysis. ``group`` labels its rows (e.g. a cohort)."""

    group: dict[str, str] = Field(default_factory=dict)
    spec: dict[str, Any]


class ExpectedRow(_Model):
    """A pinned result row: ``group`` identifies it, ``value`` is the rounded engine value.
    ``values`` pins further cells of a ``filter_rows`` row by column."""

    group: dict[str, str]
    value: float | int
    values: dict[str, float | int] = Field(default_factory=dict)


class ClaimText(_Model):
    text: str = Field(min_length=1)
    claim_type: ClaimType


class Related(_Model):
    analyses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)


class AnalysisSpec(_Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    title: str
    question: str
    category: Category
    op: Op
    dataset: str
    unit: AnalysisUnit
    presentation: Literal["bar", "table", "single"]
    denominator_label: str | None = None
    filter_labels: dict[str, str] = Field(default_factory=dict)
    value_column: str | None = None  # filter_rows: the column a row's value is read from
    parts: list[Part] = Field(min_length=1, max_length=4)
    expected: list[ExpectedRow] = Field(min_length=1)
    caveats: list[str] = Field(default_factory=list)
    # v2
    business_area: BusinessArea | None = None
    summary: str | None = None  # every number must match a computed row (insights.summary)
    interpretation: ClaimText | None = None

    @model_validator(mode="after")
    def _check(self) -> AnalysisSpec:
        if self.interpretation is not None and self.interpretation.claim_type != "inference":
            raise ValueError(f"{self.id}: an interpretation must be an inference")
        if parse_dataset_id(self.dataset) is None:
            raise ValueError(f"{self.id}: invalid dataset id {self.dataset!r}")
        model = SPEC_MODELS[self.op]
        for part in self.parts:
            if part.spec.get("dataset") != self.dataset:
                raise ValueError(f"{self.id}: every part must target {self.dataset}")
            model.model_validate(part.spec)
        if self.op == "filter_rows" and not self.value_column:
            raise ValueError(f"{self.id}: filter_rows needs value_column")
        return self


class Pick(_Model):
    analysis_id: str
    group: dict[str, str] = Field(default_factory=dict)
    column: str | None = None  # filter_rows: read this pinned cell instead of the row value


class Derive(_Model):
    op: Literal["diff", "pct_change"]
    of: list[Pick] = Field(min_length=2, max_length=2)


class MetricSpec(_Model):
    label: str
    pick: Pick | None = None
    derive: Derive | None = None
    unit: AnalysisUnit | None = None  # defaults to the analysis unit
    denominator_label: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> MetricSpec:
        if (self.pick is None) == (self.derive is None):
            raise ValueError(f"metric {self.label!r}: exactly one of pick / derive")
        if self.derive is not None and self.unit is None:
            raise ValueError(f"metric {self.label!r}: a derived metric needs a unit")
        return self


class EvidenceSpec(_Model):
    handle: str
    quote: str = Field(min_length=8)
    role: Literal["support", "contradict"] = "support"
    note: str | None = None
    states_projection: bool = False  # the quoted passage itself states a forward projection


class RiskSpec(_Model):
    text: str = Field(min_length=1)
    claim_type: ClaimType
    evidence: list[EvidenceSpec] = Field(min_length=1)


class SignalSpec(_Model):
    id: str
    category: str
    title: str
    statement: str
    evidence: list[EvidenceSpec] = Field(min_length=1)
    metrics: list[MetricSpec] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    # v2
    kind: SignalKind | None = None
    status: SignalStatus | None = None
    claim_type: ClaimType | None = None  # of ``statement``
    implication: ClaimText | None = None
    gaps: list[str] = Field(default_factory=list)
    related: Related = Field(default_factory=Related)


class OpportunitySpec(_Model):
    id: str
    title: str
    status: OpportunityStatus
    status_rationale: str
    thesis: str
    evidence: list[EvidenceSpec] = Field(min_length=1)
    metrics: list[MetricSpec] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next_step: str
    caveats: list[str] = Field(default_factory=list)
    # v2
    thesis_claim_type: ClaimType | None = None
    why_it_matters: ClaimText | None = None
    risks: list[RiskSpec] = Field(default_factory=list)
    next_investigation: str | None = None
    related: Related = Field(default_factory=Related)


class CorpusEntry(_Model):
    version: int = Field(ge=1)


class Fixture(_Model):
    schema_version: Literal[1, 2]
    fixture_version: str
    workspace: str
    label: Literal["Curated analyst brief"]
    corpus: dict[str, CorpusEntry]
    analyses: list[AnalysisSpec]
    signals: list[SignalSpec]
    opportunities: list[OpportunitySpec]

    def all_evidence(self) -> list[EvidenceSpec]:
        return (
            [e for s in self.signals for e in s.evidence]
            + [e for o in self.opportunities for e in o.evidence]
            + [e for o in self.opportunities for r in o.risks for e in r.evidence]
        )

    def all_metrics(self) -> list[MetricSpec]:
        return [m for s in self.signals for m in s.metrics] + [
            m for o in self.opportunities for m in o.metrics
        ]

    def analysis(self, analysis_id: str) -> AnalysisSpec | None:
        return next((a for a in self.analyses if a.id == analysis_id), None)

    @model_validator(mode="after")
    def _check(self) -> Fixture:
        ids = [a.id for a in self.analyses]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate analysis id")
        for ev in self.all_evidence():
            _check_handle(self, ev.handle)
        for analysis in self.analyses:
            code, _sheet = parse_dataset_id(analysis.dataset) or ("", 0)
            if code not in self.corpus:
                raise ValueError(f"{analysis.id}: dataset source {code} missing from corpus")
        for metric in self.all_metrics():
            picks = (
                [metric.pick] if metric.pick else list(metric.derive.of if metric.derive else [])
            )
            for pick in picks:
                _check_pick(self, pick)
        if self.schema_version >= 2:
            _check_v2(self)
        else:
            _reject_v2_fields(self)
        return self


def _check_handle(fixture: Fixture, handle_text: str) -> None:
    handle = parse_handle(handle_text)  # MalformedHandleError (a ValueError) propagates
    if handle.workspace_code != fixture.workspace:
        raise ValueError(f"{handle_text}: handle outside workspace {fixture.workspace}")
    if any(handle_text.startswith(p) for p in BANNED_HANDLE_PREFIXES):
        raise ValueError(f"{handle_text}: banned handle")
    entry = fixture.corpus.get(handle.source_code)
    if entry is None or entry.version != handle.version:
        raise ValueError(f"{handle_text}: source version not pinned in corpus")


def _check_pick(fixture: Fixture, pick: Pick) -> None:
    analysis = fixture.analysis(pick.analysis_id)
    if analysis is None:
        raise ValueError(f"metric references unknown analysis {pick.analysis_id}")
    rows = [r for r in analysis.expected if r.group == pick.group]
    if len(rows) != 1:
        raise ValueError(f"{pick.analysis_id}: pick {pick.group} must match one expected row")
    if pick.column is not None and pick.column not in rows[0].values:
        raise ValueError(f"{pick.analysis_id}: column {pick.column} is not pinned")


V2_FIELDS: dict[type[_Model], tuple[str, ...]] = {
    SignalSpec: ("kind", "status", "claim_type", "implication", "related"),
    OpportunitySpec: (
        "thesis_claim_type",
        "why_it_matters",
        "risks",
        "next_investigation",
        "related",
    ),
    AnalysisSpec: ("business_area", "summary"),
}
V2_OPTIONAL: dict[type[_Model], tuple[str, ...]] = {
    SignalSpec: ("gaps",),
    OpportunitySpec: (),
    AnalysisSpec: ("interpretation",),
}


def _items(fixture: Fixture) -> list[tuple[str, _Model]]:
    return [
        *((s.id, s) for s in fixture.signals),
        *((o.id, o) for o in fixture.opportunities),
        *((a.id, a) for a in fixture.analyses),
    ]


def _reject_v2_fields(fixture: Fixture) -> None:
    """A v1 file is never claim-checked, so it may not carry v2 fields at all."""
    for item_id, item in _items(fixture):
        extra = item.model_fields_set & {*V2_FIELDS[type(item)], *V2_OPTIONAL[type(item)]}
        if extra:
            raise ValueError(f"{item_id}: schema_version 1 cannot carry {sorted(extra)}")


def check_claim(
    where: str, claim_type: ClaimType, evidence: Sequence[EvidenceSpec], metric_count: int
) -> None:
    """The grounding a claim type needs (v2 rules 1-4); ``evidence`` and ``metric_count`` are
    what the claim's item cites."""
    support = [e for e in evidence if e.role == "support"]
    if claim_type == "observed" and not support:
        raise ValueError(f"{where}: an observed claim needs a supporting quote")
    if claim_type == "derived" and metric_count == 0:
        raise ValueError(f"{where}: a derived claim needs a metric")
    if claim_type in INTERPRETIVE and not evidence and metric_count == 0:
        raise ValueError(f"{where}: a {claim_type} claim needs evidence or a metric")
    if claim_type == "forecast" and not any(e.states_projection for e in support):
        raise ValueError(f"{where}: a forecast needs a cited passage that states the projection")


def _check_required(fixture: Fixture) -> None:
    for item_id, item in _items(fixture):
        for name in V2_FIELDS[type(item)]:
            value = getattr(item, name)
            if name not in item.model_fields_set or value is None or value == "":
                raise ValueError(f"{item_id}: schema_version 2 requires {name}")


def _check_related(fixture: Fixture, item_id: str, related: Related) -> None:
    known = {
        "analyses": {a.id for a in fixture.analyses},
        "opportunities": {o.id for o in fixture.opportunities},
        "signals": {s.id for s in fixture.signals},
    }
    for kind, ids in known.items():
        missing = [i for i in getattr(related, kind) if i not in ids]
        if missing:
            raise ValueError(f"{item_id}: related {kind} {missing} do not exist")


def _check_v2(fixture: Fixture) -> None:
    _check_required(fixture)
    for kind, ids in (
        ("signal", [s.id for s in fixture.signals]),
        ("opportunity", [o.id for o in fixture.opportunities]),
    ):
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate {kind} id")
    for s in fixture.signals:
        assert s.claim_type is not None
        assert s.implication is not None
        check_claim(f"{s.id} statement", s.claim_type, s.evidence, len(s.metrics))
        check_claim(f"{s.id} implication", s.implication.claim_type, s.evidence, len(s.metrics))
        _check_related(fixture, s.id, s.related)
    for o in fixture.opportunities:
        assert o.thesis_claim_type is not None
        assert o.why_it_matters is not None
        check_claim(f"{o.id} thesis", o.thesis_claim_type, o.evidence, len(o.metrics))
        why = o.why_it_matters.claim_type
        check_claim(f"{o.id} why it matters", why, o.evidence, len(o.metrics))
        for n, risk in enumerate(o.risks, 1):
            # a risk carries no metrics of its own, so it can never be "derived"
            check_claim(f"{o.id} risk {n}", risk.claim_type, risk.evidence, 0)
        _check_related(fixture, o.id, o.related)


def parse_fixture(raw: dict[str, Any]) -> Fixture:
    try:
        return Fixture.model_validate(raw)
    except (ValidationError, ValueError) as exc:
        raise FixtureError(str(exc)) from exc


@cache
def _load_file(path: Path) -> Fixture:
    return parse_fixture(json.loads(path.read_text(encoding="utf-8")))


def newest_fixture_path(workspace_code: str, directory: Path | None = None) -> Path | None:
    """``<CODE>.v<N>.json`` with the highest integer ``N`` (so v10 beats v2); names that do not
    match exactly are ignored."""
    pattern = re.compile(rf"{re.escape(workspace_code)}\.v([1-9][0-9]*)\.json")
    versions = [
        (int(match.group(1)), path)
        for path in (directory or FIXTURE_DIR).glob(f"{workspace_code}.v*.json")
        if (match := pattern.fullmatch(path.name)) is not None
    ]
    return max(versions)[1] if versions else None


def load_fixture(workspace_code: str) -> Fixture | None:
    """The newest fixture for ``workspace_code``, or ``None`` when it has no curated brief."""
    path = newest_fixture_path(workspace_code)
    if path is None:
        return None
    fixture = _load_file(path)
    if fixture.workspace != workspace_code:
        raise FixtureError(f"{path.name}: workspace mismatch")
    return fixture


FixtureLoader = Callable[[str], "Fixture | None"]
