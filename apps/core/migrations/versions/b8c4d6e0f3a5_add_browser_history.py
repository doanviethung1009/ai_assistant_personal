"""add browser_history

Revision ID: b8c4d6e0f3a5
Revises: a7b3c5d9e2f4
Create Date: 2026-10-08 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b8c4d6e0f3a5"
down_revision: str | None = "a7b3c5d9e2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "browser_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile", sa.String(length=200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("title", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("visit_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_visit_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "visit_count >= 0", name=op.f("ck_browser_history_visit_count_non_negative")
        ),
        sa.CheckConstraint(
            "url_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_browser_history_url_hash_hex")
        ),
        sa.CheckConstraint("char_length(url) <= 4096", name=op.f("ck_browser_history_url_max_len")),
        sa.CheckConstraint("profile <> ''", name=op.f("ck_browser_history_profile_not_empty")),
        sa.CheckConstraint("url ~ '^https?://'", name=op.f("ck_browser_history_url_http_scheme")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_browser_history")),
        sa.UniqueConstraint("profile", "url_hash", name="uq_browser_history_profile_url_hash"),
    )
    op.create_index(
        "ix_browser_history_last_visit_at_id",
        "browser_history",
        [sa.literal_column("last_visit_at DESC"), "id"],
        unique=False,
    )
    op.create_index(
        "ix_browser_history_profile_last_visit_at_id",
        "browser_history",
        ["profile", sa.literal_column("last_visit_at DESC"), "id"],
        unique=False,
    )


def downgrade() -> None:
    # Mất toàn bộ lịch sử đã đẩy lên; nguồn gốc vẫn là file Chrome trên máy chạy web.
    op.drop_index("ix_browser_history_profile_last_visit_at_id", table_name="browser_history")
    op.drop_index("ix_browser_history_last_visit_at_id", table_name="browser_history")
    op.drop_table("browser_history")
