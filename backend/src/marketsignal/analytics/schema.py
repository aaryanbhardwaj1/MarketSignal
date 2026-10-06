"""Analysable datasets: typed tables of the *active* version of each source.

A dataset is one ``dataset_tables`` row whose version is the source's current version, is
``ready``/``ready_degraded``, belongs to a non-deleted source, has a confidentiality at or below
the token's ``max_conf`` and a class inside the token's class claim (if any). Purged and
superseded versions are therefore never analysable. Dataset id: ``"<SOURCE_CODE>:<sheet>"``.

Units are inferred deterministically from the column type and the column name's ``_``-separated,
lower-cased tokens (first rule that matches wins):

1. type ``date`` -> ``date``; ``text``/``categorical`` -> ``text``;
2. numeric with a token ``pct``/``percent``/``percentage`` -> ``percent``;
3. numeric with a token ``usd`` -> ``currency_usd`` (scale such as ``_m``/``_bn`` stays in the
   column name: ``value_usd_bn`` = 15.1 means USD 15.1 bn);
4. numeric with a token ``rating``/``nps``/``stars``/``score`` -> ``rating``;
5. numeric with a token ``ratio`` -> ``ratio``;
6. numeric with a token ``count``/``units``/``orders``/``sessions``/``qty``/``quantity``/
   ``returns``/``respondents`` -> ``count``;
7. otherwise ``number``.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marketsignal.tools.analytics_contracts import ColumnInfo, DatasetInfo, Unit

SOURCE_CODE_RE = re.compile(r"^[A-Z0-9]{1,12}(-[A-Z0-9]{1,12}){0,5}$")
SHEET_RE = re.compile(r"^[1-9][0-9]{0,3}$")
MAX_DATASETS = 50

_PERCENT = frozenset({"pct", "percent", "percentage"})
_RATING = frozenset({"rating", "nps", "stars", "score"})
_COUNT = frozenset(
    {"count", "units", "orders", "sessions", "qty", "quantity", "returns", "respondents"}
)
_TOKEN = re.compile(r"[^a-z0-9]+")


def infer_unit(name: str, column_type: str) -> Unit:
    if column_type == "date":
        return "date"
    if column_type != "numeric":
        return "text"
    tokens = set(_TOKEN.split(name.lower()))
    if tokens & _PERCENT:
        return "percent"
    if "usd" in tokens:
        return "currency_usd"
    if tokens & _RATING:
        return "rating"
    if "ratio" in tokens:
        return "ratio"
    if tokens & _COUNT:
        return "count"
    return "number"


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    name: str
    type: str  # numeric | categorical | text | date
    role: str
    unit: Unit
    levels: tuple[str, ...]
    distinct: int
    non_empty: int

    @property
    def complete_levels(self) -> bool:
        """The stored levels list every distinct value (profiles cap the level list)."""
        return self.type == "categorical" and 0 < self.distinct <= len(self.levels)


@dataclass(frozen=True, slots=True)
class DatasetRef:
    dataset: str
    table_id: uuid.UUID
    source_version_id: uuid.UUID
    source_code: str
    source_version: int
    title: str
    table: str
    source_class: str
    row_count: int
    columns: tuple[ColumnSpec, ...]

    def column(self, name: str) -> ColumnSpec | None:
        return next((c for c in self.columns if c.name == name), None)

    def info(self, *, with_columns: bool) -> DatasetInfo:
        cols = (
            [
                ColumnInfo(
                    name=c.name,
                    type=c.type,
                    unit=c.unit,
                    levels=list(c.levels),
                    non_empty=c.non_empty,
                )
                for c in self.columns
            ]
            if with_columns
            else []
        )
        return DatasetInfo(
            dataset=self.dataset,
            source_code=self.source_code,
            source_version=self.source_version,
            title=self.title,
            table=self.table,
            source_class=self.source_class,
            row_count=self.row_count,
            columns=cols,
        )


def parse_dataset_id(dataset: str) -> tuple[str, int] | None:
    """``"CODE:N"`` -> ``("CODE", N)``; anything else (SQL-ish payloads included) -> ``None``."""
    code, sep, sheet = dataset.rpartition(":")
    if not sep or not SOURCE_CODE_RE.match(code) or not SHEET_RE.match(sheet):
        return None
    return code, int(sheet)


def _columns(raw: Any) -> tuple[ColumnSpec, ...]:
    out = []
    for c in raw if isinstance(raw, list) else []:
        name, ctype = str(c.get("name", "")), str(c.get("type", "text"))
        if not name:
            continue
        out.append(
            ColumnSpec(
                name=name,
                type=ctype,
                role=str(c.get("role", "")),
                unit=infer_unit(name, ctype),
                levels=tuple(str(v) for v in c.get("levels") or ()),
                distinct=int(c.get("distinct") or 0),
                non_empty=int(c.get("non_empty") or 0),
            )
        )
    return tuple(out)


_DATASETS = """
SELECT dt.id, dt.source_version_id, dt.sheet_ordinal, dt.name, dt.columns, dt.row_count,
       s.source_code, s.title, v.version, v.source_class
FROM dataset_tables dt
JOIN source_versions v ON v.workspace_id = dt.workspace_id AND v.id = dt.source_version_id
JOIN sources s ON s.workspace_id = v.workspace_id AND s.current_version_id = v.id
WHERE dt.workspace_id = :ws AND s.deleted_at IS NULL
  AND v.status IN ('ready', 'ready_degraded')
  AND v.confidentiality = ANY(CAST(:conf AS text[]))
  AND (cardinality(CAST(:classes AS text[])) = 0 OR v.source_class = ANY(CAST(:classes AS text[])))
  AND (CAST(:code AS text) IS NULL OR (s.source_code = :code AND dt.sheet_ordinal = :sheet))
ORDER BY s.source_code, dt.sheet_ordinal
LIMIT :limit
"""


async def find_datasets(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    confidentiality: Sequence[str],
    classes: Sequence[str],
    dataset: str | None = None,
    limit: int = MAX_DATASETS + 1,
) -> list[DatasetRef]:
    """The analysable datasets (all, or the one named by ``dataset``). ``classes`` empty means
    every class. An unparseable ``dataset`` id finds nothing (no query is run)."""
    code: str | None = None
    sheet = 0
    if dataset is not None:
        parsed = parse_dataset_id(dataset)
        if parsed is None:
            return []
        code, sheet = parsed
    rows = (
        await session.execute(
            text(_DATASETS),
            {
                "ws": workspace_id,
                "conf": list(confidentiality),
                "classes": list(classes),
                "code": code,
                "sheet": sheet,
                "limit": limit,
            },
        )
    ).all()
    return [
        DatasetRef(
            dataset=f"{r[6]}:{int(r[2])}",
            table_id=r[0],
            source_version_id=r[1],
            source_code=r[6],
            source_version=int(r[8]),
            title=r[7],
            table=r[3],
            source_class=r[9],
            row_count=int(r[5]),
            columns=_columns(r[4]),
        )
        for r in rows
    ]
