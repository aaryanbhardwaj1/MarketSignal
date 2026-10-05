"""DOCX parser (python-docx). Walks the body in document order: paragraphs and tables.

Built-in styles drive structure: "Title"/"Heading 1" open a section, "Heading 2+" extend the
heading path, "List ..." styles are list items. Q:/A: interview pairs are handled by
:class:`SectionBuilder`.
"""

from __future__ import annotations

import io
import re

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from marketsignal.config import Settings
from marketsignal.domain.enums import IngestErrorCode
from marketsignal.ingestion.models import IngestionError, ParsedSource
from marketsignal.ingestion.parsers.sections import SectionBuilder
from marketsignal.ingestion.tokenizer import Tokenizer

_HEADING_STYLE = re.compile(r"^Heading (\d)$")
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse_docx(data: bytes, tokenizer: Tokenizer, settings: Settings) -> ParsedSource:
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises several unrelated types on corrupt input
        raise IngestionError(IngestErrorCode.PARSE_FAILED.value, "unreadable DOCX") from exc
    builder = SectionBuilder(tokenizer, settings.parent_max_tokens)
    for element in document.element.body.iterchildren():
        if element.tag == f"{_W_NS}p":
            paragraph = Paragraph(element, document)
            style = paragraph.style.name if paragraph.style is not None else ""
            text = paragraph.text
            match = _HEADING_STYLE.match(style)
            if style == "Title":
                builder.heading(text, 1)
            elif match:
                builder.heading(text, int(match.group(1)))
            elif style.startswith("List"):
                builder.list_item(text)
            else:
                builder.paragraph(text)
        elif element.tag == f"{_W_NS}tbl":
            table = Table(element, document)
            builder.table_rows([[cell.text for cell in row.cells] for row in table.rows])
    return ParsedSource(parents=tuple(builder.finish()))
