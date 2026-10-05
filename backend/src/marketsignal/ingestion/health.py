"""Post-index health check on a version *before* it becomes active (plan §4).

For a deterministic sample of children:

* lexical: the child's own ``tsv_body`` matches a query built from its own words (the generated
  FTS column is populated and matchable);
* dense (when embeddings exist): an exact nearest-neighbour query over the version returns the
  child itself in the top-k (vectors are stored, retrievable and not degenerate);
* span: ``parent.text[char_start:char_end]`` equals the window text, or is contained in a row
  child's retrieval text (D1 contract holds in the database, not only in memory).

A failure blocks activation (``HEALTH_CHECK_FAILED``) rather than silently serving bad evidence.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.config import Settings

_QUERY_WORDS = 12


async def check_version_health(
    session: AsyncSession, version_id: uuid.UUID, model_id: str | None, settings: Settings
) -> dict[str, Any]:
    sample = (
        await session.execute(
            text(
                "SELECT c.id, c.kind, c.text, c.char_start, c.char_end, "
                "substr(p.text, c.char_start + 1, c.char_end - c.char_start) AS span "
                "FROM child_chunks c JOIN parent_chunks p ON p.id = c.parent_id "
                "WHERE c.source_version_id = :v ORDER BY md5(c.id::text) LIMIT :n"
            ),
            {"v": version_id, "n": settings.health_sample_size},
        )
    ).all()
    result: dict[str, Any] = {
        "ok": True,
        "reason": "",
        "checked": len(sample),
        "lexical_ok": 0,
        "dense_ok": 0,
        "span_ok": 0,
        "dense_checked": model_id is not None,
    }
    for child_id, kind, child_text, _cs, _ce, span in sample:
        span_ok = span == child_text if kind == "window" else (span and span in child_text)
        result["span_ok"] += int(bool(span_ok))

        words = " ".join(child_text.split()[:_QUERY_WORDS])
        lexical = (
            await session.execute(
                text(
                    "SELECT numnode(q) = 0 OR c.tsv_body @@ q FROM child_chunks c, "
                    "plainto_tsquery('english', :q) q WHERE c.id = :id"
                ),
                {"q": words, "id": child_id},
            )
        ).scalar_one()
        result["lexical_ok"] += int(bool(lexical))

        if model_id is not None:
            dims = settings.embed_dimensions
            top = (
                await session.execute(
                    text(
                        f"WITH q AS (SELECT embedding::vector({dims}) AS v FROM chunk_embeddings "  # noqa: S608 - dims is an int setting
                        f"WHERE child_id = :id AND model_id = :m) "
                        f"SELECT e.child_id, (e.embedding::vector({dims})) <=> q.v AS d "
                        f"FROM chunk_embeddings e JOIN child_chunks c ON c.id = e.child_id, q "
                        f"WHERE c.source_version_id = :v AND e.model_id = :m "
                        f"ORDER BY d, e.child_id LIMIT :k"
                    ),
                    {
                        "v": version_id,
                        "m": model_id,
                        "id": child_id,
                        "k": settings.health_dense_top_k,
                    },
                )
            ).all()
            # Self, or an exact duplicate (identical text => identical vector), must rank first.
            found = any(cid == child_id for cid, _ in top) or (bool(top) and top[0][1] < 1e-6)
            result["dense_ok"] += int(found)

    failures = []
    if result["span_ok"] != len(sample):
        failures.append("child span does not match parent text")
    if result["lexical_ok"] != len(sample):
        failures.append("lexical index does not match child text")
    if model_id is not None and result["dense_ok"] != len(sample):
        failures.append("dense self-retrieval failed")
    if failures:
        result["ok"] = False
        result["reason"] = "; ".join(failures)
    return result
