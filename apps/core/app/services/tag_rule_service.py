"""Quy tắc đồng bộ tag (docs/specs/tag-rules.md).

Vì sao có: T6 cho đổi tên/xoá tag hàng loạt, nhưng `task_sync_service` gộp (union) tag hiện có
với tag từ nguồn nên lần sync kế tiếp tag cũ quay lại. Bảng `tag_rules` nhớ quyết định đó:
`source_tag -> target_tag` (alias) hoặc `source_tag -> NULL` (chặn), và được áp lên tag ĐẾN TỪ
NGUỒN NGOÀI (Jira, Excel, URL). Tag đang có trên task và tag User tự gõ không bị đụng tới.

Bất biến phẳng (không target nào là source của rule khác) do `record_change` giữ khi ghi, để
`apply_rules` chỉ tra một bước, idempotent và không có vòng.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.models.enums import AuditAction
from app.models.tag_rule import TagRule
from app.models.user import User
from app.services import audit_service
from app.services.errors import NotFoundError

# source_tag -> target_tag (None = chặn).
TagRules = Mapping[str, str | None]


def apply_rules(tags: Sequence[str], rules: TagRules) -> list[str]:
    """Đổi/bỏ tag NGUỒN theo rule; giữ thứ tự, bỏ trùng sau khi đổi. Không chạm DB.

    Chỉ tra một bước (bất biến phẳng), nên áp hai lần ra cùng kết quả: cho phép áp ở cả
    `jira_mapping` (trước khi cắt MAX_TAGS) lẫn `upsert_batch` (phủ Excel/URL).
    """
    if not rules:
        return list(dict.fromkeys(tags))
    out: dict[str, None] = {}
    for tag in tags:
        if tag in rules:
            target = rules[tag]
            if target is None:
                continue
            tag = target
        out[tag] = None
    return list(out)


async def load_rules(session: AsyncSession) -> dict[str, str | None]:
    """Một SELECT toàn bảng: mỗi lần đổi tên/xoá thêm tối đa một dòng nên bảng nhỏ."""
    rows = await session.execute(select(TagRule.source_tag, TagRule.target_tag))
    return dict(rows.tuples().all())


async def record_change(
    session: AsyncSession, user: CurrentUser, old: str, new: str | None
) -> TagRule:
    """Ghi rule sau khi đổi tên (`new` là tag mới) hoặc xoá (`new=None`) chạm task work.

    Thứ tự (a) -> (b) -> (c) là điều kiện của bất biến phẳng; người gọi phải đã giữ advisory
    lock của nhập để không xen với một lô sync đang đọc rule.
    """
    revived: list[str] = []
    if new is not None:
        # (a) User vừa chủ động chọn `new` làm tên tag: rule cũ đổi/chặn `new` hết hiệu lực,
        # nếu không sync sau sẽ đổi tag Jira `new` đi trong khi task đang mang chính nó.
        result = await session.execute(
            delete(TagRule).where(TagRule.source_tag == new).returning(TagRule.source_tag)
        )
        revived = list(result.scalars())
    # (b) Làm phẳng chuỗi: x -> old nay thành x -> new (hoặc x bị chặn nếu xoá old).
    rewired = await session.execute(
        update(TagRule)
        .where(TagRule.target_tag == old)
        .values(target_tag=new, updated_at=func.now())
    )
    # (c) Rule chính; upsert vì đổi tên/xoá cùng một tag nguồn nhiều lần chỉ giữ quyết định cuối.
    stmt = pg_insert(TagRule).values(source_tag=old, target_tag=new, created_by_user_id=user.id)
    stmt = stmt.on_conflict_do_update(
        index_elements=[TagRule.source_tag],
        set_={
            "target_tag": stmt.excluded.target_tag,
            "created_by_user_id": stmt.excluded.created_by_user_id,
            "updated_at": func.now(),
        },
    ).returning(TagRule.id)
    rule_id = (await session.execute(stmt)).scalar_one()
    # populate_existing: dòng có thể đã nằm trong identity map với giá trị cũ.
    rule = (
        await session.execute(
            select(TagRule).where(TagRule.id == rule_id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    audit_service.record(
        session,
        AuditAction.TAG_RULE_SET,
        actor_user_id=user.id,
        target_type="tag_rule",
        target_id=rule.id,
        details={
            "source_tag": old,
            "target_tag": new,
            "revived": revived,
            "rewired": rewired.rowcount,
        },
    )
    return rule


async def list_rules(
    session: AsyncSession, *, limit: int, offset: int
) -> tuple[list[tuple[TagRule, str | None]], int]:
    """Trang rule theo source_tag, kèm tên người tạo (LEFT JOIN, không trả email)."""
    total = (await session.execute(select(func.count()).select_from(TagRule))).scalar_one()
    rows = await session.execute(
        select(TagRule, User.name)
        .outerjoin(User, User.id == TagRule.created_by_user_id)
        .order_by(TagRule.source_tag)
        .limit(limit)
        .offset(offset)
    )
    return [(rule, name) for rule, name in rows.all()], total


async def delete_rule(session: AsyncSession, user: CurrentUser, rule_id: uuid.UUID) -> None:
    """Gỡ rule (xoá cứng). Không lấy advisory lock: gỡ chỉ làm tag quay lại, đua với sync vô hại."""
    rule = await session.get(TagRule, rule_id)
    if rule is None:
        raise NotFoundError("không có quy tắc tag này")
    details = {"source_tag": rule.source_tag, "target_tag": rule.target_tag}
    await session.delete(rule)
    audit_service.record(
        session,
        AuditAction.TAG_RULE_DELETED,
        actor_user_id=user.id,
        target_type="tag_rule",
        target_id=rule_id,
        details=details,
    )
