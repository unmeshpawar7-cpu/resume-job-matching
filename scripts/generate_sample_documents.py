"""Generate the binary sample resumes (.docx / .pdf) from the plain-text samples.

    python scripts/generate_sample_documents.py

Requires the dev extra (python-docx is a runtime dependency, fpdf2 a dev dependency).
Output is deterministic apart from the PDF/DOCX metadata timestamps, which are pinned.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt
from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
RESUMES = ROOT / "samples" / "resumes"
FIXED_DATE = datetime(2026, 10, 8, tzinfo=UTC)
HEADINGS = {"summary", "skills", "experience", "education", "certifications", "projects"}


def _is_heading(line: str) -> bool:
    return line.strip().lower() in HEADINGS


def to_docx(source: Path, target: Path) -> None:
    lines = source.read_text(encoding="utf-8").splitlines()
    doc = Document()
    doc.core_properties.created = FIXED_DATE.replace(tzinfo=None)
    doc.core_properties.modified = FIXED_DATE.replace(tzinfo=None)
    doc.core_properties.author = "sample"
    for i, line in enumerate(lines):
        if i == 0:
            doc.add_heading(line, level=0)
        elif _is_heading(line):
            doc.add_heading(line, level=1)
        elif line.startswith("- "):
            doc.add_paragraph(line[2:], style="List Bullet")
        elif line.strip():
            para = doc.add_paragraph(line)
            para.runs[0].font.size = Pt(10.5)
    doc.save(str(target))


def _latin1(text: str) -> str:
    replacements = {"–": "-", "—": "-", "’": "'", "“": '"', "”": '"', "•": "-"}
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


def to_pdf(source: Path, target: Path) -> None:
    pdf = FPDF(format="A4")
    pdf.set_creation_date(FIXED_DATE)
    pdf.set_author("sample")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    for i, raw in enumerate(source.read_text(encoding="utf-8").splitlines()):
        line = _latin1(raw)
        if i == 0:
            pdf.set_font("Helvetica", "B", 16)
        elif _is_heading(line):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 12)
        else:
            pdf.set_font("Helvetica", "", 10)
        if not line.strip():
            pdf.ln(3)
            continue
        pdf.multi_cell(width, 5.5, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(target))


def main() -> int:
    to_docx(RESUMES / "maya_chen_ml_engineer.txt", RESUMES / "maya_chen_ml_engineer.docx")
    to_pdf(
        RESUMES / "rohan_deshpande_dotnet_backend.txt",
        RESUMES / "rohan_deshpande_dotnet_backend.pdf",
    )
    print("wrote maya_chen_ml_engineer.docx and rohan_deshpande_dotnet_backend.pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
