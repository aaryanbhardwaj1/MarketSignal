"""Deck request body and the business labels the composer writes into slides."""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_SIGNALS = 30
MAX_OPPORTUNITIES = 10
MAX_ANALYSES = 10

ItemId = Annotated[str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)]

# Claim types that must carry a visible tag; observed and derived stay untagged.
CLAIM_LABELS = {"inference": "Inference", "hypothesis": "Hypothesis", "forecast": "Forecast"}

OPPORTUNITY_STATUS = {
    "supported": "Supported",
    "emerging": "Emerging",
    "mixed_evidence": "Mixed evidence",
    "needs_research": "Needs validation",
}
SIGNAL_STATUS = {
    "strong_evidence": "Strong evidence",
    "emerging": "Emerging",
    "mixed_evidence": "Mixed evidence",
    "needs_validation": "Needs validation",
}
SIGNAL_KIND = {
    "emerging_signal": "Emerging signal",
    "risk_blocker": "Risk or blocker",
    "competitor_finding": "Competitor finding",
    "optimization": "Optimization opportunity",
    "future_outlook": "Future outlook",
}


def _clean(value: str | None) -> str | None:
    """Collapse whitespace (including control characters); empty becomes ``None``."""
    if value is None:
        return None
    text = " ".join(value.split())
    return text or None


class DeckRequest(BaseModel):
    """Which curated items to present. The workspace always comes from the trusted scope."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)
    question: str | None = Field(default=None, max_length=300)
    signal_ids: list[ItemId] = Field(default_factory=list, max_length=MAX_SIGNALS)
    opportunity_ids: list[ItemId] = Field(default_factory=list, max_length=MAX_OPPORTUNITIES)
    analysis_ids: list[ItemId] = Field(default_factory=list, max_length=MAX_ANALYSES)

    @model_validator(mode="after")
    def _normalise(self) -> Self:
        if not (self.signal_ids or self.opportunity_ids or self.analysis_ids):
            raise ValueError("select at least one signal, opportunity or analysis")
        self.title = _clean(self.title)
        self.question = _clean(self.question)
        self.signal_ids = list(dict.fromkeys(self.signal_ids))
        self.opportunity_ids = list(dict.fromkeys(self.opportunity_ids))
        self.analysis_ids = list(dict.fromkeys(self.analysis_ids))
        return self
