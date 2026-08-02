"""
Cross-cutting models: AuditLog, NewsArticle, Document / DocumentEmbedding,
Watchlist / WatchlistItem, GeneratedReport and AppSetting.

CHANGE LOG (v2.0):
  - REMOVED `AuditLog.user_id` and `Document.uploaded_by` (and their FKs to the
    deleted `users` table). Audit entries now record *what happened* and from
    which client IP — the only attribution that still exists.
  - `NewsArticle` is no longer schema-only. It is populated (see
    app/services/news_service.py + scripts/seed_data.py) and served by
    GET /api/v1/news, with a lexicon-based sentiment score computed at ingest.
    Previously the table existed with no pipeline behind it and the UI had no
    news at all.
  - ADDED `Watchlist` / `WatchlistItem`, `GeneratedReport` and `AppSetting` —
    the persistence behind the watchlist, reports and settings pages, which
    previously had no backend whatsoever.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import AuditAction, DocumentType, Market, ReportFormat, ReportType
from app.models.base import GUID, IDMixin, TimestampMixin


class AuditLog(Base, IDMixin):
    """
    Immutable record of state-changing and compute-consuming operations, plus
    per-request API telemetry. This table is the sole data source behind the
    admin dashboard's usage analytics — nothing there is fabricated.
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_action_ts", "action", "timestamp"),
        Index("ix_audit_ts", "timestamp"),
    )

    action: Mapped[AuditAction] = mapped_column(String(50), nullable=False)
    resource: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} @ {self.timestamp}>"


class NewsArticle(Base, IDMixin, TimestampMixin):
    __tablename__ = "news_articles"
    __table_args__ = (
        Index("ix_news_market_published", "market", "published_at"),
        Index("ix_news_stock_published", "stock_id", "published_at"),
    )

    stock_id: Mapped[str | None] = mapped_column(
        GUID(), ForeignKey("stocks.id", ondelete="SET NULL"), nullable=True
    )
    market: Mapped[Market] = mapped_column(String(4), nullable=False, default=Market.INDIA)
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # -1..1
    impact_score: Mapped[float | None] = mapped_column(Float, nullable=True)     # 0..1
    entities: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    stock: Mapped["Stock | None"] = relationship()  # noqa: F821


class Document(Base, IDMixin, TimestampMixin):
    """
    A financial document ingested by the AI Copilot: PDF -> pypdf extraction ->
    chunking -> embedding -> vector store. See app/services/rag_service.py.
    """
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_stock_type", "stock_id", "document_type"),)

    stock_id: Mapped[str | None] = mapped_column(
        GUID(), ForeignKey("stocks.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(String(50), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    chunks: Mapped[list["DocumentEmbedding"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class DocumentEmbedding(Base, IDMixin, TimestampMixin):
    """
    One chunk of a Document plus its embedding vector — the unit that both the
    FAISS/ChromaDB indices (app/rag/vector_store.py) and citations operate on.
    """
    __tablename__ = "document_embeddings"
    __table_args__ = (Index("ix_doc_embeddings_document_chunk", "document_id", "chunk_index"),)

    document_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Production note: with pgvector installed this column becomes the native
    # `vector` type and similarity search moves into the database. Kept as JSON
    # so the schema runs on stock PostgreSQL and SQLite; the FAISS/ChromaDB
    # indices are built FROM this table rather than replacing it.
    embedding_vector: Mapped[list] = mapped_column(JSON, nullable=True)
    vector_store_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Watchlist(Base, IDMixin, TimestampMixin):
    __tablename__ = "watchlists"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    market: Mapped[Market] = mapped_column(String(4), nullable=False, default=Market.INDIA, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan",
        passive_deletes=True, order_by="WatchlistItem.position",
    )


class WatchlistItem(Base, IDMixin, TimestampMixin):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        # Enforces "a symbol appears at most once per watchlist" in the database
        # rather than in application code — the only place a concurrent
        # double-add can actually be prevented.
        UniqueConstraint("watchlist_id", "stock_id", name="uq_watchlist_stock"),
    )

    watchlist_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alert_above: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_below: Mapped[float | None] = mapped_column(Float, nullable=True)

    watchlist: Mapped["Watchlist"] = relationship(back_populates="items")
    stock: Mapped["Stock"] = relationship()  # noqa: F821


class GeneratedReport(Base, IDMixin, TimestampMixin):
    """
    Metadata for a report artifact produced by app/services/report_service.py.
    The file itself lives on disk (REPORT_STORAGE_DIR) — storing multi-megabyte
    PDFs as BLOBs would bloat every backup and every replica of the database.
    """
    __tablename__ = "generated_reports"
    __table_args__ = (Index("ix_reports_type_created", "report_type", "created_at"),)

    report_type: Mapped[ReportType] = mapped_column(String(30), nullable=False)
    report_format: Mapped[ReportFormat] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    portfolio_id: Mapped[str | None] = mapped_column(
        GUID(), ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True
    )
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)


class AppSetting(Base, IDMixin, TimestampMixin):
    """
    Server-persisted application preferences (theme, language, default market,
    notification toggles). A key/value table rather than a wide
    column-per-setting table, so adding a preference never needs a migration.
    """
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
