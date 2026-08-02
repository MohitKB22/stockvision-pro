"""
Audit Service.

CHANGE LOG (v2.0): the `user_id` parameter is gone — there are no users. What
this records now is *what happened*, when, from which client IP, and under which
request correlation ID. That is genuinely useful: it is the sole data source
behind the admin dashboard's usage analytics, and it links an operation back to
the exact request in the application logs.

`log()` never raises. Audit is observability, not business logic — a failure to
write an audit row must never fail the user's operation.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_request_id
from app.domain.enums import AuditAction
from app.models.system import AuditLog
from app.repositories.system_repository import AuditRepository

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditRepository(db)

    def log(
        self,
        action: AuditAction,
        resource: str = "",
        detail: dict[str, Any] | None = None,
        ip_address: str | None = None,
        status_code: int | None = None,
        duration_ms: float | None = None,
    ) -> AuditLog | None:
        try:
            entry = AuditLog(
                action=action,
                resource=resource,
                detail=detail or {},
                ip_address=ip_address,
                request_id=get_request_id(),
                status_code=status_code,
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            return self.repo.create(entry)
        except Exception:
            self.db.rollback()
            logger.warning("Failed to write audit entry for action=%s", action, exc_info=True)
            return None

    def recent(self, limit: int = 100, action: AuditAction | None = None) -> list[AuditLog]:
        return self.repo.list_recent(limit=limit, action=action)

    def usage_since(self, hours: int = 24) -> dict[str, Any]:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
        return {
            "window_hours": hours,
            "total_events": self.repo.count_since(since),
            "by_action": self.repo.counts_by_action(since),
            "errors": self.repo.error_count(since),
            "avg_latency_ms": round(self.repo.average_latency_ms(since), 2),
        }
