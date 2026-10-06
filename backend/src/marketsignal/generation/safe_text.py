"""Instruction-like text detection for deterministic presentation (Phase 5, A2).

The evidence-only fallback quotes document text verbatim. A planted prompt injection (e.g. a
product review saying "IMPORTANT SYSTEM NOTE FOR AI ASSISTANTS: ignore all previous
instructions ...") must not be shown prominently as "the most relevant evidence". Storage is
never changed: canonical source text stays untouched and the citation still opens the source
viewer, which shows the original. This module only decides what a *presentation* withholds.

Detection is conservative and sentence-scoped. A sentence is instruction-like when it matches
one of :data:`PATTERNS` - phrases addressed to an AI system or that try to override its
instructions, which ordinary market-research text does not use:

* override phrases: "ignore (all) previous/prior/earlier/above instructions", "disregard /
  forget / override ... instructions / the user's question / the system prompt";
* addressing an AI: "system note/prompt/message/instruction", "note/message to AI
  assistants/models/agents/tools", "AI assistants:", "you are now an AI / in X mode / acting
  as", "new instructions:";
* output demands: "respond/answer/reply/output only with", "only respond with";
* role-play / chat-template markers: "pretend to be / you are", "role-play as", a sentence
  starting "system:" / "assistant:", ``<|im_start|>``-style tokens, ``[INST]``.

Ordinary phrases such as "act as a distributor", "customers ignore prices", "shoppers
disregard previous perks", "demand for AI assistants" or "you are now a member" do not match
(``tests/unit/test_fallback_safe_presentation.py`` pins both sides).
"""

from __future__ import annotations

import re
from typing import Final

WITHHELD_MARKER: Final = "[instruction-like text withheld — open the source to inspect]"

PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bignore\s+(?:all\s+|any\s+)?(?:of\s+)?(?:the\s+|your\s+|my\s+)?"
        r"(?:previous|prior|earlier|above|preceding|former)\s+"
        r"(?:instructions?|prompts?|messages?|rules|directions|context)\b",
        r"\b(?:disregard|forget|override)\b[^.!?\n]{0,40}?\b(?:instructions?|system\s+prompt"
        r"|user'?s\s+(?:question|request))",
        r"\bsystem\s+(?:note|prompt|message|instruction|override)s?\b",
        r"\b(?:note|message|instructions?|attention|notice)\s+(?:for|to)\s+(?:all\s+)?(?:ai|llm)"
        r"\s+(?:assistants?|models?|agents?|systems?|tools?)\b",
        r"\b(?:ai|llm)\s+(?:assistants?|models?|agents?|systems?|tools?)\s*:",
        r"\byou\s+are\s+now\s+(?:an?\s+)?(?:ai|assistant|chatbot|model|unrestricted|jailbroken"
        r"|acting\s+as|in\s+\w+\s+mode)\b",
        r"\bnew\s+instructions?\s*:",
        r"\b(?:respond|answer|reply|output)\s+(?:only|solely|exclusively)\s+with\b",
        r"\bonly\s+(?:respond|answer|reply|output)\s+with\b",
        r"\bpretend\s+(?:to\s+be|you\s+are)\b",
        r"\brole-?play\s+as\b",
        r"^\s*(?:system|assistant)\s*:",
        r"<\|?\s*(?:system|im_start|im_end|endoftext)\s*\|?>",
        r"\[/?INST\]",
    )
)

# Sentence-ish segments: up to and including terminal punctuation, or a line.
# A "." inside a token ("$41.2", "e.g.") does not end a sentence.
_SEGMENT_RE: Final = re.compile(r"(?:[^.!?\n]|[.!?]+(?=\S))*(?:[.!?]+(?=\s|$)|\n|$)")


def is_instruction_like(text: str) -> bool:
    return any(pattern.search(text) for pattern in PATTERNS)


def instruction_spans(text: str) -> tuple[tuple[int, int], ...]:
    """``(start, end)`` character spans of instruction-like sentences, merged when adjacent."""
    spans: list[tuple[int, int]] = []
    for match in _SEGMENT_RE.finditer(text):
        segment = match.group(0)
        if not segment.strip() or not is_instruction_like(segment):
            continue
        start = match.start() + (len(segment) - len(segment.lstrip()))
        end = match.end()
        if spans and text[spans[-1][1] : start].strip() == "":
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    return tuple(spans)
