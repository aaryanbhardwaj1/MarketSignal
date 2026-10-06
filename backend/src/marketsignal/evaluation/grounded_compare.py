"""Paired standard-vs-research comparison of two grounded-evaluation runs (Phase 4, ADR-0015).

Operates on the per-item dicts of ``results-standard.json`` / ``results-research.json``
(``ItemOutcome.as_dict``), paired by item id; items present in only one run are listed under
``unpaired`` and excluded. Every delta is research - standard.

* rate metrics (booleans per item): both rates, the paired difference with a paired-bootstrap
  95% CI over the 0/1 differences, and the exact McNemar test on discordant pairs;
* mean metrics: per-item paired difference over items where both runs have a value, with a
  paired-bootstrap 95% CI (``stats.paired_bootstrap_diff``, fixed seed);
* per category: the same means/rates and deltas without CIs (categories are 5-12 items).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from marketsignal.evaluation.stats import (
    BOOTSTRAP_SAMPLES,
    mcnemar_exact,
    paired_bootstrap_diff,
)

Getter = Callable[[dict[str, Any]], Any]


def _check(key: str) -> Getter:
    return lambda item: (item.get("checks") or {}).get(key)


def _metric(key: str) -> Getter:
    return lambda item: (item.get("metrics") or {}).get(key)


def _tokens_total(item: dict[str, Any]) -> int | None:
    tokens = (item.get("metrics") or {}).get("tokens")
    return sum(int(v) for v in tokens.values()) if tokens else None


RATE_METRICS: dict[str, Getter] = {
    "behaviour_pass": _check("pass_behaviour"),
    "answered": _check("answered"),
}
MEAN_METRICS: dict[str, Getter] = {
    "gold_coverage": _check("gold_coverage"),
    "answer_completeness": _check("answer_completeness"),
    "gold_handle_recall": _check("gold_handle_recall"),
    "unsupported_claim_rate": _check("unsupported_claim_rate"),
    "first_token_ms": _metric("first_token_ms"),
    "total_ms": _metric("total_ms"),
    "model_calls": _metric("model_calls"),
    "tool_calls": _metric("tool_calls"),
    "retrieval_calls": _metric("retrieval_calls"),
    "tokens_total": _tokens_total,
    "cost_usd": _metric("cost_usd"),
}


def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _pairs(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]], get: Getter
) -> tuple[list[float], list[float]]:
    std, res = [], []
    for a, b in pairs:
        x, y = get(a), get(b)
        if x is not None and y is not None:
            std.append(float(x))
            res.append(float(y))
    return std, res


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _summarise(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]], *, samples: int | None
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, get in {**RATE_METRICS, **MEAN_METRICS}.items():
        std, res = _pairs(pairs, get)
        sm, rm = _mean(std), _mean(res)
        row: dict[str, Any] = {
            "kind": "rate" if name in RATE_METRICS else "mean",
            "n_pairs": len(std),
            "standard_mean": _r(sm),
            "research_mean": _r(rm),
            "delta_mean": _r(rm - sm) if sm is not None and rm is not None else None,
        }
        if samples and std:
            ci = paired_bootstrap_diff(std, res, samples=samples)
            row["ci"] = {"low": _r(ci.low), "high": _r(ci.high)}
        if samples and name in RATE_METRICS and std:
            test = mcnemar_exact([bool(x) for x in std], [bool(y) for y in res])
            row["mcnemar"] = {
                "only_standard": test.only_a,
                "only_research": test.only_b,
                "p_value": _r(test.p_value),
            }
        out[name] = row
    return out


def _item_row(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"id": a["id"], "category": a["category"]}
    for label, item in (("standard", a), ("research", b)):
        metrics = item.get("metrics") or {}
        row[label] = {
            **{name: get(item) for name, get in {**RATE_METRICS, **MEAN_METRICS}.items()},
            "termination_state": item.get("termination_state"),
            "stop_reason": metrics.get("stop_reason"),
            "route_decided": metrics.get("route_decided"),
            "research_fallback": metrics.get("research_fallback"),
        }
    row["delta"] = {}
    for name, get in MEAN_METRICS.items():
        x, y = get(a), get(b)
        row["delta"][name] = _r(float(y) - float(x)) if x is not None and y is not None else None
    return row


def compare(
    standard: list[dict[str, Any]],
    research: list[dict[str, Any]],
    *,
    samples: int = BOOTSTRAP_SAMPLES,
) -> dict[str, Any]:
    """Paired comparison (research - standard) of two runs over the same items."""
    by_id = {i["id"]: i for i in research}
    std_ids = {i["id"] for i in standard}
    pairs = [(a, by_id[a["id"]]) for a in standard if a["id"] in by_id]
    unpaired = sorted(std_ids ^ set(by_id))
    categories: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for a, b in pairs:
        categories.setdefault(a["category"], []).append((a, b))
    return {
        "delta": "research - standard",
        "n_pairs": len(pairs),
        "unpaired": unpaired,
        "bootstrap_samples": samples,
        "metrics": _summarise(pairs, samples=samples),
        "categories": {
            name: {"n": len(members), "metrics": _summarise(members, samples=None)}
            for name, members in sorted(categories.items())
        },
        "items": [_item_row(a, b) for a, b in pairs],
    }
