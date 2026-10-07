"""add notes.archived_at

Revision ID: d4e9f2a6b8c5
Revises: c3d8e5f1a7b4
Create Date: 2026-10-08 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "d4e9f2a6b8c5"
down_revision: str | None = "c3d8e5f1a7b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Cột nullable, không default nên chỉ đổi metadata, không viết lại bảng và
    # không cần backfill: mọi note hiện có coi như chưa lưu trữ.
    op.add_column("notes", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    # CREATE INDEX thường (không CONCURRENTLY) vì bảng notes nhỏ. Partial để
    # index chỉ chứa note lưu trữ, cùng kiểu với ix_notes_deleted_at.
    op.create_index(
        "ix_notes_archived_at",
        "notes",
        ["archived_at"],
        unique=False,
        postgresql_where=sa.text("archived_at IS NOT NULL"),
    )


def downgrade() -> None:
    # Mất thông tin lưu trữ: note quay về danh sách thường, nội dung không mất.
    op.drop_index(
        "ix_notes_archived_at",
        table_name="notes",
        postgresql_where=sa.text("archived_at IS NOT NULL"),
    )
    op.drop_column("notes", "archived_at")
