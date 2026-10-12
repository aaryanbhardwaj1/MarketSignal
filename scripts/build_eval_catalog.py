"""Build the developer evaluation catalog from committed evaluation artifacts (stdlib only).

Reads an allowlist of files under ``eval/`` (and two phase reports, for prose-only decisions)
read-only, and writes ``backend/src/marketsignal/devtools/eval_catalog_data/catalog.v1.json``
plus ``items/<EvalRunId>.json``. Nothing is computed per request and nothing under ``eval/``
is ever written.

Rules (see the frozen contract ``frontend/src/lib/api/contracts.ts``, E11):
- every number is an ``EvalMetric`` whose ``source.pointer`` (RFC 6901) resolves, in the
  original file, to exactly ``value``;
- aggregate hard gates (for example 256/256 resolvable citations) are summed here from
  ``items[].checks`` and point at the ``/items`` array;
- prose-only decisions carry ``kind: "report_md"`` with a heading anchor, and their numbers
  stay inside ``text`` (numbers are never parsed out of prose).

Usage:
    uv --directory backend run python ../scripts/build_eval_catalog.py [--out DIR] [--built-at ISO]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from eval_catalog_builder import DEFAULT_OUT, REPO, build, dump


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--built-at", default=None, help="ISO timestamp (default: now, UTC)")
    args = parser.parse_args(argv)
    out: Path = args.out.resolve()
    if (REPO / "eval").resolve() in (out, *out.parents):
        raise SystemExit("refusing to write under eval/")
    built_at = args.built_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    catalog, files = build(REPO, built_at)
    (out / "items").mkdir(parents=True, exist_ok=True)
    (out / "catalog.v1.json").write_text(dump(catalog), encoding="utf-8")
    for rid, payload in files.items():
        (out / "items" / f"{rid}.json").write_text(dump(payload), encoding="utf-8")
    sizes = ", ".join(f"{rid} {len(dump(p)) // 1024} KB" for rid, p in files.items())
    n_src = len(catalog["sources"])
    sys.stdout.write(f"catalog {len(dump(catalog)) // 1024} KB, {n_src} sources; items: {sizes}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
