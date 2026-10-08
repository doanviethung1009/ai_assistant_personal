"""add import_runs and import_audit (sổ cái các lần nhập dữ liệu)

Revision ID: e5f1a3b7c9d2
Revises: d4e9f2a6b8c5
Create Date: 2026-10-07 17:42:53.306895
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e5f1a3b7c9d2"
down_revision: str | None = "d4e9f2a6b8c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Hai bảng mới, không đụng bảng nghiệp vụ. import_audit cố ý không có FK tới
    # tasks/projects/notes để dấu vết còn nguyên khi bản ghi bị xoá về sau.
    op.create_table(
        "import_runs",
        sa.Column(
            "kind",
            sa.Enum("datafile", "ai_logs", name="import_kind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("file_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        # CHECK tường minh: `sa.Enum(native_enum=False)` không tự tạo CHECK ở DB.
        sa.CheckConstraint(
            "kind IN ('datafile', 'ai_logs')", name=op.f("ck_import_runs_kind_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_runs")),
    )
    op.create_index("ix_import_runs_created_at", "import_runs", ["created_at"], unique=False)
    op.create_table(
        "import_audit",
        sa.Column("import_id", sa.UUID(), nullable=False),
        sa.Column(
            "entity",
            sa.Enum(
                "project",
                "task",
                "task_event",
                "note",
                "ai_log",
                name="import_entity",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column(
            "action",
            sa.Enum("created", "replaced", name="import_action", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            "before", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "changed_fields", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["import_runs.id"],
            name=op.f("fk_import_audit_import_id_import_runs"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "entity IN ('project', 'task', 'task_event', 'note', 'ai_log')",
            name=op.f("ck_import_audit_entity_valid"),
        ),
        sa.CheckConstraint(
            "action IN ('created', 'replaced')", name=op.f("ck_import_audit_action_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_audit")),
    )
    op.create_index(
        "ix_import_audit_entity_entity_id", "import_audit", ["entity", "entity_id"], unique=False
    )
    op.create_index("ix_import_audit_import_id", "import_audit", ["import_id"], unique=False)


def downgrade() -> None:
    # Mất lịch sử nhập và khả năng hoàn tác theo `before`; dữ liệu nghiệp vụ không đổi.
    op.drop_index("ix_import_audit_import_id", table_name="import_audit")
    op.drop_index("ix_import_audit_entity_entity_id", table_name="import_audit")
    op.drop_table("import_audit")
    op.drop_index("ix_import_runs_created_at", table_name="import_runs")
    op.drop_table("import_runs")
