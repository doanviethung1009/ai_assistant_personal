"""Declarative base và mixin dùng chung."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Đặt tên constraint theo quy ước để Alembic autogenerate sinh diff ổn định
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def enum_column(enum_cls: type, name: str) -> SAEnum:
    """Cột enum lưu dạng VARCHAR + CHECK, không dùng native enum của Postgres.

    Lý do: thêm giá trị mới chỉ cần sửa CHECK constraint, không phải ALTER TYPE
    với các ràng buộc về transaction mà nó kéo theo.

    Helper này nằm ở đây thay vì trong một file model cụ thể, để mọi model
    dùng chung một cấu hình. Lệch cấu hình giữa các bảng sẽ làm Alembic
    autogenerate sinh diff nhiễu.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [member.value for member in e],
        name=name,
        validate_strings=True,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Timestamp luôn là timestamptz và do DB sinh, tránh lệch giờ giữa client."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
