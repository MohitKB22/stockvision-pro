"""
PDF text extraction for the RAG ingestion pipeline.

Uses pypdf (see /mnt/skills/public/pdf/SKILL.md and pdf-reading/SKILL.md,
both of which recommend it for straightforward text extraction) rather than
a heavier layout-aware library — financial filings (10-Ks, earnings call
transcripts, research notes) are predominantly single-column running text,
which is exactly pypdf's strong case; pdfplumber's layout/table awareness
matters more for multi-column or table-heavy documents, which is a Phase-3
extension noted in app/services/rag_service.py if ever needed.
"""
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader


@dataclass
class ExtractionResult:
    pages: list[tuple[int, str]]  # (1-indexed page number, extracted text)
    page_count: int
    pages_with_no_extractable_text: list[int]  # likely scanned/image-only pages


def extract_text_by_page(pdf_bytes: bytes) -> ExtractionResult:
    """
    Extracts text page by page. A page whose extraction returns empty/
    whitespace-only text is recorded in `pages_with_no_extractable_text`
    (likely a scanned image with no text layer — OCR is a Phase-3 addition,
    see pdf-reading skill's "Scanned documents" section) rather than silently
    dropped or treated as an error; the rest of the document still ingests.
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    pages: list[tuple[int, str]] = []
    empty_pages: list[int] = []

    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        text = text.strip()
        if not text:
            empty_pages.append(i)
        pages.append((i, text))

    return ExtractionResult(pages=pages, page_count=len(reader.pages), pages_with_no_extractable_text=empty_pages)
