"""Quyền (permission) theo role, khai cứng.

Web và core kiểm theo PERMISSION, không so chuỗi role. Không có bảng `roles`/`permissions`
trong DB: ba role cố định, thêm bảng chỉ làm tăng bề mặt sai cấu hình. `/me` trả danh sách
permission của user để web ẩn/hiện; core vẫn là bên quyết định.

KHÔNG có permission nào cho phép đọc task `personal` hay note của người khác: kể cả admin
cũng không (xem services/access.py).
"""

from __future__ import annotations

from enum import StrEnum

from app.models.enums import UserRole


class Permission(StrEnum):
    # Đọc mọi task `work` (member cũng có: work là dùng chung cả team).
    TASK_READ_WORK = "task:read_work"
    # Sửa/xoá mọi task `work`, không cần là người được giao hay người tạo.
    TASK_WRITE_ANY_WORK = "task:write_any_work"
    # Trang Team: tham dự dự án, danh sách assignee.
    TEAM_READ = "team:read"
    # Chạy sync, upsert-batch, nhập Excel/URL.
    INTEGRATION_SYNC = "integration:sync"
    # Tạo/sửa/xoá kết nối tích hợp và danh sách URL đồng bộ.
    INTEGRATION_MANAGE = "integration:manage"
    PROJECT_WRITE_ANY = "project:write_any"
    # Nhập JSON vào Postgres (ghi đè hàng loạt).
    DATA_IMPORT = "data:import"
    # Mời, đổi role/status, alias, thu hồi phiên, xem nhật ký.
    USER_MANAGE = "user:manage"
    SYSTEM_READ = "system:read"


_MEMBER = frozenset({Permission.TASK_READ_WORK})
_LEAD = _MEMBER | {
    Permission.TASK_WRITE_ANY_WORK,
    Permission.TEAM_READ,
    Permission.INTEGRATION_SYNC,
    Permission.PROJECT_WRITE_ANY,
}
_ADMIN = _LEAD | {
    Permission.INTEGRATION_MANAGE,
    Permission.DATA_IMPORT,
    Permission.USER_MANAGE,
    Permission.SYSTEM_READ,
}

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.MEMBER: _MEMBER,
    UserRole.LEAD: frozenset(_LEAD),
    UserRole.ADMIN: frozenset(_ADMIN),
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]
