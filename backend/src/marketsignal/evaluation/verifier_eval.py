"""Verifier precision harness (Phase 4, workstream A8).

Replays the labelled ``eval/datasets/verifier-v1`` cases through
:func:`marketsignal.generation.verifier.verify_answer` and measures what the deterministic
verifier does to each gold unit. No model and no database are involved, so the numbers are a
pure function of the dataset and the verifier code.

Metrics (``summary``):

* ``false_positive_rejection_rate`` - supported units removed / supported units.
* ``supported_retention`` - 1 - the above.
* ``false_negative_acceptance_rate`` - unsupported units presented as evidence-backed (kept
  and not tagged ``[inference]``), plus miscited units kept with a wrong citation, over all
  unsupported + miscited units. A unit downgraded to ``[inference]`` is visibly marked as not
  evidence-backed, which is the contract's intended outcome for an uncited claim.
* ``repair_frequency`` - cases with any repair or numeric violation recorded.
* ``regeneration_request_frequency`` - cases whose first answer fails verification (ok=False).
* ``fallback_frequency`` - cases whose first answer and regenerated answer (``retry_answer``,
  or the same answer replayed when none is given) both fail: the run would fall back to the
  evidence-only answer.
* ``structural_agreement`` - cases where ``ok`` matches the gold ``expected.ok``.
* ``latency_ms_p50`` / ``latency_ms_p95`` - per-case median of repeated verifier calls.

Usage::

    uv --directory backend run python -m marketsignal.evaluation.verifier_eval --split dev \
        [--out DIR] [--tag after]
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import statistics
import sys
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from marketsignal.generation import verifier
from marketsignal.generation.contract import SECTION_TITLES
from marketsignal.generation.types import EvidencePack, PackItem

DATASET_DIR = Path(__file__).resolve().parents[4] / "eval" / "datasets" / "verifier-v1"
REPEATS = 5
SUPPORTED, UNSUPPORTED, MISCITED = "supported", "unsupported", "miscited"


def _handle(case_id: str, rank: int) -> str:
    code = "".join(ch for ch in case_id.upper() if ch.isalnum())[:12] or "CASE"
    return f"VV1/{code}@v1:P{rank}"


def build_pack(case: dict[str, Any]) -> EvidencePack:
    items = []
    for rank, raw in enumerate(case["pack"], start=1):
        text = raw["text"]
        items.append(
            PackItem(
                alias=raw["alias"],
                rank=rank,
                handle=_handle(case["case_id"], rank),
                parent_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{case['case_id']}/{rank}"),
                source_code=f"SRC{rank}",
                source_title=raw["source_title"],
                source_class=raw.get("source_class", "document"),
                source_type="text",
                locator_label=raw["locator_label"],
                heading_path=tuple(raw.get("heading_path", ())),
                text=text,
                window=None,
                tokens=len(text.split()),
                content_hash=hashlib.sha256(text.encode()).hexdigest(),
                anchor_child_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{case['case_id']}/{rank}/c"),
                anchor_char_start=0,
                anchor_char_end=min(len(text), 40),
                fused_rank=rank,
            )
        )
    return EvidencePack(items=tuple(items), tokens=0, truncated=case.get("pack_truncated", False))


def _verify_fn() -> Callable[[str, EvidencePack, dict[str, Any]], Any]:
    """``verify_answer`` called with only the keyword arguments this verifier accepts, so the
    same harness measures the original (pre-Phase-4) verifier and the current one."""
    accepted = set(inspect.signature(verifier.verify_answer).parameters)

    def call(raw: str, pack: EvidencePack, case: dict[str, Any]) -> Any:
        kwargs: dict[str, Any] = {"pack_truncated": case.get("pack_truncated", False)}
        if "question" in accepted:
            kwargs["question"] = case.get("question", "")
        if "max_citations" in accepted:
            kwargs["max_citations"] = case.get("max_citations", 20)
        return verifier.verify_answer(raw, pack, **kwargs)

    return call


def _locate(sections: dict[str, list[str]], key: str) -> str | None:
    for name, units in sections.items():
        if name not in SECTION_TITLES:
            continue  # auxiliary keys (e.g. answer_unknowns) duplicate answer units
        for unit in units:
            if key in unit:
                return unit
    return None


def _unit_outcome(
    unit: dict[str, Any], sections: dict[str, list[str]], case: dict[str, Any]
) -> dict[str, Any]:
    found = _locate(sections, unit["key"])
    kept = found is not None
    tagged = kept and "[inference]" in (found or "")
    label = unit["label"]
    outcome: dict[str, Any] = {"key": unit["key"], "label": label, "type": unit["type"]}
    if label == SUPPORTED:
        outcome["result"] = "kept" if kept else "removed"
    elif label == UNSUPPORTED:
        outcome["result"] = "accepted" if kept and not tagged else ("tagged" if kept else "removed")
    else:
        aliases = {item["alias"]: rank for rank, item in enumerate(case["pack"], start=1)}
        right = _handle(case["case_id"], aliases.get(unit.get("correct_alias", ""), 0))
        if not kept:
            outcome["result"] = "removed"
        elif f"[[{right}]]" in (found or ""):
            outcome["result"] = "repaired"
        else:
            outcome["result"] = "tagged" if tagged else "accepted"
    return outcome


def _timed(call: Callable[[], Any]) -> tuple[Any, float]:
    samples, result = [], None
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        result = call()
        samples.append((time.perf_counter() - t0) * 1000)
    return result, statistics.median(samples)


def _conflict_signal(pack: EvidencePack) -> bool | None:
    detect = getattr(verifier, "detect_conflicts", None)
    return None if detect is None else bool(detect(pack))


def evaluate_case(case: dict[str, Any], call: Callable[..., Any]) -> dict[str, Any]:
    pack = build_pack(case)
    result, latency = _timed(lambda: call(case["answer"], pack, case))
    retry_ok = result.ok
    if not result.ok:
        retry = call(case.get("retry_answer") or case["answer"], pack, case)
        retry_ok = retry.ok
    report = result.report
    return {
        "case_id": case["case_id"],
        "case_types": case.get("case_types", []),
        "ok": result.ok,
        "expected_ok": case["expected"]["ok"],
        "structural_failures": list(report.structural_failures),
        "expected_failures": case["expected"].get("structural_failures", []),
        "repaired": bool(report.repairs or report.numeric_violations),
        "fallback": not result.ok and not retry_ok,
        "latency_ms": round(latency, 4),
        "conflict_expected": case["expected"].get("conflict_present", False),
        "conflict_signal": _conflict_signal(pack),
        "units": [_unit_outcome(u, result.sections, case) for u in case["units"]],
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return round(ordered[index], 4)


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    units = [u for c in cases for u in c["units"]]
    results = Counter((u["label"], u["result"]) for u in units)
    supported = sum(n for (label, _), n in results.items() if label == SUPPORTED)
    removed = results[(SUPPORTED, "removed")]
    bad = sum(n for (label, _), n in results.items() if label != SUPPORTED)
    accepted = results[(UNSUPPORTED, "accepted")] + results[(MISCITED, "accepted")]
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    for u in units:
        by_type[u["type"]][f"{u['label']}:{u['result']}"] += 1
    n = len(cases)
    conflicts = [c for c in cases if c["conflict_signal"] is not None]
    summary: dict[str, Any] = {
        "cases": n,
        "units": len(units),
        "supported_units": supported,
        "unsupported_units": bad,
        "false_positive_rejection_rate": _rate(removed, supported),
        "supported_retention": _rate(supported - removed, supported),
        "false_negative_acceptance_rate": _rate(accepted, bad),
        "miscited_repaired": results[(MISCITED, "repaired")],
        "repair_frequency": _rate(sum(c["repaired"] for c in cases), n),
        "regeneration_request_frequency": _rate(sum(not c["ok"] for c in cases), n),
        "fallback_frequency": _rate(sum(c["fallback"] for c in cases), n),
        "structural_agreement": _rate(sum(c["ok"] == c["expected_ok"] for c in cases), n),
        "latency_ms_p50": _percentile([c["latency_ms"] for c in cases], 0.5),
        "latency_ms_p95": _percentile([c["latency_ms"] for c in cases], 0.95),
        "outcomes": {f"{label}:{result}": k for (label, result), k in sorted(results.items())},
        "by_type": {t: dict(sorted(c.items())) for t, c in sorted(by_type.items())},
    }
    if conflicts:
        hits = Counter((c["conflict_expected"], c["conflict_signal"]) for c in conflicts)
        summary["conflict_signal"] = {
            "true_positive": hits[(True, True)],
            "false_positive": hits[(False, True)],
            "false_negative": hits[(True, False)],
            "true_negative": hits[(False, False)],
        }
    return summary


def run(split: str, dataset_dir: Path = DATASET_DIR) -> dict[str, Any]:
    payload = json.loads((dataset_dir / f"{split}.json").read_text())
    call = _verify_fn()
    cases = [evaluate_case(case, call) for fam in payload["families"] for case in fam["cases"]]
    return {"split": split, "summary": summarize(cases), "cases": cases}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifier precision harness (verifier-v1).")
    parser.add_argument("--split", choices=("dev", "holdout"), required=True)
    parser.add_argument("--out", type=Path, default=None, help="directory for the JSON result")
    parser.add_argument("--tag", default="current", help="file suffix, e.g. before/after")
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    args = parser.parse_args(argv)
    result = run(args.split, args.dataset_dir)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"{args.split}-{args.tag}.json").write_text(text)
    sys.stdout.write(json.dumps(result["summary"], indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
