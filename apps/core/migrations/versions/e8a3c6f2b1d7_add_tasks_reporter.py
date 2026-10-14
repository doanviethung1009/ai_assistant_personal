"""add tasks.reporter

Revision ID: e8a3c6f2b1d7
Revises: b2f7a9c1d4e6
Create Date: 2026-10-10 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "e8a3c6f2b1d7"
down_revision: str | None = "b2f7a9c1d4e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Chờ khoá tối đa 5s thay vì treo hàng đợi truy vấn của bảng tasks. Cột nullable,
    # không default nên chỉ đổi metadata, không viết lại bảng; không index (chưa có truy
    # vấn lọc theo reporter).
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("tasks", sa.Column("reporter", sa.String(length=200), nullable=True))


def downgrade() -> None:
    # Mất tên reporter. Dữ liệu do Jira sở hữu: sync đầy đủ sau khi upgrade lại sẽ điền lại.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_column("tasks", "reporter")
