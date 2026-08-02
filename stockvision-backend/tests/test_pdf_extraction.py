from pathlib import Path

import pytest
from pypdf.errors import PdfReadError

from app.rag.pdf_extraction import extract_text_by_page

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_pdfs"
TENQ_PATH = SAMPLE_DIR / "meridian_robotics_10q_q3_2025.pdf"


@pytest.fixture(scope="module", autouse=True)
def ensure_sample_pdfs_exist():
    if not TENQ_PATH.exists():
        import subprocess
        subprocess.run(["python3", str(Path(__file__).resolve().parent.parent / "scripts" / "generate_sample_documents.py")], check=True)


class TestExtractTextByPage:
    def test_extracts_correct_page_count(self):
        result = extract_text_by_page(TENQ_PATH.read_bytes())
        assert result.page_count == 3  # built with 2 PageBreaks -> 3 pages

    def test_extracts_known_text_from_page_one(self):
        result = extract_text_by_page(TENQ_PATH.read_bytes())
        page_1_text = result.pages[0][1]
        assert "412.6 million" in page_1_text
        assert "fourteen percent" in page_1_text

    def test_extracts_known_text_from_later_page(self):
        result = extract_text_by_page(TENQ_PATH.read_bytes())
        # Risk factors section was written on page 2
        page_2_text = result.pages[1][1]
        assert "key suppliers" in page_2_text.lower() or "precision actuators" in page_2_text.lower()

    def test_page_numbers_are_1_indexed_and_sequential(self):
        result = extract_text_by_page(TENQ_PATH.read_bytes())
        page_numbers = [p[0] for p in result.pages]
        assert page_numbers == [1, 2, 3]

    def test_no_pages_flagged_as_empty_for_a_real_text_pdf(self):
        result = extract_text_by_page(TENQ_PATH.read_bytes())
        assert result.pages_with_no_extractable_text == []

    def test_malformed_pdf_bytes_raise_rather_than_silently_succeed(self):
        # Asserts the SPECIFIC exception pypdf raises, not a blind `Exception`.
        # A bare `pytest.raises(Exception)` passes even if the code fails for a
        # completely unrelated reason (an ImportError, a typo in the call), which
        # makes it near-worthless as a regression guard — ruff's B017 exists for
        # exactly this. PdfStreamError subclasses PdfReadError.
        with pytest.raises(PdfReadError):
            extract_text_by_page(b"this is not a real pdf file")
