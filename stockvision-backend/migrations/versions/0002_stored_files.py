"""Database-backed file storage (`stored_files`).

Revision ID: 0002_stored_files
Revises: 0001_v2_initial
Create Date: 2026-10-19

Holds model artifacts, generated reports and uploaded PDFs when
STORAGE_BACKEND=database — the default on serverless hosts, whose filesystem is
read-only and not shared between instances. See app/core/storage.py.

Purely additive: existing rows keep their filesystem paths and remain readable,
because reads dispatch on the stored locator (`db://...` vs. a path).
"""
import sqlalchemy as sa
from alembic import op

from app.models.base import GUID

revision = "0002_stored_files"
down_revision = "0001_v2_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_stored_files_category", "stored_files", ["category"])


def downgrade() -> None:
    op.drop_index("ix_stored_files_category", table_name="stored_files")
    op.drop_table("stored_files")
