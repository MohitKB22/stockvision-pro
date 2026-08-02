"""Report generation and download endpoints — new in v2.0."""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.domain.enums import ReportFormat, ReportType
from app.repositories.system_repository import ReportRepository
from app.schemas.common import OperationResult
from app.schemas.report import ReportGenerateRequest, ReportPublic
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


def _to_public(record) -> ReportPublic:
    filename = (record.parameters or {}).get("filename") or (
        f"report.{ReportFormat(record.report_format).extension}"
    )
    return ReportPublic(
        id=record.id,
        report_type=record.report_type,
        report_format=record.report_format,
        title=record.title,
        portfolio_id=record.portfolio_id,
        size_bytes=record.size_bytes,
        filename=filename,
        download_url=f"/api/v1/reports/{record.id}/download",
        created_at=record.created_at,
    )


@router.get("", response_model=list[ReportPublic], summary="Previously generated reports")
def list_reports(
    report_type: ReportType | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return [_to_public(r) for r in ReportRepository(db).list_recent(limit=limit, report_type=report_type)]


@router.post("/generate", response_model=ReportPublic, status_code=201, summary="Generate a report")
def generate_report(payload: ReportGenerateRequest, db: Session = Depends(get_db)):
    """
    Produces a real artifact on disk (PDF/CSV/XLSX) built from the same service
    calls the UI renders from, and returns its download URL.
    """
    record = ReportService(db).generate(
        report_type=payload.report_type,
        report_format=payload.report_format,
        portfolio_id=payload.portfolio_id,
        lookback_days=payload.lookback_days,
    )
    return _to_public(record)


@router.get("/{report_id}/download", summary="Download a generated report")
def download_report(report_id: uuid.UUID, db: Session = Depends(get_db)):
    payload, filename, media_type = ReportService(db).read_file(report_id)
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(payload)),
        },
    )


@router.delete("/{report_id}", response_model=OperationResult, summary="Delete a report")
def delete_report(report_id: uuid.UUID, db: Session = Depends(get_db)):
    repo = ReportRepository(db)
    record = repo.get(report_id)
    if not record:
        raise NotFoundException("Report not found")

    # Remove the artifact too — deleting only the row leaks disk forever.
    path = Path(record.storage_path)
    if path.exists():
        path.unlink(missing_ok=True)
    repo.delete(record)
    return OperationResult(message="Report deleted.", id=str(report_id))
