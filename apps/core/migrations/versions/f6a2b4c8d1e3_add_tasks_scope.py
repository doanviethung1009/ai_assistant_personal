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
    # ADD COLUMN cần khoá ACCESS EXCLUSIVE ngắn; nếu có transaction dài đang giữ bảng
    # thì thất bại sau 5s thay vì xếp hàng và chặn mọi truy vấn phía sau.
    op.execute("SET LOCAL lock_timeout = '5s'")
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
    # Chuẩn hoá assignee một lần: view=mine so khớp chính xác và coi NULL là "chưa giao",
    # nên '' hoặc ' Hung ' cũ sẽ làm task rơi khỏi "Hôm nay". Cũng không đụng updated_at.
    op.execute(
        "UPDATE tasks SET assignee = NULLIF(btrim(assignee), '') "
        "WHERE assignee IS DISTINCT FROM NULLIF(btrim(assignee), '')"
    )
    # CHECK tường minh (sa.Enum(native_enum=False) không tự tạo CHECK). NOT VALID rồi
    # VALIDATE: bước thêm chỉ cần khoá ngắn, bước quét bảng chỉ giữ khoá không chặn ghi.
    op.execute(
        "ALTER TABLE tasks ADD CONSTRAINT ck_tasks_scope_valid "
        "CHECK (scope IN ('work', 'personal')) NOT VALID"
    )
    op.execute("ALTER TABLE tasks VALIDATE CONSTRAINT ck_tasks_scope_valid")


def downgrade() -> None:
    # Không hoàn lại việc chuẩn hoá assignee (strip, '' -> NULL): không còn giá trị gốc.
    # Mất các lựa chọn scope User đã sửa tay (task Jira chuyển thành cá nhân và ngược lại).
    op.drop_constraint(op.f("ck_tasks_scope_valid"), "tasks", type_="check")
    op.drop_column("tasks", "scope")
