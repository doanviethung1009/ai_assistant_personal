"""add integration connections

Revision ID: c9d1e3f5a7b2
Revises: b8c4d6e0f3a5
Create Date: 2026-10-08 18:05:45.548948
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c9d1e3f5a7b2"
down_revision: str | None = "b8c4d6e0f3a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Bảng mới, không đụng bảng cũ nên không khoá bảng nào. Chứa secret đã mã hoá
    # (secret_ciphertext): TUYỆT ĐỐI không thêm bảng này vào export/import JSON.
    op.create_table(
        "integration_connections",
        sa.Column(
            "kind",
            sa.Enum("jira", name="integration_kind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("account_email", sa.String(length=200), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("secret_last4", sa.String(length=4), nullable=True),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "base_url LIKE 'https://%'", name=op.f("ck_integration_connections_base_url_https")
        ),
        sa.CheckConstraint("kind IN ('jira')", name=op.f("ck_integration_connections_kind_valid")),
        sa.CheckConstraint(
            "(secret_ciphertext IS NULL) = (secret_last4 IS NULL)",
            name=op.f("ck_integration_connections_secret_pair_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_connections")),
        sa.UniqueConstraint("kind", "name", name="uq_integration_connections_kind_name"),
    )


def downgrade() -> None:
    # Mất toàn bộ kết nối đã lưu, kể cả token đã mã hoá (phải nhập lại sau khi upgrade).
    # Dữ liệu task không bị ảnh hưởng.
    op.drop_table("integration_connections")
