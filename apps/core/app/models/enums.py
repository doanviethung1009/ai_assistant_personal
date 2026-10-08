"""Enum dùng chung.

Lưu trong DB dưới dạng VARCHAR + CHECK (native_enum=False) thay vì native
enum của Postgres. Lý do: thêm giá trị mới chỉ cần sửa CHECK, không phải
ALTER TYPE với các ràng buộc về transaction.
"""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"

    @property
    def is_closed(self) -> bool:
        return self in {TaskStatus.DONE, TaskStatus.CANCELLED}


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

    @property
    def weight(self) -> int:
        return {"low": 0, "medium": 1, "high": 2, "urgent": 3}[self.value]


class TaskSource(StrEnum):
    """Nguồn gốc của task.

    Phase 1 chỉ dùng MANUAL. Các giá trị còn lại khai báo trước để thêm
    integration không cần migration đổi CHECK constraint.
    """

    MANUAL = "manual"
    JIRA = "jira"
    CALENDAR = "calendar"
    EMAIL = "email"
    OBSIDIAN = "obsidian"
    GITHUB = "github"
    GITLAB = "gitlab"
    AGENT = "agent"


class TaskScope(StrEnum):
    """Task là việc công ty hay việc riêng.

    Khác `source` (task đến từ đâu): scope quyết định task có bị tích hợp đồng
    bộ ghi đè hay không, và có hiện ở `/team` hay không. User sửa được.

    CẠM BẪY: có CHECK ở DB (`ck_tasks_scope_valid`), và `alembic check` KHÔNG so
    sánh CHECK. Thêm giá trị mà quên migration DROP/ADD CONSTRAINT thì INSERT bị từ chối.
    """

    WORK = "work"
    PERSONAL = "personal"


# Nguồn tích hợp mà task mặc định là việc công ty (spec task-scope S2).
WORK_SOURCES = frozenset({TaskSource.JIRA, TaskSource.GITHUB, TaskSource.GITLAB})


def default_scope_for(source: TaskSource) -> TaskScope:
    """Nguồn duy nhất của quy tắc suy scope từ source (migration, service, nhập file).

    Web có bản sao ở apps/web/lib/task-scope.ts (`defaultScopeFor`), hai bản phải
    khớp. Migration `add_tasks_scope` viết tay danh sách nguồn trong SQL vì
    migration phải đóng băng theo thời điểm viết, không import code đang đổi.
    """
    return TaskScope.WORK if source in WORK_SOURCES else TaskScope.PERSONAL


class NoteKind(StrEnum):
    """Loại nội dung của một note, quyết định cách hiển thị và tô màu.

    Đây là phân loại ngữ nghĩa, không phải tên ngôn ngữ. `COMMAND` gồm cả
    bash, psql, docker, kubectl — mọi thứ gõ vào terminal. Chia nhỏ hơn theo
    ngôn ngữ chỉ làm người dùng phải quyết định nhiều hơn mà chẳng đổi lại
    được gì ở tầng nghiệp vụ.
    """

    COMMAND = "command"
    SQL = "sql"
    TEXT = "text"
    CONFIG = "config"
    CODE = "code"
    SYSTEM_INFO = "system_info"
    SYSTEM_FLOW = "system_flow"
    KNOWLEDGE = "knowledge"

    @property
    def is_executable(self) -> bool:
        """Loại có thể chạy được ở đâu đó, nên cần cảnh báo trước khi copy.

        Lưu ý: app KHÔNG BAO GIỜ tự chạy nội dung note. Thuộc tính này chỉ để
        UI biết có cần nhắc người dùng đọc lại trước khi dán vào terminal.
        """
        return self in {NoteKind.COMMAND, NoteKind.SQL}


class NoteSource(StrEnum):
    """Nguồn gốc của note.

    Tách riêng khỏi TaskSource dù một số giá trị trùng tên. Note không đến từ
    Jira hay Calendar, còn Obsidian thì gần như chỉ sinh ra note. Dùng chung
    một enum sẽ khiến CHECK constraint cho phép những tổ hợp vô nghĩa.

    Phase 1 chỉ dùng MANUAL. Các giá trị còn lại khai báo trước để thêm
    integration không cần migration đổi CHECK constraint.
    """

    MANUAL = "manual"
    OBSIDIAN = "obsidian"
    GITHUB = "github"
    AGENT = "agent"


class TaskEventType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    STATUS_CHANGED = "status_changed"
    SCHEDULED = "scheduled"
    TIME_LOGGED = "time_logged"
    COMPLETED = "completed"
    REOPENED = "reopened"
    NOTE_ADDED = "note_added"
    SYNCED = "synced"
    # Xoá mềm, đưa vào thùng rác. Task vẫn còn trong DB.
    DELETED = "deleted"
    # Lấy lại từ thùng rác
    RESTORED = "restored"


class AiLogCategory(StrEnum):
    APP = "app"
    API = "api"
    WEB = "web"
    TOOL = "tool"
    OTHER = "other"


class ImportKind(StrEnum):
    """Loại file nguồn của một lần nhập (xem models/import_audit.py).

    CẠM BẪY: ba enum Import* có CHECK constraint ở DB, và `alembic check` KHÔNG so
    sánh CHECK. Thêm giá trị ở đây mà quên viết migration DROP/ADD CONSTRAINT thì
    `alembic check` vẫn xanh nhưng INSERT giá trị mới bị DB từ chối.
    """

    DATAFILE = "datafile"
    AI_LOGS = "ai_logs"


class ImportEntity(StrEnum):
    """Thực thể bị một lần nhập chạm tới, dùng cho import_audit.

    Thêm giá trị phải tự viết migration DROP/ADD CONSTRAINT cho
    `ck_import_audit_entity_valid` (`alembic check` không thấy CHECK).
    """

    PROJECT = "project"
    TASK = "task"
    TASK_EVENT = "task_event"
    NOTE = "note"
    AI_LOG = "ai_log"


class ImportAction(StrEnum):
    """Thêm giá trị phải tự viết migration DROP/ADD CONSTRAINT cho
    `ck_import_audit_action_valid` (`alembic check` không thấy CHECK)."""

    CREATED = "created"
    REPLACED = "replaced"
