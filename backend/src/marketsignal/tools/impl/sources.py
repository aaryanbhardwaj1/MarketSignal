"""``list_sources``: the workspace catalogue - active, non-deleted sources the run may see
(class filter and maximum confidentiality applied), ordered by source code."""

from __future__ import annotations

from sqlalchemy import text

from marketsignal.db.session import scoped_session
from marketsignal.retrieval.types import allowed_confidentiality
from marketsignal.tools.contracts import ListSourcesIn, ListSourcesOut, SourceCard
from marketsignal.tools.env import ToolEnv

MAX_SOURCES = 50

_SOURCES = """
SELECT s.source_code, s.title, v.source_class, s.source_type, v.version,
       (SELECT count(*) FROM parent_chunks p
        WHERE p.workspace_id = :ws AND p.source_version_id = v.id) AS parents
FROM sources s JOIN source_versions v ON v.id = s.current_version_id
WHERE s.workspace_id = :ws AND s.deleted_at IS NULL AND v.status IN ('ready', 'ready_degraded')
  AND v.confidentiality = ANY(CAST(:conf AS text[]))
  AND (cardinality(CAST(:classes AS text[])) = 0 OR v.source_class = ANY(CAST(:classes AS text[])))
ORDER BY s.source_code
LIMIT :limit
"""


async def list_sources(env: ToolEnv, args: ListSourcesIn) -> ListSourcesOut:
    async with scoped_session(env.factory, env.scope) as session:
        rows = (
            await session.execute(
                text(_SOURCES),
                {
                    "ws": env.scope.workspace_id,
                    "conf": allowed_confidentiality(env.max_confidentiality),
                    "classes": sorted({c.value for c in args.source_classes or ()}),
                    "limit": MAX_SOURCES + 1,  # one extra row tells the governor to flag TRUNCATED
                },
            )
        ).all()
    return ListSourcesOut(
        sources=[
            SourceCard(
                source_code=r[0],
                title=r[1],
                source_class=r[2],
                source_type=r[3],
                version=int(r[4]),
                parent_count=int(r[5]),
            )
            for r in rows
        ]
    )
