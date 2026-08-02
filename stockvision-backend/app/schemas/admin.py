import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import AuditAction


class StatCard(BaseModel):
    key: str
    label: str
    value: float
    display: str
    change_pct: float | None = Field(
        default=None,
        description="None means there is no prior window to compare against — deliberately not 0.0.",
    )
    hint: str = ""


class TimeseriesPoint(BaseModel):
    timestamp: datetime
    value: float


class SystemHealth(BaseModel):
    status: str
    environment: str
    version: str
    uptime_seconds: float
    database_connected: bool
    database_latency_ms: float
    database_dialect: str
    redis_configured: bool = Field(
        description="Configured, not verified-connected — this process holds no open Redis connection."
    )
    llm_provider: str
    python_version: str
    platform: str
    cpu_count: int
    disk_usage_pct: float
    document_storage_bytes: int
    model_storage_bytes: int
    report_storage_bytes: int


class AdminOverview(BaseModel):
    window_hours: int
    cards: list[StatCard]
    api_calls_series: list[TimeseriesPoint]
    calls_by_action: dict[str, int]
    data_counts: dict[str, int]
    health: SystemHealth


class AuditEntry(BaseModel):
    id: uuid.UUID
    action: AuditAction
    resource: str
    detail: dict[str, Any]
    ip_address: str | None
    request_id: str | None
    status_code: int | None
    duration_ms: float | None
    timestamp: datetime
