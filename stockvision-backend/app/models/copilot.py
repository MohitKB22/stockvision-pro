"""
AI Copilot conversation persistence.

CHANGE LOG (v2.0):
  - REMOVED `CopilotQuery.user_id` and its FK to the deleted `users` table.
  - ADDED `CopilotConversation`. Previously every question was a standalone row,
    so "history" was a flat list with no notion of a thread — the chat UI could
    not group turns and follow-up questions had no context to inherit. Queries
    now hang off a conversation, which is what makes multi-turn chat and the
    "New Chat" button meaningful.
"""
from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import GUID, IDMixin, TimestampMixin


class CopilotConversation(Base, IDMixin, TimestampMixin):
    __tablename__ = "copilot_conversations"

    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    queries: Mapped[list["CopilotQuery"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        passive_deletes=True, order_by="CopilotQuery.created_at",
    )


class CopilotQuery(Base, IDMixin, TimestampMixin):
    __tablename__ = "copilot_queries"
    __table_args__ = (Index("ix_copilot_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[str | None] = mapped_column(
        GUID(), ForeignKey("copilot_conversations.id", ondelete="CASCADE"), nullable=True
    )
    stock_id: Mapped[str | None] = mapped_column(
        GUID(), ForeignKey("stocks.id", ondelete="SET NULL"), nullable=True
    )

    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # [{document_name, page_number, chunk_text, relevance_score}, ...]
    citations: Mapped[list] = mapped_column(JSON, default=list)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    conversation: Mapped["CopilotConversation | None"] = relationship(back_populates="queries")

    def __repr__(self) -> str:
        return f"<CopilotQuery {self.question[:50]!r}>"
