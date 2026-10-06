"""Deterministic, user-overridable mode router (plan §3 step 4; ADR-0015; ADR-0018).

Precedence, highest first:

1. an explicit request mode ``standard`` | ``research``;
2. an explicit request ``auto``: the cue rules (this overrides the persona default);
3. the persona's default mode ``standard`` | ``research``;
4. a persona default of ``auto`` (or no/unknown persona): the cue rules.

The cue rules select ``research`` for hypothesis/evaluation wording, comparisons, numeric or
analytic asks, two or more source-class cues, or a follow-up that needs earlier conversation
context; everything else is ``standard``. The router never calls a model: the same inputs
always give the same decision, and the decision (with the cues that fired) is recorded in
``query_runs.route`` and the ``run_started`` event.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

Mode = Literal["standard", "research"]
TaskType = Literal["retrieval", "analytics", "mixed"]
RequestedMode = Literal["auto", "standard", "research"]
Reason = Literal[
    "explicit_request",
    "auto_cues",
    "auto_no_cue",
    "persona_default",
    "persona_auto_cues",
    "persona_auto_no_cue",
    "analytics_task",
]

# ADR-0018: Customer Insights → standard; Growth, Brand, Marketing → research; Generalist → auto.
PERSONA_DEFAULT_MODES: dict[str, RequestedMode] = {
    "generalist": "auto",
    "growth_strategy": "research",
    "customer_insights": "standard",
    "brand_strategy": "research",
    "marketing_strategy": "research",
}

_I = re.IGNORECASE
_HYPOTHESIS = re.compile(
    r"\b(hypothes[ie]s|evaluate|assess whether|test whether|is it true that|validate)\b", _I
)
_COMPARISON = re.compile(
    r"\b(vs\.?|versus|compared?\b|comparison|relative to|which competitors?)(?=\W|$)", _I
)
_NUMERIC = re.compile(
    r"%|\b(how many|percent(age)?|trends?|trending|by (segment|region|channel|cohort)|"
    r"break(s)? down|breakdown)\b",
    _I,
)
# Plural "reviews" only: a singular "review" is usually a meeting or document ("Q3 review").
_CLASS_CUES: dict[str, re.Pattern[str]] = {
    "customer": re.compile(
        r"\b(customers?|surveys?|reviews|interviews?|respondents?|shoppers?|buyers?|"
        r"focus groups?)\b",
        _I,
    ),
    "competitor": re.compile(r"\b(competitors?|competitive|rivals?)\b", _I),
    "market": re.compile(r"\b(market (size|share|growth)|industry|category growth)\b", _I),
    "financial": re.compile(r"\b(revenue|margins?|financials?|profit|earnings|budget|spend)\b", _I),
    "internal": re.compile(r"\b(roadmap|pilot|internal|memo|leadership|strategy review)\b", _I),
}
# Task type (Phase 5): quantitative asks need the deterministic analytics tools (only the agent
# has them); qualitative asks need evidence retrieval; both together are mixed.
_QUANT = re.compile(
    r"%|\b(how many|how much|(what|which) (percentage|percent|share|proportion|fraction)|"
    r"percentage of|share of|proportion of|averag(e|ed|es|ing)|median|sum of|"
    r"count of|calculate|compute|correlat(e|ion)|"
    r"number of|top \d+|bottom \d+|top (three|five|ten)|rank(ing)?|"
    r"by (segment|region|channel|age( group)?|category|month|quarter|product|sku)|"
    r"break(s)? down|breakdown|distribution)\b"
    # ambiguous words count only near a metric noun ("highest return rate", "mean NPS"), so
    # "what does premium mean" or "highest priority" stay document questions (review finding)
    r"|\b(mean|total|highest|lowest)\b(\W+\w+){0,3}?\W+(rate|share|nps|rating|score|revenue|"
    r"sales|count|number|percent|value|margin|conversion|returns?|price|units|orders|"
    r"sessions|aov|growth|spend|satisfaction|dissatisfaction)\b"
    r"|\bgr(ow|ows|ew|owing|owth)\b\W+(the\W+)?(fastest|slowest)\b|\b(fastest|slowest)[- ]growing\b"
    # a figure looked up in a data table ("what did the channel table show for conversion")
    r"|\b(table|data|dataset|spreadsheet)\b.{0,60}\b(figure|conversion|rate|margin|aov|"
    r"sessions|orders|units|share|value)\b"
    r"|\b(figure|conversion|rate|margin|aov|sessions|orders|units|value)\b.{0,60}\b(table|"
    r"data|dataset|spreadsheet)\b",
    _I,
)
_QUAL = re.compile(
    r"\b(say|says|said|saying|mention(s|ed)?|complain(t|ts|s|ing)?|describe[sd]?|feel|think|"
    r"why|reasons?|caus(e|es|ed|ing)|themes?|quotes?|verbatims?|opinions?|want(s|ed)?|"
    r"wish(es)?|failing|cites?|cited)\b",
    _I,
)
_FOLLOW_UP = re.compile(
    r"^\s*(and|also|what about|how about|why|so)\b|^\W*(\w+\W+){0,3}(it|they|that|those|these|"
    r"this|them)\b",
    _I,
)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    requested: RequestedMode | None
    persona_default: RequestedMode
    decided: Mode
    reason: Reason
    cues: tuple[str, ...]
    task_type: TaskType = "retrieval"

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "persona_default": self.persona_default,
            "decided": self.decided,
            "reason": self.reason,
            "cues": list(self.cues),
            "task_type": self.task_type,
        }


def task_type(question: str) -> TaskType:
    """Deterministic task type: quantitative and qualitative cues together → mixed."""
    quant, qual = bool(_QUANT.search(question)), bool(_QUAL.search(question))
    if quant and qual:
        return "mixed"
    return "analytics" if quant else "retrieval"


def cues(question: str, recent_questions: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The research cues that fire for ``question``, in a fixed order."""
    fired: list[str] = []
    if _HYPOTHESIS.search(question):
        fired.append("hypothesis")
    if _COMPARISON.search(question):
        fired.append("comparison")
    if _NUMERIC.search(question):
        fired.append("numeric")
    if sum(1 for rx in _CLASS_CUES.values() if rx.search(question)) >= 2:
        fired.append("multi_class")
    if recent_questions and _FOLLOW_UP.search(question):
        fired.append("follow_up")
    return tuple(fired)


def route(
    question: str,
    *,
    requested: RequestedMode | None,
    persona: str,
    recent_questions: tuple[str, ...] = (),
) -> RouteDecision:
    if requested not in (None, "auto", "standard", "research"):
        raise ValueError(f"unknown mode {requested!r}")
    persona_default = PERSONA_DEFAULT_MODES.get(persona, "auto")
    task = task_type(question)
    if requested in ("standard", "research"):  # the user's choice always wins
        return RouteDecision(requested, persona_default, requested, "explicit_request", (), task)
    if task != "retrieval":
        # Exact quantitative work needs the deterministic analytics tools, which only the
        # bounded agent can call: this overrides a persona's soft default (ADR-0015 note).
        fired = (*cues(question, recent_questions), task)
        return RouteDecision(requested, persona_default, "research", "analytics_task", fired, task)
    if requested is None and persona_default in ("standard", "research"):
        return RouteDecision(None, persona_default, persona_default, "persona_default", (), task)
    fired = cues(question, recent_questions)
    decided: Mode = "research" if fired else "standard"
    if requested == "auto":
        reason: Reason = "auto_cues" if fired else "auto_no_cue"
    else:
        reason = "persona_auto_cues" if fired else "persona_auto_no_cue"
    return RouteDecision(requested, persona_default, decided, reason, fired, task)
