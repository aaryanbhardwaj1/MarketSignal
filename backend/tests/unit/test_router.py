import pytest

from marketsignal.runs.router import PERSONA_DEFAULT_MODES, RouteDecision, route


def test_explicit_request_always_wins_over_cues_and_persona() -> None:
    d = route(
        "Compare our survey vs competitor pricing trends",
        requested="standard",
        persona="growth_strategy",
    )
    assert d.decided == "standard"
    assert d.reason == "explicit_request"
    r = route("What did the Q3 review decide?", requested="research", persona="customer_insights")
    assert r.decided == "research"
    assert r.reason == "explicit_request"


def test_explicit_auto_applies_cues_and_overrides_the_persona_default() -> None:
    d = route("What did the Q3 review decide?", requested="auto", persona="growth_strategy")
    assert d.decided == "standard"
    assert d.reason == "auto_no_cue"
    assert d.persona_default == "research"


def test_persona_default_applies_only_without_a_request_mode() -> None:
    assert (
        route("What did the Q3 review decide?", requested=None, persona="growth_strategy").decided
        == "research"
    )
    assert (
        route(
            "Compare survey vs competitor pricing", requested=None, persona="customer_insights"
        ).decided
        == "standard"
    )
    d = route("What did the Q3 review decide?", requested=None, persona="generalist")
    assert d.decided == "standard"
    assert d.reason == "persona_auto_no_cue"


@pytest.mark.parametrize(
    ("question", "cue"),
    [
        ("Evaluate the hypothesis that Gen Z pays for fit personalization", "hypothesis"),
        ("How does our return rate compare with Kinetic Lab?", "comparison"),
        ("Northstar vs Pace on delivery speed", "comparison"),
        ("Which competitors offer build-to-order shoes?", "comparison"),
        ("How many reviews mention sizing?", "numeric"),
        ("What % of buyers name fit as the top frustration?", "numeric"),
        ("What is the trend in social first-response time?", "numeric"),
        ("Break down satisfaction by segment", "numeric"),
        ("What do customer reviews and our financial results say about returns?", "multi_class"),
    ],
)
def test_cue_rules_select_research(question: str, cue: str) -> None:
    d = route(question, requested="auto", persona="generalist")
    assert d.decided == "research"
    assert cue in d.cues
    # Phase 5: quantitative asks are analytics tasks (routed for the analytics tools).
    assert d.reason in ("auto_cues", "analytics_task")


@pytest.mark.parametrize(
    "question",
    [
        "What did the Q3 strategy review decide about personalization?",
        "What delivery window does Kinetic Lab quote?",
        "Summarize the brand strategy memo",
    ],
)
def test_simple_lookups_route_standard(question: str) -> None:
    d = route(question, requested="auto", persona="generalist")
    assert d.decided == "standard"
    assert d.cues == ()


def test_follow_up_cue_needs_earlier_context() -> None:
    q = "What about those returns in the northeast?"
    assert route(q, requested="auto", persona="generalist").decided == "standard"
    d = route(
        q,
        requested="auto",
        persona="generalist",
        recent_questions=("Why do online buyers return shoes?",),
    )
    assert d.decided == "research"
    assert "follow_up" in d.cues


def test_routing_is_deterministic_and_serializable() -> None:
    q = "Compare customer reviews with competitor claims on comfort"
    first = route(q, requested=None, persona="brand_strategy")
    assert all(route(q, requested=None, persona="brand_strategy") == first for _ in range(20))
    payload = first.as_dict()
    assert payload == {
        "requested": None,
        "persona_default": "research",
        "decided": "research",
        "reason": "persona_default",
        "cues": list(first.cues),
        "task_type": first.task_type,
    }


def test_unknown_persona_behaves_like_generalist_and_unknown_mode_is_rejected() -> None:
    assert route("What did the review decide?", requested=None, persona="nobody").decided == (
        "standard"
    )
    with pytest.raises(ValueError, match="mode"):
        route("x", requested="turbo", persona="generalist")  # type: ignore[arg-type]
    assert set(PERSONA_DEFAULT_MODES) >= {
        "generalist",
        "growth_strategy",
        "customer_insights",
        "brand_strategy",
        "marketing_strategy",
    }
    assert isinstance(route("x", requested=None, persona="generalist"), RouteDecision)


@pytest.mark.parametrize(
    ("question", "task"),
    [
        ("What complaints do younger customers mention about delivery?", "retrieval"),
        ("What did the Q3 strategy review decide about personalization?", "retrieval"),
        (
            "What percentage of respondents aged 18-21 named delivery speed as their top "
            "pain point?",
            "analytics",
        ),
        ("How many reviews gave the Pivot Trainer a rating of 2 or lower?", "analytics"),
        ("What is the average NPS by region?", "analytics"),
        ("Which three SKUs have the highest return rate?", "analytics"),
        (
            "Which segment reports the highest delivery dissatisfaction, and what do those "
            "customers say is causing it?",
            "mixed",
        ),
        ("What share of reviews mention sizing problems and what do they complain about?", "mixed"),
    ],
)
def test_task_type_is_classified_deterministically(question: str, task: str) -> None:
    d = route(question, requested="auto", persona="generalist")
    assert d.task_type == task
    if task in ("analytics", "mixed"):
        assert d.decided == "research"  # only the agent has the analytics tools
        assert task in d.cues


def test_explicit_standard_is_honoured_for_an_analytics_question() -> None:
    d = route("What is the average NPS by region?", requested="standard", persona="generalist")
    assert d.decided == "standard"
    assert d.task_type == "analytics"  # recorded, so the trace shows the user overrode it
    assert d.as_dict()["task_type"] == "analytics"


@pytest.mark.parametrize(
    ("question", "task"),
    [
        ("What has the outlet averaged for weekly orders?", "analytics"),
        ("Compute the correlation between price and rating.", "analytics"),
        ("What did the sales table show for margin in March?", "analytics"),
        ("What share of shoppers chose express, and what do they want improved?", "mixed"),
        ("What share name zippers as the issue, and which models are failing them?", "mixed"),
        ("What rate does the board memo cite, and what is the conversion in the data?", "mixed"),
        (
            "What percentage of SKUs exceed a 10% return rate per the performance sheet?",
            "analytics",
        ),
    ],
)
def test_phase5_task_cues(question: str, task: str) -> None:
    assert route(question, requested="auto", persona="generalist").task_type == task


@pytest.mark.parametrize(
    "question",
    ["What does 'premium' mean for Gen Z?", "Which project has the highest priority in the memo?"],
)
def test_ambiguous_quant_words_without_metric_context_stay_retrieval(question: str) -> None:
    """Security review finding 23: no agent run (or persona override) for a document question."""
    d = route(question, requested=None, persona="customer_insights")
    assert d.task_type == "retrieval"
    assert d.decided == "standard"
