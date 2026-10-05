"""Markdown and plain-text parser.

Markdown: ATX headings (``#`` opens a section, ``##``+ extend the heading path), ``-``/``*``/
``1.`` list items, blank-line-separated paragraphs. HTML comments and fenced code are kept as
ordinary text: document content is *data*, never instructions, and must stay citable.
Plain text: blank-line-separated paragraphs in a single section.
"""

from __future__ import annotations

import re

from marketsignal.config import Settings
from marketsignal.ingestion.models import ParsedSource
from marketsignal.ingestion.parsers.sections import SectionBuilder
from marketsignal.ingestion.tokenizer import Tokenizer
from marketsignal.ingestion.validation import decode_text

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+(.*)$")


def parse_markdown(data: bytes, tokenizer: Tokenizer, settings: Settings) -> ParsedSource:
    builder = SectionBuilder(tokenizer, settings.parent_max_tokens)
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            builder.paragraph(" ".join(paragraph))
            paragraph.clear()

    for line in decode_text(data).splitlines():
        if not line.strip():
            flush_paragraph()
            continue
        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            builder.heading(heading.group(2), len(heading.group(1)))
            continue
        item = _LIST_ITEM.match(line)
        if item:
            flush_paragraph()
            builder.list_item(item.group(1))
            continue
        paragraph.append(line.strip())
    flush_paragraph()
    return ParsedSource(parents=tuple(builder.finish()))


def parse_text(data: bytes, tokenizer: Tokenizer, settings: Settings) -> ParsedSource:
    builder = SectionBuilder(tokenizer, settings.parent_max_tokens)
    for paragraph in re.split(r"\n\s*\n", decode_text(data)):
        builder.paragraph(paragraph)
    return ParsedSource(parents=tuple(builder.finish()))
