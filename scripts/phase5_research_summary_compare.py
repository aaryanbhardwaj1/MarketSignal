"""Phase 5 A3: paired before/after comparison of research runs without and with the research
summary hand-off (``MS_RESEARCH_SUMMARY=0`` vs default), on the same items.

Reads two grounded-eval ``results.json`` files (``--mode research`` runs) and writes the paired
comparison (after - before) using ``evaluation.grounded_compare.compare``; prints answer
completeness per item and overall. Offline: no model calls.

    uv --directory backend run python ../scripts/phase5_research_summary_compare.py \
        --before ../eval/baselines/phase5/research-dev-p5-summary-off/results.json \
        --after ../eval/baselines/phase5/research-dev-p5-summary-on/results.json \
        --out ../eval/baselines/phase5/research-dev-p5-compare.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from marketsignal.evaluation.grounded_compare import compare


def _completeness(item: dict[str, Any]) -> float | None:
    checks = item.get("checks") or {}
    value = checks.get("answer_completeness", checks.get("fallback_answer_completeness"))
    return None if value is None else float(value)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--before", type=Path, required=True, help="summary OFF results.json")
    parser.add_argument("--after", type=Path, required=True, help="summary ON results.json")
    parser.add_argument("--out", type=Path, help="write the paired comparison JSON here")
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))["items"]
    after = json.loads(args.after.read_text(encoding="utf-8"))["items"]
    by_id = {i["id"]: i for i in before}
    rows = []
    for item in after:
        old = by_id.get(item["id"])
        b, a = (_completeness(old) if old else None), _completeness(item)
        rows.append((item["id"], b, a))
        print(f"{item['id']:<9} before={b!s:<6} after={a!s:<6}")
    paired = [(b, a) for _, b, a in rows if b is not None and a is not None]
    print(
        f"answer completeness (paired n={len(paired)}): "
        f"before={_mean([b for b, _ in paired])} after={_mean([a for _, a in paired])}"
    )
    result = compare(before, after)  # labelled "research - standard": read as after - before
    result["delta"] = "after (summary on) - before (summary off)"
    if args.out:
        args.out.write_text(json.dumps(result, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
