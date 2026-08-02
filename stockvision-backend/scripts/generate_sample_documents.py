"""
Generates realistic-looking (but entirely fictional) financial PDFs for
testing the RAG ingestion pipeline end-to-end: extraction -> chunking ->
embedding -> retrieval -> citation. Uses reportlab per /mnt/skills/public/pdf/SKILL.md's
guidance for PDF creation (pypdf is for reading/merging/splitting, not authoring).

These are clearly fictional documents about a fictional "Meridian Robotics
Inc." — not real filings from any real company.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_pdfs"


def build_10q(path: Path) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Meridian Robotics Inc. — Form 10-Q", styles["Title"]))
    story.append(Paragraph("Quarterly Report for the Period Ended September 30, 2025", styles["Normal"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph("Item 2. Management's Discussion and Analysis", styles["Heading1"]))
    story.append(Paragraph(
        "Total revenue for the third quarter of fiscal 2025 was $412.6 million, an increase of "
        "fourteen percent compared to $362.1 million in the prior-year quarter. The increase was "
        "primarily driven by higher unit shipments of our warehouse automation robots and expanded "
        "service contract renewals.", styles["Normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Gross margin improved to 41.2 percent, up from 38.7 percent in the prior-year period, "
        "reflecting lower input costs for servo motors and improved manufacturing yield at our "
        "Ohio facility.", styles["Normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Operating expenses increased to $98.3 million, up from $87.5 million, driven by continued "
        "investment in our research and development organization, which grew headcount by twelve "
        "percent during the quarter.", styles["Normal"]
    ))
    story.append(PageBreak())

    story.append(Paragraph("Item 1A. Risk Factors", styles["Heading1"]))
    story.append(Paragraph(
        "Our business depends on a small number of key suppliers for precision actuators. A "
        "prolonged disruption at any single supplier could materially impact our ability to "
        "fulfill customer orders on schedule.", styles["Normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "We face increasing competition from both established industrial automation companies and "
        "well-funded startups, some of which have introduced lower-priced alternatives to our "
        "flagship warehouse robot platform.", styles["Normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Approximately thirty-one percent of our revenue in the quarter was derived from customers "
        "outside the United States, exposing us to foreign currency exchange rate fluctuations, "
        "particularly with respect to the Euro and Japanese Yen.", styles["Normal"]
    ))
    story.append(PageBreak())

    story.append(Paragraph("Liquidity and Capital Resources", styles["Heading1"]))
    story.append(Paragraph(
        "As of September 30, 2025, we had cash and cash equivalents of $215.4 million and no "
        "outstanding borrowings under our revolving credit facility. We believe our existing cash "
        "balance, together with cash generated from operations, will be sufficient to fund operations "
        "for at least the next twelve months.", styles["Normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "During the quarter, we repurchased 1.2 million shares of common stock for approximately "
        "$54 million under our existing share repurchase authorization.", styles["Normal"]
    ))

    doc.build(story)


def build_earnings_call(path: Path) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Meridian Robotics Inc. — Q3 2025 Earnings Call Transcript", styles["Title"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph("CEO Remarks", styles["Heading1"]))
    story.append(Paragraph(
        "Thank you all for joining. This was a strong quarter for Meridian. Revenue grew fourteen "
        "percent year over year to $412.6 million, ahead of the high end of our guidance range. We "
        "signed three new enterprise logistics customers in the quarter, including our first "
        "deployment in the automotive parts distribution vertical.", styles["Normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Looking ahead, we are raising our full-year revenue guidance to a range of $1.62 billion "
        "to $1.65 billion, up from our prior range of $1.55 billion to $1.60 billion.", styles["Normal"]
    ))
    story.append(PageBreak())

    story.append(Paragraph("CFO Remarks", styles["Heading1"]))
    story.append(Paragraph(
        "Gross margin came in at 41.2 percent this quarter, a 250 basis point improvement year over "
        "year, driven primarily by component cost reductions and yield improvements at our Ohio "
        "manufacturing facility. We expect gross margin to remain in the 40 to 42 percent range for "
        "the remainder of the fiscal year.", styles["Normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "We ended the quarter with $215.4 million in cash and no debt outstanding, giving us "
        "significant flexibility to continue investing in research and development while also "
        "returning capital to shareholders through our buyback program.", styles["Normal"]
    ))
    story.append(PageBreak())

    story.append(Paragraph("Q&A Session", styles["Heading1"]))
    story.append(Paragraph(
        "Analyst question: Can you comment on competitive pressure from newer entrants in the "
        "warehouse automation space?", styles["Normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "CEO response: We're aware of several well-funded startups in this space. Our approach has "
        "been to compete on reliability and total cost of ownership rather than upfront price alone, "
        "and our renewal rates with existing customers remain above ninety percent.", styles["Normal"]
    ))

    doc.build(story)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build_10q(OUTPUT_DIR / "meridian_robotics_10q_q3_2025.pdf")
    build_earnings_call(OUTPUT_DIR / "meridian_robotics_earnings_call_q3_2025.pdf")
    print(f"Wrote sample PDFs to {OUTPUT_DIR}")
    for f in OUTPUT_DIR.glob("*.pdf"):
        print(f"  {f.name} ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
