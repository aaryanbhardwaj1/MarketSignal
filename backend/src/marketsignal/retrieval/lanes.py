"""Production candidate lanes: dense (pgvector) and lexical (IDF-weighted Postgres FTS).

Both lanes:
* search only the *active* version of each non-deleted source, from one active-version read;
* add an explicit ``workspace_id`` predicate on top of RLS (defence in depth, and it lets the
  planner use the ``(workspace_id, source_version_id)`` index);
* apply the request filters (source classes, source codes, maximum confidentiality);
* return children in a deterministic order - every ranked query ends ``…, child_id``;
* return the anchor metadata (child id, parent handle, ``char_start/char_end``) so a parent
  result can be highlighted at the exact span that matched.

Lexical (plan §11): lexemes come from ``to_tsvector('english', query)`` (Postgres, never Python
tokens, so stemming/stopwords match the index); the query is an OR of those lexemes; a child's
score is the sum of IDF over the lexemes it contains, IDF from document frequencies over
``tsv_body`` (headings excluded) cached per (workspace, corpus version); quoted phrases add a
bonus; ties break on a heading-damped ``ts_rank_cd`` then child id. User text never reaches
``to_tsquery``.
"""

from __future__ import annotations

import math
import re
import unicodedata
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.ingestion.repository import vector_literal
from marketsignal.providers.embeddings import Vector
from marketsignal.retrieval.types import ChildHit, RetrievalFilters, allowed_confidentiality

LEXICAL = "lexical"
DENSE = "dense"
_PHRASE = re.compile(r'"([^"]{2,200})"')
_MAX_QUERY_CHARS = 1000

_ACTIVE_VERSIONS = """
SELECT v.id FROM sources s JOIN source_versions v ON v.id = s.current_version_id
WHERE s.deleted_at IS NULL AND v.status IN ('ready', 'ready_degraded')
  AND (cardinality(CAST(:codes AS text[])) = 0 OR s.source_code = ANY(CAST(:codes AS text[])))
ORDER BY v.id
"""

_CHILD_FILTER = (
    "c.workspace_id = :ws AND c.source_version_id = ANY(CAST(:active AS uuid[])) "
    "AND c.confidentiality = ANY(CAST(:conf AS text[])) "
    "AND (cardinality(CAST(:classes AS text[])) = 0 "
    "     OR c.source_class = ANY(CAST(:classes AS text[])))"
)
_HIT_COLUMNS = (
    "c.id, c.parent_id, p.handle, s.source_code, c.source_class, c.kind, c.char_start, c.char_end"
)
_HIT_JOINS = (
    "JOIN parent_chunks p ON p.id = c.parent_id "
    "JOIN source_versions v ON v.id = c.source_version_id "
    "JOIN sources s ON s.id = v.source_id"
)


@dataclass(frozen=True, slots=True)
class LaneScope:
    """What every lane query is restricted to, read once per request."""

    workspace_id: uuid.UUID
    active_version_ids: tuple[uuid.UUID, ...]
    filters: RetrievalFilters

    def params(self, classes: tuple[str, ...] | None = None) -> dict[str, Any]:
        return {
            "ws": self.workspace_id,
            "active": list(self.active_version_ids),
            "conf": allowed_confidentiality(self.filters.max_confidentiality),
            "classes": list(self.filters.source_classes if classes is None else classes),
        }


async def lane_scope(
    session: AsyncSession, workspace_id: uuid.UUID, filters: RetrievalFilters
) -> LaneScope:
    rows = await session.execute(text(_ACTIVE_VERSIONS), {"codes": list(filters.source_codes)})
    return LaneScope(workspace_id, tuple(r[0] for r in rows.all()), filters)


def _hits(lane: str, rows: Any) -> list[ChildHit]:
    return [
        ChildHit(
            lane=lane,
            rank=i,
            score=float(r[8]),
            child_id=r[0],
            parent_id=r[1],
            parent_handle=r[2],
            source_code=r[3],
            source_class=r[4],
            kind=r[5],
            char_start=r[6],
            char_end=r[7],
        )
        for i, r in enumerate(rows, start=1)
    ]


# --- dense ------------------------------------------------------------------------------------


async def dense_lane(
    session: AsyncSession,
    scope: LaneScope,
    query_vector: Vector,
    *,
    model_id: str,
    dimensions: int,
    k: int,
    ef_search: int,
    exact: bool = False,
    classes: tuple[str, ...] | None = None,
) -> list[ChildHit]:
    """Canonical dense query (plan §7): transaction-local HNSW settings, MATERIALIZED CTE with
    all filters inside it, ``ORDER BY distance + 0, child_id`` outside (needed on PG17+).
    ``exact`` disables index scans for this transaction, forcing an exact (sequential) scan."""
    if not scope.active_version_ids:
        return []
    await session.execute(
        text(
            "SELECT set_config('hnsw.ef_search', :ef, true), "
            "set_config('hnsw.iterative_scan', 'relaxed_order', true), "
            "set_config('enable_indexscan', :idx, true)"
        ),
        {"ef": str(ef_search), "idx": "off" if exact else "on"},
    )
    rows = await session.execute(
        text(
            f"WITH dense AS MATERIALIZED ("  # noqa: S608 - dims is an int setting, rest constants
            f"  SELECT e.child_id, (e.embedding::vector({dimensions})) <=> "
            f"         CAST(:q AS vector({dimensions})) AS distance "
            f"  FROM chunk_embeddings e JOIN child_chunks c ON c.id = e.child_id "
            f"  WHERE e.model_id = :m AND e.workspace_id = :ws AND {_CHILD_FILTER} "
            f"  ORDER BY distance LIMIT :k) "
            f"SELECT {_HIT_COLUMNS}, 1 - d.distance AS score FROM dense d "
            f"JOIN child_chunks c ON c.id = d.child_id {_HIT_JOINS} "
            f"ORDER BY d.distance + 0, c.id"
        ),
        {"q": vector_literal(query_vector), "m": model_id, "k": k, **scope.params(classes)},
    )
    return _hits(DENSE, rows.all())


# --- lexical ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LexicalQuery:
    lexemes: tuple[str, ...]  # after DF pruning
    idf: tuple[float, ...]
    phrases: tuple[str, ...]
    pruned: tuple[str, ...]


def normalize_query(query: str) -> str:
    return unicodedata.normalize("NFKC", query)[:_MAX_QUERY_CHARS].lower()


def quoted_phrases(query: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(m.strip() for m in _PHRASE.findall(query) if m.strip()))


# Constant ts_stat input: every active child body in the scoped workspace (RLS restricts rows to
# the current workspace). DF is computed over the whole active workspace corpus, independent of
# per-request filters, so term weights are stable across filtered and unfiltered requests.
_DF_SQL = (
    "SELECT c.tsv_body FROM child_chunks c "
    "JOIN sources s ON s.current_version_id = c.source_version_id "
    "JOIN source_versions v ON v.id = c.source_version_id "
    "WHERE s.deleted_at IS NULL AND v.status IN ('ready', 'ready_degraded')"
)


class DocumentFrequencies:
    """``ts_stat`` over ``tsv_body`` of active children, cached per (workspace, corpus version).

    Only body text counts toward DF, so a heading repeated on every window of a long section does
    not make its words look common (plan §11). Activation and purge bump the corpus version, so
    a stale entry is never reused after the corpus changes."""

    def __init__(self, max_entries: int = 32) -> None:
        self._max = max_entries
        self._cache: OrderedDict[tuple[uuid.UUID, int], tuple[int, dict[str, int]]] = OrderedDict()

    async def get(self, session: AsyncSession, scope: LaneScope) -> tuple[int, dict[str, int]]:
        version = (
            await session.execute(
                text("SELECT version FROM workspace_corpus_state WHERE workspace_id = :ws"),
                {"ws": scope.workspace_id},
            )
        ).scalar_one_or_none() or 0
        key = (scope.workspace_id, int(version))
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        n = (
            await session.execute(text(f"SELECT count(*) FROM ({_DF_SQL}) d"))  # noqa: S608 - constant
        ).scalar_one()
        rows = await session.execute(text("SELECT word, ndoc FROM ts_stat(:sql)"), {"sql": _DF_SQL})
        value = (int(n), {str(w): int(d) for w, d in rows.all()})
        self._cache[key] = value
        while len(self._cache) > self._max:
            self._cache.popitem(last=False)
        return value


def idf(n: int, df: int) -> float:
    """``ln(1 + (N - df + 0.5) / (df + 0.5))`` - BM25's IDF, always positive."""
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


async def build_lexical_query(
    session: AsyncSession,
    query: str,
    stats: tuple[int, dict[str, int]],
    *,
    df_prune: float,
) -> LexicalQuery:
    normalized = normalize_query(query)
    lexemes = [
        str(r[0])
        for r in (
            await session.execute(
                text(
                    "SELECT lexeme FROM (SELECT DISTINCT unnest(tsvector_to_array("
                    "to_tsvector('english', :q))) AS lexeme) t ORDER BY lexeme"
                ),
                {"q": normalized},
            )
        ).all()
    ]
    n, df = stats
    kept = [lx for lx in lexemes if n == 0 or df.get(lx, 0) / max(n, 1) <= df_prune]
    pruned = [lx for lx in lexemes if lx not in kept]
    if not kept:  # never prune the query to empty
        kept, pruned = lexemes, []
    return LexicalQuery(
        lexemes=tuple(kept),
        idf=tuple(idf(n, df.get(lx, 0)) for lx in kept),
        phrases=quoted_phrases(normalized),
        pruned=tuple(pruned),
    )


async def lexical_lane(
    session: AsyncSession,
    scope: LaneScope,
    lq: LexicalQuery,
    *,
    k: int,
    phrase_bonus: float,
    classes: tuple[str, ...] | None = None,
) -> list[ChildHit]:
    if not scope.active_version_ids or not lq.lexemes:
        return []
    rows = await session.execute(
        text(
            "WITH terms AS ("  # noqa: S608 - constant fragments only
            "  SELECT t.idf, quote_literal(t.lexeme)::tsquery AS q "
            "  FROM unnest(CAST(:lexemes AS text[]), CAST(:idfs AS float8[])) AS t(lexeme, idf)"
            "), phrases AS ("
            "  SELECT phraseto_tsquery('english', p) AS q FROM unnest(CAST(:phrases AS text[])) p"
            "), anyq AS ("
            "  SELECT string_agg(quote_literal(l), ' | ')::tsquery AS q "
            "  FROM unnest(CAST(:lexemes AS text[])) l"
            "), scored AS ("
            "  SELECT c.id, "
            "    (SELECT coalesce(sum(t.idf), 0) FROM terms t WHERE c.tsv @@ t.q) "
            "    + :bonus * (SELECT count(*) FROM phrases ph "
            "                WHERE numnode(ph.q) > 0 AND c.tsv @@ ph.q) AS score, "
            "    ts_rank_cd('{0.1,0.2,0.3,0.3}', c.tsv, (SELECT q FROM anyq), 1) AS tiebreak "
            "  FROM child_chunks c "
            f"  WHERE {_CHILD_FILTER} AND c.tsv @@ (SELECT q FROM anyq) "
            "  ORDER BY score DESC, tiebreak DESC, c.id LIMIT :k"
            ") "
            f"SELECT {_HIT_COLUMNS}, sc.score FROM scored sc "
            f"JOIN child_chunks c ON c.id = sc.id {_HIT_JOINS} "
            "ORDER BY sc.score DESC, sc.tiebreak DESC, c.id"
        ),
        {
            "lexemes": list(lq.lexemes),
            "idfs": list(lq.idf),
            "phrases": list(lq.phrases),
            "bonus": phrase_bonus,
            "k": k,
            **scope.params(classes),
        },
    )
    return _hits(LEXICAL, rows.all())
