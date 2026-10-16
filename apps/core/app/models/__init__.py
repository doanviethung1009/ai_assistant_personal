"""Import mọi model ở đây để Alembic autogenerate thấy đủ metadata.

Quên import một model thì autogenerate sẽ không thấy bảng của nó, và tệ hơn
là có thể sinh migration DROP bảng đó.
"""

from app.db.base import Base
from app.models.app_setting import AppSetting
from app.models.audit_log import AuditLog
from app.models.enums import (
    AliasSource,
    AuditAction,
    ImportAction,
    ImportEntity,
    ImportKind,
    IntegrationKind,
    NoteKind,
    NoteSource,
    SettingKey,
    TaskEventType,
    TaskPriority,
    TaskSource,
    TaskStatus,
    UserRole,
    UserStatus,
)
from app.models.import_audit import ImportAudit, ImportRun
from app.models.integration import IntegrationConnection
from app.models.note import Note
from app.models.project import Project
from app.models.tag_rule import TagRule
from app.models.task import Task, TaskEvent
from app.models.user import User, UserAlias

__all__ = [
    "AliasSource",
    "AppSetting",
    "AuditAction",
    "AuditLog",
    "Base",
    "ImportAction",
    "ImportAudit",
    "ImportEntity",
    "ImportKind",
    "ImportRun",
    "IntegrationConnection",
    "IntegrationKind",
    "Note",
    "NoteKind",
    "NoteSource",
    "Project",
    "SettingKey",
    "TagRule",
    "Task",
    "TaskEvent",
    "TaskEventType",
    "TaskPriority",
    "TaskSource",
    "TaskStatus",
    "User",
    "UserAlias",
    "UserRole",
    "UserStatus",
]
