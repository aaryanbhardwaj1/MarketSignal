"""Phase 1 *smoke* search: single-lane lexical or dense lookups used to verify ingestion.

Deliberately NOT the retrieval pipeline: no fusion, reranking, balancing or expansion (those are
Phase 2, ADR-0002/0005). Both lanes search only the *current, ready* version of each
non-deleted source, scoped by RLS plus an explicit workspace predicate, and return the anchor
child's span so a hit can be highlighted inside its parent.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.ingestion.repository import vector_literal
from marketsignal.providers.embeddings import Vector

_ACTIVE = (
    "SELECT s.current_version_id FROM sources s JOIN source_versions v "
    "ON v.id = s.current_version_id WHERE s.deleted_at IS NULL "
    "AND v.status IN ('ready', 'ready_degraded')"
)
_HIT_COLUMNS = (
    "c.id, p.handle, p.locator_label, s.source_code, s.title, c.source_class, c.kind, "
    "c.char_start, c.char_end, left(c.text, 280)"
)


@dataclass(frozen=True, slots=True)
class SmokeHit:
    rank: int
    child_id: uuid.UUID
    handle: str
    locator_label: str
    source_code: str
    source_title: str
    source_class: str
    child_kind: str
    char_start: int
    char_end: int
    snippet: str
    score: float

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["child_id"] = str(self.child_id)
        return out


def _hits(rows: Any) -> list[SmokeHit]:
    return [
        SmokeHit(
            rank=i,
            child_id=r[0],
            handle=r[1],
            locator_label=r[2],
            source_code=r[3],
            source_title=r[4],
            source_class=r[5],
            child_kind=r[6],
            char_start=r[7],
            char_end=r[8],
            snippet=r[9],
            score=float(r[10]),
        )
        for i, r in enumerate(rows, start=1)
    ]


async def lexical_search(
    session: AsyncSession, workspace_id: uuid.UUID, query: str, k: int
) -> list[SmokeHit]:
    rows = await session.execute(
        text(
            f"SELECT {_HIT_COLUMNS}, ts_rank_cd(c.tsv, q) AS score "  # noqa: S608 - constants only
            "FROM child_chunks c JOIN parent_chunks p ON p.id = c.parent_id "
            "JOIN source_versions v ON v.id = c.source_version_id "
            "JOIN sources s ON s.id = v.source_id, "
            "websearch_to_tsquery('english', :q) q "
            f"WHERE c.workspace_id = :ws AND c.source_version_id IN ({_ACTIVE}) AND c.tsv @@ q "
            "ORDER BY score DESC, c.id LIMIT :k"
        ),
        {"q": query, "ws": workspace_id, "k": k},
    )
    return _hits(rows.all())


async def dense_search(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    query_vector: Vector,
    *,
    model_id: str,
    dimensions: int,
    k: int,
    ef_search: int,
) -> list[SmokeHit]:
    # Transaction-local HNSW settings (SET LOCAL outside a transaction is a silent no-op).
    await session.execute(
        text(
            "SELECT set_config('hnsw.ef_search', :ef, true), "
            "set_config('hnsw.iterative_scan', 'relaxed_order', true)"
        ),
        {"ef": str(ef_search)},
    )
    rows = await session.execute(
        text(
            f"WITH dense AS MATERIALIZED ("  # noqa: S608 - dims is an int setting, rest constants
            f"  SELECT e.child_id, (e.embedding::vector({dimensions})) <=> "
            f"         CAST(:q AS vector({dimensions})) AS distance "
            f"  FROM chunk_embeddings e JOIN child_chunks c ON c.id = e.child_id "
            f"  WHERE e.model_id = :m AND e.workspace_id = :ws "
            f"    AND c.source_version_id IN ({_ACTIVE}) "
            f"  ORDER BY distance LIMIT :k) "
            f"SELECT {_HIT_COLUMNS}, 1 - d.distance AS score FROM dense d "
            f"JOIN child_chunks c ON c.id = d.child_id JOIN parent_chunks p ON p.id = c.parent_id "
            f"JOIN source_versions v ON v.id = c.source_version_id "
            f"JOIN sources s ON s.id = v.source_id "
            f"ORDER BY d.distance + 0, c.id"
        ),
        {"q": vector_literal(query_vector), "m": model_id, "ws": workspace_id, "k": k},
    )
    return _hits(rows.all())
