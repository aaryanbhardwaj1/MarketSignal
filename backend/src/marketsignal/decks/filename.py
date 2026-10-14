"""A download name that is safe in a ``Content-Disposition`` header and on any file system:
ASCII letters and digits joined by hyphens, never quotes, CR/LF, slashes or dots."""

from __future__ import annotations

import re
import unicodedata

FALLBACK = "marketsignal-deck"
MAX_STEM = 80
EXTENSION = ".pptx"


def safe_filename(title: str | None) -> str:
    ascii_text = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode()
    stem = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-")[:MAX_STEM].rstrip("-")
    return f"{stem or FALLBACK}{EXTENSION}"


def content_disposition(title: str | None) -> str:
    return f'attachment; filename="{safe_filename(title)}"'
