"""File validation (extension + magic bytes) and text extraction for PDF, DOCX and TXT.

Security posture:
* the declared extension AND the leading magic bytes must agree (a ``.pdf`` that is really a
  ZIP is rejected with 415);
* size is enforced by the caller while streaming the upload (413);
* PDFs are limited by page count, DOCX by total uncompressed size (zip-bomb guard);
* nothing is ever executed or rendered - we only read text.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from resume_matching.core.errors import UnprocessableError, UnsupportedMediaTypeError

FileType = Literal["pdf", "docx", "txt"]

ALLOWED_EXTENSIONS: dict[str, FileType] = {".pdf": "pdf", ".docx": "docx", ".txt": "txt"}
CONTENT_TYPES: dict[FileType, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"
_MIN_TEXT_CHARS = 40
_BULLETS = "•▪●◦‣⁃■□➢∙·"
_BULLET_RE = re.compile(rf"^\s*[{re.escape(_BULLETS)}*]\s*")


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    text: str
    file_type: FileType
    content_type: str
    page_count: int | None
    checksum: str
    size_bytes: int


def detect_file_type(filename: str, data: bytes) -> FileType:
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    file_type = ALLOWED_EXTENSIONS.get(suffix)
    if file_type is None:
        raise UnsupportedMediaTypeError(
            f"Unsupported file extension '{suffix or '(none)'}'; allowed: .pdf, .docx, .txt"
        )
    if file_type == "pdf" and not data.startswith(_PDF_MAGIC):
        raise UnsupportedMediaTypeError("File content is not a PDF (magic bytes mismatch)")
    if file_type == "docx" and not data.startswith(_ZIP_MAGIC):
        raise UnsupportedMediaTypeError("File content is not a DOCX (magic bytes mismatch)")
    if file_type == "txt" and (
        data.startswith(_PDF_MAGIC) or data.startswith(_ZIP_MAGIC) or b"\x00" in data[:8192]
    ):
        raise UnsupportedMediaTypeError("File content is not plain text")
    return file_type


def normalize_text(text: str) -> str:
    """Unicode-normalise, unify bullets/whitespace, drop empty-line runs."""
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    blank = 0
    for raw in text.split("\n"):
        line = _BULLET_RE.sub("- ", raw.replace("\t", " "))
        line = re.sub(r"[  ]{2,}", " ", line).strip()
        if not line:
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        lines.append(line)
    return "\n".join(lines).strip()


def _extract_pdf(data: bytes, max_pages: int) -> tuple[str, int]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UnprocessableError("Encrypted PDFs are not supported")
        pages = len(reader.pages)
        if pages > max_pages:
            raise UnprocessableError(f"PDF has {pages} pages; the maximum is {max_pages}")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except UnprocessableError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise UnprocessableError("The PDF could not be read") from exc
    return text, pages


def _extract_docx(data: bytes, max_uncompressed: int) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names:
                raise UnsupportedMediaTypeError("ZIP archive is not a Word document")
            total = sum(info.file_size for info in archive.infolist())
            if total > max_uncompressed:
                raise UnprocessableError("DOCX expands beyond the allowed uncompressed size")
    except zipfile.BadZipFile as exc:
        raise UnprocessableError("The DOCX archive is corrupt") from exc

    from docx import Document

    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises a variety of lxml/zip errors
        raise UnprocessableError("The DOCX could not be read") from exc
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
    return "\n".join(parts)


def _decode_txt(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnsupportedMediaTypeError("Text file encoding not recognised (use UTF-8)")


def extract_document(
    filename: str,
    data: bytes,
    *,
    max_pdf_pages: int = 10,
    max_docx_uncompressed_bytes: int = 20 * 1024 * 1024,
) -> ExtractedDocument:
    file_type = detect_file_type(filename, data)
    page_count: int | None = None
    if file_type == "pdf":
        raw, page_count = _extract_pdf(data, max_pdf_pages)
    elif file_type == "docx":
        raw = _extract_docx(data, max_docx_uncompressed_bytes)
    else:
        raw = _decode_txt(data)
    text = normalize_text(raw)
    if len(re.sub(r"\s", "", text)) < _MIN_TEXT_CHARS:
        raise UnprocessableError(
            "No extractable text found (scanned/image-only documents are not supported)"
        )
    return ExtractedDocument(
        text=text,
        file_type=file_type,
        content_type=CONTENT_TYPES[file_type],
        page_count=page_count,
        checksum=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )
