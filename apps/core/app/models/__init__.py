"""Import mọi model ở đây để Alembic autogenerate thấy đủ metadata.

Quên import một model thì autogenerate sẽ không thấy bảng của nó, và tệ hơn
là có thể sinh migration DROP bảng đó.
"""

from app.db.base import Base
from app.models.enums import (
    NoteKind,
    NoteSource,
    TaskEventType,
    TaskPriority,
    TaskSource,
    TaskStatus,
)
from app.models.note import Note
from app.models.project import Project
from app.models.task import Task, TaskEvent

__all__ = [
    "Base",
    "Note",
    "NoteKind",
    "NoteSource",
    "Project",
    "Task",
    "TaskEvent",
    "TaskEventType",
    "TaskPriority",
    "TaskSource",
    "TaskStatus",
]
