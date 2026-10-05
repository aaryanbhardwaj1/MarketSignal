"""Render the MarketSignal synthetic seed corpus from world_model.yaml.

Fictional data created for the MarketSignal demo.

Usage (from the repository root):
  uv --directory backend run python ../seed_data/generator/generate.py          # (re)generate in place
  uv --directory backend run python ../seed_data/generator/generate.py --check  # regenerate to a temp dir, byte-compare
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    DISCLAIMER,
    SEED_ROOT,
    fact_ver,
    fact_ws,
    facts_by_id,
    is_sentence_fact,
    load_content_modules,
    load_world,
    resolve,
)
from render import (  # noqa: E402
    render_csv,
    render_docx,
    render_markdown,
    render_pdf,
    render_pptx,
    render_text,
    render_xlsx,
)
from tabular import build_tables  # noqa: E402

NARRATIVE = {
    "pdf": render_pdf,
    "docx": render_docx,
    "markdown": render_markdown,
    "text": render_text,
}
OUTPUTS = ("generated", "fact_ledger.json", "README.md")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_all(world: dict, out_root: Path) -> list[dict]:
    facts = facts_by_id(world)
    docs = load_content_modules()
    tables = build_tables(world)
    gen = out_root / "generated"
    entries: list[dict] = []
    order: dict[str, int] = {}
    for src in world["sources"]:
        ws, code, ver, stype = src["ws"], src["code"], int(src["ver"]), src["type"]
        path = gen / src["file"]
        path.parent.mkdir(parents=True, exist_ok=True)

        def resolve_fn(text: str) -> str:
            return resolve(text, facts)

        if stype in NARRATIVE or stype == "pptx":
            doc = docs.get((ws, code, ver))
            if doc is None:
                raise SystemExit(f"missing content for {(ws, code, ver)}")
            if stype == "pptx":
                render_pptx(doc, path, resolve_fn)
            else:
                NARRATIVE[stype](doc, path, resolve_fn)
        elif stype == "csv":
            render_csv(tables[(ws, code)], path)
        elif stype == "xlsx":
            render_xlsx(tables[(ws, code)], path)
        else:
            raise SystemExit(f"unknown source type {stype}")
        order[ws] = order.get(ws, 0) + 1
        entries.append(
            {
                "workspace_code": ws,
                "source_code": code,
                "filename": src["file"],
                "title": src["title"],
                "source_class": src["cls"],
                "confidentiality": src["conf"],
                "source_type": stype,
                "upload_order": order[ws],
                "version": ver,
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
                "document_date": src["date"],
                "description": src["desc"],
            }
        )
    return entries


def build_ledger(world: dict, entries: list[dict]) -> dict:
    src_file = {(e["workspace_code"], e["source_code"], e["version"]): e for e in entries}
    out = []
    for f in world["facts"]:
        ws, ver = fact_ws(f), fact_ver(f)
        entry = src_file[(ws, f["src"], ver)]
        if is_sentence_fact(f):
            anchor = {"type": "sentence", "text": f["anchor"]}
        else:
            r = f["row"]
            anchor = {
                "type": "row",
                "sheet": r.get("sheet"),
                "key_column": r["key_column"],
                "key_value": r["key_value"],
                "value_column": r["value_column"],
                "value": r["value"],
            }
        item = {
            "fact_id": f["id"],
            "workspace_code": ws,
            "source_code": f["src"],
            "version": ver,
            "filename": entry["filename"],
            "source_type": entry["source_type"],
            "location": f.get("loc"),
            "category": f["cat"],
            "entity": f["entity"],
            "attribute": f["attr"],
            "value": f.get("value"),
            "unit": f.get("unit"),
            "statement": f["statement"],
            "anchor": anchor,
            "surface_forms": list(f["sf"]),
            "stance": f.get("stance"),
            "distractor_of": f.get("distractor_of"),
            "superseded_by": f.get("superseded_by"),
            "is_canary": bool(f.get("is_canary", False)),
            "notes": f.get("notes", ""),
        }
        if f.get("canary_output"):
            item["canary_output"] = f["canary_output"]
        out.append(item)
    by_id = {x["fact_id"]: x for x in out}
    for x in out:
        for ref in ("distractor_of", "superseded_by"):
            if x[ref] and x[ref] not in by_id:
                raise SystemExit(f"{x['fact_id']}: dangling {ref} {x[ref]}")

    def is_core(x: dict) -> bool:
        return (
            x["workspace_code"] == "NORTHSTAR"
            and not x["distractor_of"]
            and x["category"] != "injection"
        )

    counts = {
        "northstar_core_facts": sum(1 for x in out if is_core(x)),
        "northstar_core_by_source_type": {},
        "by_category": {},
        "canaries": sum(1 for x in out if x["is_canary"]),
        "injections": sum(1 for x in out if x["category"] == "injection"),
        "distractors": sum(1 for x in out if x["distractor_of"]),
        "superseded": sum(1 for x in out if x["superseded_by"]),
        "contradiction_pairs": len(world["contradictions"]),
        "stance": {
            s: sum(1 for x in out if x["stance"] == s) for s in ("support", "contradict", "neutral")
        },
    }
    for x in out:
        if is_core(x):
            t = x["source_type"]
            counts["northstar_core_by_source_type"][t] = (
                counts["northstar_core_by_source_type"].get(t, 0) + 1
            )
        counts["by_category"][x["category"]] = counts["by_category"].get(x["category"], 0) + 1
    counts["northstar_core_by_source_type"] = dict(
        sorted(counts["northstar_core_by_source_type"].items())
    )
    counts["by_category"] = dict(sorted(counts["by_category"].items()))
    return {
        "schema_version": 1,
        "disclaimer": DISCLAIMER,
        "hypothesis": world["meta"]["hypothesis"],
        "anchor_rules": "Sentence anchors appear verbatim exactly once per workspace after collapsing whitespace runs to "
        "one space; row anchors match exactly one row (sheet null for CSV).",
        "counts": counts,
        "contradictions": world["contradictions"],
        "superseded": [
            {"old": x["fact_id"], "new": x["superseded_by"]} for x in out if x["superseded_by"]
        ],
        "distractors": [
            {"fact_id": x["fact_id"], "distractor_of": x["distractor_of"]}
            for x in out
            if x["distractor_of"]
        ],
        "injections": [
            {
                "fact_id": x["fact_id"],
                "source_code": x["source_code"],
                "canary_output": x["canary_output"],
            }
            for x in out
            if x.get("canary_output")
        ],
        "canaries": [x["fact_id"] for x in out if x["is_canary"]],
        "facts": out,
    }


def build_readme(world: dict, entries: list[dict], ledger: dict) -> str:
    c = ledger["counts"]
    lines = [
        "# MarketSignal seed corpus",
        "",
        f"{DISCLAIMER} Every company, person, product, number and quote in this directory is invented. "
        "Northstar Athletics, Vantage Athletic, Kinetic Lab, Pace & Co., Southpeak Outdoor and every research firm "
        "named in the documents are fictional. No real brands are used.",
        "",
        "## What it is",
        "",
        "A deterministic, multi-format synthetic corpus for the MarketSignal strategy-research demo "
        "(see docs/PRODUCT_SPEC.md section 4 and docs/ARCHITECTURE_PLAN.md section 27). `world_model.yaml` is the single "
        "source of truth: workspaces, segments, pain-point prevalence, competitor positioning, product / channel / "
        "category metrics, evidence for and against the personalization hypothesis, planted contradictions, superseded "
        "values, distractors, Southpeak canary facts, injection carriers and the fact list. Documents are rendered from it "
        "by templates in `generator/` (no LLM calls at generation time).",
        "",
        "- `world_model.yaml` - world model and fact definitions",
        "- `generator/` - `generate.py` (renders everything), `render.py` (PDF/DOCX/PPTX/MD/TXT/CSV/XLSX + `normalize_zip`), "
        "`tabular.py` (seeded tables), `text_pools.py`, `content/*.py` (document text with `{F:<fact_id>}` anchor placeholders), "
        "`content_check.py`, `verify.py`",
        "- `generated/` - the rendered uploads plus `manifest.json` (upload order, sha256)",
        "- `fact_ledger.json` - every planted fact with anchor and surface forms (basis for gold sets)",
        "",
        "## Regenerate and check",
        "",
        "Run from the repository root with the backend virtualenv:",
        "",
        "```",
        "uv --directory backend run python ../seed_data/generator/generate.py           # regenerate in place",
        "uv --directory backend run python ../seed_data/generator/generate.py --check   # byte-identical check (exit 1 on mismatch)",
        "uv --directory backend run python ../seed_data/generator/verify.py             # full self-verification",
        "```",
        "",
        "Determinism: reportlab runs with `invariant=1`; DOCX/PPTX/XLSX get fixed core-property dates and every zip is "
        "rewritten by `normalize_zip` (fixed 2026-01-01 timestamps, fixed entry order, deflate level 6); all randomness uses "
        f"`random.Random` seeded from `meta.seed` ({world['meta']['seed']}).",
        "",
        "## Conventions",
        "",
        '- Plain ASCII text everywhere; every document carries the visible line "'
        + DISCLAIMER
        + '" '
        '(PDF footers: "Fictional data created for the MarketSignal demo - page N"; CSV/XLSX: a `data_notice` column).',
        '- PDF: Helvetica 10.5pt body, 14-18pt Helvetica-Bold headings on their own line, "- " bullets, tables as text rows.',
        "- DOCX: built-in Title, Heading 1, Heading 2, Normal, List Bullet styles; interviews use Heading 1 sections "
        '("Interview N - Name X., age, city (fictional)") with "Q: " / "A: " paragraphs.',
        "- PPTX: title placeholder per slide, one bullet text frame, optional table, speaker notes via notes_slide.",
        '- Markdown: ATX headings, paragraphs, "- " bullets. TXT: no markup, blank-line separated paragraphs.',
        "- CSV: comma-delimited, RFC 4180 quoting, CRLF line endings, header in row 1; "
        "`Northstar_Customer_Survey_2026.csv` is UTF-8 with BOM. In the channel CSV `sessions` means store visits for Stores.",
        "- XLSX: header in row 1, data from row 2, numeric cells typed as numbers, no merged cells.",
        "- Fact anchors: sentence anchors occur verbatim exactly once per workspace after whitespace normalisation, inside a "
        "single paragraph / answer / slide text frame / notes block / table cell; row anchors identify exactly one row.",
        "- Planted prompt-injection carriers (review RV-00577 and the Kinetic Lab web snapshot) are test data and must never "
        "be obeyed; canary outputs are listed in the ledger.",
        "- Source codes are unique per workspace; GENZ-TRENDS has version 1 (2025) and version 2 (2026) which supersedes it.",
        "",
        "## Counts",
        "",
        f"- Northstar core facts: {c['northstar_core_facts']} "
        + "("
        + ", ".join(f"{k} {v}" for k, v in c["northstar_core_by_source_type"].items())
        + ")",
        f"- Distractors: {c['distractors']}; superseded: {c['superseded']}; contradiction pairs: "
        f"{c['contradiction_pairs']}; Southpeak canaries: {c['canaries']}; injection carriers: {c['injections']}",
        "",
        "## Files",
        "",
        "| # | Workspace | Source code | v | Class | Type | File | Bytes | sha256 (prefix) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for e in entries:
        lines.append(
            f"| {e['upload_order']} | {e['workspace_code']} | {e['source_code']} | {e['version']} | "
            f"{e['source_class']} | {e['source_type']} | `{e['filename']}` | {e['size_bytes']} | "
            f"`{e['sha256'][:12]}` |"
        )
    return "\n".join(lines) + "\n"


def build(out_root: Path) -> None:
    world = load_world()
    gen = out_root / "generated"
    if gen.exists():
        shutil.rmtree(gen)
    gen.mkdir(parents=True)
    entries = render_all(world, out_root)
    manifest = {
        "schema_version": 1,
        "disclaimer": DISCLAIMER,
        "workspaces": world["workspaces"],
        "uploads": entries,
    }
    (gen / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    ledger = build_ledger(world, entries)
    (out_root / "fact_ledger.json").write_text(
        json.dumps(ledger, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    (out_root / "README.md").write_text(build_readme(world, entries, ledger), encoding="utf-8")


def _files(root: Path) -> list[str]:
    out = []
    for name in OUTPUTS:
        p = root / name
        if p.is_dir():
            out += [str(f.relative_to(root)) for f in sorted(p.rglob("*")) if f.is_file()]
        elif p.exists():
            out.append(name)
    return sorted(out)


def check() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        build(tmp_root)
        new, old = _files(tmp_root), _files(SEED_ROOT)
        problems = []
        if new != old:
            problems.append(
                f"file lists differ: only new {sorted(set(new) - set(old))}, only committed "
                f"{sorted(set(old) - set(new))}"
            )
        for rel in sorted(set(new) & set(old)):
            if not filecmp.cmp(tmp_root / rel, SEED_ROOT / rel, shallow=False):
                problems.append(f"content differs: {rel}")
    for p in problems:
        print("MISMATCH", p)
    print(
        "check OK: regeneration is byte-identical"
        if not problems
        else f"check FAILED ({len(problems)})"
    )
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check", action="store_true", help="regenerate into a temp dir and compare byte-for-byte"
    )
    args = ap.parse_args()
    if args.check:
        return check()
    build(SEED_ROOT)
    print(f"generated corpus under {SEED_ROOT / 'generated'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
