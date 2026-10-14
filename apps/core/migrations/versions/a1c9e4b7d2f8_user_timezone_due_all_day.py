"""khoá display_timezone cho app_settings và cột tasks.due_all_day

Revision ID: a1c9e4b7d2f8
Revises: f3a8c1d5e7b9
Create Date: 2026-10-09 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a1c9e4b7d2f8"
down_revision: str | None = "f3a8c1d5e7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEY_OLD = "key IN ('current_users', 'sync_urls')"
_KEY_NEW = "key IN ('current_users', 'sync_urls', 'display_timezone')"
# Hạn cả ngày phải là đúng 00:00 UTC. `timestamptz AT TIME ZONE 'UTC'` với múi giờ là
# hằng chuỗi là IMMUTABLE nên dùng được trong CHECK.
_ALL_DAY_CHECK = (
    "NOT due_all_day OR (due_at IS NOT NULL AND (due_at AT TIME ZONE 'UTC')::time = '00:00')"
)


def upgrade() -> None:
    # DROP/ADD CONSTRAINT và ADD CHECK cần khoá mạnh trên bảng; thất bại sau 5s thay vì xếp
    # hàng chặn mọi truy vấn phía sau.
    op.execute("SET LOCAL lock_timeout = '5s'")

    # app_settings: nhận thêm khoá display_timezone (alembic check KHÔNG so CHECK nên viết tay).
    op.drop_constraint(op.f("ck_app_settings_key_valid"), "app_settings", type_="check")
    op.create_check_constraint(op.f("ck_app_settings_key_valid"), "app_settings", _KEY_NEW)

    # tasks.due_all_day: PG >= 11 thêm cột có DEFAULT hằng chỉ đổi metadata, không viết lại bảng.
    op.add_column(
        "tasks",
        sa.Column("due_all_day", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    # Backfill TRƯỚC khi thêm CHECK. Cả hai đường sync Jira chỉ sinh 00:00 UTC từ `duedate`
    # (ngày thuần, Jira Cloud không có giờ), nên heuristic này khôi phục đúng ý nghĩa. Không lọc
    # deleted_at để task trong thùng rác phục hồi ra vẫn đúng. Task manual không bị đụng.
    op.execute(
        """
        UPDATE tasks
        SET due_all_day = true
        WHERE source = 'jira'
          AND due_at IS NOT NULL
          AND (due_at AT TIME ZONE 'UTC')::time = '00:00'
        """
    )
    # Đối soát hạn với raw_payload. Trước epic `due_at` là CREATE_ONLY còn raw_payload bị ghi đè
    # mỗi lần sync, nên task cũ có due_at lệch `raw_payload.fields.duedate`; luật mới (so hạn
    # hiện có với duedate trong payload) sẽ hiểu nhầm là "User sửa tay" và giữ hạn cũ mãi.
    # Hạn 00:00 UTC (due_all_day) là do sync sinh ra nên chưa ai sửa tay: kéo về duedate. Jira đã
    # bỏ hạn (không có duedate) thì giữ nguyên, regex cũng loại giá trị không phải ngày.
    op.execute(
        r"""
        UPDATE tasks
        SET due_at = ((raw_payload->'fields'->>'duedate')::date)::timestamp AT TIME ZONE 'UTC'
        WHERE source = 'jira'
          AND due_all_day
          AND raw_payload->'fields'->>'duedate' ~ '^\d{4}-\d{2}-\d{2}$'
          AND due_at IS DISTINCT FROM
              ((raw_payload->'fields'->>'duedate')::date)::timestamp AT TIME ZONE 'UTC'
        """
    )
    op.create_check_constraint(op.f("ck_tasks_due_all_day_midnight"), "tasks", _ALL_DAY_CHECK)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_constraint(op.f("ck_tasks_due_all_day_midnight"), "tasks", type_="check")
    # `due_at` không đổi giá trị nên không mất hạn, chỉ quay về quy tắc quá hạn theo giờ.
    op.drop_column("tasks", "due_all_day")

    # Xoá dòng display_timezone TRƯỚC, nếu không ADD CONSTRAINT cũ thất bại. Mất lựa chọn
    # múi giờ: hệ thống quay về giá trị env DISPLAY_TIMEZONE.
    op.execute("DELETE FROM app_settings WHERE key = 'display_timezone'")
    op.drop_constraint(op.f("ck_app_settings_key_valid"), "app_settings", type_="check")
    op.create_check_constraint(op.f("ck_app_settings_key_valid"), "app_settings", _KEY_OLD)
