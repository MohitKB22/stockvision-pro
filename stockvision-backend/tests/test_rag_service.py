from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.services.rag_service import MIN_RELEVANCE_SCORE, RAGService

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_pdfs"
TENQ_PATH = SAMPLE_DIR / "meridian_robotics_10q_q3_2025.pdf"


def _ensure_sample_pdfs():
    if not TENQ_PATH.exists():
        import subprocess
        script = Path(__file__).resolve().parent.parent / "scripts" / "generate_sample_documents.py"
        subprocess.run(["python3", str(script)], check=True)


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()



class TestMinRelevanceThreshold:
    def test_min_relevance_threshold_filters_off_topic_results(self):
        """
        Direct regression test for the threshold calibration documented in
        rag_service.py: an off-topic query against real ingested financial
        text should retrieve ZERO chunks (all below MIN_RELEVANCE_SCORE),
        not the top-k nearest matches regardless of relevance.
        """
        _ensure_sample_pdfs()
        session = _session()
        service = RAGService(session)
        service.ingest_document(
            file_bytes=TENQ_PATH.read_bytes(), filename="10q.pdf",
            document_type="quarterly_report", stock_symbol=None,
        )

        result = service.query(question="What is the capital of France?", top_k=5)
        assert result.citations == []
        assert "no relevant passages" in result.answer.lower()

    def test_relevant_query_clears_the_threshold(self):
        _ensure_sample_pdfs()
        session = _session()
        service = RAGService(session)
        service.ingest_document(
            file_bytes=TENQ_PATH.read_bytes(), filename="10q.pdf",
            document_type="quarterly_report", stock_symbol=None,
        )

        result = service.query(question="What was total revenue this quarter?", top_k=5)
        assert len(result.citations) > 0
        assert all(c["relevance_score"] >= MIN_RELEVANCE_SCORE for c in result.citations)


class TestIngestDocument:
    def test_ingest_returns_transient_chunk_count_attribute(self):
        _ensure_sample_pdfs()
        session = _session()
        service = RAGService(session)
        document = service.ingest_document(
            file_bytes=TENQ_PATH.read_bytes(), filename="10q.pdf",
            document_type="quarterly_report", stock_symbol=None,
        )
        assert document._chunks_created > 0
        assert document.page_count == 3

    def test_ingest_persists_chunks_queryable_via_repository(self):
        _ensure_sample_pdfs()
        session = _session()
        service = RAGService(session)
        document = service.ingest_document(
            file_bytes=TENQ_PATH.read_bytes(), filename="10q.pdf",
            document_type="quarterly_report", stock_symbol=None,
        )
        chunks = service.chunks.get_for_retrieval()
        assert len(chunks) == document._chunks_created
        assert all(c.document_id == document.id for c in chunks)
        assert all(c.page_number >= 1 for c in chunks)
