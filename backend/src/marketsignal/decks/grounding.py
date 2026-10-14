"""Request-time grounding checks and the bullet shape.

The insights service has already re-verified every reference and recomputed every metric; this
module only decides what of that may be shown. A reference is usable only when ``verified``; a
metric only when its value was computed. A claim is shown only when its grounding survives:

* observed / forecast -> at least one verified supporting passage;
* derived             -> at least one computed metric;
* inference / hypothesis (and untyped v1 claims) -> a verified passage or a computed metric.

A forecast on an item that is not fully verified is shown as a hypothesis: the passage that
states the projection may be the one that no longer verifies.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from marketsignal.decks.models import CLAIM_LABELS


def verified(refs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in refs if r.get("integrity") == "verified" and r.get("quote")]


def supporting(refs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in verified(refs) if r.get("role") == "support"]


def live_metrics(metrics: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in metrics if m.get("value") is not None and m.get("display")]


def effective_claim(claim_type: str | None, integrity: str) -> str | None:
    if claim_type == "forecast" and integrity != "verified":
        return "hypothesis"
    return claim_type


def grounded(
    claim_type: str | None,
    support: list[dict[str, Any]],
    refs: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> bool:
    if claim_type in ("observed", "forecast"):
        return bool(support)
    if claim_type == "derived":
        return bool(metrics)
    return bool(refs) or bool(metrics)


def bullet(
    text: str,
    claim_type: str | None = None,
    cites: Iterable[int] = (),
    *,
    heading: str | None = None,
    level: int = 0,
) -> dict[str, Any]:
    return {
        "heading": heading,
        "text": text,
        "claim_type": claim_type,
        "label": CLAIM_LABELS.get(claim_type or ""),
        "cites": sorted(set(cites)),
        "level": level,
    }
