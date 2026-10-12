"""The checked-in featured-conversation list and its parser (final productization phase)."""

from __future__ import annotations

import uuid

import pytest

from marketsignal.demo.featured import FeaturedFileError, featured_ids, parse_featured

NORTHSTAR_ORDER = [
    "0ec3ca8c-5a3d-41c4-aca2-6f0967dacb51",
    "42719cd8-909b-4997-a25e-2b08508a029e",
    "97c28be3-392b-46b3-aa5d-4cf86bcc45da",
    "7c8c6da4-1551-4a53-bbcd-9018de5957ba",
    "75577600-577c-4ae7-aaa2-964175d647f6",
    "008b11b4-4e48-495f-abca-9e5490fe112d",
]


def test_northstar_featured_order() -> None:
    assert [str(i) for i in featured_ids("NORTHSTAR")] == NORTHSTAR_ORDER


def test_unknown_workspace_has_no_featured() -> None:
    assert featured_ids("SOMEWHERE") == ()


def test_parse_dedupes_and_keeps_order() -> None:
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    assert parse_featured({"W": [b, a, b]}) == {"W": (uuid.UUID(b), uuid.UUID(a))}


@pytest.mark.parametrize("raw", [[], {"W": "x"}, {"W": ["not-a-uuid"]}, {"W": [1]}])
def test_parse_rejects_malformed(raw: object) -> None:
    with pytest.raises(FeaturedFileError):
        parse_featured(raw)
