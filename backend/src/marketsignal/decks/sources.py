"""Deck-wide numbered sources.

A source is either a verified evidence passage (keyed by handle and quote) or a computed
analysis (keyed by analysis id). Each gets one number, in order of first citation, so a bullet's
``[n]``, the slide's speaker notes and the appendix always agree. Only verified passages and
computed analyses can be registered; the composer never hands anything else in.
"""

from __future__ import annotations

from typing import Any


class Sources:
    def __init__(self, analyses: dict[str, dict[str, Any]]) -> None:
        self._analyses = analyses
        self._index: dict[tuple[str, str], int] = {}
        self._items: list[dict[str, Any]] = []

    def _add(self, key: tuple[str, str], entry: dict[str, Any]) -> int:
        found = self._index.get(key)
        if found is not None:
            return found
        n = len(self._items) + 1
        self._index[key] = n
        self._items.append({"n": n, **entry})
        return n

    def passage(self, ref: dict[str, Any]) -> int:
        """Number for a verified evidence reference (``integrity == "verified"``)."""
        assert ref["integrity"] == "verified"
        assert ref["quote"]
        source = ref.get("source") or {}
        return self._add(
            ("passage", f"{ref['handle']}\n{ref['quote']}"),
            {
                "kind": "passage",
                "source_title": source.get("title") or "Untitled source",
                "locator": ref.get("locator_label") or "",
                "quote": ref["quote"],
                "handle": ref["handle"],
            },
        )

    def analysis(self, analysis_id: str) -> int | None:
        """Number for a computed analysis, or ``None`` when it is missing or not computed."""
        payload = self._analyses.get(analysis_id)
        if payload is None or payload.get("status") != "computed":
            return None
        provenance = payload.get("provenance") or {}
        return self._add(
            ("analysis", analysis_id),
            {
                "kind": "analysis",
                "source_title": provenance.get("source_title") or "Dataset",
                "locator": f"Analysis: {payload['title']}",
                "quote": None,
                "handle": f"{provenance.get('dataset', '')} analysis {analysis_id}".strip(),
            },
        )

    def get(self, n: int) -> dict[str, Any]:
        return self._items[n - 1]

    def all(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._items]
