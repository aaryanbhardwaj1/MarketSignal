"""Shared helpers for the MarketSignal seed generator (fictional data only)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml

SEED_ROOT = Path(__file__).resolve().parent.parent
GEN_DIR = Path(__file__).resolve().parent
WORLD_PATH = SEED_ROOT / "world_model.yaml"
CONTENT_DIR = GEN_DIR / "content"

DISCLAIMER = "Fictional data created for the MarketSignal demo."
DISCLAIMER_CORE = "Fictional data created for the MarketSignal demo"

PLACEHOLDER = re.compile(r"\{F:([A-Z0-9-]+)\}")

# Real brands / companies / platforms that must never appear (case-insensitive
# whole-word match). "On" (the shoe brand) is matched only in brand phrasing.
FORBIDDEN_TERMS = [
    "nike",
    "adidas",
    "lululemon",
    "on running",
    "on holding",
    "on cloud",
    "hoka",
    "under armour",
    "under armor",
    "puma",
    "new balance",
    "asics",
    "gymshark",
    "visa",
    "mastercard",
    "reebok",
    "saucony",
    "allbirds",
    "vuori",
    "fabletics",
    "skechers",
    "alo yoga",
    "patagonia",
    "north face",
    "salomon",
    "arc'teryx",
    "columbia sportswear",
    "amazon",
    "tiktok",
    "instagram",
    "youtube",
    "snapchat",
    "pinterest",
    "shopify",
    "strava",
    "klarna",
    "afterpay",
    "walmart",
    "foot locker",
    "dick's sporting",
    "jd sports",
    "zappos",
    "nordstrom",
    "nielsen",
    "mckinsey",
    "deloitte",
    "gartner",
    "euromonitor",
    "statista",
    "circana",
    "mizuno",
    "fila",
    "decathlon",
    "google",
    "facebook",
    "apple",
    "openai",
    "anthropic",
    "chatgpt",
    "brooks running",
]
_FORBIDDEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(re.escape(t) for t in FORBIDDEN_TERMS) + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def load_world() -> dict:
    with WORLD_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def fact_ws(fact: dict) -> str:
    return fact.get("ws", "NORTHSTAR")


def fact_ver(fact: dict) -> int:
    return int(fact.get("ver", 1))


def facts_by_id(world: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in world["facts"]:
        if f["id"] in out:
            raise ValueError(f"duplicate fact id {f['id']}")
        out[f["id"]] = f
    return out


def is_sentence_fact(fact: dict) -> bool:
    return isinstance(fact.get("anchor"), str)


def norm_ws(text: str) -> str:
    return " ".join(text.split())


def forbidden_hits(text: str) -> list[str]:
    return sorted({m.group(1).lower() for m in _FORBIDDEN_RE.finditer(text)})


def non_ascii_chars(text: str) -> list[str]:
    return sorted({ch for ch in text if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\n\t")})


def resolve(text: str, facts: dict[str, dict], used: list[str] | None = None) -> str:
    """Replace {F:ID} placeholders with the fact's sentence anchor."""

    def _sub(m: re.Match) -> str:
        fid = m.group(1)
        if fid not in facts:
            raise KeyError(f"unknown fact placeholder {fid}")
        fact = facts[fid]
        if not is_sentence_fact(fact):
            raise ValueError(f"fact {fid} has no sentence anchor")
        if used is not None:
            used.append(fid)
        return fact["anchor"]

    return PLACEHOLDER.sub(_sub, text)


def load_content_modules(paths: list[Path] | None = None) -> dict[tuple, dict]:
    """Load DOCS dicts from content/*.py modules, keyed by (ws, code, ver)."""
    docs: dict[tuple, dict] = {}
    files = paths if paths is not None else sorted(CONTENT_DIR.glob("*.py"))
    for path in files:
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"content_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        for key, doc in getattr(mod, "DOCS", {}).items():
            if key in docs:
                raise ValueError(f"duplicate content key {key} in {path.name}")
            docs[key] = doc
    return docs


def iter_doc_strings(doc: dict):
    """Yield (location, text) for every string in a content doc spec."""
    for k in ("title", "subtitle"):
        if doc.get(k):
            yield (k, doc[k])
    for line in doc.get("meta", []) or []:
        yield ("meta", line)
    if doc["kind"] == "narrative":
        for i, block in enumerate(doc["blocks"]):
            btype = block[0]
            if btype in ("h1", "h2", "p"):
                yield (f"{btype}#{i}", block[1])
            elif btype == "bullets":
                for item in block[1]:
                    yield (f"bullet#{i}", item)
            elif btype == "table":
                for row in block[1]:
                    for cell in row:
                        yield (f"table#{i}", cell)
            elif btype == "pagebreak":
                continue
            else:
                raise ValueError(f"unknown block type {btype}")
    elif doc["kind"] == "slides":
        for s, slide in enumerate(doc["slides"]):
            yield (f"slide{s}:title", slide["title"])
            for item in slide.get("bullets") or []:
                yield (f"slide{s}:body", item)
            for row in slide.get("table") or []:
                for cell in row:
                    yield (f"slide{s}:table", cell)
            if slide.get("notes"):
                yield (f"slide{s}:notes", slide["notes"])
    else:
        raise ValueError(f"unknown doc kind {doc['kind']}")
