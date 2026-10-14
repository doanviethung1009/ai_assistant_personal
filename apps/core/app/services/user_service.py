"""Quản lý bản ghi `users`: mời, đồng bộ `ADMIN_EMAILS`, múi giờ, gán alias.

Quản trị qua HTTP (P3: `/admin/users/**`) sẽ thêm vào đây. P1 chỉ có phần CLI cần:
`invite`, `sync_admin_emails`, alias cho bootstrap/nhập file.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezones import normalize_timezone
from app.models.enums import AliasSource, UserRole, UserStatus
from app.models.user import User, UserAlias
from app.schemas.settings import MAX_NAME_LEN
from app.services.errors import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)

_EMAIL_MAX = 320
_CONTROL_OR_SPACE = re.compile(r"[\s\x00-\x1f\x7f]")


def normalize_email(raw: str) -> str:
    """lower(strip), KHÔNG bỏ dấu chấm hay `+tag` của Gmail: admin mời đúng địa chỉ người dùng
    đăng nhập. Khớp CHECK `ck_users_email_normalized`.

    Raises:
        ValidationError: không giống email (thiếu `@`, có khoảng trắng/ký tự điều khiển, quá dài).
    """
    email = (raw or "").strip().lower()
    if (
        not email
        or len(email) > _EMAIL_MAX
        or _CONTROL_OR_SPACE.search(email)
        or email.find("@") < 1
        or email.count("@") != 1
    ):
        raise ValidationError("Email không hợp lệ")
    return email


async def get_by_email(session: AsyncSession, email: str, *, lock: bool = False) -> User | None:
    stmt = select(User).where(User.email == normalize_email(email))
    if lock:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalars().unique().one_or_none()


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"Không tìm thấy user {user_id}")
    return user


async def invite(
    session: AsyncSession,
    email: str,
    role: UserRole = UserRole.MEMBER,
    *,
    name: str | None = None,
    invited_by: uuid.UUID | None = None,
) -> User:
    """Tạo user `invited` (chưa có google_sub). Người được mời đăng nhập Google để kích hoạt.

    Raises:
        ConflictError: email đã có (409, `email_exists`).
    """
    normalized = normalize_email(email)
    if await get_by_email(session, normalized) is not None:
        raise ConflictError("Email này đã được mời hoặc đã có tài khoản", code="email_exists")
    user = User(
        email=normalized,
        name=(name or "").strip()[:MAX_NAME_LEN] or None,
        role=role,
        status=UserStatus.INVITED,
        invited_by=invited_by,
    )
    session.add(user)
    await session.flush()
    return user


async def sync_admin_emails(session: AsyncSession, emails: Iterable[str]) -> int:
    """Upsert các email trong `ADMIN_EMAILS`: chưa có thì tạo `invited` role admin, có rồi thì
    ép `role = admin` (KHÔNG đổi status). Trả số dòng đã tạo hoặc đổi.

    Đây là đường "phá kính" khi lỡ khoá hết admin: chỉ cần sửa env rồi khởi động lại core.
    Email sai định dạng bị bỏ qua kèm cảnh báo (không để một dòng env hỏng chặn khởi động).
    """
    changed = 0
    for raw in emails:
        try:
            email = normalize_email(raw)
        except ValidationError:
            logger.warning("ADMIN_EMAILS có một mục không phải email, bỏ qua")
            continue
        user = await get_by_email(session, email, lock=True)
        if user is None:
            session.add(User(email=email, role=UserRole.ADMIN, status=UserStatus.INVITED))
            changed += 1
        elif user.role is not UserRole.ADMIN:
            user.role = UserRole.ADMIN
            changed += 1
    await session.flush()
    return changed


async def set_timezone(session: AsyncSession, user_id: uuid.UUID, name: str | None) -> User:
    """Đặt (tên IANA đã chuẩn hoá) hoặc xoá (None = về mặc định env) múi giờ của user."""
    user = await get_user(session, user_id)
    user.timezone = None if name is None else normalize_timezone(name)
    await session.flush()
    return user


async def add_aliases(
    session: AsyncSession, user_id: uuid.UUID, source: AliasSource, aliases: Iterable[str]
) -> tuple[list[str], list[str]]:
    """Thêm alias cho user; trả `(đã thêm, bị bỏ qua)`.

    Tên đã thuộc MỘT USER KHÁC thì bỏ qua (không cướp): alias quyết định quyền sửa task `work`
    và duy nhất theo `(source, alias)`. Tên đã thuộc chính user này cũng nằm ở "bỏ qua".
    """
    added: list[str] = []
    skipped: list[str] = []
    for alias in aliases:
        clean = alias.strip()
        if not clean:
            continue
        taken = await session.scalar(
            select(UserAlias.id).where(UserAlias.source == source, UserAlias.alias == clean)
        )
        if taken is not None:
            skipped.append(clean)
            continue
        session.add(UserAlias(user_id=user_id, source=source, alias=clean))
        added.append(clean)
    await session.flush()
    return added, skipped
