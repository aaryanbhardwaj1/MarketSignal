"""Compose a grounded deck from the re-verified brief and analyses (no model, no I/O).

Selected items are taken in the brief's curated order. Unverified items, analyses that did not
recompute, and items whose main claim lost its grounding (``decks.grounding``) are excluded and
reported. Slide text is copied from the selected items, never written here, except for fixed
section titles, status labels and evidence counts. Each bullet cites numbered sources; the
slide's speaker notes list those sources (with handles, for audit) and the appendix lists all.

Structure: title, executive summary, key customer findings, quantitative evidence, competitor
and market findings, growth opportunities (one slide each), risks and blockers, recommended
next steps, appendix. Content slides with nothing to show are omitted; long sections continue
on ``(cont.)`` slides.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from marketsignal.decks import grounding as g
from marketsignal.decks.models import (
    CLAIM_LABELS,
    OPPORTUNITY_STATUS,
    SIGNAL_KIND,
    SIGNAL_STATUS,
    DeckRequest,
)
from marketsignal.decks.quant import analysis_block, metric_item
from marketsignal.decks.sources import Sources

MAX_BULLETS = 5
STATUS_ROWS = 8
METRICS_PER_SLIDE = 6
SOURCES_PER_SLIDE = 6
CONT = " (cont.)"
CUSTOMER_KINDS = frozenset({"emerging_signal", "optimization"})
MARKET_KINDS = frozenset({"competitor_finding", "future_outlook"})
UNVERIFIED = "Its evidence could not be re-verified against the current sources."
UNGROUNDED = "Its main claim no longer has verified support."
NOT_COMPUTED = "Its figures could not be recomputed from the current data."
NOTHING = "None of the selected items could be re-verified against the current sources."


class UnknownItemsError(ValueError):
    def __init__(self, unknown: list[str]) -> None:
        super().__init__(f"unknown items: {', '.join(unknown)}")
        self.unknown = unknown


@dataclass(frozen=True, slots=True)
class _Item:
    raw: dict[str, Any]
    claim: str | None  # effective claim type of the headline claim
    support: list[dict[str, Any]]  # verified supporting passages
    refs: list[dict[str, Any]]  # every verified passage (support and contradict)
    metrics: list[dict[str, Any]]  # computed metrics only


def _pick(items: list[dict[str, Any]], ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    wanted = set(ids)
    known = {i["id"] for i in items}
    return [i for i in items if i["id"] in wanted], [i for i in ids if i not in known]


def _prepare(
    raw: dict[str, Any],
    claim: str | None,
    refs: list[dict[str, Any]],
    excluded: list[dict[str, str]],
) -> _Item | None:
    if raw.get("integrity") == "unverified":
        excluded.append({"id": raw["id"], "reason": UNVERIFIED})
        return None
    item = _Item(
        raw,
        g.effective_claim(claim, raw.get("integrity", "")),
        g.supporting(refs),
        g.verified(refs),
        g.live_metrics(raw.get("metrics", [])),
    )
    if not g.grounded(item.claim, item.support, item.refs, item.metrics):
        excluded.append({"id": raw["id"], "reason": UNGROUNDED})
        return None
    return item


class _Composer:
    def __init__(self, analyses: dict[str, dict[str, Any]]) -> None:
        self.sources = Sources(analyses)
        self.analyses = analyses
        self.slides: list[dict[str, Any]] = []

    # citations -------------------------------------------------------------------------------
    def cite(
        self, refs: Iterable[dict[str, Any]], metrics: Iterable[dict[str, Any]] = ()
    ) -> list[int]:
        out = [self.sources.passage(r) for r in refs]
        out += [n for m in metrics if (n := self.sources.analysis(m["analysis_id"])) is not None]
        return out

    def claim_cites(self, item: _Item) -> list[int]:
        return self.cite(item.support, item.metrics if item.claim == "derived" else ())

    # slides ----------------------------------------------------------------------------------
    def add(self, kind: str, title: str, blocks: list[dict[str, Any]], **extra: Any) -> None:
        cites = sorted(
            {n for b in blocks for i in b.get("items", []) for n in i.get("cites", [])}
            | {n for b in blocks for n in b.get("cites", [])}
        )
        notes = [{k: self.sources.get(n)[k] for k in _NOTE_KEYS} for n in cites]
        self.slides.append(
            {
                "index": len(self.slides) + 1,
                "kind": kind,
                "title": title,
                "subtitle": extra.pop("subtitle", None),
                **extra,
                "blocks": blocks,
                "notes": notes,
            }
        )

    def bullet_section(
        self, kind: str, title: str, groups: list[list[dict[str, Any]]], subtitle: str | None = None
    ) -> None:
        pages: list[list[dict[str, Any]]] = []
        for group in groups:
            for start in range(0, len(group), MAX_BULLETS):
                part = group[start : start + MAX_BULLETS]
                if pages and len(pages[-1]) + len(part) <= MAX_BULLETS:
                    pages[-1].extend(part)
                else:
                    pages.append(list(part))
        for i, page in enumerate(pages):
            block = {"type": "bullets", "items": page}
            self.add(kind, title + (CONT if i else ""), [block], subtitle=subtitle)

    def chunked(self, kind: str, title: str, block_type: str, items: list[Any], size: int) -> None:
        for i, start in enumerate(range(0, len(items), size)):
            block = {"type": block_type, "items": items[start : start + size]}
            self.add(kind, title + (CONT if i else ""), [block])

    def signal_group(self, item: _Item) -> list[dict[str, Any]]:
        s = item.raw
        cites = self.claim_cites(item)
        out = [g.bullet(s["statement"], item.claim, cites, heading=s["title"])]
        imp = s.get("implication")
        if imp:
            out.append(g.bullet(imp["text"], imp["claim_type"], cites, level=1))
        return out


_NOTE_KEYS = ("n", "source_title", "locator", "quote", "handle")


def _summary_rows(
    c: _Composer, signals: list[_Item], opps: list[_Item], analyses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = [
        {
            "title": o.raw["title"],
            "kind_label": "Growth opportunity",
            "status": o.raw.get("status"),
            "status_label": OPPORTUNITY_STATUS.get(o.raw.get("status") or ""),
            "claim_type": None,
            "label": None,
            "cites": sorted(set(c.cite(o.support))),
        }
        for o in opps
    ]
    for s in signals:
        rows.append(
            {
                "title": s.raw["title"],
                "kind_label": SIGNAL_KIND.get(s.raw.get("kind") or "", "Finding"),
                "status": s.raw.get("status"),
                "status_label": SIGNAL_STATUS.get(s.raw.get("status") or ""),
                "claim_type": s.claim,
                "label": CLAIM_LABELS.get(s.claim or ""),
                "cites": sorted(set(c.claim_cites(s))),
            }
        )
    for a in analyses:
        n = c.sources.analysis(a["id"])
        rows.append(
            {
                "title": a["title"],
                "kind_label": "Analysis",
                "status": None,
                "status_label": None,
                "claim_type": "derived",
                "label": None,
                "cites": [] if n is None else [n],
            }
        )
    return rows


def _quantitative(c: _Composer, items: list[_Item], analyses: list[dict[str, Any]]) -> None:
    seen: set[tuple[str, str]] = set()
    callouts: list[dict[str, Any]] = []
    for item in items:
        for m in item.metrics:
            key = (m["analysis_id"], m["label"])
            n = c.sources.analysis(m["analysis_id"])
            if key in seen or n is None:
                continue
            seen.add(key)
            callouts.append(metric_item(m, n))
    c.chunked("quantitative", "Key figures", "metrics", callouts, METRICS_PER_SLIDE)
    for a in analyses:
        n = c.sources.analysis(a["id"])
        if n is None:
            continue
        notes: list[dict[str, Any]] = []
        if a.get("summary") and a.get("summary_status") == "verified":
            notes.append(g.bullet(a["summary"], "derived", [n]))
        interp = a.get("interpretation")
        if interp:
            notes.append(g.bullet(interp["text"], interp["claim_type"], [n]))
        blocks = [analysis_block(a, n)]
        if notes:
            blocks.append({"type": "bullets", "items": notes})
        c.add("quantitative", a["title"], blocks, subtitle="Quantitative evidence")


def _evidence_balance(item: _Item) -> str:
    sup = sum(r["role"] == "support" for r in item.refs)
    con = sum(r["role"] == "contradict" for r in item.refs)
    noun = "passage" if sup <= 1 and con <= 1 else "passages"
    return f"{sup} supporting and {con} contradicting {noun}"


def _opportunity(c: _Composer, o: _Item) -> None:
    raw = o.raw
    cites = c.cite(o.support)
    items = [g.bullet(raw["thesis"], o.claim, cites)]
    why = raw.get("why_it_matters")
    if why:
        items.append(g.bullet(why["text"], why["claim_type"], cites))
    items.append(g.bullet(_evidence_balance(o), None, c.cite(o.refs), heading="Evidence"))
    for m in o.metrics[:1]:
        items.append(g.bullet(f"{m['label']}: {m['display']}", "derived", c.cite([], [m])))
    status = OPPORTUNITY_STATUS.get(raw.get("status") or "")
    subtitle = "Growth opportunity" + (f" · {status}" if status else "")
    c.add("opportunity", raw["title"], [{"type": "bullets", "items": items}], subtitle=subtitle)


def _risk_groups(c: _Composer, signals: list[_Item], opps: list[_Item]) -> list[list[Any]]:
    groups = [c.signal_group(s) for s in signals if s.raw.get("kind") == "risk_blocker"]
    for o in opps:
        for risk in o.raw.get("risks", []):
            if risk.get("integrity") == "unverified":
                continue
            refs = g.verified(risk.get("evidence", []))
            support = g.supporting(refs)
            claim = g.effective_claim(risk.get("claim_type"), risk.get("integrity", ""))
            if not g.grounded(claim, support, refs, []):
                continue
            heading = f"Risk to {o.raw['title']}"
            groups.append([g.bullet(risk["text"], claim, c.cite(support), heading=heading)])
    return groups


def _next_steps(opps: list[_Item]) -> list[list[dict[str, Any]]]:
    groups = []
    for o in opps:
        group = (
            [g.bullet(o.raw["next_step"], heading=o.raw["title"])] if o.raw.get("next_step") else []
        )
        if o.raw.get("next_investigation"):
            group.append(g.bullet(o.raw["next_investigation"], heading="Open question", level=1))
        if group:
            groups.append(group)
    return groups


def _is_customer(item: _Item) -> bool:
    """Customer findings, plus any untyped (v1) signal, which has no other home."""
    kind = item.raw.get("kind")
    return kind in CUSTOMER_KINDS or kind not in MARKET_KINDS | {"risk_blocker"}


def _prepared(
    raws: list[dict[str, Any]],
    claim_key: str,
    refs: Callable[[dict[str, Any]], list[dict[str, Any]]],
    excluded: list[dict[str, str]],
) -> list[_Item]:
    out = [_prepare(raw, raw.get(claim_key), refs(raw), excluded) for raw in raws]
    return [item for item in out if item is not None]


def _date(generated_at: str) -> str:
    dt = datetime.fromisoformat(generated_at)
    return f"{dt.day} {dt:%B %Y}"


def _select(
    brief: dict[str, Any], listing: dict[str, Any], request: DeckRequest
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    signals, u1 = _pick(brief.get("signals", []), request.signal_ids)
    opps, u2 = _pick(brief.get("opportunities", []), request.opportunity_ids)
    analyses, u3 = _pick(listing.get("analyses", []), request.analysis_ids)
    if u1 or u2 or u3:
        raise UnknownItemsError(u1 + u2 + u3)
    return signals, opps, analyses


def compose(
    brief: dict[str, Any],
    listing: dict[str, Any],
    request: DeckRequest,
    *,
    workspace: dict[str, str],
    generated_at: str,
) -> dict[str, Any]:
    """The deck for ``request``; raises :class:`UnknownItemsError` for ids not in the brief."""
    raw_signals, raw_opps, raw_analyses = _select(brief, listing, request)
    excluded: list[dict[str, str]] = []
    signals = _prepared(raw_signals, "claim_type", lambda s: s.get("evidence", []), excluded)
    opps = _prepared(
        raw_opps, "thesis_claim_type", lambda o: o["supporting"] + o["contradicting"], excluded
    )
    analyses = [a for a in raw_analyses if a.get("status") == "computed"]
    excluded += [{"id": a["id"], "reason": NOT_COMPUTED} for a in raw_analyses if a not in analyses]
    c = _Composer({a["id"]: a for a in listing.get("analyses", [])})
    _sections(c, signals, opps, analyses)
    total = len(signals) + len(opps) + len(analyses)
    title = request.title or f"Strategic findings: {workspace['name']}"
    meta = [
        workspace["name"],
        _date(generated_at),
        f"Built from {total} verified finding{'' if total == 1 else 's'}",
    ]
    cover = {"kind": "title", "title": title, "subtitle": request.question, "meta": meta}
    c.slides = [
        {**slide, "index": n}
        for n, slide in enumerate([{**cover, "blocks": [], "notes": []}, *c.slides], start=1)
    ]
    sources = c.sources.all()
    return {
        "title": title,
        "question": request.question,
        "workspace": {"code": workspace["code"], "name": workspace["name"]},
        "generated_at": generated_at,
        "fixture_version": brief.get("fixture_version"),
        "slides": c.slides,
        "sources": sources,
        "excluded": excluded,
        "counts": {"items": total, "sources": len(sources), "slides": len(c.slides)},
    }


def _sections(
    c: _Composer, signals: list[_Item], opps: list[_Item], analyses: list[dict[str, Any]]
) -> None:
    rows = _summary_rows(c, signals, opps, analyses)
    if rows:
        c.chunked("summary", "Executive summary", "statuses", rows, STATUS_ROWS)
    else:
        c.add("summary", "Executive summary", [{"type": "bullets", "items": [g.bullet(NOTHING)]}])
    customer = [c.signal_group(s) for s in signals if _is_customer(s)]
    c.bullet_section("customer_findings", "Key customer findings", customer)
    _quantitative(c, signals + opps, analyses)
    market = [c.signal_group(s) for s in signals if s.raw.get("kind") in MARKET_KINDS]
    c.bullet_section("market_findings", "Competitor and market findings", market)
    for o in opps:
        _opportunity(c, o)
    c.bullet_section("risks", "Risks and blockers", _risk_groups(c, signals, opps))
    c.bullet_section(
        "next_steps", "Recommended next steps", _next_steps(opps), "From the analyst brief"
    )
    sources = [
        {k: s[k] for k in ("n", "source_title", "locator", "quote")} for s in c.sources.all()
    ]
    if sources:
        c.chunked("appendix", "Appendix: Sources", "sources", sources, SOURCES_PER_SLIDE)
    else:
        c.add("appendix", "Appendix: Sources", [{"type": "sources", "items": []}])
    for slide in c.slides:
        if slide["kind"] == "appendix":
            numbers = [i["n"] for b in slide["blocks"] for i in b["items"]]
            slide["notes"] = [{k: c.sources.get(n)[k] for k in _NOTE_KEYS} for n in numbers]
