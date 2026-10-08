"""add tasks.scope (tách task công việc và task cá nhân)

Revision ID: f6a2b4c8d1e3
Revises: e5f1a3b7c9d2
Create Date: 2026-10-08 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f6a2b4c8d1e3"
down_revision: str | None = "e5f1a3b7c9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL + DEFAULT hằng số: Postgres 11+ chỉ ghi metadata, không viết lại bảng.
    op.add_column(
        "tasks",
        sa.Column(
            "scope",
            sa.Enum("work", "personal", name="task_scope", native_enum=False, length=32),
            server_default="personal",
            nullable=False,
        ),
    )
    # Backfill theo default_scope_for(). Cố ý KHÔNG đụng updated_at: đây là phân
    # loại lại dữ liệu cũ, không phải User sửa task. Đổi updated_at sẽ làm lần nhập
    # B1 sau báo nhầm "file_older_than_db" cho mọi task Jira.
    op.execute("UPDATE tasks SET scope = 'work' WHERE source IN ('jira', 'github', 'gitlab')")
    # CHECK tường minh: sa.Enum(native_enum=False) không tự tạo CHECK.
    op.create_check_constraint(
        op.f("ck_tasks_scope_valid"), "tasks", "scope IN ('work', 'personal')"
    )


def downgrade() -> None:
    # Mất các lựa chọn scope User đã sửa tay (task Jira chuyển thành cá nhân và ngược lại).
    op.drop_constraint(op.f("ck_tasks_scope_valid"), "tasks", type_="check")
    op.drop_column("tasks", "scope")
