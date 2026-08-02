"""
Admin / observability endpoints — new in v2.0.

Serves only metrics this application genuinely records. See
app/services/admin_service.py for why "Users" and "Subscriptions" are absent.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.enums import AuditAction
from app.schemas.admin import AdminOverview, AuditEntry, SystemHealth
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/overview", response_model=AdminOverview, summary="Platform analytics")
def admin_overview(
    window_hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
):
    return AdminService(db).overview(window_hours=window_hours)


@router.get("/health", response_model=SystemHealth, summary="Detailed system health")
def admin_health(db: Session = Depends(get_db)):
    return AdminService(db).health()


@router.get("/logs", response_model=list[AuditEntry], summary="Audit log")
def admin_logs(
    limit: int = Query(default=100, ge=1, le=500),
    action: AuditAction | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return AdminService(db).logs(limit=limit, action=action)
