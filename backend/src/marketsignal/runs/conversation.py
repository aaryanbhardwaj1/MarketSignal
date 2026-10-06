"""Bounded, deterministic conversation state (plan §20; Phase 3 scope).

No LLM call and no transcript replay. After each verified answer the conversation keeps:
* a rolling summary of at most ``SUMMARY_MAX_CHARS`` (~400 tokens) built from the Answer
  sections of recent verified answers, newest first, citation markers removed and
  ``[inference]`` units left out (the model is told the summary is verified);
* the last two user questions;
* up to 20 recently cited canonical handles.
Retrieval uses the current question only (``standalone_query`` = the question): follow-up
rewriting is deferred to the Phase 4 router. Synthesis receives the summary and the two
previous questions, so per-turn input stays O(pack + bounded state).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from marketsignal.generation.contract import split_units
from marketsignal.generation.types import CANONICAL_RE, INFERENCE_TAG

SUMMARY_MAX_CHARS = 1600
RECENT_QUESTIONS = 2
RECENT_HANDLES = 20
_SPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"(?<=\S) +([.,;:!?])(?=\s|$)")


def answer_digest(sections: dict[str, object]) -> str:
    """Evidence-backed Answer units only: ``[inference]`` units are guesses, and the summary is
    presented to the model as verified context, so they are left out (not untagged)."""
    answer = sections.get("answer") or []
    units = [str(u) for u in answer] if isinstance(answer, list) else split_units(str(answer))
    text = " ".join(u for u in units if INFERENCE_TAG not in u.lower())
    text = _SPACE.sub(" ", CANONICAL_RE.sub("", text)).strip()
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text)


def next_state(
    *,
    summary: str,
    recent_questions: Sequence[str],
    recent_handles: Sequence[str],
    question: str,
    sections: dict[str, object],
    cited_handles: Sequence[str],
) -> tuple[str, list[str], list[str]]:
    digest = answer_digest(sections)
    combined = f"Q: {question} A: {digest}" if digest else ""
    new_summary = " ".join(p for p in (combined, summary) if p)
    if len(new_summary) > SUMMARY_MAX_CHARS:
        new_summary = new_summary[:SUMMARY_MAX_CHARS].rsplit(" ", 1)[0] + " …"
    questions = [*recent_questions, question][-RECENT_QUESTIONS:]
    handles = list(dict.fromkeys([*cited_handles, *recent_handles]))[:RECENT_HANDLES]
    return new_summary, questions, handles
