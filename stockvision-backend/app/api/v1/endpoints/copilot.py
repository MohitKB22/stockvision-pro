"""
AI Copilot (RAG) endpoints.

CHANGE LOG (v2.0): auth removed. Added conversation threading, suggested prompts
and a streaming endpoint — the reference design's Copilot panel shows a chat with
streamed responses and a thread sidebar, none of which the old single-shot query
endpoint could support.
"""
import asyncio
import json
import uuid

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import BadRequestException, NotFoundException
from app.domain.enums import AuditAction, DocumentType
from app.models.copilot import CopilotConversation
from app.repositories.document_repository import (
    CopilotConversationRepository,
    CopilotQueryRepository,
    DocumentRepository,
)
from app.schemas.common import OperationResult
from app.schemas.rag import (
    ConversationDetail,
    ConversationPublic,
    CopilotQueryRequest,
    CopilotQueryResponse,
    DocumentPublic,
    DocumentUploadResponse,
    SuggestedPrompt,
)
from app.services.audit_service import AuditService
from app.services.rag_service import RAGService

router = APIRouter(tags=["AI Copilot"])

# Curated starting points shown as chips in the empty chat state. Kept
# server-side so they stay in step with what the corpus can actually answer.
SUGGESTED_PROMPTS: list[SuggestedPrompt] = [
    SuggestedPrompt(label="Summarize revenue", prompt="Summarize the revenue performance described in the uploaded reports.", category="Financials"),
    SuggestedPrompt(label="Key risks", prompt="What are the principal risk factors disclosed in these documents?", category="Risk"),
    SuggestedPrompt(label="Margin trend", prompt="How did operating margins move, and what explanation is given?", category="Financials"),
    SuggestedPrompt(label="Segment breakdown", prompt="Break down performance by business segment.", category="Financials"),
    SuggestedPrompt(label="Management outlook", prompt="What forward guidance does management provide?", category="Outlook"),
    SuggestedPrompt(label="Capital allocation", prompt="Describe capital allocation: capex, buybacks and dividends.", category="Capital"),
]


def _to_response(record) -> CopilotQueryResponse:
    return CopilotQueryResponse(
        id=record.id,
        conversation_id=record.conversation_id,
        question=record.question,
        answer=record.answer,
        llm_provider=record.llm_provider,
        citations=record.citations or [],
        latency_ms=record.latency_ms,
        generated_at=record.created_at,
    )


# --- Documents --------------------------------------------------------------
@router.post("/documents/upload", response_model=DocumentUploadResponse, status_code=201,
             summary="Ingest a PDF into the RAG corpus")
async def upload_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    stock_symbol: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    Full pipeline: PDF -> text extraction -> chunking -> embedding -> indexed and
    immediately queryable.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise BadRequestException("Only PDF files are supported.", code="unsupported_file_type")

    file_bytes = await file.read()
    if len(file_bytes) > settings.MAX_UPLOAD_BYTES:
        # Security/stability: without this a single large upload is read fully
        # into memory and can exhaust the worker.
        raise BadRequestException(
            f"File exceeds the {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
            code="file_too_large",
            context={"size_bytes": len(file_bytes), "limit_bytes": settings.MAX_UPLOAD_BYTES},
        )
    if not file_bytes:
        raise BadRequestException("The uploaded file is empty.", code="empty_file")

    document = RAGService(db).ingest_document(
        file_bytes=file_bytes,
        filename=file.filename,
        document_type=document_type.value,
        stock_symbol=stock_symbol,
    )
    AuditService(db).log(
        action=AuditAction.DOCUMENT_UPLOADED,
        resource=f"document:{document.id}",
        detail={"filename": file.filename, "type": document_type.value},
    )
    return DocumentUploadResponse(
        id=document.id,
        filename=document.filename,
        document_type=document.document_type,
        page_count=document.page_count,
        chunks_created=getattr(document, "_chunks_created", 0),
        pages_with_no_extractable_text=getattr(document, "_pages_with_no_extractable_text", []),
    )


@router.get("/documents", response_model=list[DocumentPublic], summary="Indexed documents")
def list_documents(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    return DocumentRepository(db).list_recent(limit=limit)


@router.delete("/documents/{document_id}", response_model=OperationResult, summary="Remove a document")
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db)):
    """Deletes the row and cascades to its chunks, removing it from retrieval."""
    repo = DocumentRepository(db)
    document = repo.get(document_id)
    if not document:
        raise NotFoundException("Document not found")
    repo.delete(document)
    return OperationResult(message="Document removed from the corpus.", id=str(document_id))


# --- Conversations -----------------------------------------------------------
@router.get("/copilot/prompts", response_model=list[SuggestedPrompt], summary="Suggested prompts")
def suggested_prompts():
    return SUGGESTED_PROMPTS


@router.get("/copilot/conversations", response_model=list[ConversationPublic],
            summary="Conversation threads")
def list_conversations(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    return CopilotConversationRepository(db).list_recent(limit=limit)


@router.post("/copilot/conversations", response_model=ConversationPublic, status_code=201,
             summary="Start a thread")
def create_conversation(
    title: str = Body(default="New conversation", embed=True), db: Session = Depends(get_db)
):
    return CopilotConversationRepository(db).create(CopilotConversation(title=title[:255]))


@router.get("/copilot/conversations/{conversation_id}", response_model=ConversationDetail,
            summary="Thread with messages")
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)):
    conversation = CopilotConversationRepository(db).get_with_queries(conversation_id)
    if not conversation:
        raise NotFoundException("Conversation not found")
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        message_count=conversation.message_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[_to_response(q) for q in conversation.queries],
    )


@router.delete("/copilot/conversations/{conversation_id}", response_model=OperationResult,
               summary="Delete a thread")
def delete_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)):
    repo = CopilotConversationRepository(db)
    conversation = repo.get(conversation_id)
    if not conversation:
        raise NotFoundException("Conversation not found")
    repo.delete(conversation)
    return OperationResult(message="Conversation deleted.", id=str(conversation_id))


# --- Query ---------------------------------------------------------------------
@router.post("/copilot/query", response_model=CopilotQueryResponse, summary="Ask the copilot")
def query_copilot(payload: CopilotQueryRequest, db: Session = Depends(get_db)):
    """
    Retrieval-augmented answer over the indexed corpus. Uses a real LLM when an
    API key is configured; otherwise falls back to a clearly-labelled extractive
    mode that returns the most relevant retrieved passages. The `llm_provider`
    field always states which produced the answer.
    """
    result = RAGService(db).query(
        question=payload.question,
        stock_symbol=payload.stock_symbol,
        top_k=payload.top_k,
        vector_store_backend=payload.vector_store_backend,
        conversation_id=payload.conversation_id,
    )
    AuditService(db).log(
        action=AuditAction.COPILOT_QUERY,
        resource=f"copilot_query:{result.id}",
        detail={"provider": result.llm_provider, "citations": len(result.citations or [])},
    )
    return _to_response(result)


@router.post("/copilot/query/stream", summary="Ask the copilot (streamed)")
async def query_copilot_stream(payload: CopilotQueryRequest, db: Session = Depends(get_db)):
    """
    Server-Sent Events stream so the chat UI renders progressively instead of
    blocking on a complete answer.

    Honest implementation note: retrieval and answer generation complete
    server-side first, then the answer is emitted in word groups. True
    token-level streaming requires a streaming-capable LLM client (`stream=True`
    against OpenAI/Gemini); the fallback extractive engine has no tokens to
    stream at all. The transport here is the real SSE contract the UI consumes,
    so swapping in a token-streaming client later changes only this generator
    body — not the endpoint, and not the client.
    """
    result = RAGService(db).query(
        question=payload.question,
        stock_symbol=payload.stock_symbol,
        top_k=payload.top_k,
        vector_store_backend=payload.vector_store_backend,
        conversation_id=payload.conversation_id,
    )
    response = _to_response(result)

    async def event_stream():
        yield f"event: start\ndata: {json.dumps({'id': str(response.id), 'provider': response.llm_provider})}\n\n"
        words = response.answer.split(" ")
        for index in range(0, len(words), 4):
            chunk = " ".join(words[index:index + 4])
            yield f"event: token\ndata: {json.dumps({'text': chunk + ' '})}\n\n"
            await asyncio.sleep(0.02)
        yield f"event: done\ndata: {response.model_dump_json()}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/copilot/history", response_model=list[CopilotQueryResponse], summary="Recent questions")
def get_copilot_history(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    return [_to_response(r) for r in CopilotQueryRepository(db).list_recent(limit=limit)]
