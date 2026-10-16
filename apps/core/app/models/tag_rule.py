"""Quy tắc đồng bộ tag: nhớ quyết định đổi tên/xoá tag để lần sync sau không làm tag cũ quay lại.

Toàn cục theo instance (chưa có khái niệm team). Spec: docs/specs/tag-rules.md mục 2.

BẤT BIẾN PHẲNG: không `target_tag` nào đồng thời là `source_tag` của rule khác. Service ghi giữ
bất biến này (tag_rule_service.record_change) để khi sync chỉ cần tra MỘT bước, áp hai lần ra
cùng kết quả và không có vòng. DB không tự bảo đảm được điều này.

Chuẩn hoá chữ thường chỉ ở service (normalize_tags), không CHECK `lower()` ở DB vì lower của
Postgres và Python khác nhau với một số ký tự Unicode.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TagRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tag_rules"

    # Tag từ nguồn ngoài cần đổi/chặn, đã chuẩn hoá.
    source_tag: Mapped[str] = mapped_column(String(64))
    # NULL = chặn (tag đã bị xoá); khác NULL = alias.
    target_tag: Mapped[str | None] = mapped_column(String(64), default=None)
    # SET NULL: xoá user không được kéo theo mất rule.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    __table_args__ = (
        # Một tag nguồn chỉ có một quyết định; rule xoá cứng nên không cần partial.
        UniqueConstraint("source_tag"),
        Index("ix_tag_rules_target_tag", "target_tag"),
        CheckConstraint(
            "length(source_tag) > 0 AND source_tag = btrim(source_tag)",
            name="source_not_blank",
        ),
        CheckConstraint(
            "target_tag IS NULL OR (length(target_tag) > 0 AND target_tag = btrim(target_tag))",
            name="target_not_blank",
        ),
        CheckConstraint("target_tag IS NULL OR target_tag <> source_tag", name="not_self"),
    )

    def __repr__(self) -> str:
        return f"<TagRule {self.source_tag} -> {self.target_tag}>"
