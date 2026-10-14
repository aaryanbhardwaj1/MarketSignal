"""Deck theme: 16:9, white background, ink text, one signal-blue accent, cool greys.

Fonts are Calibri with Arial as the fallback a viewer substitutes. Geometry is in EMU via
python-pptx length helpers so every slide places its title at the same position."""

from __future__ import annotations

from collections.abc import Callable

from pptx.dml.color import RGBColor
from pptx.util import Emu, Inches, Pt

# python-pptx leaves the constructor unannotated; this gives it a typed signature.
_rgb: Callable[[int, int, int], RGBColor] = RGBColor

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN_X = Inches(0.7)
CONTENT_W = Emu(SLIDE_W - 2 * MARGIN_X)

RULE_TOP = Inches(0.42)
RULE_W = Inches(0.55)
RULE_H = Inches(0.05)
TITLE_TOP = Inches(0.55)
TITLE_H = Inches(0.7)
SUBTITLE_TOP = Inches(1.2)
SUBTITLE_H = Inches(0.4)
BODY_TOP = Inches(1.8)
BODY_BOTTOM = Inches(6.75)
FOOTER_TOP = Inches(7.0)
FOOTER_H = Inches(0.3)

FONT = "Calibri"
TITLE_PT = Pt(26)
COVER_TITLE_PT = Pt(36)
COVER_SUBTITLE_PT = Pt(18)
SUBTITLE_PT = Pt(14)
BODY_PT = Pt(15)
SUB_BULLET_PT = Pt(13)
SMALL_PT = Pt(11)
FOOTER_PT = Pt(9)
METRIC_PT = Pt(30)

INK = _rgb(0x0F, 0x17, 0x2A)
MUTED = _rgb(0x5B, 0x66, 0x7A)
SUBTLE = _rgb(0x8A, 0x94, 0xA6)
HAIRLINE = _rgb(0xDD, 0xE2, 0xEA)
SUNKEN = _rgb(0xF4, 0xF6, 0xF9)
WHITE = _rgb(0xFF, 0xFF, 0xFF)
ACCENT = _rgb(0x1F, 0x5F, 0xE0)
BAR_GREY = _rgb(0xB8, 0xC0, 0xCC)

# Claim tags: inference violet, hypothesis and forecast amber (product-wide claim tones).
CLAIM_COLOURS = {
    "Inference": _rgb(0x6D, 0x28, 0xD9),
    "Hypothesis": _rgb(0xB4, 0x53, 0x09),
    "Forecast": _rgb(0xB4, 0x53, 0x09),
}
STATUS_COLOURS = {
    "Supported": _rgb(0x15, 0x80, 0x3D),
    "Strong evidence": _rgb(0x15, 0x80, 0x3D),
    "Emerging": _rgb(0x1F, 0x5F, 0xE0),
    "Mixed evidence": _rgb(0xB4, 0x53, 0x09),
    "Needs validation": _rgb(0x5B, 0x66, 0x7A),
}
