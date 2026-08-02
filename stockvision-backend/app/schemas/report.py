import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import ReportFormat, ReportType


class ReportGenerateRequest(BaseModel):
    report_type: ReportType
    report_format: ReportFormat = ReportFormat.PDF
    portfolio_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the default portfolio for portfolio/risk/tax reports."
    )
    lookback_days: int = Field(default=252, ge=30, le=2000)


class ReportPublic(BaseModel):
    id: uuid.UUID
    report_type: ReportType
    report_format: ReportFormat
    title: str
    portfolio_id: uuid.UUID | None
    size_bytes: int
    filename: str
    download_url: str
    created_at: datetime
