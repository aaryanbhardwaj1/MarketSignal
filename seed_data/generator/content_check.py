"""Validate one or more content modules before rendering.

Usage:
  uv --directory backend run python seed_data/generator/content_check.py seed_data/generator/content/<module>.py [...]

Checks per document: placeholders resolve; every sentence-anchor fact of that
document (same workspace, source code, version) is placed exactly once; facts are
only placed in their own document; PPTX facts sit in the declared location
(body/notes/table); interview facts sit in "A: " answers; text is plain ASCII;
no forbidden real-brand names; the resolved anchor occurs exactly once in the
document's whitespace-normalised text. Prints word counts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    PLACEHOLDER,
    fact_ver,
    fact_ws,
    facts_by_id,
    forbidden_hits,
    is_sentence_fact,
    iter_doc_strings,
    load_content_modules,
    load_world,
    non_ascii_chars,
    norm_ws,
    resolve,
)

LOC_MAP = {"body": "body", "notes": "notes", "table": "table"}


def check_doc(key, doc, facts) -> list[str]:
    ws, code, ver = key
    errors: list[str] = []
    used: list[str] = []
    resolved_parts: list[str] = []
    for loc, text in iter_doc_strings(doc):
        ids = PLACEHOLDER.findall(text)
        for fid in ids:
            f = facts.get(fid)
            if f is None:
                errors.append(f"{key}: unknown placeholder {fid}")
                continue
            if (fact_ws(f), f["src"], fact_ver(f)) != (ws, code, ver):
                errors.append(f"{key}: fact {fid} belongs to {(fact_ws(f), f['src'], fact_ver(f))}")
            want = f.get("loc")
            if doc["kind"] == "slides" and want and not loc.endswith(":" + LOC_MAP[want]):
                errors.append(f"{key}: fact {fid} must be in slide {want}, found at {loc}")
            if code == "INTERVIEWS" and not text.startswith("A: "):
                errors.append(
                    f"{key}: interview fact {fid} must be inside an 'A: ' answer paragraph"
                )
        try:
            out = resolve(text, facts, used)
        except (KeyError, ValueError) as exc:
            errors.append(f"{key}: {exc}")
            continue
        bad = non_ascii_chars(out)
        if bad:
            errors.append(f"{key}: non-ASCII characters {bad!r} at {loc}: {out[:60]!r}")
        hits = forbidden_hits(out)
        if hits:
            errors.append(f"{key}: forbidden terms {hits} at {loc}")
        if "Fictional data created for the MarketSignal demo" in out:
            errors.append(
                f"{key}: do not write the disclaimer yourself (renderer adds it) at {loc}"
            )
        resolved_parts.append(out)
    expected = sorted(
        fid
        for fid, f in facts.items()
        if is_sentence_fact(f) and (fact_ws(f), f["src"], fact_ver(f)) == (ws, code, ver)
    )
    for fid in expected:
        n = used.count(fid)
        if n != 1:
            errors.append(f"{key}: fact {fid} placed {n} times (expected exactly 1)")
    joined = norm_ws(" \n ".join(resolved_parts))
    for fid in expected:
        n = joined.count(norm_ws(facts[fid]["anchor"]))
        if n != 1:
            errors.append(f"{key}: anchor of {fid} occurs {n} times in resolved text")
    words = len(joined.split())
    print(
        f"  {ws}/{code} v{ver} [{doc['kind']}]: {words} words"
        + (f", {len(doc['slides'])} slides" if doc["kind"] == "slides" else "")
    )
    return errors


def main(argv: list[str]) -> int:
    world = load_world()
    facts = facts_by_id(world)
    paths = [Path(a).resolve() for a in argv] or None
    docs = load_content_modules(paths)
    errors: list[str] = []
    for key, doc in sorted(docs.items()):
        errors.extend(check_doc(key, doc, facts))
    for e in errors:
        print("ERROR", e)
    print("OK" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
