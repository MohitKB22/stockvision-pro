"""Initial schema (v2.0 — no authentication, multi-market).

Revision ID: 0001_v2_initial
Revises:
Create Date: 2026-07-25

This REPLACES the two v1 migrations (`ddd9b8bb246c_initial_schema` and
`34b7ecbe609c_add_rag_copilot_tables`). They were deleted rather than superseded
by a down-migration because:

  1. The v2 change is not additive. It drops the `users` table and every foreign
     key into it (`portfolios.owner_id`, `documents.uploaded_by`,
     `audit_logs.user_id`, `copilot_queries.user_id`). A migration that drops the
     identity table of a running system is not something to apply silently to
     production data — it is a new schema.
  2. No deployed database exists to migrate FROM. Preserving a migration path out
     of a schema nobody is running adds maintenance burden and a misleading
     impression of upgrade support.

Anyone holding v1 data should export it, apply this schema fresh, and re-import
the market/portfolio tables (users have no destination, by design).

Indexing principle: index the columns that appear in WHERE/ORDER BY on the hot
read paths — market-scoped listings, latest-bar-per-stock, order replay and
time-ordered audit queries — and nothing else, because every extra index is a
write-time cost on the highest-volume table in the schema.
"""
import sqlalchemy as sa
from alembic import op

from app.models.base import GUID

revision = "0001_v2_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Market reference data ------------------------------------------------
    op.create_table(
        "stocks",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("exchange", sa.String(50), nullable=False),
        sa.Column("market", sa.String(4), nullable=False, server_default="IN"),
        sa.Column("sector", sa.String(100)),
        sa.Column("industry", sa.String(100)),
        sa.Column("currency", sa.String(10), server_default="INR"),
        sa.Column("is_index", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("market_cap", sa.Float),
        sa.Column("shares_outstanding", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_stocks_symbol", "stocks", ["symbol"], unique=True)
    op.create_index("ix_stocks_market", "stocks", ["market"])
    op.create_index("ix_stocks_market_sector", "stocks", ["market", "sector"])
    op.create_index("ix_stocks_market_is_index", "stocks", ["market", "is_index"])

    op.create_table(
        "historical_prices",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("stock_id", GUID(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=False, server_default="0"),
        sa.Column("source", sa.String(50), server_default="csv_import"),
    )
    # Unique — this is what makes the bulk importer idempotent.
    op.create_index("ix_historical_prices_stock_ts", "historical_prices",
                    ["stock_id", "timestamp"], unique=True)
    op.create_index("ix_historical_prices_ts", "historical_prices", ["timestamp"])

    # --- Portfolios -----------------------------------------------------------
    op.create_table(
        "portfolios",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("market", sa.String(4), nullable=False, server_default="IN"),
        sa.Column("base_currency", sa.String(10), server_default="INR"),
        sa.Column("benchmark_symbol", sa.String(20), server_default="NIFTY50"),
        sa.Column("cash_balance", sa.Float, nullable=False, server_default="0"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_portfolios_market", "portfolios", ["market"])

    op.create_table(
        "portfolio_holdings",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("portfolio_id", GUID(), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stock_id", GUID(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("average_cost", sa.Float, nullable=False),
        sa.Column("realized_pnl", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_holdings_portfolio_stock", "portfolio_holdings",
                    ["portfolio_id", "stock_id"], unique=True)

    op.create_table(
        "orders",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("portfolio_id", GUID(), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stock_id", GUID(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("transaction_cost", sa.Float, server_default="0"),
        sa.Column("slippage", sa.Float, server_default="0"),
        sa.Column("status", sa.String(20), server_default="filled"),
        sa.Column("is_simulated", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(500)),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Order replay reads the full ledger in execution order on every write.
    op.create_index("ix_orders_portfolio_executed", "orders", ["portfolio_id", "executed_at"])
    op.create_index("ix_orders_stock", "orders", ["stock_id"])

    # --- ML registry -----------------------------------------------------------
    op.create_table(
        "ml_models",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("task", sa.String(50), nullable=False),
        sa.Column("algorithm", sa.String(50), nullable=False),
        sa.Column("stage", sa.String(20), server_default="staging"),
        sa.Column("artifact_path", sa.String(500), nullable=False),
        sa.Column("hyperparameters", sa.JSON),
        sa.Column("metrics", sa.JSON),
        sa.Column("feature_names", sa.JSON),
        sa.Column("mlflow_run_id", sa.String(100)),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Serves the production-model lookup, which is (name, task, stage) scoped.
    op.create_index("ix_ml_models_name_task_stage", "ml_models", ["name", "task", "stage"])

    op.create_table(
        "predictions",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("model_id", GUID(), sa.ForeignKey("ml_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stock_id", GUID(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("predicted_value", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("shap_values", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_predictions_stock_created", "predictions", ["stock_id", "created_at"])

    op.create_table(
        "signals",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("stock_id", GUID(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prediction_id", GUID(), sa.ForeignKey("predictions.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("risk_score", sa.Float, nullable=False),
        sa.Column("supporting_indicators", sa.JSON),
        sa.Column("explanation", sa.String(2000), server_default=""),
        sa.Column("llm_explanation", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_signals_stock_created", "signals", ["stock_id", "created_at"])

    # --- RAG corpus ---------------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("stock_id", GUID(), sa.ForeignKey("stocks.id", ondelete="SET NULL")),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("page_count", sa.Integer),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_stock_type", "documents", ["stock_id", "document_type"])

    op.create_table(
        "document_embeddings",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("document_id", GUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("embedding_vector", sa.JSON),
        sa.Column("vector_store_ref", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_doc_embeddings_document_chunk", "document_embeddings",
                    ["document_id", "chunk_index"])

    op.create_table(
        "copilot_conversations",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("title", sa.String(255), server_default="New conversation"),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "copilot_queries",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("conversation_id", GUID(), sa.ForeignKey("copilot_conversations.id", ondelete="CASCADE")),
        sa.Column("stock_id", GUID(), sa.ForeignKey("stocks.id", ondelete="SET NULL")),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("llm_provider", sa.String(50), nullable=False),
        sa.Column("citations", sa.JSON),
        sa.Column("latency_ms", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_copilot_conversation_created", "copilot_queries",
                    ["conversation_id", "created_at"])

    # --- Content & platform ------------------------------------------------------------
    op.create_table(
        "news_articles",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("stock_id", GUID(), sa.ForeignKey("stocks.id", ondelete="SET NULL")),
        sa.Column("market", sa.String(4), nullable=False, server_default="IN"),
        sa.Column("headline", sa.String(500), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sentiment_score", sa.Float),
        sa.Column("impact_score", sa.Float),
        sa.Column("entities", sa.JSON),
        sa.Column("summary", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_news_market_published", "news_articles", ["market", "published_at"])
    op.create_index("ix_news_stock_published", "news_articles", ["stock_id", "published_at"])

    op.create_table(
        "watchlists",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("market", sa.String(4), nullable=False, server_default="IN"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_watchlists_market", "watchlists", ["market"])

    op.create_table(
        "watchlist_items",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("watchlist_id", GUID(), sa.ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stock_id", GUID(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("alert_above", sa.Float),
        sa.Column("alert_below", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("watchlist_id", "stock_id", name="uq_watchlist_stock"),
    )

    op.create_table(
        "generated_reports",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("report_type", sa.String(30), nullable=False),
        sa.Column("report_format", sa.String(10), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("portfolio_id", GUID(), sa.ForeignKey("portfolios.id", ondelete="SET NULL")),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("parameters", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_reports_type_created", "generated_reports", ["report_type", "created_at"])

    op.create_table(
        "app_settings",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_app_settings_key", "app_settings", ["key"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource", sa.String(255), server_default=""),
        sa.Column("detail", sa.JSON),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("duration_ms", sa.Float),
        sa.Column("status_code", sa.Integer),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_action_ts", "audit_logs", ["action", "timestamp"])
    op.create_index("ix_audit_ts", "audit_logs", ["timestamp"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])


def downgrade() -> None:
    # Reverse dependency order so foreign keys never block a drop.
    for table in (
        "audit_logs", "app_settings", "generated_reports", "watchlist_items", "watchlists",
        "news_articles", "copilot_queries", "copilot_conversations", "document_embeddings",
        "documents", "signals", "predictions", "ml_models", "orders", "portfolio_holdings",
        "portfolios", "historical_prices", "stocks",
    ):
        op.drop_table(table)
