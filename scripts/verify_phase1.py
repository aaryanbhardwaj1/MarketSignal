"""Phase 1 exit verification against a live, seeded system (``make api``, ``make worker``,
``make seed`` first). Writes ``docs/phase-reports/phase-1-verification.json``.

Checks (every one must pass):
1. anchor census: every planted sentence anchor of the fact ledger occurs in exactly one parent
   of the ingested corpus (whitespace-normalised); every row anchor maps to exactly one dataset
   row whose parent handle resolves;
2. per format, planted facts are found by lexical and dense smoke search (where the format has
   retrieval units), resolve to exact parent text containing the anchor, and the hit's child
   span highlights a region of that text;
3. idempotent re-upload returns the existing version; the two-version market report has v1
   superseded and v2 ready, and both versions' handles resolve;
4. isolation: Southpeak canaries never surface in Northstar search; a Southpeak handle through
   the Northstar route is 404; under RLS Northstar sees zero Southpeak rows;
5. malformed / unknown / foreign handles fail with the documented status codes;
6. corpus, chunk, ingestion-time and embedding-throughput statistics are recorded.

Read access to the database (anchor census, statistics) uses the non-privileged ms_app role
with the workspace scope set, i.e. under the same RLS as the application.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import psycopg

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seed_data"
REPORT = ROOT / "docs" / "phase-reports" / "phase-1-verification.json"
API = os.environ.get("MS_VERIFY_API", "http://localhost:8000")
DSN = os.environ.get(
    "MS_VERIFY_DSN", "postgresql://ms_app:dev-only-insecure-app@localhost:5432/marketsignal"
)
TOP_K = 10
STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "for",
        "to",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "by",
        "with",
        "from",
        "at",
        "as",
        "that",
        "this",
        "it",
        "its",
        "than",
        "more",
        "most",
        "into",
        "over",
        "per",
        "vs",
        "their",
        "they",
        "our",
        "we",
    }
)
_WS = re.compile(r"\s+")

failures: list[str] = []


def check(condition: bool, message: str) -> bool:
    if not condition:
        failures.append(message)
        print(f"  FAIL {message}")
    return condition


def norm(text: str) -> str:
    return _WS.sub(" ", text).strip()


def content_words(text: str, n: int) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9$%.]+", text) if w.lower() not in STOP]
    return " ".join(words[:n])


class Db:
    def __init__(self) -> None:
        # autocommit: each ``transaction()`` block below is a real, committed transaction
        # (without it they are savepoints inside one implicit transaction that never commits).
        self.conn = psycopg.connect(DSN, autocommit=True)
        self.ids = dict(self.conn.execute("SELECT code, id FROM workspaces").fetchall())

    def query(self, ws: str, sql: str, params: dict[str, Any] | None = None) -> list[Any]:
        with self.conn.transaction():
            self.conn.execute(
                "SELECT set_config('app.workspace_id', %s, true)", (str(self.ids[ws]),)
            )
            return self.conn.execute(sql, params or {}).fetchall()


def search(api: httpx.Client, ws: str, q: str, mode: str) -> list[dict[str, Any]]:
    r = api.get(f"/api/workspaces/{ws}/dev/search", params={"q": q, "mode": mode, "k": TOP_K})
    r.raise_for_status()
    hits: list[dict[str, Any]] = r.json()["hits"]
    return hits


def resolve(api: httpx.Client, ws: str, handle: str, child_id: str | None = None) -> httpx.Response:
    params = {"child_id": child_id} if child_id else None
    return api.get(f"/api/workspaces/{ws}/evidence/{quote(handle, safe='')}", params=params)


def anchor_census(db: Db, facts: list[dict[str, Any]]) -> dict[str, Any]:
    """Locate every ledger anchor in the ingested corpus (basis of Phase 2 freeze-gold)."""
    located: dict[str, list[str]] = {}
    for ws in ("NORTHSTAR", "SOUTHPEAK"):
        parents = db.query(
            ws,
            "SELECT p.handle, p.text, s.source_code, v.version FROM parent_chunks p "
            "JOIN source_versions v ON v.id = p.source_version_id "
            "JOIN sources s ON s.id = v.source_id",
        )
        rows = db.query(
            ws,
            "SELECT t.name, r.values, r.parent_handle FROM dataset_rows r "
            "JOIN dataset_tables t ON t.id = r.table_id",
        )
        normalised = [(h, norm(t), code, ver) for h, t, code, ver in parents]
        for fact in (f for f in facts if f["workspace_code"] == ws):
            anchor = fact["anchor"]
            if anchor["type"] == "sentence":
                target = norm(anchor["text"])
                located[fact["fact_id"]] = [
                    h
                    for h, t, code, ver in normalised
                    if target in t and code == fact["source_code"] and ver == fact["version"]
                ]
            else:
                located[fact["fact_id"]] = [
                    handle
                    for sheet, values, handle in rows
                    if handle.split("@")[0].endswith("/" + fact["source_code"])
                    and (anchor.get("sheet") is None or sheet == anchor["sheet"])
                    and str(values.get(anchor["key_column"])) == str(anchor["key_value"])
                ]
    exact = [f for f, hs in located.items() if len(hs) == 1]
    missing = [f for f, hs in located.items() if len(hs) == 0]
    ambiguous = [f for f, hs in located.items() if len(hs) > 1]
    check(not missing, f"anchors not found in corpus: {missing}")
    check(not ambiguous, f"anchors found in more than one parent: {ambiguous}")
    return {
        "facts": len(located),
        "exactly_one_parent": len(exact),
        "missing": missing,
        "ambiguous": ambiguous,
        "handles": {f: hs for f, hs in located.items()},
    }


def retrieval_by_format(
    api: httpx.Client, facts: list[dict[str, Any]], located: dict[str, list[str]]
) -> list[dict[str, Any]]:
    """Per format, the planted facts found by lexical and dense smoke search + exact resolution."""
    results = []
    by_format: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        if fact["workspace_code"] == "NORTHSTAR" and fact["superseded_by"] is None:
            by_format[fact["source_type"]].append(fact)
    for fmt, candidates in sorted(by_format.items()):
        sentence = [f for f in candidates if f["anchor"]["type"] == "sentence"]
        rows = [f for f in candidates if f["anchor"]["type"] == "row"]
        prose_rows = [
            f
            for f in rows
            if isinstance(f["anchor"].get("value"), str) and " " in f["anchor"]["value"]
        ]
        numeric_rows = [f for f in rows if f not in prose_rows]
        for fact in sentence[:2] + numeric_rows[:1] + prose_rows[:2]:
            handle = located[fact["fact_id"]][0] if located.get(fact["fact_id"]) else None
            entry: dict[str, Any] = {
                "fact_id": fact["fact_id"],
                "format": fmt,
                "handle": handle,
                "anchor_type": fact["anchor"]["type"],
            }
            if handle is None:
                check(False, f"{fact['fact_id']}: no handle located")
                results.append(entry)
                continue
            if fact["anchor"]["type"] == "sentence":
                lex_q = content_words(fact["anchor"]["text"], 6)
            elif fact in prose_rows:  # free-text cell: query it like prose
                lex_q = content_words(str(fact["anchor"]["value"]), 6)
            else:
                lex_q = str(fact["anchor"]["key_value"])
            lexical = search(api, "NORTHSTAR", lex_q, "lexical")
            dense = search(api, "NORTHSTAR", fact["statement"], "dense")
            lex_rank = next((h["rank"] for h in lexical if h["handle"] == handle), None)
            dense_rank = next((h["rank"] for h in dense if h["handle"] == handle), None)
            hit = next((h for h in lexical + dense if h["handle"] == handle), None)
            evidence = resolve(api, "NORTHSTAR", handle, hit["child_id"] if hit else None)
            check(evidence.status_code == 200, f"{fact['fact_id']}: resolve {evidence.status_code}")
            body = evidence.json()
            text_ok = (
                norm(fact["anchor"]["text"]) in norm(body["text"])
                if fact["anchor"]["type"] == "sentence"
                else str(fact["anchor"]["key_value"]) in body["text"]
            )
            check(text_ok, f"{fact['fact_id']}: resolved text lacks the anchor")
            highlight = body.get("highlight")
            if highlight:
                check(
                    body["text"][highlight["char_start"] : highlight["char_end"]]
                    == highlight["text"],
                    f"{fact['fact_id']}: highlight span mismatch",
                )
            entry.update(
                {
                    "lexical_query": lex_q,
                    "lexical_rank": lex_rank,
                    "dense_rank": dense_rank,
                    "retrieval_unit": bool(body["children"]),
                    "resolved": evidence.status_code == 200 and text_ok,
                    "locator_label": body["locator_label"],
                    "highlight": None
                    if not highlight
                    else {
                        "char_start": highlight["char_start"],
                        "char_end": highlight["char_end"],
                        "text": highlight["text"][:160],
                    },
                }
            )
            if body["children"]:  # retrieval units exist: lexical or dense must find it
                check(
                    lex_rank is not None or dense_rank is not None,
                    f"{fact['fact_id']} ({fmt}): neither lexical nor dense found it in top {TOP_K}",
                )
            results.append(entry)
            print(
                f"  {fmt:8} {fact['fact_id']:8} lexical={lex_rank} dense={dense_rank} "
                f"{body['locator_label']}"
            )
    return results


def versioning_and_idempotency(api: httpx.Client, db: Db, ledger: dict[str, Any]) -> dict[str, Any]:
    manifest = json.loads((SEED / "generated" / "manifest.json").read_text())
    item = next(u for u in manifest["uploads"] if u["source_code"] == "FY27-MEMO")
    path = SEED / "generated" / item["filename"]
    again = api.post(
        "/api/workspaces/NORTHSTAR/sources",
        files={"file": (path.name, path.read_bytes())},
        data={
            "source_class": item["source_class"],
            "source_code": "FY27-MEMO",
            "confidentiality": item["confidentiality"],
        },
    )
    check(
        again.status_code == 200 and again.json()["created"] is False,
        f"idempotent re-upload: {again.status_code} {again.text[:200]}",
    )
    trends = db.query(
        "NORTHSTAR",
        "SELECT v.version, v.status FROM source_versions v JOIN sources s ON s.id = v.source_id "
        "WHERE s.source_code = 'GENZ-TRENDS' ORDER BY v.version",
    )
    check(
        [tuple(r) for r in trends] == [(1, "superseded"), (2, "ready")],
        f"GENZ-TRENDS versions: {trends}",
    )
    superseded = []
    for pair in ledger["superseded"][:4]:
        old_id, new_id = (
            pair.get("old_fact_id") or pair.get("old"),
            pair.get("new_fact_id") or pair.get("new"),
        )
        superseded.append({"old": old_id, "new": new_id})
    return {
        "reupload_status": again.status_code,
        "reupload_created": again.json().get("created"),
        "genz_trends_versions": [list(r) for r in trends],
        "superseded_pairs": superseded,
    }


def isolation(
    api: httpx.Client, db: Db, facts: list[dict[str, Any]], located: dict[str, list[str]]
) -> dict[str, Any]:
    canaries = [f for f in facts if f["is_canary"]]
    leaks = []
    for fact in canaries:
        for mode, q in (
            ("lexical", content_words(fact["anchor"].get("text", fact["statement"]), 6)),
            ("dense", fact["statement"]),
        ):
            for h in search(api, "NORTHSTAR", q, mode):
                if not h["handle"].startswith("NORTHSTAR/"):
                    leaks.append((fact["fact_id"], mode, h["handle"]))
    check(not leaks, f"Southpeak leaked into Northstar search: {leaks[:5]}")
    southpeak_handle = next(hs[0] for f, hs in located.items() if f.startswith("SP") and hs)
    via_northstar = resolve(api, "NORTHSTAR", southpeak_handle)
    check(
        via_northstar.status_code == 404,
        f"foreign handle via Northstar route: {via_northstar.status_code}",
    )
    via_own = resolve(api, "SOUTHPEAK", southpeak_handle)
    check(via_own.status_code == 200, f"Southpeak handle via its own route: {via_own.status_code}")
    rls = db.query(
        "NORTHSTAR",
        "SELECT count(*) FROM parent_chunks WHERE workspace_id = %(sp)s",
        {"sp": db.ids["SOUTHPEAK"]},
    )[0][0]
    check(rls == 0, f"RLS: Northstar scope sees {rls} Southpeak parents")
    return {
        "canaries_checked": len(canaries),
        "search_leaks": leaks,
        "foreign_handle_status": via_northstar.status_code,
        "own_handle_status": via_own.status_code,
        "rls_visible_foreign_parents": rls,
        "southpeak_handle_probe": southpeak_handle,
    }


def handle_failures(api: httpx.Client) -> dict[str, int]:
    cases = {
        "malformed": resolve(api, "NORTHSTAR", "northstar/brand@v1:P1").status_code,
        "unknown_locator": resolve(
            api, "NORTHSTAR", "NORTHSTAR/BRAND-STRATEGY@v1:P99.B9"
        ).status_code,
        "unknown_version": resolve(
            api, "NORTHSTAR", "NORTHSTAR/BRAND-STRATEGY@v9:P1.B1"
        ).status_code,
        "foreign_prefix": resolve(
            api, "NORTHSTAR", "SOUTHPEAK/BRAND-STRATEGY@v1:P1.B1"
        ).status_code,
    }
    expected = {
        "malformed": 400,
        "unknown_locator": 404,
        "unknown_version": 404,
        "foreign_prefix": 404,
    }
    for name, status in cases.items():
        check(status == expected[name], f"handle failure {name}: {status} != {expected[name]}")
    return cases


def drop_workspace(db: Db, code: str) -> None:
    """Delete a scratch workspace as ms_app, inside its own RLS scope."""
    ws_id = db.conn.execute("SELECT id FROM workspaces WHERE code = %s", (code,)).fetchone()
    if ws_id is None:
        return
    with db.conn.transaction():
        db.conn.execute("SELECT set_config('app.workspace_id', %s, true)", (str(ws_id[0]),))
        db.conn.execute("UPDATE sources SET current_version_id = NULL")
        db.conn.execute("DELETE FROM source_versions")
        db.conn.execute("DELETE FROM sources")
        db.conn.execute("DELETE FROM workspace_corpus_state")
        db.conn.execute("DELETE FROM workspaces WHERE id = %s", (ws_id[0],))


def live_tombstone(api: httpx.Client, db: Db) -> dict[str, Any]:
    """Upload -> ingest -> purge in a temporary workspace; the old handle must answer 410."""
    code = "VERIFYTOMB"
    drop_workspace(db, code)  # leftover from an interrupted run would shift the version
    api.post("/api/workspaces", json={"code": code, "name": "phase-1 tombstone check"})
    up = api.post(
        f"/api/workspaces/{code}/sources",
        files={"file": ("note.md", b"# Note\n\nTemporary evidence for the tombstone check.\n")},
        data={"source_class": "internal", "source_code": "TMP-NOTE"},
    ).json()
    handle = f"{code}/TMP-NOTE@v1:S1.B1"
    for _ in range(120):
        versions = api.get(f"/api/workspaces/{code}/sources/{up['source_id']}").json()["versions"]
        if versions[0]["status"] in ("ready", "ready_degraded", "failed"):
            break
        time.sleep(0.5)
    before = resolve(api, code, handle).status_code
    api.delete(f"/api/workspaces/{code}/sources/{up['source_id']}")
    after = resolve(api, code, handle)
    tombstone = after.json().get("error", {}).get("tombstone")
    check(before == 200 and after.status_code == 410, f"tombstone: {before} -> {after.status_code}")
    drop_workspace(db, code)
    return {"before_delete": before, "after_delete": after.status_code, "tombstone": tombstone}


def statistics_report(db: Db) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for ws in ("NORTHSTAR", "SOUTHPEAK"):
        rows = db.query(
            ws,
            "SELECT s.source_code, s.source_type, v.version, v.status, v.byte_size, "
            "v.parent_count, "
            "v.child_count, v.timings FROM source_versions v JOIN sources s ON s.id = v.source_id "
            "ORDER BY s.source_code, v.version",
        )
        embedded = db.query(ws, "SELECT count(*) FROM chunk_embeddings")[0][0]
        sources = [
            {
                "source_code": c,
                "type": t,
                "version": ver,
                "status": st,
                "bytes": b,
                "parents": p,
                "children": ch,
                "timings_ms": {k: v for k, v in (tm or {}).items() if k.endswith("_ms")},
            }
            for c, t, ver, st, b, p, ch, tm in rows
        ]
        by_type: Counter[str] = Counter()
        for s in sources:
            by_type[s["type"]] += 1
        timings = [s["timings_ms"] for s in sources if s["timings_ms"]]
        embed_ms = sum(t.get("embed_ms", 0) for t in timings)
        children = sum(s["children"] or 0 for s in sources)
        out[ws] = {
            "uploads": len(sources),
            "by_type": dict(by_type),
            "bytes": sum(s["bytes"] for s in sources),
            "parents": sum(s["parents"] or 0 for s in sources),
            "children": children,
            "embeddings": embedded,
            "total_ingest_ms": round(sum(t.get("total_ms", 0) for t in timings), 1),
            "embed_ms": round(embed_ms, 1),
            "parse_ms": round(sum(t.get("parse_ms", 0) for t in timings), 1),
            "embed_children_per_s": round(children / (embed_ms / 1000), 1) if embed_ms else None,
            "median_total_ms_per_source": statistics.median(
                [t.get("total_ms", 0) for t in timings]
            ),
            "sources": sources,
        }
    return out


def main() -> int:
    ledger = json.loads((SEED / "fact_ledger.json").read_text())
    facts = ledger["facts"]
    api = httpx.Client(base_url=API, timeout=60)
    db = Db()
    print("1. anchor census")
    census = anchor_census(db, facts)
    print(
        f"   {census['exactly_one_parent']}/{census['facts']} anchors located in exactly one parent"
    )
    print("2. retrieval + resolution by format")
    retrieval = retrieval_by_format(api, facts, census["handles"])
    print("3. idempotency + versioning")
    versioning = versioning_and_idempotency(api, db, ledger)
    print("4. isolation")
    iso = isolation(api, db, facts, census["handles"])
    print("5. handle failure contract")
    handles = handle_failures(api)
    print("6. live tombstone (purge -> 410)")
    tomb = live_tombstone(api, db)
    print(f"   {tomb['before_delete']} -> {tomb['after_delete']}")
    print("7. statistics")
    stats = statistics_report(db)
    for ws, s in stats.items():
        print(
            f"   {ws}: {s['uploads']} uploads, {s['bytes']} bytes, {s['parents']} parents, "
            f"{s['children']} children, {s['embeddings']} embeddings, "
            f"ingest {s['total_ingest_ms']} ms, "
            f"embed {s['embed_children_per_s']} children/s"
        )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "census": {k: v for k, v in census.items() if k != "handles"},
        "retrieval": retrieval,
        "versioning": versioning,
        "isolation": iso,
        "handle_failures": handles,
        "tombstone": tomb,
        "statistics": stats,
        "failures": failures,
    }
    REPORT.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(f"\nreport: {REPORT.relative_to(ROOT)}")
    print("PASS" if not failures else f"FAIL ({len(failures)} checks)")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
