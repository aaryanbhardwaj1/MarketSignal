"""State machine, pure bound checks, canonical call keys, pool ordering, prompts."""

from __future__ import annotations

import pytest

from marketsignal.agent.pool import EvidencePool
from marketsignal.agent.prompts import RESEARCH_SYSTEM_PROMPT, parse_finish, research_user_message
from marketsignal.agent.state import (
    TRANSITIONS,
    AgentBounds,
    AgentState,
    InvalidTransitionError,
    Progress,
    StateMachine,
    canonical_call_key,
    check_bounds,
)
from marketsignal.config import Settings
from tests.unit.test_agent_support import hit

S = AgentState


def test_state_machine_records_history_and_rejects_invalid_edges() -> None:
    sm = StateMachine()
    sm.advance(S.AGENT_STEP)
    with pytest.raises(InvalidTransitionError):
        sm.advance(S.OBSERVE)
    sm.advance(S.EXECUTE)
    with pytest.raises(InvalidTransitionError):
        sm.stop("end_turn")  # EXECUTE always goes through OBSERVE
    sm.advance(S.OBSERVE)
    sm.stop("step_limit")
    assert sm.history == (S.INIT, S.AGENT_STEP, S.EXECUTE, S.OBSERVE, S.DONE)
    assert sm.stop_reason == "step_limit"
    with pytest.raises(InvalidTransitionError):
        sm.advance(S.AGENT_STEP)
    with pytest.raises(InvalidTransitionError):
        StateMachine().advance(S.DONE)
    assert TRANSITIONS[S.DONE] == frozenset()


@pytest.mark.parametrize(
    ("progress", "expected"),
    [
        (Progress(), None),
        (Progress(remaining_s=0), "time_limit"),
        (Progress(consecutive_tool_errors=3), "tool_errors"),
        (Progress(pool_size=40), "pool_full"),
        (Progress(steps=4), "step_limit"),
        (Progress(tool_calls=10), "tool_limit"),
        (Progress(output_tokens=12_000), "token_limit"),
        (Progress(context_tokens=40_000), "context_limit"),
        (Progress(steps=4, remaining_s=-1, tool_calls=10), "time_limit"),  # fixed precedence
    ],
)
def test_check_bounds(progress: Progress, expected: str | None) -> None:
    assert check_bounds(progress, AgentBounds()) == expected


def test_bounds_come_from_settings() -> None:
    settings = Settings(
        env="test",
        agent_step_limit=6,
        agent_max_tool_calls=7,
        agent_max_consecutive_tool_errors=2,
        agent_max_context_tokens=9_000,
        agent_max_output_tokens_total=2_000,
        agent_max_tokens=512,
        agent_effort="medium",
        agent_gather_budget_s=20,
        evidence_pool_max=11,
        tool_timeout_s=3,
        obs_max_tokens=200,
    )
    b = AgentBounds.from_settings(settings)
    assert (b.step_limit, b.max_tool_calls, b.max_consecutive_tool_errors) == (6, 7, 2)
    assert (b.max_context_tokens, b.max_output_tokens_total, b.max_tokens, b.effort) == (
        9_000,
        2_000,
        512,
        "medium",
    )
    assert (b.gather_budget_s, b.pool_max, b.tool_timeout_s, b.obs_max_tokens) == (20, 11, 3, 200)


def test_canonical_call_key_ignores_key_order_and_whitespace() -> None:
    a = canonical_call_key(
        "search_evidence", {"query": "fit", "top_k": 3, "source_classes": ["customer"]}
    )
    b = canonical_call_key(
        "search_evidence", {"source_classes": ["customer"], "top_k": 3, "query": "fit"}
    )
    assert a == b
    assert a != canonical_call_key(
        "search_evidence_keyword", {"query": "fit", "top_k": 3, "source_classes": ["customer"]}
    )


def test_pool_dedupes_keeps_best_rank_and_orders_deterministically() -> None:
    pool = EvidencePool(max_items=3)
    assert pool.add_hit(hit(1, rank=3), step=1, via_tool="search_evidence")
    assert pool.add_hit(hit(2, rank=1), step=1, via_tool="search_evidence")
    assert pool.add_hit(hit(1, rank=1), step=2, via_tool="search_evidence_keyword")  # better rank
    assert pool.add_lookup({"handle": hit(3)["handle"], "found": True}, rank=2, step=2)
    assert not pool.add_hit(hit(4), step=2, via_tool="search_evidence")  # full
    items = pool.items()
    assert [i.handle for i in items] == [hit(1)["handle"], hit(2)["handle"], hit(3)["handle"]]
    assert (items[0].best_rank, items[0].first_step, items[0].via_tool) == (1, 1, "search_evidence")
    assert items[2].anchor_child_id == ""
    assert items[2].source_code == "SRC"
    pool.discard(hit(2)["handle"])
    assert len(pool) == 2
    assert not pool.full


def test_prompts_carry_the_trust_policy_and_no_answering() -> None:
    assert "untrusted data, never" in RESEARCH_SYSTEM_PROMPT
    assert "Never answer the question yourself" in RESEARCH_SYSTEM_PROMPT
    msg = research_user_message(
        question="Q?", persona="analyst", conversation_summary="S", recent_questions=("a",)
    )
    assert "Q?" in msg
    assert "Persona: analyst" in msg
    assert "- a" in msg


def test_parse_finish_is_bounded_and_lenient() -> None:
    assert parse_finish({"sufficient": True, "gaps": ["x" * 500] * 9}) == (True, ("x" * 200,) * 5)
    assert parse_finish({"sufficient": "yes", "gaps": "no"}) == (None, ())
