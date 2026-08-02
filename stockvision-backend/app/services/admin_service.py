"""
Admin Analytics Service — new in v2.0.

Every number the admin dashboard shows is aggregated from tables this
application actually writes to: `audit_logs` (API telemetry, written by the audit
middleware on every request), `ml_models` / `predictions` / `signals` (the ML
registry), `documents` / `document_embeddings` (the RAG corpus),
`copilot_queries`, `portfolios` and `stocks`.

Explicit scoping note: the reference design's admin panel includes "Users" and
"Subscriptions" tiles. This platform has no accounts and no billing — so rather
than render two tiles of invented numbers, the admin API exposes what genuinely
exists (documents indexed, models trained, API volume, error rate, storage
consumed, system health) and the UI presents those. Fabricating a user count for
a product with no users would be the exact "fake component" the brief rules out.
"""
import logging
import os
import platform
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import AuditAction
from app.models.copilot import CopilotQuery
from app.models.market import HistoricalPrice, Stock
from app.models.ml import MLModel, Prediction, Signal
from app.models.portfolio import Order, Portfolio
from app.models.system import AuditLog, Document, DocumentEmbedding, GeneratedReport
from app.repositories.system_repository import AuditRepository
from app.schemas.admin import AdminOverview, AuditEntry, StatCard, SystemHealth, TimeseriesPoint

logger = logging.getLogger(__name__)

_PROCESS_START = time.time()


class AdminService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditRepository(db)

    def _count(self, model) -> int:
        return int(self.db.execute(select(func.count()).select_from(model)).scalar_one())

    def overview(self, window_hours: int = 24) -> AdminOverview:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=window_hours)
        previous_since = since - timedelta(hours=window_hours)

        api_calls = self.audit.count_since(since)
        previous_calls = max(self.audit.count_since(previous_since) - api_calls, 0)
        errors = self.audit.error_count(since)
        latency = self.audit.average_latency_ms(since)

        def delta(current: int, previous: int) -> float | None:
            # None (not 0.0) when there is no prior window: "no comparison
            # available" and "0% change" are different claims, and rendering the
            # former as the latter is misleading on a fresh install.
            if previous <= 0:
                return None
            return (current - previous) / previous

        predictions = self._count(Prediction)
        signals = self._count(Signal)
        documents = self._count(Document)
        chunks = self._count(DocumentEmbedding)
        models = self._count(MLModel)
        copilot = self._count(CopilotQuery)

        cards = [
            StatCard(key="api_calls", label="API Calls", value=float(api_calls),
                     display=f"{api_calls:,}", change_pct=delta(api_calls, previous_calls),
                     hint=f"Last {window_hours}h"),
            StatCard(key="predictions", label="Predictions Generated", value=float(predictions),
                     display=f"{predictions:,}", change_pct=None, hint="All time"),
            StatCard(key="signals", label="Signals Generated", value=float(signals),
                     display=f"{signals:,}", change_pct=None, hint="All time"),
            StatCard(key="documents", label="Documents Indexed", value=float(documents),
                     display=f"{documents:,}", change_pct=None, hint=f"{chunks:,} chunks"),
            StatCard(key="models", label="Model Versions", value=float(models),
                     display=f"{models:,}", change_pct=None, hint="Registry"),
            StatCard(key="copilot", label="Copilot Queries", value=float(copilot),
                     display=f"{copilot:,}", change_pct=None, hint="All time"),
            StatCard(key="error_rate", label="Error Rate",
                     value=(errors / api_calls) if api_calls else 0.0,
                     display=f"{(errors / api_calls * 100) if api_calls else 0:.2f}%",
                     change_pct=None, hint=f"{errors} of {api_calls:,} requests"),
            StatCard(key="latency", label="Avg Latency", value=latency,
                     display=f"{latency:.0f} ms", change_pct=None, hint=f"Last {window_hours}h"),
        ]

        return AdminOverview(
            window_hours=window_hours,
            cards=cards,
            api_calls_series=[
                TimeseriesPoint(timestamp=ts, value=float(count))
                for ts, count in self.audit.hourly_api_calls(hours=min(window_hours, 24))
            ],
            calls_by_action=self.audit.counts_by_action(since),
            data_counts={
                "stocks": self._count(Stock),
                "price_bars": self._count(HistoricalPrice),
                "portfolios": self._count(Portfolio),
                "orders": self._count(Order),
                "documents": documents,
                "document_chunks": chunks,
                "models": models,
                "predictions": predictions,
                "signals": signals,
                "copilot_queries": copilot,
                "reports": self._count(GeneratedReport),
                "audit_events": self._count(AuditLog),
            },
            health=self.health(),
        )

    def health(self) -> SystemHealth:
        db_ok, db_latency = self._probe_db()

        def dir_bytes(path: str) -> int:
            root = Path(path)
            if not root.exists():
                return 0
            return sum(f.stat().st_size for f in root.rglob("*") if f.is_file())

        try:
            usage = shutil.disk_usage(".")
            disk_pct = usage.used / usage.total if usage.total else 0.0
        except OSError:  # pragma: no cover — platform dependent
            disk_pct = 0.0

        return SystemHealth(
            status="healthy" if db_ok else "degraded",
            environment=settings.ENVIRONMENT,
            version=settings.APP_VERSION,
            uptime_seconds=time.time() - _PROCESS_START,
            database_connected=db_ok,
            database_latency_ms=db_latency,
            database_dialect="sqlite" if settings.is_sqlite else "postgresql",
            # Reported as "configured", never as "connected": this process does
            # not hold an open Redis connection, and claiming a live check we did
            # not perform is exactly the kind of dashboard lie that gets someone
            # paged at 3am for the wrong reason.
            redis_configured=bool(settings.REDIS_URL),
            llm_provider=(
                "openai" if settings.OPENAI_API_KEY
                else "gemini" if settings.GEMINI_API_KEY
                else "extractive_fallback"
            ),
            python_version=sys.version.split()[0],
            platform=platform.platform(),
            cpu_count=os.cpu_count() or 1,
            disk_usage_pct=disk_pct,
            document_storage_bytes=dir_bytes(settings.DOCUMENT_STORAGE_DIR),
            model_storage_bytes=dir_bytes(settings.MODEL_ARTIFACT_DIR),
            report_storage_bytes=dir_bytes(settings.REPORT_STORAGE_DIR),
        )

    def _probe_db(self) -> tuple[bool, float]:
        started = time.perf_counter()
        try:
            self.db.execute(select(1))
            return True, (time.perf_counter() - started) * 1000
        except Exception:
            logger.exception("Database health probe failed")
            return False, -1.0

    def logs(self, limit: int = 100, action: AuditAction | None = None) -> list[AuditEntry]:
        return [
            AuditEntry(
                id=row.id, action=row.action, resource=row.resource, detail=row.detail or {},
                ip_address=row.ip_address, request_id=row.request_id,
                status_code=row.status_code, duration_ms=row.duration_ms, timestamp=row.timestamp,
            )
            for row in self.audit.list_recent(limit=limit, action=action)
        ]
