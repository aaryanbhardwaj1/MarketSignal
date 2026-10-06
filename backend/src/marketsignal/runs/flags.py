"""Run degradation flags, termination precedence and status text (plan §28)."""

from __future__ import annotations

# Degradation flags (plan §28).
EVIDENCE_EMPTY = "EVIDENCE_EMPTY"
LLM_SYNTHESIS_UNAVAILABLE = "LLM_SYNTHESIS_UNAVAILABLE"
MODEL_REFUSAL = "MODEL_REFUSAL"
GENERATION_TRUNCATED = "GENERATION_TRUNCATED"
CITATION_VERIFICATION_FAILED = "CITATION_VERIFICATION_FAILED"
PACK_BUDGET_TRUNCATED = "PACK_BUDGET_TRUNCATED"
SOURCE_DELETED_DURING_RUN = "SOURCE_DELETED_DURING_RUN"
RUN_TIMEOUT = "RUN_TIMEOUT"
RETRIEVAL_TIMEOUT = "RETRIEVAL_TIMEOUT"
RETRIEVAL_FLAGS = frozenset(
    {"RETRIEVAL_LEXICAL_FALLBACK", "RETRIEVAL_DENSE_UNAVAILABLE", "RERANKER_UNAVAILABLE"}
)
# A finished run's conversation summary could not be updated (best effort after ``final``).
CONVERSATION_STATE_NOT_UPDATED = "CONVERSATION_STATE_NOT_UPDATED"
# Research mode was requested but no agent is configured: the standard gather ran instead.
RESEARCH_UNAVAILABLE = "RESEARCH_UNAVAILABLE"
PRECEDENCE = (
    "cancelled",
    "timeout",
    "tool_failure",
    "no_relevant_evidence",
    "generation_unavailable",
    "retrieval_degraded",
    "completed_with_limited_evidence",
    "completed",
)
STATUS = {
    "planning": "Planning the research",
    "searching": "Searching workspace evidence",
    "analyzing": "Assembling the evidence pack",
    "synthesizing": "Writing a grounded answer",
    "verifying": "Verifying citations and numbers",
}


def termination_state(states: set[str]) -> str:
    """Highest-precedence state among those reached (plan §28)."""
    return next((s for s in PRECEDENCE if s in states), "completed")
