"""Import mọi model ở đây để Alembic autogenerate thấy đủ metadata.

Quên import một model thì autogenerate sẽ không thấy bảng của nó, và tệ hơn
là có thể sinh migration DROP bảng đó.
"""

from app.db.base import Base
from app.models.app_setting import AppSetting
from app.models.enums import (
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
)
from app.models.import_audit import ImportAudit, ImportRun
from app.models.integration import IntegrationConnection
from app.models.note import Note
from app.models.project import Project
from app.models.task import Task, TaskEvent

__all__ = [
    "AppSetting",
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
    "Task",
    "TaskEvent",
    "TaskEventType",
    "TaskPriority",
    "TaskSource",
    "TaskStatus",
]
