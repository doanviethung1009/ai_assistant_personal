"""thêm users, user_aliases, audit_log và cột chủ sở hữu (owner_id, actor_user_id)

Revision ID: b2f7a9c1d4e6
Revises: a1c9e4b7d2f8
Create Date: 2026-10-10 09:00:00.000000

Đăng nhập Google đa người dùng (docs/specs/auth-multiuser.md mục 2).

Hai CHECK `ck_tasks_personal_has_owner` và `ck_notes_owner_required` tạo NOT VALID: dữ liệu cũ
chưa có chủ nên VALIDATE ngay sẽ thất bại. Chúng chỉ kiểm dòng MỚI hoặc dòng được SỬA; lệnh CLI
`python -m app.cli.auth bootstrap` gán chủ cho dữ liệu cũ rồi chạy VALIDATE CONSTRAINT.

Downgrade: mất toàn bộ users, aliases, audit_log và mọi owner_id. Dump trước khi hạ:
  pg_dump -t users -t user_aliases -t audit_log
  COPY (SELECT id, owner_id FROM tasks WHERE owner_id IS NOT NULL) TO STDOUT
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2f7a9c1d4e6"
down_revision: str | None = "a1c9e4b7d2f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TASK_OWNER_CHECK = "scope <> 'personal' OR owner_id IS NOT NULL"
_NOTE_OWNER_CHECK = "owner_id IS NOT NULL"


def upgrade() -> None:
    # ALTER TABLE và CREATE INDEX trên bảng đang chạy cần khoá; thất bại sau 5s thay vì xếp
    # hàng chặn mọi truy vấn phía sau.
    op.execute("SET LOCAL lock_timeout = '5s'")

    # ── Bảng mới (không đụng bảng cũ nên không khoá bảng nào) ───────────────
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column(
            "role",
            sa.Enum("admin", "lead", "member", name="user_role", native_enum=False, length=32),
            server_default="member",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "invited", "active", "disabled", name="user_status", native_enum=False, length=32
            ),
            server_default="invited",
            nullable=False,
        ),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("session_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
            "email = lower(btrim(email)) AND position('@' in email) > 1",
            name=op.f("ck_users_email_normalized"),
        ),
        sa.CheckConstraint("role IN ('admin', 'lead', 'member')", name=op.f("ck_users_role_valid")),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'disabled')", name=op.f("ck_users_status_valid")
        ),
        sa.CheckConstraint(
            "status <> 'active' OR google_sub IS NOT NULL", name=op.f("ck_users_active_has_sub")
        ),
        sa.CheckConstraint(
            "session_version >= 0", name=op.f("ck_users_session_version_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_users_invited_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("google_sub", name="uq_users_google_sub"),
    )

    op.create_table(
        "user_aliases",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("jira", name="alias_source", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("alias", sa.String(length=200), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("source IN ('jira')", name=op.f("ck_user_aliases_source_valid")),
        sa.CheckConstraint(
            "alias = btrim(alias) AND length(alias) > 0",
            name=op.f("ck_user_aliases_alias_trimmed"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_aliases_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_aliases")),
        sa.UniqueConstraint("source", "alias", name="uq_user_aliases_source_alias"),
    )
    op.create_index("ix_user_aliases_user_id", "user_aliases", ["user_id"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("client_ip", postgresql.INET(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_log_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"], unique=False)
    op.create_index(
        "ix_audit_log_actor_created", "audit_log", ["actor_user_id", "created_at"], unique=False
    )

    # ── Cột chủ sở hữu: NULL, chỉ đổi metadata (không viết lại bảng) ─────────
    op.add_column("tasks", sa.Column("owner_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_tasks_owner_id_users"), "tasks", "users", ["owner_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index(
        "ix_tasks_owner_scope",
        "tasks",
        ["owner_id", "scope"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.add_column("notes", sa.Column("owner_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_notes_owner_id_users"), "notes", "users", ["owner_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index(
        "ix_notes_owner_id",
        "notes",
        ["owner_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.add_column("projects", sa.Column("owner_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_projects_owner_id_users"),
        "projects",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"], unique=False)

    op.add_column("task_events", sa.Column("actor_user_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_task_events_actor_user_id_users"),
        "task_events",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_task_events_actor_created",
        "task_events",
        ["actor_user_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("event_type = 'time_logged'"),
    )

    # NOT VALID: chỉ kiểm dòng mới/sửa. VALIDATE do CLI bootstrap chạy sau khi gán chủ.
    op.execute(
        "ALTER TABLE tasks ADD CONSTRAINT ck_tasks_personal_has_owner "
        f"CHECK ({_TASK_OWNER_CHECK}) NOT VALID"
    )
    op.execute(
        "ALTER TABLE notes ADD CONSTRAINT ck_notes_owner_required "
        f"CHECK ({_NOTE_OWNER_CHECK}) NOT VALID"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")

    op.drop_constraint(op.f("ck_notes_owner_required"), "notes", type_="check")
    op.drop_constraint(op.f("ck_tasks_personal_has_owner"), "tasks", type_="check")

    op.drop_index("ix_task_events_actor_created", table_name="task_events")
    op.drop_constraint(
        op.f("fk_task_events_actor_user_id_users"), "task_events", type_="foreignkey"
    )
    op.drop_column("task_events", "actor_user_id")

    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_constraint(op.f("fk_projects_owner_id_users"), "projects", type_="foreignkey")
    op.drop_column("projects", "owner_id")

    op.drop_index("ix_notes_owner_id", table_name="notes")
    op.drop_constraint(op.f("fk_notes_owner_id_users"), "notes", type_="foreignkey")
    op.drop_column("notes", "owner_id")

    op.drop_index("ix_tasks_owner_scope", table_name="tasks")
    op.drop_constraint(op.f("fk_tasks_owner_id_users"), "tasks", type_="foreignkey")
    op.drop_column("tasks", "owner_id")

    op.drop_index("ix_audit_log_actor_created", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_user_aliases_user_id", table_name="user_aliases")
    op.drop_table("user_aliases")
    op.drop_table("users")
