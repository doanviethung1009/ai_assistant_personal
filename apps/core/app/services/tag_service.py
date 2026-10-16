"""Quản lý tag toàn cục: thống kê, đổi tên, xoá.

Tag không có bảng riêng, chỉ là cột `ARRAY` trên `tasks` và `notes`. Vì vậy mọi thao tác ở đây là
một câu SQL trên mảng, không cần migration.

PHẠM VI (đi qua `access`, không tự viết điều kiện owner/scope):
- Thống kê: task nhìn thấy được + note của chính user.
- Đổi tên/xoá: note của chính user; task `personal` của chính user; task `work` chỉ khi có
  `task:write_any_work`. Cố ý chặt hơn `access.task_permissions`: member không sửa tag hàng loạt
  trên task work dù là người tạo/được giao. Mỗi task bị đổi ghi một `TaskEvent` UPDATED.

Tag có nguồn từ Jira/Excel sẽ quay lại ở lần sync kế tiếp vì `task_sync_service` gộp (union)
tag cũ với tag nhận về. Để chặn điều đó, lệnh đổi tên/xoá chạm ít nhất một task `work` ghi một
quy tắc (`tag_rule_service.record_change`) mà sync áp lên tag nguồn (docs/specs/tag-rules.md).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, and_, case, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import String

from app.core.auth import CurrentUser
from app.core.permissions import Permission
from app.db import locks
from app.models.enums import TaskEventType, TaskScope
from app.models.note import Note
from app.models.task import Task, TaskEvent
from app.schemas.common import normalize_tags
from app.schemas.tag import TagChangeResponse, TagRuleRead, TagStat
from app.services import access, tag_rule_service
from app.services.errors import ConflictError, NotFoundError, ValidationError


def normalize_name(name: str) -> str:
    tags = normalize_tags([name])
    if not tags:
        raise ValidationError("tên tag không hợp lệ")
    return tags[0]


def _writable_task_clause(user: CurrentUser) -> ColumnElement[bool]:
    mine = and_(Task.scope == TaskScope.PERSONAL, Task.owner_id == user.id)
    if user.has(Permission.TASK_WRITE_ANY_WORK):
        return access.task_visible_clause(user)
    return mine


async def list_stats(session: AsyncSession, user: CurrentUser) -> list[TagStat]:
    t_tag = func.unnest(Task.tags).column_valued("tag")
    task_rows = (
        select(t_tag.label("name"), func.count(func.distinct(Task.id)).label("n"))
        .select_from(Task)
        .where(Task.deleted_at.is_(None), access.task_visible_clause(user))
        .group_by(t_tag)
    )
    n_tag = func.unnest(Note.tags).column_valued("tag")
    note_rows = (
        select(n_tag.label("name"), func.count(func.distinct(Note.id)).label("n"))
        .select_from(Note)
        .where(Note.deleted_at.is_(None), access.note_visible_clause(user))
        .group_by(n_tag)
    )
    counts: dict[str, list[int]] = {}
    for name, n in (await session.execute(task_rows)).all():
        counts.setdefault(name, [0, 0])[0] = n
    for name, n in (await session.execute(note_rows)).all():
        counts.setdefault(name, [0, 0])[1] = n
    return [TagStat(name=k, task_count=v[0], note_count=v[1]) for k, v in sorted(counts.items())]


def _variants(name: str, canonical: str) -> list[str]:
    """Các cách viết của tag có thể đang nằm trong DB: tên thô (đã strip) và tên chuẩn hoá.

    `/tags/stats` trả đúng giá trị đang lưu; dữ liệu cũ nhập trước khi có `normalize_tags` có thể
    là "Foo" hay "Legacy Tag". Chỉ so khớp tên chuẩn hoá thì tag đó hiện ở thống kê nhưng
    đổi tên/xoá trả 404.
    """
    return list(dict.fromkeys([name.strip(), canonical]))


async def rename(
    session: AsyncSession, user: CurrentUser, old_name: str, new_name: str
) -> TagChangeResponse:
    old = normalize_name(old_name)
    new = normalize_name(new_name)
    variants = _variants(old_name, old)
    # Tên mới chỉ "trùng" khi không còn biến thể nào khác nó để đổi. Đổi "Foo" -> "foo" là hợp
    # lệ (chuẩn hoá lại dữ liệu cũ).
    if all(v == new for v in variants):
        raise ConflictError("tên mới trùng tên cũ")
    return await _apply(session, user, old, new, variants)


async def delete(session: AsyncSession, user: CurrentUser, name: str) -> TagChangeResponse:
    canonical = normalize_name(name)
    return await _apply(session, user, canonical, None, _variants(name, canonical))


async def _apply(
    session: AsyncSession,
    user: CurrentUser,
    old: str,
    new: str | None,
    variants: list[str],
) -> TagChangeResponse:
    """Bọc `_apply_locked` để lỗi hết hạn chờ khoá thành 409.

    `take_import_write_lock` đặt `lock_timeout` cho CẢ transaction, nên các UPDATE tasks/notes
    phía sau cũng có thể ném 55P03 khi dòng đang bị request khác giữ. Không bọc thì thành 500
    (trước T7 đổi tên tag chỉ chờ, không có timeout).
    """
    async with locks.conflict_on_lock_timeout(
        session, "Tag đang được sửa ở nơi khác, hãy thử lại sau."
    ):
        return await _apply_locked(session, user, old, new, variants)


def _replacement(
    tags_col: Any, variants: list[str], new: str | None
) -> ColumnElement[Any]:
    """Biểu thức SQL tính mảng tag mới: bỏ (new=None) hoặc đổi mọi biến thể sang `new`."""
    if new is None:
        expr = tags_col
        for v in variants:
            expr = func.array_remove(expr, literal(v, String))
        return expr
    # Biến thể trùng đúng `new` không cần đổi (đã là tên đích).
    todo = [v for v in variants if v != new]
    removed = tags_col
    replaced = tags_col
    for v in todo:
        removed = func.array_remove(removed, literal(v, String))
        replaced = func.array_replace(replaced, literal(v, String), literal(new, String))
    branches = [(tags_col.contains([new]), removed)]
    if len(todo) == 2:
        # Dòng mang cả hai biến thể: đổi cái đầu, bỏ cái sau, nếu không `new` bị lặp hai lần.
        both = and_(tags_col.contains([todo[0]]), tags_col.contains([todo[1]]))
        branches.append(
            (
                both,
                func.array_remove(
                    func.array_replace(tags_col, literal(todo[0], String), literal(new, String)),
                    literal(todo[1], String),
                ),
            )
        )
    return case(*branches, else_=replaced)


async def _apply_locked(
    session: AsyncSession,
    user: CurrentUser,
    old: str,
    new: str | None,
    variants: list[str],
) -> TagChangeResponse:
    """`new=None` nghĩa là xoá. Đổi tên sang tag đã có trên cùng dòng thì chỉ bỏ tag cũ (gộp).

    `old` là tên chuẩn hoá (dùng làm `source_tag` của rule, giữ bất biến phẳng); `variants` là các
    cách viết cần khớp trong DB. Người có `task:write_any_work` lấy advisory lock của nhập TRƯỚC
    các câu UPDATE: tuần tự hoá với lô sync (lô không đọc rule cũ rồi ghi đè sau khi đổi tên xong)
    và giữ cùng thứ tự khoá (advisory -> dòng) với `upsert_batch` để không deadlock. Member không
    chạm task work nên không cần khoá.
    """
    can_write_work = user.has(Permission.TASK_WRITE_ANY_WORK)
    if can_write_work:
        await locks.take_import_write_lock(session)
    counts: list[int] = []
    work_changed = 0
    for model, scope_clause in (
        (Task, _writable_task_clause(user)),
        (Note, access.note_visible_clause(user)),
    ):
        # Khớp dòng mang BẤT KỲ biến thể nào, trừ khi biến thể đó chính là tên đích (không phải
        # đổi gì); nếu không, dòng chỉ có `new` bị đếm như đã sửa.
        match = [v for v in variants if v != new]
        stmt = (
            update(model)
            .where(
                model.deleted_at.is_(None),
                scope_clause,
                or_(*[model.tags.contains([v]) for v in match]),
            )
            .values(tags=_replacement(model.tags, variants, new))
        )
        if model is Task:
            # Cần scope để biết có chạm task work không (chỉ khi đó mới ghi rule).
            rows = (await session.execute(stmt.returning(Task.id, Task.scope))).all()
            ids = [row[0] for row in rows]
            work_changed = sum(1 for row in rows if row[1] is TaskScope.WORK)
            # Sửa hàng loạt task cả team phải để lại dấu vết như update_task (audit log).
            for task_id in ids:
                session.add(
                    TaskEvent(
                        task_id=task_id,
                        event_type=TaskEventType.UPDATED,
                        actor=user.actor,
                        actor_user_id=user.id,
                        payload={"tags": {"from": old, "to": new}},
                    )
                )
        else:
            ids = list((await session.execute(stmt.returning(model.id))).scalars())
        counts.append(len(ids))
    if not any(counts):
        raise NotFoundError("không có task hoặc note nào bạn sửa được đang dùng tag này")
    rule_read: TagRuleRead | None = None
    # old == new (chuẩn hoá lại "Foo" -> "foo") không phải quyết định đổi tag nguồn: ghi rule
    # foo -> foo sẽ là vòng tự trỏ, phá bất biến phẳng.
    if work_changed and can_write_work and old != new:
        rule = await tag_rule_service.record_change(session, user, old, new)
        rule_read = TagRuleRead(
            id=rule.id,
            source_tag=rule.source_tag,
            target_tag=rule.target_tag,
            created_by_user_id=rule.created_by_user_id,
            created_by_name=user.name,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )
    return TagChangeResponse(tasks=counts[0], notes=counts[1], rule=rule_read)
