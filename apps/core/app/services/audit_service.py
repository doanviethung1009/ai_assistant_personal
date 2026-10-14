"""Ghi `audit_log`. CHỈ INSERT: không có hàm sửa hay xoá.

`details` KHÔNG BAO GIỜ chứa token, cookie, JWT, mã OAuth, mật khẩu hay claim Google thô.
Người gọi tự chịu trách nhiệm không đưa chúng vào; hàm này chỉ chặn vài tên khoá rõ ràng.
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction

# Lớp phòng thủ thứ hai, không thay cho việc người gọi không đưa secret vào details.
_FORBIDDEN_KEYS = frozenset(
    {"token", "id_token", "access_token", "refresh_token", "jwt", "cookie", "password", "secret"}
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
