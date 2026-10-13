"""NGUỒN DUY NHẤT của quy tắc "ai thấy/sửa được gì".

══════════════════════════════════════════════════════════════════════
 Mọi truy vấn task, note, project trong `task_service`, `note_service`,
 `project_service` PHẢI đi qua hàm ở đây, không tự viết điều kiện owner/scope.
 Quên một chỗ là IDOR (đọc/sửa dữ liệu người khác). Task ngoài phạm vi nhìn thấy
 trả 404 (NotFoundError), không phải 403, để không lộ sự tồn tại.
══════════════════════════════════════════════════════════════════════

Quy tắc (docs/specs/auth-multiuser.md mục 3):
- Task `work`: mọi user đều đọc. Task `personal`: chỉ owner, KỂ CẢ admin cũng không.
- Note: chỉ owner, mọi role.
- Project: mọi user đọc; sửa khi có `project:write_any` hoặc là owner.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, or_

from app.core.auth import CurrentUser
from app.core.permissions import Permission
from app.models.enums import TaskScope
from app.models.note import Note
from app.models.project import Project
from app.models.task import Task
from app.schemas.task import TaskView


def has_permission(user: CurrentUser, permission: Permission) -> bool:
    return user.has(permission)


# ═══════════════════════════════════════════════════════════════════════
#  Task
# ═══════════════════════════════════════════════════════════════════════


def task_visible_clause(user: CurrentUser) -> ColumnElement[bool]:
    """Task tồn tại với user: mọi `work` cộng `personal` của chính họ.

    Dùng cho list, agenda, stats, trash, get, update, delete, restore, complete, time.
    """
    return or_(
        Task.scope == TaskScope.WORK,
        and_(Task.scope == TaskScope.PERSONAL, Task.owner_id == user.id),
    )


def task_view_clause(view: TaskView, user: CurrentUser) -> ColumnElement[bool] | None:
    """Điều kiện của một view; None nghĩa là không lọc thêm (view=all).

    Luôn dùng cùng `task_visible_clause` (xem `task_query_clause`). Định nghĩa "việc của tôi"
    (`mine`) duy nhất ở backend; web có bản sao ở lib/task-scope.ts cho chế độ local.
    Nhánh `assignee IS NULL AND external_id IS NULL AND owner_id = me` giữ task công việc tự
    tạo không giao ai: nó chỉ là "của tôi" với người tạo, không phải của cả team. So khớp
    assignee CHÍNH XÁC (phân biệt hoa thường); chuỗi rỗng đã chuẩn hoá thành NULL khi ghi.
    """
    if view is TaskView.ALL:
        return None
    if view is TaskView.PERSONAL:
        return Task.scope == TaskScope.PERSONAL
    if view is TaskView.WORK:
        return Task.scope == TaskScope.WORK
    work_mine: list[ColumnElement[bool]] = [
        and_(Task.assignee.is_(None), Task.external_id.is_(None), Task.owner_id == user.id)
    ]
    if user.aliases:
        work_mine.append(Task.assignee.in_(sorted(user.aliases)))
    return or_(
        and_(Task.scope == TaskScope.PERSONAL, Task.owner_id == user.id),
        and_(Task.scope == TaskScope.WORK, or_(*work_mine)),
    )


def task_query_clause(view: TaskView, user: CurrentUser) -> ColumnElement[bool]:
    """`task_visible_clause` AND điều kiện view: điều kiện mà service gắn vào truy vấn."""
    visible = task_visible_clause(user)
    clause = task_view_clause(view, user)
    return visible if clause is None else and_(visible, clause)


@dataclass(frozen=True, slots=True)
class TaskPerms:
    can_edit: bool
    can_delete: bool


def task_permissions(user: CurrentUser, task: Task) -> TaskPerms:
    """Quyền ghi của user trên một task ĐÃ NHÌN THẤY được (không thay cho việc lọc visible).

    - personal: chỉ owner.
    - work: sửa khi `task:write_any_work`, hoặc được giao (assignee thuộc alias của user), hoặc
      là người tạo task tự nhập (`owner_id = me`, không đến từ tích hợp). Xoá thì bỏ nhánh
      "được giao": người được giao một task Jira không có quyền xoá nó khỏi cả team.
    """
    if task.scope is TaskScope.PERSONAL:
        mine = task.owner_id == user.id
        return TaskPerms(can_edit=mine, can_delete=mine)
    write_any = user.has(Permission.TASK_WRITE_ANY_WORK)
    own_manual = task.owner_id == user.id and task.external_id is None
    assigned = task.assignee is not None and task.assignee in user.aliases
    return TaskPerms(
        can_edit=write_any or assigned or own_manual,
        can_delete=write_any or own_manual,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Note, Project
# ═══════════════════════════════════════════════════════════════════════


def note_visible_clause(user: CurrentUser) -> ColumnElement[bool]:
    """Note chỉ của chủ, mọi role (admin cũng không đọc được note người khác)."""
    return Note.owner_id == user.id


def project_can_modify(user: CurrentUser, project: Project) -> bool:
    """Sửa/xoá project: `project:write_any`, hoặc là người tạo."""
    return user.has(Permission.PROJECT_WRITE_ANY) or project.owner_id == user.id
