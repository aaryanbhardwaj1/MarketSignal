"""PDF parser (pdfplumber / pdfminer.six; PyMuPDF is excluded for licensing).

Text lines carry per-character font sizes, which give a document-relative structure:

* body size = the most common character size in the document;
* lines markedly larger than the body are headings (they extend the heading path; the
  largest level resets it), and lines markedly smaller are running headers/footers (dropped);
* within a page, a vertical gap larger than ``PARAGRAPH_GAP_RATIO`` x body size starts a new
  paragraph; lines starting with a bullet marker are list items.

Parents never cross a page: ``P{page}.B{block}``. Pages with almost no extractable text raise
a ``PARTIAL_EXTRACTION`` warning (OCR is out of scope).
"""

from __future__ import annotations

import io
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Any

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError

from marketsignal.config import Settings
from marketsignal.domain.enums import IngestErrorCode
from marketsignal.evidence.handles import LocatorKind
from marketsignal.ingestion.models import IngestionError, ParentDraft, ParentKind, ParsedSource
from marketsignal.ingestion.structure import Unit, clean, group_units
from marketsignal.ingestion.tokenizer import Tokenizer

HEADING_MIN_DELTA_PT = 2.0  # size above body that marks a heading
HEADING_TOP_LEVEL_DELTA_PT = 5.0  # size above body that marks a top-level heading
FOOTER_MAX_DELTA_PT = -2.0  # size below body that marks a running header/footer
PARAGRAPH_GAP_RATIO = 0.45  # vertical gap (x body size) that starts a new paragraph
HEADING_MAX_CHARS = 160
BULLETS = ("- ", "* ", "• ")


@dataclass(frozen=True, slots=True)
class _Line:
    text: str
    size: float
    top: float
    bottom: float


def _lines(page: Any) -> list[_Line]:
    out: list[_Line] = []
    for line in page.extract_text_lines(layout=False, strip=True, return_chars=True):
        chars = [c for c in line.get("chars", []) if c.get("text", "").strip()]
        text = clean(line.get("text", ""))
        if not text or not chars:
            continue
        size = statistics.median(round(float(c["size"]), 1) for c in chars)
        out.append(_Line(text, size, float(line["top"]), float(line["bottom"])))
    return out


def parse_pdf(data: bytes, tokenizer: Tokenizer, settings: Settings) -> ParsedSource:
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except (PDFPasswordIncorrect, PDFEncryptionError) as exc:
        raise IngestionError(IngestErrorCode.ENCRYPTED_DOCUMENT.value, "encrypted PDF") from exc
    except (PDFSyntaxError, ValueError, KeyError) as exc:
        raise IngestionError(IngestErrorCode.PARSE_FAILED.value, "unreadable PDF") from exc
    with pdf:
        if len(pdf.pages) > settings.max_pdf_pages:
            raise IngestionError(IngestErrorCode.CONTENT_TOO_LARGE.value, "too many pages")
        try:
            pages = [_lines(page) for page in pdf.pages]
        except (PDFPasswordIncorrect, PDFEncryptionError) as exc:
            raise IngestionError(IngestErrorCode.ENCRYPTED_DOCUMENT.value, "encrypted PDF") from exc
        except Exception as exc:  # pdfminer raises many internal types on malformed streams
            raise IngestionError(IngestErrorCode.PARSE_FAILED.value, "unreadable PDF") from exc
    return _structure(pages, tokenizer, settings)


def _structure(pages: list[list[_Line]], tokenizer: Tokenizer, settings: Settings) -> ParsedSource:
    sizes: Counter[float] = Counter()
    for lines in pages:
        for line in lines:
            sizes[line.size] += len(line.text)
    if not sizes:
        raise IngestionError(IngestErrorCode.EMPTY_DOCUMENT.value, "no extractable text")
    body = sizes.most_common(1)[0][0]
    gap_threshold = PARAGRAPH_GAP_RATIO * body

    parents: list[ParentDraft] = []
    warnings: list[str] = []
    state = _Assembler()
    for page_number, lines in enumerate(pages, start=1):
        state.start_page()
        prev: _Line | None = None
        words = 0
        for line in lines:
            delta = line.size - body
            if delta <= FOOTER_MAX_DELTA_PT:
                continue  # running header / footer
            words += len(line.text.split())
            if delta >= HEADING_MIN_DELTA_PT and len(line.text) <= HEADING_MAX_CHARS:
                # A heading closes the current group of paragraphs.
                parents.extend(state.take_blocks(page_number, tokenizer, settings))
                state.set_heading(line.text, top_level=delta >= HEADING_TOP_LEVEL_DELTA_PT)
            elif line.text.startswith(BULLETS):
                state.bullet(line.text[2:].strip())
            elif prev is None or (line.top - prev.bottom) > gap_threshold:
                state.new_paragraph(line.text)
            else:
                state.continue_paragraph(line.text)  # wrapped line (incl. of a bullet item)
            prev = line
        if words < settings.pdf_min_words_per_page:
            warnings.append(f"PARTIAL_EXTRACTION:page={page_number}")
        parents.extend(state.take_blocks(page_number, tokenizer, settings))
    # Re-number blocks per page in document order.
    numbered: list[ParentDraft] = []
    counters: Counter[int] = Counter()
    for parent in parents:
        page = int(parent.locator_meta["page"])
        counters[page] += 1
        numbered.append(
            ParentDraft(
                locator=((LocatorKind.PAGE, page), (LocatorKind.BLOCK, counters[page])),
                kind=parent.kind,
                text=parent.text,
                heading_path=parent.heading_path,
                locator_meta=parent.locator_meta,
                list_group_id=parent.list_group_id,
            )
        )
    if not numbered:
        raise IngestionError(IngestErrorCode.EMPTY_DOCUMENT.value, "no extractable text")
    return ParsedSource(parents=tuple(numbered), warnings=tuple(warnings))


class _Assembler:
    """Per-document paragraph/list assembly; the heading path carries across pages."""

    def __init__(self) -> None:
        self.heading_path: list[str] = []
        self.units: list[Unit] = []
        self.paragraph: list[str] = []
        self.in_bullet = False
        self.list_run = 0
        self.block_heading: tuple[str, ...] = ()

    def start_page(self) -> None:
        self.units, self.paragraph, self.in_bullet = [], [], False
        self.block_heading = tuple(self.heading_path)

    def _flush_paragraph(self) -> None:
        if self.paragraph:
            run = self.list_run if self.in_bullet else None
            self.units.append(Unit(" ".join(self.paragraph), run))
            self.paragraph = []
        self.in_bullet = False

    def set_heading(self, text: str, *, top_level: bool) -> None:
        self.heading_path = [text] if top_level else [*self.heading_path[:1], text]
        self.block_heading = tuple(self.heading_path)

    def bullet(self, text: str) -> None:
        continuing = self.in_bullet or bool(self.units and self.units[-1].list_run == self.list_run)
        self._flush_paragraph()
        if not continuing:
            self.list_run += 1
        self.in_bullet = True
        self.paragraph.append(text)

    def new_paragraph(self, text: str) -> None:
        self._flush_paragraph()
        self.paragraph.append(text)

    def continue_paragraph(self, text: str) -> None:
        self.paragraph.append(text)

    def take_blocks(self, page: int, tokenizer: Tokenizer, settings: Settings) -> list[ParentDraft]:
        self._flush_paragraph()
        units, self.units = self.units, []
        if not units:
            return []
        return _page_blocks(page, units, self.block_heading, tokenizer, settings)


def _page_blocks(
    page: int,
    units: list[Unit],
    heading: tuple[str, ...],
    tokenizer: Tokenizer,
    settings: Settings,
) -> list[ParentDraft]:
    return [
        ParentDraft(
            locator=((LocatorKind.PAGE, page), (LocatorKind.BLOCK, 1)),  # renumbered later
            kind=ParentKind.NARRATIVE,
            text=block.text,
            heading_path=heading,
            locator_meta={"page": page},
            list_group_id=block.list_group_id,
        )
        for block in group_units(units, tokenizer, settings.parent_max_tokens, f"P{page}")
    ]
