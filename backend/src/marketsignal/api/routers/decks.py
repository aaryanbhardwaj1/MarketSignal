"""Grounded presentation decks from the curated analyst brief (business route).

* ``POST /api/workspaces/{ws}/decks/preview`` -> ``{"deck": Deck}``
* ``POST /api/workspaces/{ws}/decks/pptx``    -> the deck as a ``.pptx`` download

Both read the same re-verified brief and recomputed analyses as ``GET /insights`` (same
request-time verification and cache) and compose deterministically; nothing is persisted and
no model is called. The workspace comes from the trusted scope only. Ids that are not in this
workspace's brief are a 422 ``DECK_ITEMS_NOT_FOUND`` listing them; a download whose every
selected item failed re-verification is a 422 ``DECK_EMPTY``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import text

from marketsignal.api.deps import Factory, Scope, SettingsDep
from marketsignal.api.errors import AppError
from marketsignal.api.routers.insights import Loader
from marketsignal.db.session import scoped_session, unscoped_session
from marketsignal.decks.composer import UnknownItemsError, compose
from marketsignal.decks.filename import content_disposition
from marketsignal.decks.models import DeckRequest
from marketsignal.decks.render import DeckTooLargeError, render_pptx
from marketsignal.insights.service import build_bundle, empty_analyses, empty_brief

router = APIRouter(prefix="/api/workspaces/{ws}/decks", tags=["decks"])

PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


async def _workspace_name(factory: Factory, scope: Scope) -> str:
    async with unscoped_session(factory) as session:
        name = (
            await session.execute(
                text("SELECT name FROM workspaces WHERE id = :id"), {"id": scope.workspace_id}
            )
        ).scalar_one_or_none()
    return str(name or scope.workspace_code)


async def _deck(
    body: DeckRequest, scope: Scope, factory: Factory, settings: SettingsDep, loader: Loader
) -> dict[str, Any]:
    fixture = loader(scope.workspace_code)
    if fixture is None:
        brief, listing = empty_brief(), empty_analyses()
    else:
        async with scoped_session(factory, scope) as session:
            bundle = await build_bundle(session, scope, settings, fixture)
        brief, listing = bundle.brief, bundle.analyses
    workspace = {"code": scope.workspace_code, "name": await _workspace_name(factory, scope)}
    try:
        return compose(
            brief,
            listing,
            body,
            workspace=workspace,
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
    except UnknownItemsError as exc:
        raise AppError(
            422,
            "DECK_ITEMS_NOT_FOUND",
            "some selected items are not in this workspace's brief",
            unknown=exc.unknown,
        ) from exc


@router.post("/preview")
async def preview_deck(
    body: DeckRequest, scope: Scope, factory: Factory, settings: SettingsDep, loader: Loader
) -> dict[str, Any]:
    return {"deck": await _deck(body, scope, factory, settings, loader)}


@router.post(
    "/pptx",
    response_class=Response,
    responses={200: {"content": {PPTX_MEDIA_TYPE: {}}}},
)
async def download_deck(
    body: DeckRequest, scope: Scope, factory: Factory, settings: SettingsDep, loader: Loader
) -> Response:
    deck = await _deck(body, scope, factory, settings, loader)
    if deck["counts"]["items"] == 0:
        raise AppError(
            422,
            "DECK_EMPTY",
            "none of the selected items could be re-verified",
            excluded=deck["excluded"],
        )
    try:
        data = await asyncio.to_thread(render_pptx, deck)
    except DeckTooLargeError as exc:
        raise AppError(422, "DECK_TOO_LARGE", "the deck is too large to render") from exc
    return Response(
        content=data,
        media_type=PPTX_MEDIA_TYPE,
        headers={
            "Content-Disposition": content_disposition(deck["title"]),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
