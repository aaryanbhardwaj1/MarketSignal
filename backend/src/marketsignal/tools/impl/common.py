"""Helpers shared by the tool implementations."""

from __future__ import annotations

import re

from marketsignal.tools.contracts import SNIPPET_MAX_CHARS

_WS = re.compile(r"\s+")
ELLIPSIS = "…"


def compact(text: str) -> str:
    return _WS.sub(" ", text).strip()


def snippet(text: str, *, around: int | None = None, limit: int = SNIPPET_MAX_CHARS) -> str:
    """At most ``limit`` characters of ``text`` (whitespace collapsed); ``around`` centres the
    window on that offset of the collapsed text (keyword hits show the match)."""
    flat = compact(text)
    if len(flat) <= limit:
        return flat
    if around is None or around < limit // 2:
        return flat[: limit - 1] + ELLIPSIS
    start = min(around - limit // 3, len(flat) - (limit - 1))
    body = flat[start + 1 : start + limit - 1]
    return ELLIPSIS + body + (ELLIPSIS if start + limit - 1 < len(flat) else "")


def truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[: limit - 1] + ELLIPSIS, True
