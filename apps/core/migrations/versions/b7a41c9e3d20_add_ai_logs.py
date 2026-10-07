"""add ai_logs

Revision ID: b7a41c9e3d20
Revises: 22721dfd9b56
Create Date: 2026-10-08 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b7a41c9e3d20"
down_revision: str | None = "22721dfd9b56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Bảng mới hoàn toàn, không đụng bảng đang có nên không cần backfill và
    # không khoá bảng nào. Enum lưu VARCHAR (native_enum=False) như các bảng khác.
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


def downgrade() -> None:
    # Mất toàn bộ nhật ký trong bảng này. Chấp nhận được: bản gốc còn ở
    # docs/ai_logs.md và data/ai-logs.json.
    op.drop_index(op.f("ix_ai_logs_category"), table_name="ai_logs")
    op.drop_table("ai_logs")
