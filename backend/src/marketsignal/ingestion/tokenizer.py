"""Token counting with character offsets.

Child windows are cut on token boundaries but stored as character spans into the parent text,
so the tokenizer must report offsets. Production uses the embedding model's own WordPiece
tokenizer (window sizes are then exactly what the embedder and cross-encoder see); unit tests
use :class:`RegexTokenizer`, which needs no model download.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class TokenSpans:
    starts: tuple[int, ...]
    ends: tuple[int, ...]

    def __len__(self) -> int:
        return len(self.starts)


class Tokenizer(Protocol):
    def spans(self, text: str) -> TokenSpans: ...

    def count(self, text: str) -> int: ...


_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class RegexTokenizer:
    """Deterministic word/punctuation tokenizer for tests and offline tooling."""

    def spans(self, text: str) -> TokenSpans:
        matches = list(_TOKEN_RE.finditer(text))
        return TokenSpans(tuple(m.start() for m in matches), tuple(m.end() for m in matches))

    def count(self, text: str) -> int:
        return sum(1 for _ in _TOKEN_RE.finditer(text))


class HuggingFaceTokenizer:
    """Wraps a ``tokenizers.Tokenizer`` (the embedder's). Truncation is disabled so long
    parents are counted fully; special tokens are excluded."""

    def __init__(self, tokenizer: Any) -> None:
        tok = tokenizer.__class__.from_str(tokenizer.to_str())  # private copy
        tok.no_truncation()
        tok.no_padding()
        self._tok = tok

    def spans(self, text: str) -> TokenSpans:
        encoding = self._tok.encode(text, add_special_tokens=False)
        offsets = [(s, e) for s, e in encoding.offsets if e > s]
        return TokenSpans(tuple(s for s, _ in offsets), tuple(e for _, e in offsets))

    def count(self, text: str) -> int:
        return len(self.spans(text))
