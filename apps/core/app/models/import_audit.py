"""Sổ cái của các lần nhập dữ liệu hàng loạt (import_runs, import_audit).

Vì sao có hai bảng này: nhập là thao tác GHI ĐÈ bản ghi đã tồn tại. Không lưu
giá trị trước khi ghi đè thì không còn cách hoàn tác nào ngoài `pg_dump`.
`import_audit.before` giữ toàn bộ cột của bản ghi trước khi bị ghi đè.

Không có FK từ import_audit tới bảng nghiệp vụ, để dấu vết còn nguyên khi bản
ghi đó bị xoá về sau.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import ImportAction, ImportEntity, ImportKind


def _in_list(column: str, enum_cls: type[StrEnum]) -> str:
    """Sinh `col IN ('a','b')` từ enum, để CHECK luôn khớp enum Python.

    Giá trị lấy từ enum do code định nghĩa (không phải đầu vào người dùng).

    CẠM BẪY: `alembic check` KHÔNG so sánh CHECK constraint, nên thêm giá trị vào
    enum mà không viết migration DROP/ADD CONSTRAINT sẽ không bị phát hiện, và DB
    sẽ từ chối giá trị mới.
    """
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return f"{column} IN ({values})"


class ImportRun(UUIDPrimaryKeyMixin, Base):
    """Một lần nhập đã COMMIT. Dry-run không để lại dòng nào."""

    __tablename__ = "import_runs"

    kind: Mapped[ImportKind] = mapped_column(enum_column(ImportKind, "import_kind"))
    # sha256 của body thô, để biết hai lần nhập có cùng một file hay không.
    file_sha256: Mapped[str] = mapped_column(CHAR(64))
    schema_version: Mapped[int] = mapped_column(Integer)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB)
    actor: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_import_runs_created_at", "created_at"),
        # `enum_column` không tạo CHECK ở DB, nên khai tường minh: sổ cái dùng để
        # hoàn tác, một giá trị lạ lọt vào sẽ làm script hoàn tác bỏ sót dòng.
        CheckConstraint(_in_list("kind", ImportKind), name="kind_valid"),
    )


class ImportAudit(UUIDPrimaryKeyMixin, Base):
    """Một bản ghi nghiệp vụ bị lần nhập tạo mới hoặc ghi đè."""

    __tablename__ = "import_audit"

    import_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("import_runs.id", ondelete="CASCADE")
    )
    entity: Mapped[ImportEntity] = mapped_column(enum_column(ImportEntity, "import_entity"))
    # Cố ý KHÔNG có FK: dấu vết phải sống lâu hơn bản ghi.
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    action: Mapped[ImportAction] = mapped_column(enum_column(ImportAction, "import_action"))
    # NULL thật (không phải JSON null) khi action = created.
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), default=None)
    changed_fields: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_import_audit_import_id", "import_id"),
        Index("ix_import_audit_entity_entity_id", "entity", "entity_id"),
        CheckConstraint(_in_list("entity", ImportEntity), name="entity_valid"),
        CheckConstraint(_in_list("action", ImportAction), name="action_valid"),
    )
