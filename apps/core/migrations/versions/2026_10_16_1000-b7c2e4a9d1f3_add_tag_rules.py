"""thêm bảng tag_rules: nhớ quyết định đổi tên/xoá tag để sync không làm tag cũ quay lại

Revision ID: b7c2e4a9d1f3
Revises: a4d7e1c9b3f5
Create Date: 2026-10-16 10:00:00.000000

Spec: docs/specs/tag-rules.md mục 2.

Bảng mới, không backfill, không khoá bảng hiện có.

Downgrade: MẤT toàn bộ rule; lần sync kế tiếp tag đã đổi tên/xoá quay lại như trước T7. Không
mất dữ liệu task/note. Dump trước khi hạ trên dữ liệu thật:
  pg_dump -t tag_rules
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b7c2e4a9d1f3"
down_revision: str | None = "a4d7e1c9b3f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tag_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_tag", sa.String(length=64), nullable=False),
        sa.Column("target_tag", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(source_tag) > 0 AND source_tag = btrim(source_tag)",
            name=op.f("ck_tag_rules_source_not_blank"),
        ),
        sa.CheckConstraint(
            "target_tag IS NULL OR (length(target_tag) > 0 AND target_tag = btrim(target_tag))",
            name=op.f("ck_tag_rules_target_not_blank"),
        ),
        sa.CheckConstraint(
            "target_tag IS NULL OR target_tag <> source_tag",
            name=op.f("ck_tag_rules_not_self"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_tag_rules_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tag_rules")),
        sa.UniqueConstraint("source_tag", name=op.f("uq_tag_rules_source_tag")),
    )
    op.create_index("ix_tag_rules_target_tag", "tag_rules", ["target_tag"])


def downgrade() -> None:
    op.drop_index("ix_tag_rules_target_tag", table_name="tag_rules")
    op.drop_table("tag_rules")
