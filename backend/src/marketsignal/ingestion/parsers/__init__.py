"""Format dispatch. Every parser returns structure-derived :class:`ParentDraft` units."""

from __future__ import annotations

from marketsignal.config import Settings
from marketsignal.domain.enums import SourceType
from marketsignal.ingestion.models import ParsedSource
from marketsignal.ingestion.parsers.docx import parse_docx
from marketsignal.ingestion.parsers.pdf import parse_pdf
from marketsignal.ingestion.parsers.pptx import parse_pptx
from marketsignal.ingestion.parsers.tabular import parse_csv, parse_xlsx
from marketsignal.ingestion.parsers.text import parse_markdown, parse_text
from marketsignal.ingestion.tokenizer import Tokenizer


def parse_source(
    source_type: SourceType, data: bytes, *, title: str, tokenizer: Tokenizer, settings: Settings
) -> ParsedSource:
    match source_type:
        case SourceType.PDF:
            return parse_pdf(data, tokenizer, settings)
        case SourceType.DOCX:
            return parse_docx(data, tokenizer, settings)
        case SourceType.PPTX:
            return parse_pptx(data, tokenizer, settings)
        case SourceType.XLSX:
            return parse_xlsx(data, tokenizer, settings, title=title)
        case SourceType.CSV:
            return parse_csv(data, tokenizer, settings, title=title)
        case SourceType.MARKDOWN:
            return parse_markdown(data, tokenizer, settings)
        case SourceType.TEXT:
            return parse_text(data, tokenizer, settings)
