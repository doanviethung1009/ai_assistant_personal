"""Ghi và đọc `audit_log`. Ghi CHỈ INSERT: không có hàm sửa hay xoá.

`details` KHÔNG BAO GIỜ chứa token, cookie, JWT, mã OAuth, mật khẩu (kể cả mật khẩu tạm, hash)
hay claim Google thô. Người gọi tự chịu trách nhiệm không đưa chúng vào; hàm này chỉ chặn vài
tên khoá rõ ràng. `identifier` bị cấm vì identifier gõ sai thường chính là mật khẩu gõ nhầm ô:
khi không khớp user nào chỉ ghi `identifier_sha256` (16 ký tự đầu của sha256).
"""

from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.models.user import User

# Lớp phòng thủ thứ hai, không thay cho việc người gọi không đưa secret vào details.
_FORBIDDEN_KEYS = frozenset(
    {
        "token",
        "id_token",
        "access_token",
        "refresh_token",
        "jwt",
        "cookie",
        "password",
        "secret",
        "temporary_password",
        "password_hash",
        "identifier",
    }
)


def _clean_ip(value: str | None) -> str | None:
    """Chỉ nhận chuỗi IP hợp lệ: cột INET từ chối chuỗi lạ bằng lỗi DB làm hỏng cả transaction."""
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def record(
    session: AsyncSession,
    action: AuditAction,
    *,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    client_ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Thêm một dòng vào session (commit do người gọi / dependency lo)."""
    if details is not None:
        bad = _FORBIDDEN_KEYS & {key.lower() for key in details}
        if bad:
            raise ValueError(f"audit details không được chứa khoá nhạy cảm: {sorted(bad)}")
    session.add(
        AuditLog(
            action=action.value,
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=target_id,
            client_ip=_clean_ip(client_ip),
            details=details,
        )
    )


# ── Đọc ─────────────────────────────────────────────────────────


async def list_entries(
    session: AsyncSession,
    *,
    action: AuditAction | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[AuditLog, str | None, str | None]], int]:
    """Trang nhật ký mới nhất trước, kèm email actor/target nối bằng LEFT JOIN (một truy vấn).

    Trả `(các bộ (dòng, actor_email, target_email), tổng khớp bộ lọc)`. Email NULL khi user đã bị
    xoá (audit_log giữ lại, `actor_user_id` thành NULL). Chỉ ĐỌC: không có hàm sửa hay xoá.
    """
    conditions = []
    if action is not None:
        conditions.append(AuditLog.action == action.value)
    if actor_user_id is not None:
        conditions.append(AuditLog.actor_user_id == actor_user_id)
    if target_id is not None:
        conditions.append(AuditLog.target_id == target_id)
    if since is not None:
        conditions.append(AuditLog.created_at >= since)
    if until is not None:
        conditions.append(AuditLog.created_at <= until)

    actor = aliased(User)
    target = aliased(User)
    rows = await session.execute(
        select(AuditLog, actor.email, target.email)
        .outerjoin(actor, actor.id == AuditLog.actor_user_id)
        .outerjoin(target, (AuditLog.target_type == "user") & (target.id == AuditLog.target_id))
        .where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    total = await session.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
    return [(row[0], row[1], row[2]) for row in rows.all()], int(total or 0)
