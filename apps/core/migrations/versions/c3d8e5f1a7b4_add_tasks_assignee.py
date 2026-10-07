"""add tasks.assignee

Revision ID: c3d8e5f1a7b4
Revises: b7a41c9e3d20
Create Date: 2026-10-08 09:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c3d8e5f1a7b4"
down_revision: str | None = "b7a41c9e3d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Model Task đã có `assignee` từ trước nhưng migration initial không tạo
    # cột này, nên truy vấn bảng tasks trên DB dựng bằng Alembic sẽ lỗi
    # "column tasks.assignee does not exist". Cột nullable, không default nên
    # chỉ đổi metadata, không viết lại bảng và không cần backfill.
    op.add_column("tasks", sa.Column("assignee", sa.String(length=200), nullable=True))
    op.create_index(op.f("ix_tasks_assignee"), "tasks", ["assignee"], unique=False)


def downgrade() -> None:
    # Mất dữ liệu người được giao trong bảng tasks. Chỉ chạy khi chắc chắn.
    op.drop_index(op.f("ix_tasks_assignee"), table_name="tasks")
    op.drop_column("tasks", "assignee")
