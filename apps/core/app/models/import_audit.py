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
from typing import Any

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import ImportAction, ImportEntity, ImportKind


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

    __table_args__ = (Index("ix_import_runs_created_at", "created_at"),)


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
    )
