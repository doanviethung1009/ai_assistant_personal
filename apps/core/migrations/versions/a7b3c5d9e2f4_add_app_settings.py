"""add app_settings và mở rộng import_audit.entity với 'setting'

Revision ID: a7b3c5d9e2f4
Revises: f6a2b4c8d1e3
Create Date: 2026-10-08 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a7b3c5d9e2f4"
down_revision: str | None = "f6a2b4c8d1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTITY_OLD = "entity IN ('project', 'task', 'task_event', 'note', 'ai_log')"
_ENTITY_NEW = "entity IN ('project', 'task', 'task_event', 'note', 'ai_log', 'setting')"


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # CHECK tường minh: khoá lạ bị DB từ chối dù ai INSERT (alembic check không so CHECK).
        sa.CheckConstraint(
            "key IN ('current_users', 'sync_urls')", name=op.f("ck_app_settings_key_valid")
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
    )
    # import_audit.entity nhận thêm 'setting'. Không sửa migration e5f1a3b7c9d2 tại chỗ vì
    # nó đã merge. import_audit là bảng nhỏ nên ADD CONSTRAINT quét lại tức thì.
    op.drop_constraint(op.f("ck_import_audit_entity_valid"), "import_audit", type_="check")
    op.create_check_constraint(op.f("ck_import_audit_entity_valid"), "import_audit", _ENTITY_NEW)


def downgrade() -> None:
    # Dòng audit entity='setting' (nếu có) phải xoá trước, nếu không ADD CONSTRAINT cũ
    # thất bại. Chỉ mất dấu vết nhập cài đặt, không đụng dữ liệu nghiệp vụ.
    op.execute("DELETE FROM import_audit WHERE entity = 'setting'")
    op.drop_constraint(op.f("ck_import_audit_entity_valid"), "import_audit", type_="check")
    op.create_check_constraint(op.f("ck_import_audit_entity_valid"), "import_audit", _ENTITY_OLD)
    # Mất toàn bộ cài đặt current_users/sync_urls.
    op.drop_table("app_settings")
