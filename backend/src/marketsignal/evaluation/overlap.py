"""Retriever-independent lexical-overlap hardness (plan §27).

How much of a question's content vocabulary already appears in the planted anchor. It is
computed with a deliberately simple, self-contained normaliser (lowercase, a fixed stopword
list, light suffix stripping) - *not* Postgres FTS and not the embedder - so the bins do not
favour either retriever. Every arm is reported per bin: low-overlap items are where lexical
search is expected to struggle, high-overlap items where dense search has no excuse.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_STOPWORD_TEXT = (
    "a an the of in on for to and or is are was were be been by with from at as that this these "
    "those it its than more most into over per vs their they our we what which who whom how why "
    "when where did does do has have had about across between among any all each there here "
    "not no can could would should will shall may might much many very also just only"
)
STOPWORDS = frozenset(_STOPWORD_TEXT.split())
_TOKEN = re.compile(r"[a-z0-9]+(?:[.%][a-z0-9]+)*%?")
_SUFFIXES = ("ingly", "edly", "ing", "ies", "ied", "ers", "est", "ed", "es", "er", "ly", "s")
BINS = (("low", 0.0), ("mid", 0.34), ("high", 0.67))


def _stem(token: str) -> str:
    if token[0].isdigit():
        return token
    for suffix in _SUFFIXES:
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def content_stems(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


def overlap_share(question: str, anchors: Sequence[str]) -> float:
    """Share of the question's distinct content stems found in any anchor (0..1)."""
    q = set(content_stems(question))
    if not q:
        return 0.0
    a: set[str] = set()
    for anchor in anchors:
        a |= set(content_stems(anchor))
    return len(q & a) / len(q)


def longest_shared_ngram(question: str, anchor: str) -> int:
    q, a = content_stems(question), content_stems(anchor)
    best = 0
    prev = [0] * (len(a) + 1)
    for i in range(1, len(q) + 1):
        cur = [0] * (len(a) + 1)
        for j in range(1, len(a) + 1):
            if q[i - 1] == a[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def overlap_bin(share: float) -> str:
    name = BINS[0][0]
    for label, floor in BINS:
        if share >= floor:
            name = label
    return name
