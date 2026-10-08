"""drop ai_logs

Revision ID: f3a8c1d5e7b9
Revises: d7e2a9c4b1f6
Create Date: 2026-10-08 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f3a8c1d5e7b9"
down_revision: str | None = "d7e2a9c4b1f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Gỡ hệ AI log viết tay (thay bằng hook ghi vết). MẤT dữ liệu bảng này: xuất
    # trước bằng \copy nếu cần. Cột category lưu VARCHAR (native_enum=False) nên
    # không có kiểu enum Postgres nào để drop. CHECK ở import_runs/import_audit còn
    # cho phép 'ai_logs'/'ai_log' được để nguyên (dư thừa vô hại).
    # DROP TABLE cần khoá ACCESS EXCLUSIVE: đừng chờ vô hạn nếu có phiên đang giữ bảng.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_index(op.f("ix_ai_logs_category"), table_name="ai_logs")
    op.drop_table("ai_logs")


def downgrade() -> None:
    # Tạo lại y như b7a41c9e3d20_add_ai_logs: bảng RỖNG, dữ liệu cũ không khôi phục.
    op.create_table(
        "ai_logs",
        sa.Column(
            "category",
            sa.Enum(
                "app", "api", "web", "tool", "other",
                name="ai_log_category", native_enum=False, length=32,
            ),
            server_default="other",
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("handling", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_logs")),
    )
    op.create_index(op.f("ix_ai_logs_category"), "ai_logs", ["category"], unique=False)
