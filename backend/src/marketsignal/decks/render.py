"""Render a composed deck as a 16:9 PowerPoint file, entirely in memory.

Every slide uses the blank layout and the same chrome (accent rule, title, optional subtitle,
"MarketSignal" footer and slide number), so titles always sit in the same place. Speaker notes
list the slide's numbered sources with their handles, for audit; slide text never shows a
handle or an internal id. The zip is rewritten with fixed timestamps and the document
properties come from the deck, so the same deck always renders to the same bytes.
"""

from __future__ import annotations

import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.presentation import Presentation as PresentationT
from pptx.slide import Slide
from pptx.util import Emu, Inches

from marketsignal.decks import render_blocks as rb
from marketsignal.decks import theme as t
from marketsignal.decks.render_text import bullets, line, text_box

MAX_DECK_BYTES = 15 * 1024 * 1024
MAX_SLIDES = 150
BLANK_LAYOUT = 6
ZIP_TIME = (2000, 1, 1, 0, 0, 0)
SPLIT_W = Inches(7.7)
GUTTER = Inches(0.45)


class DeckTooLargeError(ValueError):
    """The rendered deck would exceed the size guard."""


def _rule(slide: Slide, top: int) -> None:
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, t.MARGIN_X, Emu(top), t.RULE_W, t.RULE_H)
    shape.fill.solid()
    shape.fill.fore_color.rgb = t.ACCENT
    shape.line.fill.background()
    shape.shadow.inherit = False


def _footer(slide: Slide, index: int) -> None:
    left = text_box(slide.shapes, t.MARGIN_X, t.FOOTER_TOP, Inches(3), t.FOOTER_H)
    line(left, "MarketSignal", t.FOOTER_PT, t.SUBTLE, bold=True)
    right = text_box(
        slide.shapes, Emu(t.SLIDE_W - t.MARGIN_X - Inches(1)), t.FOOTER_TOP, Inches(1), t.FOOTER_H
    )
    line(right, str(index), t.FOOTER_PT, t.SUBTLE, align=PP_ALIGN.RIGHT)


def _chrome(slide: Slide, spec: dict[str, Any]) -> None:
    _rule(slide, t.RULE_TOP)
    title = text_box(
        slide.shapes, t.MARGIN_X, t.TITLE_TOP, t.CONTENT_W, t.TITLE_H, anchor=MSO_ANCHOR.MIDDLE
    )
    line(title, spec["title"], t.TITLE_PT, t.INK, bold=True)
    if spec.get("subtitle"):
        sub = text_box(slide.shapes, t.MARGIN_X, t.SUBTITLE_TOP, t.CONTENT_W, t.SUBTITLE_H)
        line(sub, spec["subtitle"], t.SUBTITLE_PT, t.MUTED)
    _footer(slide, spec["index"])


def _cover(slide: Slide, spec: dict[str, Any]) -> None:
    _rule(slide, Inches(2.3))
    title = text_box(
        slide.shapes, t.MARGIN_X, Inches(2.5), t.CONTENT_W, Inches(1.5), anchor=MSO_ANCHOR.TOP
    )
    line(title, spec["title"], t.COVER_TITLE_PT, t.INK, bold=True)
    if spec.get("subtitle"):
        sub = text_box(slide.shapes, t.MARGIN_X, Inches(4.1), t.CONTENT_W, Inches(1.0))
        line(sub, spec["subtitle"], t.COVER_SUBTITLE_PT, t.MUTED)
    meta = text_box(slide.shapes, t.MARGIN_X, Inches(6.2), t.CONTENT_W, Inches(0.4))
    line(meta, "  ·  ".join(spec.get("meta", [])), t.SUB_BULLET_PT, t.MUTED)
    footer = text_box(slide.shapes, t.MARGIN_X, t.FOOTER_TOP, Inches(3), t.FOOTER_H)
    line(footer, "MarketSignal", t.FOOTER_PT, t.SUBTLE, bold=True)


def _body(slide: Slide, blocks: list[dict[str, Any]]) -> None:
    full = rb.Box(t.MARGIN_X, t.BODY_TOP, t.CONTENT_W, t.BODY_BOTTOM - t.BODY_TOP)
    data = [b for b in blocks if b["type"] in ("chart", "table")]
    text = [b for b in blocks if b["type"] == "bullets"]
    if data and text:
        left = rb.Box(full.left, full.top, SPLIT_W, full.height)
        right_left = full.left + SPLIT_W + GUTTER
        right = rb.Box(right_left, full.top, full.width - SPLIT_W - GUTTER, full.height)
        _block(slide, left, data[0])
        _block(slide, right, text[0])
        return
    for block in blocks:
        _block(slide, full, block)


def _block(slide: Slide, box: rb.Box, block: dict[str, Any]) -> None:
    kind = block["type"]
    if kind == "bullets":
        frame = text_box(
            slide.shapes, Emu(box.left), Emu(box.top), Emu(box.width), Emu(box.height), shrink=True
        )
        bullets(frame, block["items"])
    elif kind == "chart":
        rb.chart(slide.shapes, box, block)
    elif kind == "table":
        rb.table(slide.shapes, box, block)
    elif kind == "metrics":
        rb.metrics(slide.shapes, box, block)
    elif kind == "statuses":
        rb.statuses(slide.shapes, box, block)
    elif kind == "sources":
        rb.sources(slide.shapes, box, block)


def _notes(slide: Slide, notes: list[dict[str, Any]]) -> None:
    if not notes:
        return
    lines = ["Sources"]
    for n in notes:
        where = ", ".join(p for p in (n["source_title"], n.get("locator")) if p)
        quote = f": “{n['quote']}”" if n.get("quote") else ""
        lines.append(f"[{n['n']}] {where}{quote} (handle: {n['handle']})")
    frame = slide.notes_slide.notes_text_frame
    assert frame is not None
    frame.text = "\n".join(lines)


def _properties(prs: PresentationT, deck: dict[str, Any]) -> None:
    props = prs.core_properties
    stamp = datetime.fromisoformat(deck["generated_at"]).replace(tzinfo=None)
    props.title = deck["title"][:255]
    props.author = "MarketSignal"
    props.last_modified_by = "MarketSignal"
    props.subject = (deck.get("question") or "")[:255]
    props.created = stamp
    props.modified = stamp
    props.revision = 1


def _fixed_zip(data: bytes) -> bytes:
    out = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(data)) as src,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for info in src.infolist():
            fixed = zipfile.ZipInfo(info.filename, date_time=ZIP_TIME)
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = info.external_attr
            dst.writestr(fixed, src.read(info.filename))
    return out.getvalue()


def render_pptx(deck: dict[str, Any]) -> bytes:
    """The deck as ``.pptx`` bytes; raises :class:`DeckTooLargeError` past the size guards."""
    if len(deck["slides"]) > MAX_SLIDES:
        raise DeckTooLargeError(f"deck has more than {MAX_SLIDES} slides")
    prs = Presentation()
    prs.slide_width = t.SLIDE_W
    prs.slide_height = t.SLIDE_H
    layout = prs.slide_layouts[BLANK_LAYOUT]
    for spec in deck["slides"]:
        slide = prs.slides.add_slide(layout)
        if spec["kind"] == "title":
            _cover(slide, spec)
        else:
            _chrome(slide, spec)
            _body(slide, spec["blocks"])
        _notes(slide, spec.get("notes", []))
    _properties(prs, deck)
    buffer = BytesIO()
    prs.save(buffer)
    data = _fixed_zip(buffer.getvalue())
    if len(data) > MAX_DECK_BYTES:
        raise DeckTooLargeError("rendered deck exceeds the size limit")
    return data
