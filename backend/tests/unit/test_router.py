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
    assert d.reason == "auto_cues"


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
