from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import NoteKind, NoteSource

if TYPE_CHECKING:
    from app.models.project import Project


class Note(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Sổ tay: câu lệnh, câu SQL, đoạn cấu hình, ghi chú tự do.

    Mục đích là chỗ để dán lại thứ đã mất công tìm ra, rồi copy lại lần sau.
    Khác Task ở chỗ note không có vòng đời và không có hạn: nó là tài liệu
    tham khảo, không phải việc cần làm.

    ══════════════════════════════════════════════════════════════════════
     `content` LÀ DỮ LIỆU, KHÔNG PHẢI CODE.

     Hệ thống không bao giờ thực thi nội dung note, không truyền nó vào
     shell, không nối vào câu SQL. Người dùng tự copy và tự chịu trách
     nhiệm khi dán vào terminal. Một note chứa `rm -rf /` chỉ là chuỗi ký
     tự vô hại trong database.

     Nếu về sau có tính năng "chạy note", nó phải là một cơ chế riêng có
     xác nhận tường minh của con người, không phải hệ quả của việc lưu note.
    ══════════════════════════════════════════════════════════════════════
    """

    __tablename__ = "notes"

    # ── Nội dung ────────────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[NoteKind] = mapped_column(
        enum_column(NoteKind, "note_kind"),
        default=NoteKind.COMMAND,
        server_default=NoteKind.COMMAND.value,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text)
    # Vì sao cần, khi nào dùng. Tách khỏi content để copy không kéo theo văn xuôi.
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # Nơi áp dụng: tên host, tên database, môi trường. Ví dụ "prod, DB builder_ai".
    context: Mapped[str | None] = mapped_column(String(200), default=None)

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )

    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default="{}"
    )

    # ── Cách dùng ───────────────────────────────────────────────────
    # Ghim để nổi lên đầu danh sách, dành cho thứ dùng hằng ngày.
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Cờ do NGƯỜI DÙNG đặt, không phải máy suy ra. Web có gợi ý tự tích sẵn
    # dựa trên một vài từ khoá, nhưng người dùng luôn sửa được. Giữ một nguồn
    # sự thật trong DB thay vì để UI và backend đoán khác nhau.
    is_dangerous: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    use_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # ── Thùng rác ───────────────────────────────────────────────────
    # Xoá là xoá mềm, giống Task. Một câu lệnh mất nửa ngày mới dò ra thì
    # không nên bốc hơi vì bấm nhầm. Mọi truy vấn nghiệp vụ lọc
    # `deleted_at IS NULL` qua helper _alive() trong note_service.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # ── Nguồn gốc: khai báo sẵn cho integration ở Phase 2 ───────────
    source: Mapped[NoteSource] = mapped_column(
        enum_column(NoteSource, "note_source"),
        default=NoteSource.MANUAL,
        server_default=NoteSource.MANUAL.value,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(255), default=None)
    # Payload thô từ nguồn ngoài. Dữ liệu KHÔNG đáng tin, không nâng thành
    # instruction cho agent.
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

    # ── Quan hệ ─────────────────────────────────────────────────────
    project: Mapped[Project | None] = relationship(
        back_populates="notes", lazy="selectin"
    )

    __table_args__ = (
        # Partial index, cùng lý do như bên tasks: note đã xoá mềm không được
        # chiếm chỗ (source, external_id), nếu không lần sync lại từ Obsidian
        # sẽ bị chặn dù người dùng đã bỏ note đó vào thùng rác.
        Index(
            "uq_notes_source_external_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        # Note rỗng không có giá trị gì, và để lọt sẽ làm danh sách đầy rác.
        CheckConstraint("length(btrim(content)) > 0", name="content_not_blank"),
        CheckConstraint("use_count >= 0", name="use_count_non_negative"),
        Index("ix_notes_tags", "tags", postgresql_using="gin"),
        # Phủ đúng thứ tự sắp xếp mặc định của danh sách: ghim trước, rồi mới
        # xét lần sửa gần nhất.
        Index(
            "ix_notes_pinned_recent",
            "is_pinned",
            "updated_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Phục vụ view thùng rác và job dọn quá hạn
        Index(
            "ix_notes_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Note {self.id} {self.kind} {self.title[:40]!r}>"
