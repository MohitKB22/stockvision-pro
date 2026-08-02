import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DocumentType


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    document_type: DocumentType
    page_count: int
    chunks_created: int
    pages_with_no_extractable_text: list[int] = Field(
        description="Pages pypdf could not extract text from — typically scanned images needing OCR."
    )


class DocumentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    document_type: DocumentType
    page_count: int | None
    chunk_count: int
    size_bytes: int | None
    stock_id: uuid.UUID | None
    created_at: datetime


class CopilotQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    stock_symbol: str | None = Field(default=None, description="Scope retrieval to one company; null searches all.")
    top_k: int = Field(default=5, ge=1, le=20)
    vector_store_backend: str = Field(default="faiss", pattern="^(faiss|chromadb)$")
    conversation_id: uuid.UUID | None = None


class Citation(BaseModel):
    document_name: str
    page_number: int
    chunk_text: str
    relevance_score: float


class CopilotQueryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID | None
    question: str
    answer: str
    llm_provider: str
    citations: list[Citation]
    latency_ms: float | None
    generated_at: datetime


class ConversationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationPublic):
    messages: list[CopilotQueryResponse]


class SuggestedPrompt(BaseModel):
    label: str
    prompt: str
    category: str
