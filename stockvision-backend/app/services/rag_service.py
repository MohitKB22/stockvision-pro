"""
RAG Service: orchestrates the full LLM Financial Copilot pipeline.

  Ingestion:  PDF bytes -> pdf_extraction -> chunking -> embeddings -> DB
  Query:      question -> embed -> vector store search -> LLM (or extractive
              fallback) -> answer + citations -> DB (history) -> response

Design decision — embedding model is a fixed singleton, NOT swapped based on
whether an API key happens to be configured: every chunk ever embedded must
live in the same vector space as every query embedding, or retrieval breaks
silently (a chunk embedded with model A simply never matches a query embedded
with model B, with no error — just wrong/empty results). get_embedding_model()
always returns HashingEmbedding for that reason. Upgrading to OpenAIEmbedding
in a real deployment is a deliberate migration (re-embed every existing
chunk), not a config toggle — see that function's docstring.

get_llm_client(), in contrast, IS safe to switch dynamically: it only affects
how retrieved context gets turned into an answer, not what's indexed.
"""
import time
import uuid
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import InsufficientDataException, NotFoundException
from app.models.copilot import CopilotQuery
from app.models.system import Document, DocumentEmbedding
from app.rag.chunking import chunk_document
from app.rag.embeddings import EmbeddingModel, HashingEmbedding
from app.rag.llm_client import ExtractiveFallbackClient, GeminiChatClient, LLMClient, OpenAIChatClient, RetrievedChunk
from app.rag.pdf_extraction import extract_text_by_page
from app.rag.vector_store import new_vector_store
from app.repositories.document_repository import (
    CopilotConversationRepository,
    CopilotQueryRepository,
    DocumentEmbeddingRepository,
    DocumentRepository,
)
from app.repositories.market_repository import StockRepository

_EMBEDDING_MODEL: EmbeddingModel | None = None

# Calibrated empirically against this project's real test corpus and several
# genuinely off-topic queries (see tests/test_rag_service.py and the
# dimension-sweep in git history / PR discussion for the raw numbers):
#   - At the original 512-dimension setting, hash collisions were severe
#     enough that some off-topic queries scored HIGHER (0.21) than some
#     genuinely relevant ones (0.25) -- no threshold could separate them.
#   - At RAG_EMBEDDING_DIMENSION=4096 (the current default -- see
#     core/config.py), off-topic collision noise tops out around 0.05-0.06,
#     while genuine matches in this corpus score 0.19-0.48. This threshold
#     sits in that gap with margin on both sides.
# This is an inherent property of the hashing trick (a fixed-size, stateless
# bag-of-words representation — see HashingEmbedding's docstring): some
# collision noise is unavoidable, just pushed low enough to not matter at
# this dimensionality. A neural embedding model (OpenAIEmbedding) would not
# have this specific failure mode, at the cost of needing network+API key.
MIN_RELEVANCE_SCORE = 0.1


def get_embedding_model() -> EmbeddingModel:
    """
    Singleton accessor -- see module docstring for why this is fixed rather
    than picked per-call. Cached at module level (not per-request) since
    HashingEmbedding is stateless and cheap to share.
    """
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        _EMBEDDING_MODEL = HashingEmbedding(dimension=settings.RAG_EMBEDDING_DIMENSION)
    return _EMBEDDING_MODEL


def get_llm_client() -> LLMClient:
    """Picks the best available answer-generation backend. Safe to change
    per-call/per-request (unlike the embedding model) since it doesn't affect
    what's indexed -- see module docstring."""
    if settings.OPENAI_API_KEY:
        return OpenAIChatClient(api_key=settings.OPENAI_API_KEY)
    if settings.GEMINI_API_KEY:
        return GeminiChatClient(api_key=settings.GEMINI_API_KEY)
    return ExtractiveFallbackClient()


class RAGService:
    def __init__(self, db: Session):
        self.db = db
        self.documents = DocumentRepository(db)
        self.chunks = DocumentEmbeddingRepository(db)
        self.queries = CopilotQueryRepository(db)
        self.conversations = CopilotConversationRepository(db)
        self.stocks = StockRepository(db)

    def ingest_document(
        self,
        file_bytes: bytes,
        filename: str,
        document_type: str,
        stock_symbol: str | None,
    ) -> Document:
        stock = self.stocks.get_by_symbol(stock_symbol) if stock_symbol else None
        if stock_symbol and not stock:
            raise NotFoundException(f"Stock {stock_symbol} not found")

        extraction = extract_text_by_page(file_bytes)
        if not extraction.pages or all(not text.strip() for _, text in extraction.pages):
            raise InsufficientDataException(
                "No extractable text found in this PDF (it may be a scanned/image-only "
                "document — OCR ingestion is not implemented in this phase)."
            )

        storage_dir = Path(settings.DOCUMENT_STORAGE_DIR)
        storage_dir.mkdir(parents=True, exist_ok=True)
        document_id = uuid.uuid4()
        storage_path = storage_dir / f"{document_id}_{filename}"
        storage_path.write_bytes(file_bytes)

        document = Document(
            id=document_id,
            stock_id=stock.id if stock else None,
            filename=filename,
            document_type=document_type,
            storage_path=str(storage_path),
            page_count=extraction.page_count,
            size_bytes=len(file_bytes),
        )
        document = self.documents.create(document)

        chunks = chunk_document(extraction.pages)
        if chunks:
            embedding_model = get_embedding_model()
            vectors = embedding_model.embed_batch([c.text for c in chunks])
            chunk_rows = [
                DocumentEmbedding(
                    document_id=document.id,
                    chunk_index=c.chunk_index,
                    page_number=c.page_number,
                    chunk_text=c.text,
                    embedding_vector=vectors[i].tolist(),
                )
                for i, c in enumerate(chunks)
            ]
            self.chunks.bulk_create(chunk_rows)
            document.chunk_count = len(chunk_rows)
            self.db.commit()

        document._chunks_created = len(chunks)
        document._pages_with_no_extractable_text = extraction.pages_with_no_extractable_text
        return document

    def query(
        self,
        question: str,
        stock_symbol: str | None = None,
        top_k: int = 5,
        vector_store_backend: str = "faiss",
        conversation_id: uuid.UUID | None = None,
    ) -> CopilotQuery:
        stock = self.stocks.get_by_symbol(stock_symbol) if stock_symbol else None
        if stock_symbol and not stock:
            raise NotFoundException(f"Stock {stock_symbol} not found")

        started = time.perf_counter()
        candidate_chunks = self.chunks.get_for_retrieval(stock_id=stock.id if stock else None)
        if not candidate_chunks:
            scope = f"for {stock_symbol}" if stock_symbol else "in the system"
            raise InsufficientDataException(f"No documents have been ingested {scope} yet.")

        embedding_model = get_embedding_model()
        query_vector = embedding_model.embed_one(question)

        vectors = np.stack([np.array(c.embedding_vector, dtype=np.float32) for c in candidate_chunks])
        ids = [str(c.id) for c in candidate_chunks]
        metadatas = [
            {"document_id": str(c.document_id), "page_number": c.page_number, "chunk_text": c.chunk_text}
            for c in candidate_chunks
        ]

        store = new_vector_store(vector_store_backend)
        store.build(ids=ids, vectors=vectors, metadatas=metadatas)
        search_results = store.search(query_vector, top_k=top_k)
        search_results = [r for r in search_results if r.score >= MIN_RELEVANCE_SCORE]

        # Performance fix: this used to call `self.documents.get(...)` once per
        # candidate chunk — on a 2,000-chunk corpus that is 2,000 SELECTs on
        # every single copilot question, to resolve at most `top_k` filenames.
        # One lookup per distinct document replaces all of them.
        documents = {
            str(did): doc
            for did in {c.document_id for c in candidate_chunks}
            if (doc := self.documents.get(did)) is not None
        }
        document_by_id = {str(c.id): documents.get(str(c.document_id)) for c in candidate_chunks}

        retrieved = [
            RetrievedChunk(
                text=result.metadata["chunk_text"],
                document_name=document_by_id[result.id].filename if document_by_id.get(result.id) else "unknown",
                page_number=result.metadata["page_number"],
                score=result.score,
            )
            for result in search_results
        ]

        llm_client = get_llm_client()
        answer = llm_client.generate_answer(question, retrieved)

        citations = [
            {
                "document_name": r.document_name,
                "page_number": r.page_number,
                "chunk_text": r.text,
                "relevance_score": r.score,
            }
            for r in retrieved
        ]

        created = self.queries.create(CopilotQuery(
            conversation_id=conversation_id,
            stock_id=stock.id if stock else None,
            question=question,
            answer=answer,
            llm_provider=llm_client.name,
            citations=citations,
            latency_ms=(time.perf_counter() - started) * 1000,
        ))

        if conversation_id:
            conversation = self.conversations.get(conversation_id)
            if conversation:
                conversation.message_count = (conversation.message_count or 0) + 1
                # The first question becomes the thread title, so the history
                # sidebar is readable instead of a list of "New conversation".
                if conversation.title == "New conversation":
                    conversation.title = question[:80]
                self.db.commit()

        return created
