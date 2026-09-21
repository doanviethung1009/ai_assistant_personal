"""Import mọi model ở đây để Alembic autogenerate thấy đủ metadata."""

from app.db.base import Base
from app.models.enums import TaskEventType, TaskPriority, TaskSource, TaskStatus
from app.models.project import Project
from app.models.task import Task, TaskEvent

__all__ = [
    "Base",
    "Project",
    "Task",
    "TaskEvent",
    "TaskEventType",
    "TaskPriority",
    "TaskSource",
    "TaskStatus",
]
