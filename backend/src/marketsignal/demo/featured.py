"""Featured conversations: a curated, checked-in list per workspace code, in display order.

``featured.v1.json`` is ``{"<WORKSPACE_CODE>": ["<conversation uuid>", ...]}``. It is read only
by the conversations list (``featured=true`` and the per-item ``featured`` flag); ids that do
not exist in the caller's workspace are silently dropped there. A malformed file fails loudly
at first use rather than featuring anything it cannot parse.
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from importlib import resources
from typing import Final

FEATURED_FILE: Final = "featured.v1.json"


class FeaturedFileError(ValueError):
    """The featured-conversations file is not ``{code: [uuid, ...]}``."""


def parse_featured(raw: object) -> dict[str, tuple[uuid.UUID, ...]]:
    if not isinstance(raw, dict):
        raise FeaturedFileError("featured file must be an object keyed by workspace code")
    out: dict[str, tuple[uuid.UUID, ...]] = {}
    for code, ids in raw.items():
        if not isinstance(code, str) or not isinstance(ids, list):
            raise FeaturedFileError("each workspace code must map to a list of ids")
        try:
            parsed = tuple(uuid.UUID(str(i)) for i in ids)
        except ValueError as exc:
            raise FeaturedFileError(f"invalid conversation id for {code}") from exc
        out[code] = tuple(dict.fromkeys(parsed))  # de-duplicated, order kept
    return out


@lru_cache(maxsize=1)
def _load() -> dict[str, tuple[uuid.UUID, ...]]:
    text = resources.files(__package__).joinpath(FEATURED_FILE).read_text(encoding="utf-8")
    return parse_featured(json.loads(text))


def featured_ids(workspace_code: str) -> tuple[uuid.UUID, ...]:
    """The featured conversation ids for a workspace, in display order (empty if none)."""
    return _load().get(workspace_code, ())
