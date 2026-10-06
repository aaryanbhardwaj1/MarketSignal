"""``search_evidence_keyword``: exact, case-insensitive matching for identifiers, names and
quoted phrases, with exhaustive counts.

Matching is over *parent* text (what is cited), restricted exactly like the production lanes:
the active version of each non-deleted source, an explicit ``workspace_id`` predicate on top of
RLS, the class/source filters and the run's maximum confidentiality. ``all`` = every term in
the passage, ``any`` = at least one, ``phrase`` = the terms in order as one whitespace-
normalized phrase. Matching uses ``strpos`` on ``lower()`` text, so no user text is ever
interpreted as a pattern, regex or tsquery (``RV-00412`` matches literally).

``total_matches`` and ``matches_by_source`` count every matching passage; hits are the first
``limit`` passages ordered by matched-term count, then source code, then passage ordinal
(deterministic). Each hit's anchor is the first child window (by ordinal) that contains a term.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from marketsignal.db.session import scoped_session
from marketsignal.retrieval.lanes import LaneScope, lane_scope
from marketsignal.retrieval.types import RetrievalFilters, allowed_confidentiality
from marketsignal.tools.contracts import (
    SOURCE_CLASS_FILTERED,
    EvidenceHit,
    KeywordSearchIn,
    KeywordSearchOut,
)
from marketsignal.tools.env import ToolEnv, ToolInputError
from marketsignal.tools.impl.common import compact, snippet

DEFAULT_LIMIT = 10
TERM_MAX_CHARS = 60

_TERM_COUNT = (
    "(SELECT count(*) FROM unnest(CAST(:terms AS text[])) t "
    "WHERE strpos(lower(p.text), lower(t)) > 0)"
)
_MODE_PREDICATE = {  # constant fragments chosen by the validated mode; never user text
    "all": "m.n = cardinality(CAST(:terms AS text[]))",
    "any": "m.n > 0",
    "phrase": "strpos(regexp_replace(lower(m.text), '\\s+', ' ', 'g'), lower(:phrase)) > 0",
}
_MATCHED = (
    "WITH m AS ("  # noqa: S608 - constant fragments only
    "  SELECT p.id, p.handle, p.ordinal, p.locator_label, p.text, s.source_code, s.title, "
    f"   v.source_class, {_TERM_COUNT} AS n "
    "  FROM parent_chunks p JOIN source_versions v ON v.id = p.source_version_id "
    "  JOIN sources s ON s.id = v.source_id "
    "  WHERE p.workspace_id = :ws AND p.source_version_id = ANY(CAST(:active AS uuid[])) "
    "    AND v.confidentiality = ANY(CAST(:conf AS text[])) "
    "    AND (cardinality(CAST(:classes AS text[])) = 0 "
    "         OR v.source_class = ANY(CAST(:classes AS text[])))"
    "), matched AS (SELECT * FROM m WHERE {predicate}) "
)
_COUNTS = "SELECT source_code, count(*) FROM matched GROUP BY source_code ORDER BY source_code"
_HITS = (
    "SELECT mt.handle, mt.locator_label, mt.source_code, mt.title, mt.source_class, "
    "  a.id, a.char_start, a.char_end, a.text "
    "FROM matched mt CROSS JOIN LATERAL ("
    "  SELECT c.id, c.char_start, c.char_end, c.text FROM child_chunks c "
    "  WHERE c.workspace_id = :ws AND c.parent_id = mt.id "
    "  ORDER BY (SELECT count(*) FROM unnest(CAST(:terms AS text[])) t "
    "            WHERE strpos(lower(c.text), lower(t)) > 0) > 0 DESC, c.ordinal LIMIT 1"
    ") a "
    "ORDER BY mt.n DESC, mt.source_code, mt.ordinal LIMIT :limit"
)


def normalize_terms(terms: list[str]) -> list[str]:
    """Whitespace-collapsed, de-duplicated (case-insensitively, order kept), non-empty, bounded."""
    out: dict[str, str] = {}
    for term in terms:
        flat = compact(term)
        if not flat or len(flat) > TERM_MAX_CHARS:
            raise ToolInputError(f"each term must be 1..{TERM_MAX_CHARS} characters")
        out.setdefault(flat.lower(), flat)
    return list(out.values())


async def keyword_search(
    session: Any,
    scope: LaneScope,
    terms: list[str],
    match: str,
    limit: int,
) -> tuple[dict[str, int], list[tuple[Any, ...]]]:
    """Exhaustive per-source counts and the first ``limit`` hit rows (see the module doc)."""
    if not scope.active_version_ids:
        return {}, []
    sql = _MATCHED.format(predicate=_MODE_PREDICATE[match])
    params = {
        "ws": scope.workspace_id,
        "active": list(scope.active_version_ids),
        "conf": allowed_confidentiality(scope.filters.max_confidentiality),
        "classes": list(scope.filters.source_classes),
        "terms": terms,
        "phrase": " ".join(terms),
        "limit": limit,
    }
    counts = {str(r[0]): int(r[1]) for r in (await session.execute(text(sql + _COUNTS), params))}
    rows = [tuple(r) for r in (await session.execute(text(sql + _HITS), params)).all()]
    return counts, rows


async def search_evidence_keyword(env: ToolEnv, args: KeywordSearchIn) -> KeywordSearchOut:
    terms = normalize_terms(args.terms)
    match = args.match or "all"
    classes = env.classes(args.source_classes)
    if classes is None:
        return KeywordSearchOut(
            total_matches=0, matches_by_source={}, hits=[], warnings=[SOURCE_CLASS_FILTERED]
        )
    filters = RetrievalFilters.of(
        classes,
        args.source_codes or (),
        env.max_confidentiality,
    )
    async with scoped_session(env.factory, env.scope) as session:
        scope = await lane_scope(session, env.scope.workspace_id, filters)
        counts, rows = await keyword_search(
            session, scope, terms, match, args.limit or DEFAULT_LIMIT
        )
    hits = [_hit(rank, row, terms) for rank, row in enumerate(rows, start=1)]
    return KeywordSearchOut(total_matches=sum(counts.values()), matches_by_source=counts, hits=hits)


def _hit(rank: int, row: tuple[Any, ...], terms: list[str]) -> EvidenceHit:
    child_text = compact(str(row[8]))
    lowered = child_text.lower()
    positions = [p for p in (lowered.find(t.lower()) for t in terms) if p >= 0]
    return EvidenceHit(
        handle=str(row[0]),
        source_code=str(row[2]),
        source_title=str(row[3]),
        source_class=str(row[4]),
        locator_label=str(row[1]),
        snippet=snippet(child_text, around=min(positions) if positions else None),
        anchor_child_id=str(row[5]),
        anchor_char_start=int(row[6]),
        anchor_char_end=int(row[7]),
        fused_rank=rank,
    )
