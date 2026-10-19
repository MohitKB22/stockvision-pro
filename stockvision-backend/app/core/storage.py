"""
File storage for model artifacts, generated reports and uploaded PDFs.

Two backends behind one small API, chosen by STORAGE_BACKEND:

  * filesystem — files under MODEL_ARTIFACT_DIR / REPORT_STORAGE_DIR /
    DOCUMENT_STORAGE_DIR. The owning row stores the file's path. This is the
    original behaviour and the right choice wherever there is a persistent
    volume (Docker Compose, a VM, local development).
  * database   — bytes in the `stored_files` table; the owning row stores a
    `db://<uuid>` locator. Required on serverless hosts: their deployment
    directory is read-only, `/tmp` is per-instance and disappears with it, so a
    model trained on one instance was invisible to the next and every report
    download 404'd ("Losing ml_artifacts on redeploy silently degrades every
    prediction back to indicators-only", as docs/DEPLOYMENT.md warned).

Reads dispatch on the locator, not on the current setting, so rows written
under either backend stay readable after switching.

Writes to the database backend are added to the caller's session and committed
with the row that references them, so a file and its metadata are never
persisted one without the other.
"""
from __future__ import annotations

import logging
import uuid
from enum import Enum
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

DB_LOCATOR_PREFIX = "db://"


class StorageCategory(str, Enum):
    MODEL = "model"
    REPORT = "report"
    DOCUMENT = "document"


class StorageQuotaExceededException(AppException):
    status_code = 507
    code = "storage_quota_exceeded"
    detail = "This deployment's file storage is full."


def _directory(category: StorageCategory) -> Path:
    return Path({
        StorageCategory.MODEL: settings.MODEL_ARTIFACT_DIR,
        StorageCategory.REPORT: settings.REPORT_STORAGE_DIR,
        StorageCategory.DOCUMENT: settings.DOCUMENT_STORAGE_DIR,
    }[StorageCategory(category)])


def _db_id(locator: str) -> uuid.UUID:
    return uuid.UUID(locator[len(DB_LOCATOR_PREFIX):])


def is_database_locator(locator: str) -> bool:
    return locator.startswith(DB_LOCATOR_PREFIX)


def save_file(db: Session, category: StorageCategory, filename: str, data: bytes) -> str:
    """Stores `data` and returns the locator to keep on the owning row.

    `filename` must already be unique within its category (callers prefix it with
    a record id or a model version), exactly as the filesystem layout requires.
    """
    if settings.STORAGE_BACKEND == "database":
        from app.models.system import StoredFile

        _enforce_quota(db, len(data))
        row = StoredFile(
            id=uuid.uuid4(), category=StorageCategory(category).value,
            filename=filename[:500], size_bytes=len(data), content=data,
        )
        db.add(row)
        db.flush()
        return f"{DB_LOCATOR_PREFIX}{row.id}"

    directory = _directory(category)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(data)
    return str(path)


def read_file(db: Session, locator: str) -> bytes:
    """Raises FileNotFoundError when the bytes are gone."""
    if is_database_locator(locator):
        from app.models.system import StoredFile

        row = db.get(StoredFile, _db_id(locator))
        if row is None:
            raise FileNotFoundError(locator)
        return bytes(row.content)
    return Path(locator).read_bytes()


def file_exists(db: Session, locator: str) -> bool:
    if is_database_locator(locator):
        from app.models.system import StoredFile

        return db.execute(
            select(StoredFile.id).where(StoredFile.id == _db_id(locator))
        ).first() is not None
    return Path(locator).exists()


def delete_file(db: Session, locator: str | None) -> None:
    """Best-effort removal; a file that is already gone is not an error. The
    caller commits (database backend) together with deleting the owning row."""
    if not locator:
        return
    if is_database_locator(locator):
        from app.models.system import StoredFile

        row = db.get(StoredFile, _db_id(locator))
        if row is not None:
            db.delete(row)
        return
    try:
        Path(locator).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete stored file %s", locator, exc_info=True)


def usage_bytes(db: Session, category: StorageCategory) -> int:
    """Bytes held for one category by the ACTIVE backend (the admin storage tiles)."""
    if settings.STORAGE_BACKEND == "database":
        from app.models.system import StoredFile

        total = db.execute(
            select(func.coalesce(func.sum(StoredFile.size_bytes), 0)).where(
                StoredFile.category == StorageCategory(category).value
            )
        ).scalar_one()
        return int(total or 0)

    directory = _directory(category)
    if not directory.exists():
        return 0
    return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())


def _enforce_quota(db: Session, incoming: int) -> None:
    quota = settings.STORAGE_QUOTA_BYTES
    if quota <= 0:
        return
    from app.models.system import StoredFile

    used = int(db.execute(select(func.coalesce(func.sum(StoredFile.size_bytes), 0))).scalar_one() or 0)
    if used + incoming > quota:
        raise StorageQuotaExceededException(
            f"File storage for this deployment is full ({used / 1e6:.1f} of "
            f"{quota / 1e6:.0f} MB used). Delete old reports or documents and try again.",
            context={"used_bytes": used, "quota_bytes": quota, "requested_bytes": incoming},
        )
