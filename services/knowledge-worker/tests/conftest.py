"""Small real PDF documents for extraction and Skill generation checks."""

from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

REQUIREMENTS_PAGES = (
    """Resume Review - Upload Requirements
Users must sign in before uploading a resume.
The upload accepts PDF and DOCX resumes.
Maximum upload size is 10 MB.
Files larger than 10 MB show a size error and must not enter analysis.
Unsupported file formats show a format error.
An accepted resume is ready for analysis.""",
    """Resume Review - Analysis Requirements
The user must upload an accepted resume before requesting analysis.
Analysis compares the resume with a job description supplied by the user.
The completed report shows a match score, missing keywords and recommendations.
If resume parsing fails, show a processing error and let the user retry.
These requirements do not specify how long analysis takes.""",
    """Resume Review - Report Download Requirements
After analysis completes, users can download the report as a PDF.
The downloaded report includes the match score, missing keywords and recommendations.
Before analysis completes, report download is unavailable.
Payments, team sharing and bulk import are outside this product's V1 scope.""",
)


def write_pdf(path: Path, pages: tuple[str, ...], *, visual_page: bool = False) -> None:
    """Write ordinary PDF text streams using a standard font; no PDF authoring dependency."""
    with PdfWriter() as writer:
        for text in pages:
            page = writer.add_blank_page(width=612, height=792)
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
                }
            )
            lines = [
                line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                for line in text.splitlines()
            ]
            stream = DecodedStreamObject()
            stream.set_data(
                (
                    "BT /F1 11 Tf 14 TL 50 740 Td "
                    + " ".join(f"({line}) Tj T*" for line in lines)
                    + " ET"
                ).encode("ascii")
            )
            page[NameObject("/Contents")] = stream
        if visual_page:
            page = writer.add_blank_page(width=612, height=792)
            stream = DecodedStreamObject()
            stream.set_data(b"100 100 200 200 re S")
            page[NameObject("/Contents")] = stream
        writer.write(path)


@pytest.fixture
def requirements_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "resume-requirements.pdf"
    write_pdf(path, REQUIREMENTS_PAGES)
    return path
