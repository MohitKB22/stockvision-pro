"""
RAG document + copilot repositories.

CHANGE LOG (v2.0):
  - `CopilotQueryRepository.list_for_user` REMOVED (no users), replaced by
    conversation-scoped and global-recent listings.
  - `get_for_retrieval` supports an explicit document-id scope so the copilot can
    answer against a single uploaded report instead of the whole corpus.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.copilot import CopilotConversation, CopilotQuery
from app.models.system import Document, DocumentEmbedding
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Document)

    def list_recent(self, limit: int = 200) -> list[Document]:
        return list(
            self.db.execute(
                select(Document).order_by(Document.created_at.desc()).limit(limit)
            ).scalars().all()
        )

    def list_for_stock(self, stock_id: uuid.UUID) -> list[Document]:
        return list(
            self.db.execute(select(Document).where(Document.stock_id == stock_id)).scalars().all()
        )


class DocumentEmbeddingRepository(BaseRepository[DocumentEmbedding]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, DocumentEmbedding)

    def bulk_create(self, chunks: list[DocumentEmbedding]) -> list[DocumentEmbedding]:
        """One transaction for the whole document, not one per chunk."""
        self.db.add_all(chunks)
        self.db.commit()
        return chunks

    def get_for_retrieval(
        self, stock_id: uuid.UUID | None = None, document_id: uuid.UUID | None = None
    ) -> list[DocumentEmbedding]:
        """
        Every chunk eligible for retrieval, optionally scoped to one stock's
        documents or a single document. This is the candidate set the vector
        index is built from — see app/rag/vector_store.py for the
        rebuild-per-query trade-off.
        """
        stmt = select(DocumentEmbedding).join(
            Document, DocumentEmbedding.document_id == Document.id
        )
        if stock_id is not None:
            stmt = stmt.where(Document.stock_id == stock_id)
        if document_id is not None:
            stmt = stmt.where(Document.id == document_id)
        return list(self.db.execute(stmt).scalars().all())


class CopilotConversationRepository(BaseRepository[CopilotConversation]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, CopilotConversation)

    def list_recent(self, limit: int = 50) -> list[CopilotConversation]:
        return list(
            self.db.execute(
                select(CopilotConversation)
                .order_by(CopilotConversation.updated_at.desc())
                .limit(limit)
            ).scalars().all()
        )

    def get_with_queries(self, conversation_id: uuid.UUID) -> CopilotConversation | None:
        return self.db.execute(
            select(CopilotConversation)
            .options(selectinload(CopilotConversation.queries))
            .where(CopilotConversation.id == conversation_id)
        ).scalar_one_or_none()


class CopilotQueryRepository(BaseRepository[CopilotQuery]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, CopilotQuery)

    def list_recent(self, limit: int = 50) -> list[CopilotQuery]:
        return list(
            self.db.execute(
                select(CopilotQuery).order_by(CopilotQuery.created_at.desc()).limit(limit)
            ).scalars().all()
        )

    def list_for_conversation(self, conversation_id: uuid.UUID) -> list[CopilotQuery]:
        return list(
            self.db.execute(
                select(CopilotQuery)
                .where(CopilotQuery.conversation_id == conversation_id)
                .order_by(CopilotQuery.created_at)
            ).scalars().all()
        )
