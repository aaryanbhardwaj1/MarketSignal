from __future__ import annotations

import pytest

from marketsignal.config import Settings
from marketsignal.domain.enums import IngestErrorCode, SourceType
from marketsignal.ingestion.models import IngestionError
from marketsignal.ingestion.validation import sanitize_filename, validate_upload
from tests.fixtures.factories import (
    CONTENT_TYPES_DOCX,
    CONTENT_TYPES_MACRO,
    make_csv,
    make_docx,
    make_pdf,
    make_pptx,
    make_xlsx,
    make_zip,
)

SETTINGS = Settings(env="test")


def _code(filename: str, data: bytes, settings: Settings = SETTINGS) -> str:
    with pytest.raises(IngestionError) as info:
        validate_upload(filename, data, settings)
    return info.value.code


@pytest.mark.parametrize(
    ("filename", "data", "expected"),
    [
        ("report.pdf", make_pdf([[("p", "hello world")]]), SourceType.PDF),
        ("notes.docx", make_docx([("p", "hello")]), SourceType.DOCX),
        ("deck.pptx", make_pptx([{"title": "Hi", "bullets": ["a"]}]), SourceType.PPTX),
        ("data.xlsx", make_xlsx({"S": [["a"], [1]]}), SourceType.XLSX),
        ("data.CSV", make_csv([["a"], ["1"]], bom=True), SourceType.CSV),
        ("memo.md", b"# Title\n\nBody.", SourceType.MARKDOWN),
        ("call.txt", b"Plain text.", SourceType.TEXT),
    ],
)
def test_valid_uploads_are_accepted(filename: str, data: bytes, expected: SourceType) -> None:
    result = validate_upload(filename, data, SETTINGS)
    assert result.source_type is expected
    assert result.data == data


@pytest.mark.parametrize("filename", ["virus.exe", "archive.zip", "noext", "x.docm", "x.html"])
def test_unsupported_extensions(filename: str) -> None:
    assert _code(filename, b"data") == IngestErrorCode.UNSUPPORTED_TYPE


def test_empty_file() -> None:
    assert _code("a.txt", b"") == IngestErrorCode.EMPTY_DOCUMENT


def test_size_limit() -> None:
    small = Settings(env="test", upload_max_bytes=10)
    assert _code("a.txt", b"x" * 11, small) == IngestErrorCode.FILE_TOO_LARGE


def test_pdf_magic_and_encryption() -> None:
    assert _code("a.pdf", b"not a pdf") == IngestErrorCode.UNSUPPORTED_TYPE
    encrypted = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<</Encrypt 5 0 R>>"
    assert _code("a.pdf", encrypted) == IngestErrorCode.ENCRYPTED_DOCUMENT


def test_ooxml_extension_must_match_package_type() -> None:
    docx_bytes = make_docx([("p", "hello")])
    assert _code("disguised.xlsx", docx_bytes) == IngestErrorCode.UNSUPPORTED_TYPE
    assert _code("not-zip.docx", b"plain text") == IngestErrorCode.UNSUPPORTED_TYPE


def test_macro_enabled_and_encrypted_office_rejected() -> None:
    macro = make_zip({"[Content_Types].xml": CONTENT_TYPES_MACRO})
    assert _code("x.docx", macro) == IngestErrorCode.UNSUPPORTED_TYPE
    assert _code("x.docx", b"\xd0\xcf\x11\xe0" + b"\x00" * 64) == IngestErrorCode.ENCRYPTED_DOCUMENT


def test_zip_bomb_limits() -> None:
    bomb = make_zip(
        {"[Content_Types].xml": CONTENT_TYPES_DOCX, "word/media/zeros.bin": b"\0" * 5_000_000}
    )
    assert _code("x.docx", bomb) == IngestErrorCode.CONTENT_TOO_LARGE  # ratio >> 100
    many = make_zip(
        {"[Content_Types].xml": CONTENT_TYPES_DOCX, **{f"f{i}": b"x" for i in range(30)}}
    )
    assert _code("x.docx", many, Settings(env="test", zip_max_entries=10)) == (
        IngestErrorCode.CONTENT_TOO_LARGE
    )
    total = Settings(env="test", zip_max_uncompressed_bytes=1000)
    assert _code("x.docx", make_docx([("p", "hello")]), total) == IngestErrorCode.CONTENT_TOO_LARGE


def test_truncated_zip() -> None:
    data = make_docx([("p", "hello")])
    assert _code("x.docx", data[: len(data) // 2]) == IngestErrorCode.PARSE_FAILED


def test_text_must_be_utf8_without_nul() -> None:
    assert _code("a.txt", b"abc\x00def") == IngestErrorCode.UNSUPPORTED_TYPE
    assert _code("a.csv", "caf\u00e9".encode("latin-1")) == IngestErrorCode.PARSE_FAILED


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\Users\\x\\report.pdf", "report.pdf"),
        ("  ..  ", "upload"),
        (None, "upload"),
        ("a<b>c.md", "abc.md"),
    ],
)
def test_filename_is_sanitised_and_never_a_path(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected
