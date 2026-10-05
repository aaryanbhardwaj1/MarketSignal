"""Section builder shared by DOCX and Markdown/plain-text parsers.

Locator model (ADR-0004): ``S{section}.B{block}`` for narrative blocks and ``S{section}.Q{n}``
for interview question/answer pairs. A top-level heading (DOCX "Heading 1", Markdown ``#``)
opens a new section; deeper headings only extend the heading path. Content before the first
top-level heading belongs to section 1, and the first heading then opens section 2 only if
section 1 already holds content. Question paragraphs start with ``Q:``; the answer paragraphs
that follow (``A:`` or continuation text) belong to the same pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from marketsignal.evidence.handles import LocatorKind
from marketsignal.ingestion.models import ParentDraft, ParentKind
from marketsignal.ingestion.structure import Unit, clean, group_units
from marketsignal.ingestion.tokenizer import Tokenizer

QUESTION_PREFIX = "Q:"
ANSWER_PREFIX = "A:"


@dataclass
class _QA:
    question: str
    answer: list[str] = field(default_factory=list)


class SectionBuilder:
    def __init__(self, tokenizer: Tokenizer, max_tokens: int) -> None:
        self._tok = tokenizer
        self._max = max_tokens
        self.parents: list[ParentDraft] = []
        self._section = 1
        self._section_has_content = False
        self._title: str | None = None
        self._subheadings: list[str] = []
        self._units: list[Unit] = []
        self._qa: _QA | None = None
        self._block_n = 0
        self._qa_n = 0
        self._list_run = 0
        self._in_list = False

    # ── events ──────────────────────────────────────────────────────────────────
    def heading(self, text: str, level: int) -> None:
        text = clean(text)
        if not text:
            return
        self._end_list()
        if level <= 1:
            self._flush()
            if self._section_has_content or self._title is not None:
                self._section += 1
            self._section_has_content = False
            self._title = text
            self._subheadings = []
            self._block_n = 0
            self._qa_n = 0
        else:
            self._flush()
            depth = max(level - 2, 0)
            self._subheadings = [*self._subheadings[:depth], text]

    def paragraph(self, text: str) -> None:
        text = clean(text)
        if not text:
            return
        self._end_list()
        if text.startswith(QUESTION_PREFIX):
            self._flush_units()
            self._flush_qa()
            self._qa = _QA(text)
            return
        if self._qa is not None:
            self._qa.answer.append(text)
            return
        self._units.append(Unit(text))

    def list_item(self, text: str) -> None:
        text = clean(text)
        if not text:
            return
        self._flush_qa()
        if not self._in_list:
            self._list_run += 1
            self._in_list = True
        self._units.append(Unit(text, self._list_run))

    def table_rows(self, rows: list[list[str]]) -> None:
        """Tables inside narrative documents are kept as one row-per-line unit run."""
        self._end_list()
        self._flush_qa()
        for row in rows:
            cells = [clean(c) for c in row]
            if any(cells):
                self._units.append(Unit(" | ".join(cells)))

    def finish(self) -> list[ParentDraft]:
        self._flush()
        return self.parents

    # ── internals ───────────────────────────────────────────────────────────────
    def _end_list(self) -> None:
        self._in_list = False

    def _heading_path(self) -> tuple[str, ...]:
        return tuple(h for h in (self._title, *self._subheadings) if h)

    def _meta(self) -> dict[str, object]:
        return {"section": self._section, "section_title": self._title}

    def _flush(self) -> None:
        self._flush_units()
        self._flush_qa()

    def _flush_units(self) -> None:
        if not self._units:
            return
        prefix = f"S{self._section}"
        for block in group_units(self._units, self._tok, self._max, prefix):
            self._block_n += 1
            self.parents.append(
                ParentDraft(
                    locator=(
                        (LocatorKind.SECTION, self._section),
                        (LocatorKind.BLOCK, self._block_n),
                    ),
                    kind=ParentKind.NARRATIVE,
                    text=block.text,
                    heading_path=self._heading_path(),
                    locator_meta=self._meta(),
                    list_group_id=block.list_group_id,
                )
            )
        self._units = []
        self._section_has_content = True

    def _flush_qa(self) -> None:
        if self._qa is None:
            return
        qa, self._qa = self._qa, None
        self._qa_n += 1
        text = "\n".join([qa.question, *qa.answer])
        base = ((LocatorKind.SECTION, self._section), (LocatorKind.QA, self._qa_n))
        blocks = (
            [text]
            if self._tok.count(text) <= self._max
            else [
                b.text
                for b in group_units([Unit(t) for t in text.split("\n")], self._tok, self._max, "")
            ]
        )
        for i, block_text in enumerate(blocks, start=1):
            locator = base if len(blocks) == 1 else (*base, (LocatorKind.BLOCK, i))
            self.parents.append(
                ParentDraft(
                    locator=locator,
                    kind=ParentKind.QA,
                    text=block_text,
                    heading_path=self._heading_path(),
                    locator_meta={**self._meta(), "qa": self._qa_n},
                    metadata={"question": qa.question},
                )
            )
        self._section_has_content = True
