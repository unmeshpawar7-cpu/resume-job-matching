from __future__ import annotations

import io

import pytest
from docx import Document

from resume_matching.core.errors import UnprocessableError, UnsupportedMediaTypeError
from resume_matching.domain.sections import detect_sections, match_heading
from resume_matching.parsing.extractors import detect_file_type, extract_document, normalize_text

RESUME = """Jane Doe
jane@example.com | +1 555 123 4567

PROFESSIONAL SUMMARY
Backend engineer.

Technical Skills:
Languages: Python, Go
Tools: Docker

Work Experience
Engineer, Acme | 2020 - Present
- Tech stack: FastAPI, Redis

Hobbies
Chess, hiking
"""


def test_section_detection_handles_decorated_and_labelled_lines():
    parsed = detect_sections(RESUME)
    assert parsed.order == ["header", "summary", "skills", "experience", "personal"]
    assert "Languages: Python, Go" in parsed.get("skills")
    assert "Tech stack: FastAPI" in parsed.get("experience")
    assert "jane@example.com" in parsed.get("header")
    assert "personal" not in parsed.scored()
    assert "header" not in parsed.scored()


def test_heading_matching():
    assert match_heading("== EXPERIENCE ==") == ("experience", "")
    assert match_heading("Skills: Python, SQL") == ("skills", "Python, SQL")
    assert match_heading("- Skills") is None
    assert match_heading("I have strong skills in many areas of engineering and design") is None


def test_unstructured_resume_falls_back_to_other():
    parsed = detect_sections("John\nPython dev\n\nBuilt APIs in Python 2019-2022.")
    assert parsed.headings_found == 0
    assert parsed.order == ["header", "other"]


def test_normalize_text_unifies_bullets_and_blank_lines():
    text = normalize_text("Title\r\n\r\n\r\n• one\n▪ two\n\tcol  a")
    assert text == "Title\n\n- one\n- two\ncol a"


def test_detect_file_type_rejects_mismatches():
    assert detect_file_type("cv.TXT", b"hello") == "txt"
    with pytest.raises(UnsupportedMediaTypeError):
        detect_file_type("cv", b"hello")
    with pytest.raises(UnsupportedMediaTypeError):
        detect_file_type("cv.txt", b"%PDF-1.7")
    with pytest.raises(UnsupportedMediaTypeError):
        detect_file_type("cv.txt", b"abc\x00def")
    with pytest.raises(UnsupportedMediaTypeError):
        detect_file_type("cv.docx", b"%PDF-1.7")


def test_extract_docx_including_tables():
    doc = Document()
    doc.add_paragraph("Skills")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Python"
    table.rows[0].cells[1].text = "Kubernetes and Terraform in production"
    buf = io.BytesIO()
    doc.save(buf)
    result = extract_document("cv.docx", buf.getvalue())
    assert "Python | Kubernetes and Terraform in production" in result.text
    assert result.content_type.endswith("wordprocessingml.document")
    assert len(result.checksum) == 64


def test_extract_rejects_corrupt_and_oversized_inputs():
    with pytest.raises(UnprocessableError):
        extract_document("cv.pdf", b"%PDF-1.4 garbage that is not a pdf")
    with pytest.raises(UnprocessableError):
        extract_document("cv.docx", b"PK\x03\x04 truncated zip")
    pdf = (
        __import__("pathlib").Path(__file__).parents[2]
        / "samples/resumes/rohan_deshpande_dotnet_backend.pdf"
    ).read_bytes()
    with pytest.raises(UnprocessableError, match="pages"):
        extract_document("cv.pdf", pdf, max_pdf_pages=0)
    buf = io.BytesIO()
    Document().save(buf)
    with pytest.raises(UnprocessableError, match="uncompressed"):
        extract_document("cv.docx", buf.getvalue(), max_docx_uncompressed_bytes=10)


def test_txt_cp1252_fallback():
    text = "Résumé – Python developer with FastAPI and PostgreSQL experience".encode("cp1252")
    assert "Résumé" in extract_document("cv.txt", text).text
