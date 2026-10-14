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


class ImportKind(StrEnum):
    """Loại file nguồn của một lần nhập (xem models/import_audit.py).

    CẠM BẪY: ba enum Import* có CHECK constraint ở DB, và `alembic check` KHÔNG so
    sánh CHECK. Thêm giá trị ở đây mà quên viết migration DROP/ADD CONSTRAINT thì
    `alembic check` vẫn xanh nhưng INSERT giá trị mới bị DB từ chối.
    """

    DATAFILE = "datafile"
    # Di sản: tính năng ai-logs đã gỡ, giữ member vì CHECK ở DB và các dòng sổ cái cũ
    # vẫn có giá trị này (đọc qua ORM không được vỡ).
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
    # Di sản như ImportKind.AI_LOGS: dòng import_audit cũ còn giá trị này.
    AI_LOG = "ai_log"
    # B2: cài đặt app_settings. entity_id của audit là uuid5 cố định theo khoá cài đặt.
    SETTING = "setting"


class ImportAction(StrEnum):
    """Thêm giá trị phải tự viết migration DROP/ADD CONSTRAINT cho
    `ck_import_audit_action_valid` (`alembic check` không thấy CHECK)."""

    CREATED = "created"
    REPLACED = "replaced"


class SettingKey(StrEnum):
    """Khoá cài đặt hợp lệ của bảng `app_settings` (khai báo CỨNG).

    Bảng này chỉ chứa cài đặt KHÔNG bí mật. Khoá lạ bị từ chối cả ở service lẫn
    bằng CHECK `ck_app_settings_key_valid`. Thêm khoá mới phải tự viết migration
    DROP/ADD CONSTRAINT (`alembic check` không so CHECK). TUYỆT ĐỐI không thêm
    khoá chứa token hay mật khẩu vào đây.
    """

    CURRENT_USERS = "current_users"
    SYNC_URLS = "sync_urls"
    # DORMANT: không còn đọc/ghi (múi giờ chỉ là env DISPLAY_TIMEZONE). GIỮ giá trị vì CHECK
    # ck_app_settings_key_valid sinh từ enum này; gỡ cần migration riêng.
    DISPLAY_TIMEZONE = "display_timezone"


class IntegrationKind(StrEnum):
    """Loại kết nối tích hợp (bảng `integration_connections`).

    CẠM BẪY: có CHECK ở DB (`ck_integration_connections_kind_valid`) và `alembic check`
    KHÔNG so sánh CHECK. Thêm giá trị mà quên migration DROP/ADD CONSTRAINT thì INSERT
    giá trị mới bị DB từ chối.
    """

    JIRA = "jira"


class UserRole(StrEnum):
    """Vai trò của người dùng (bảng `users`).

    Ba role cố định, quyền chi tiết khai ở `core/permissions.py` (không có bảng roles).
    CẠM BẪY: có CHECK `ck_users_role_valid` và `alembic check` KHÔNG so CHECK; thêm giá trị mà
    quên migration DROP/ADD CONSTRAINT thì INSERT bị DB từ chối.
    """

    ADMIN = "admin"
    LEAD = "lead"
    MEMBER = "member"


class UserStatus(StrEnum):
    """Trạng thái tài khoản. `invited` = đã được mời, chưa đăng nhập lần nào (chưa có google_sub).

    CÓ CHECK `ck_users_status_valid` ở DB (xem cảnh báo ở UserRole).
    """

    INVITED = "invited"
    ACTIVE = "active"
    DISABLED = "disabled"


class AuthProvider(StrEnum):
    """Cách một tài khoản đăng nhập (bảng `users`). Một tài khoản chỉ có MỘT cách.

    CÓ CHECK `ck_users_auth_provider_valid` ở DB (xem cảnh báo ở UserRole).
    """

    GOOGLE = "google"
    LOCAL = "local"


class AliasSource(StrEnum):
    """Hệ thống nguồn của một alias (tên trong Jira...). CHECK `ck_user_aliases_source_valid`."""

    JIRA = "jira"


class AuditAction(StrEnum):
    """Hành động được ghi vào `audit_log`.

    CỐ Ý không có CHECK ở DB: danh sách sẽ tăng theo tính năng, mỗi lần thêm mà phải DROP/ADD
    CHECK (và `alembic check` không bắt được nếu quên) thì rủi ro làm hỏng việc ghi nhật ký
    cao hơn lợi ích. Service chỉ nhận enum này. `details` KHÔNG BAO GIỜ chứa token, cookie,
    JWT, mã OAuth hay mật khẩu.
    """

    LOGIN_SUCCESS = "login_success"
    LOGIN_DENIED = "login_denied"
    USER_INVITED = "user_invited"
    USER_UPDATED = "user_updated"
    USER_ROLE_CHANGED = "user_role_changed"
    USER_STATUS_CHANGED = "user_status_changed"
    USER_ALIASES_CHANGED = "user_aliases_changed"
    SESSIONS_REVOKED = "sessions_revoked"
    IMPORT_COMMITTED = "import_committed"
    INTEGRATION_CREATED = "integration_created"
    INTEGRATION_UPDATED = "integration_updated"
    INTEGRATION_DELETED = "integration_deleted"
    INTEGRATION_SYNCED = "integration_synced"
    BOOTSTRAP_BACKFILL = "bootstrap_backfill"
    # Tài khoản nội bộ (mật khẩu): tạo, admin đặt lại, tự đổi, bị khoá tạm, mở khoá; xoá cứng.
    USER_CREATED = "user_created"
    PASSWORD_RESET = "password_reset"  # noqa: S105 - tên hành động, không phải mật khẩu
    PASSWORD_CHANGED = "password_changed"  # noqa: S105
    LOGIN_LOCKED = "login_locked"
    USER_UNLOCKED = "user_unlocked"
    USER_DELETED = "user_deleted"
