"""Upload validation, run before anything is persisted (plan §4, ADR-0016).

Checks, in order: filename/extension allowlist, size, then a format-specific *container*
inspection that bounds the work a parser could be tricked into doing:

* OOXML (docx/pptx/xlsx) are zips: entry count, declared uncompressed total and per-entry
  compression ratio are capped (zip-bomb defence); ``[Content_Types].xml`` must declare the
  main part matching the extension; macro-enabled packages are rejected; an OLE/CFB container
  on an OOXML extension means an encrypted Office file.
* PDF must start with ``%PDF-``; an ``/Encrypt`` dictionary means encrypted.
* CSV / Markdown / text must decode as UTF-8 (BOM allowed) and contain no NUL bytes.

The filename is metadata only: it is never used as a filesystem path.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from defusedxml import ElementTree

from marketsignal.config import Settings
from marketsignal.domain.enums import IngestErrorCode, SourceType
from marketsignal.ingestion.models import IngestionError

EXTENSIONS: dict[str, tuple[SourceType, str]] = {
    ".pdf": (SourceType.PDF, "application/pdf"),
    ".docx": (
        SourceType.DOCX,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".pptx": (
        SourceType.PPTX,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    ".xlsx": (SourceType.XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".csv": (SourceType.CSV, "text/csv"),
    ".md": (SourceType.MARKDOWN, "text/markdown"),
    ".markdown": (SourceType.MARKDOWN, "text/markdown"),
    ".txt": (SourceType.TEXT, "text/plain"),
}
# Main-part content types that must appear in [Content_Types].xml for each OOXML type.
_OOXML = "application/vnd.openxmlformats-officedocument"
_OOXML_MAIN_PART = {
    SourceType.DOCX: f"{_OOXML}.wordprocessingml.document.main+xml",
    SourceType.PPTX: f"{_OOXML}.presentationml.presentation.main+xml",
    SourceType.XLSX: f"{_OOXML}.spreadsheetml.sheet.main+xml",
}
_ZIP_MAGIC = b"PK\x03\x04"
_CFB_MAGIC = b"\xd0\xcf\x11\xe0"
_PDF_ENCRYPT_RE = re.compile(rb"/Encrypt\s*(\d+\s+\d+\s+R|<<)")
_MAX_FILENAME = 255


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    filename: str
    source_type: SourceType
    mime_type: str
    data: bytes


def sanitize_filename(raw: str | None) -> str:
    """Keep only the final path component, normalised; never used as a path."""
    name = PurePosixPath((raw or "").replace("\\", "/")).name
    name = unicodedata.normalize("NFKC", name)
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')
    name = name.strip().strip(".") or "upload"
    return name[:_MAX_FILENAME]


def _reject(code: IngestErrorCode, message: str) -> IngestionError:
    return IngestionError(code.value, message)


def _check_ooxml(data: bytes, source_type: SourceType, settings: Settings) -> None:
    if data.startswith(_CFB_MAGIC):
        raise _reject(IngestErrorCode.ENCRYPTED_DOCUMENT, "encrypted or legacy Office document")
    if not data.startswith(_ZIP_MAGIC):
        raise _reject(IngestErrorCode.UNSUPPORTED_TYPE, "file content is not an OOXML package")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as exc:
        raise _reject(IngestErrorCode.PARSE_FAILED, "corrupt or truncated package") from exc
    if len(infos) > settings.zip_max_entries:
        raise _reject(IngestErrorCode.CONTENT_TOO_LARGE, "package has too many entries")
    total = sum(info.file_size for info in infos)
    if total > settings.zip_max_uncompressed_bytes:
        raise _reject(IngestErrorCode.CONTENT_TOO_LARGE, "package expands beyond the size limit")
    for info in infos:
        ratio = info.file_size / max(info.compress_size, 1)
        if info.file_size > 1024 * 1024 and ratio > settings.zip_max_compression_ratio:
            raise _reject(IngestErrorCode.CONTENT_TOO_LARGE, "suspicious compression ratio")
    try:
        content_types = archive.read("[Content_Types].xml")
    except KeyError as exc:
        raise _reject(IngestErrorCode.UNSUPPORTED_TYPE, "missing [Content_Types].xml") from exc
    try:
        root = ElementTree.fromstring(content_types)
    except ElementTree.ParseError as exc:
        raise _reject(IngestErrorCode.PARSE_FAILED, "unreadable [Content_Types].xml") from exc
    declared = {el.attrib.get("ContentType", "") for el in root.iter()}
    if any("macroEnabled" in ct for ct in declared):
        raise _reject(IngestErrorCode.UNSUPPORTED_TYPE, "macro-enabled documents are not accepted")
    if _OOXML_MAIN_PART[source_type] not in declared:
        raise _reject(IngestErrorCode.UNSUPPORTED_TYPE, "package type does not match extension")


def _check_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF-"):
        raise _reject(IngestErrorCode.UNSUPPORTED_TYPE, "file content is not a PDF")
    if _PDF_ENCRYPT_RE.search(data):
        raise _reject(IngestErrorCode.ENCRYPTED_DOCUMENT, "encrypted PDF")


def decode_text(data: bytes) -> str:
    if b"\x00" in data:
        raise _reject(IngestErrorCode.UNSUPPORTED_TYPE, "binary content in a text file")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _reject(IngestErrorCode.PARSE_FAILED, "text files must be UTF-8") from exc


def validate_upload(filename: str | None, data: bytes, settings: Settings) -> ValidatedUpload:
    name = sanitize_filename(filename)
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in EXTENSIONS:
        raise _reject(
            IngestErrorCode.UNSUPPORTED_TYPE, f"unsupported file type: {suffix or 'none'}"
        )
    if not data:
        raise _reject(IngestErrorCode.EMPTY_DOCUMENT, "empty file")
    if len(data) > settings.upload_max_bytes:
        raise _reject(IngestErrorCode.FILE_TOO_LARGE, "file exceeds the upload size limit")
    source_type, mime = EXTENSIONS[suffix]
    if source_type in _OOXML_MAIN_PART:
        _check_ooxml(data, source_type, settings)
    elif source_type is SourceType.PDF:
        _check_pdf(data)
    else:
        decode_text(data)
    return ValidatedUpload(name, source_type, mime, data)
