"""Chuyển giá trị Python sang dạng json.dumps xử lý được.

Tách khỏi task_service để import_service và task_sync_service dùng chung mà không phải
import một hàm "private" của service khác.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any


def jsonable(value: Any) -> Any:
    """Cần thiết vì payload của task_events là JSONB, mà diff có thể chứa UUID
    (project_id), datetime (due_at), date (scheduled_for) và Enum. Không chuyển thì
    SQLAlchemy ném TypeError khi serialize.
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list | tuple | set):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return value
