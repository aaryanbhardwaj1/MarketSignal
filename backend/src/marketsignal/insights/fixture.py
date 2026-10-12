"""The curated brief fixture: strict schema and loader.

One hand-authored JSON file per workspace (``fixtures/<WORKSPACE>.v<N>.json``). Every quote is
an exact sentence of an evidence passage, and every number is a named analysis that the
deterministic engine recomputes on request. Loading fails closed: an unknown field, a handle
outside the fixture's workspace, a superseded or planted handle, or a metric that points at a
value the fixture does not pin, is a :class:`FixtureError`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from marketsignal.analytics.schema import parse_dataset_id
from marketsignal.evidence.handles import parse_handle
from marketsignal.tools.analytics_contracts import AggregateIn, FilterRowsIn, GroupCompareIn

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SCHEMA_VERSION = 1
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

    @model_validator(mode="after")
    def _check(self) -> AnalysisSpec:
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


class SignalSpec(_Model):
    id: str
    category: str
    title: str
    statement: str
    evidence: list[EvidenceSpec] = Field(min_length=1)
    metrics: list[MetricSpec] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


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


class CorpusEntry(_Model):
    version: int = Field(ge=1)


class Fixture(_Model):
    schema_version: Literal[1]
    fixture_version: str
    workspace: str
    label: Literal["Curated analyst brief"]
    corpus: dict[str, CorpusEntry]
    analyses: list[AnalysisSpec]
    signals: list[SignalSpec]
    opportunities: list[OpportunitySpec]

    def all_evidence(self) -> list[EvidenceSpec]:
        return [e for s in self.signals for e in s.evidence] + [
            e for o in self.opportunities for e in o.evidence
        ]

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


def parse_fixture(raw: dict[str, Any]) -> Fixture:
    try:
        return Fixture.model_validate(raw)
    except (ValidationError, ValueError) as exc:
        raise FixtureError(str(exc)) from exc


@cache
def _load_file(path: Path) -> Fixture:
    return parse_fixture(json.loads(path.read_text(encoding="utf-8")))


def load_fixture(workspace_code: str) -> Fixture | None:
    """The newest fixture for ``workspace_code``, or ``None`` when it has no curated brief."""
    candidates = sorted(FIXTURE_DIR.glob(f"{workspace_code}.v*.json"))
    if not candidates:
        return None
    fixture = _load_file(candidates[-1])
    if fixture.workspace != workspace_code:
        raise FixtureError(f"{candidates[-1].name}: workspace mismatch")
    return fixture


FixtureLoader = Callable[[str], "Fixture | None"]
