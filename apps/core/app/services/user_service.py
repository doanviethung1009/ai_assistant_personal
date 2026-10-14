"""Quản lý bản ghi `users`: mời, tài khoản nội bộ, trạng thái, role, xoá, alias.

ĐÂY LÀ NƠI DUY NHẤT đổi role/status/xoá user (API `/admin/*` và CLI cùng gọi vào đây) để quy
tắc "luôn còn ít nhất một admin hoạt động" và nhật ký audit giống nhau ở mọi đường vào.
`enforce=False` (CLI) bỏ qua `self_lockout`/`last_admin`/`env_admin`: người có shell là chủ
máy, nhưng CLI tự in cảnh báo khi còn 0 admin hoạt động.

Mật khẩu tạm trả về cho người gọi đúng một lần; module này không log và không audit nó.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import exists, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import passwords
from app.core.config import settings
from app.db.locks import constraint_name
from app.models.enums import AliasSource, AuditAction, AuthProvider, UserRole, UserStatus
from app.models.note import Note
from app.models.task import Task
from app.models.user import User, UserAlias
from app.schemas.settings import MAX_NAME_LEN
from app.services import audit_service
from app.services.clock import now_utc
from app.services.errors import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)

_EMAIL_MAX = 320
_CONTROL_OR_SPACE = re.compile(r"[\s\x00-\x1f\x7f]")
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
# Khoá advisory serialize mọi thao tác làm GIẢM số admin hoạt động.
_ADMIN_GUARD_LOCK = "builder:admin-guard"


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


def _clean_names(names: Iterable[str]) -> list[str]:
    """Chuẩn hoá như `add_aliases` (strip, bỏ rỗng) và bỏ trùng, giữ thứ tự."""
    return list(dict.fromkeys(n.strip() for n in names if n.strip()))


async def remove_aliases(
    session: AsyncSession, user_id: uuid.UUID, source: AliasSource, aliases: Iterable[str]
) -> list[str]:
    """Gỡ alias CỦA user này; trả danh sách đã gỡ (tên không có hoặc của người khác: bỏ qua).

    Gỡ alias là rút quyền sửa task `work` của user: caller phải khoá dòng user trước
    (`get_by_email(lock=True)`) để không đè với lệnh thêm/gỡ song song.
    """
    names = _clean_names(aliases)
    if not names:
        return []
    rows = (
        await session.scalars(
            select(UserAlias).where(
                UserAlias.user_id == user_id,
                UserAlias.source == source,
                UserAlias.alias.in_(names),
            )
        )
    ).all()
    for row in rows:
        await session.delete(row)
    await session.flush()
    return [row.alias for row in rows]


async def set_aliases(
    session: AsyncSession, user_id: uuid.UUID, source: AliasSource, aliases: Iterable[str]
) -> tuple[list[str], list[str], list[str]]:
    """Thay toàn bộ alias của user (theo `source`) bằng danh sách này.

    Trả `(đã thêm, đã gỡ, bị bỏ qua)`. Tên đang thuộc user khác bị bỏ qua (không cướp, như
    `add_aliases`). Gỡ trước, thêm sau trong cùng transaction của caller.
    """
    desired = _clean_names(aliases)
    current = set(
        (
            await session.scalars(
                select(UserAlias.alias).where(
                    UserAlias.user_id == user_id, UserAlias.source == source
                )
            )
        ).all()
    )
    removed = await remove_aliases(session, user_id, source, current - set(desired))
    added, skipped = await add_aliases(
        session, user_id, source, [n for n in desired if n not in current]
    )
    return added, removed, skipped


# ═══════════════════════════════════════════════════════════════════════
#  Tra cứu, đọc
# ═══════════════════════════════════════════════════════════════════════


def normalize_username(raw: str) -> str:
    """lower(strip) rồi kiểm đúng regex của CHECK `ck_users_username_format`.

    Raises:
        ValidationError: 422 `invalid_username`.
    """
    username = (raw or "").strip().lower()
    if not _USERNAME_RE.fullmatch(username):
        raise ValidationError(
            "Tên đăng nhập 3-64 ký tự: chữ thường, số, '.', '_', '-', bắt đầu bằng chữ hoặc số",
            code="invalid_username",
        )
    return username


async def get_by_username(
    session: AsyncSession, username: str, *, lock: bool = False
) -> User | None:
    stmt = select(User).where(User.username == normalize_username(username))
    if lock:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalars().unique().one_or_none()


async def find_local_by_identifier(session: AsyncSession, identifier: str) -> User | None:
    """Tài khoản `local` khớp identifier, khoá dòng (FOR UPDATE) để đếm sai không bị đè nhau.

    Có `@` thì so email, không thì so username. CHỈ trong `auth_provider='local'`: email của
    tài khoản Google không bao giờ đăng nhập được bằng mật khẩu. Identifier dị dạng trả None
    (không ném lỗi, để đường đăng nhập vẫn đi đúng một lần verify giả).
    """
    ident = (identifier or "").strip().lower()
    if not ident:
        return None
    if "@" in ident:
        column = User.email
        try:
            ident = normalize_email(ident)
        except ValidationError:
            return None
    else:
        column = User.username
    stmt = (
        select(User)
        .where(column == ident, User.auth_provider == AuthProvider.LOCAL)
        .with_for_update()
    )
    return (await session.execute(stmt)).scalars().unique().one_or_none()


async def get_user_fresh(session: AsyncSession, user_id: uuid.UUID) -> User:
    """Đọc lại user từ DB (kể cả cột do server sinh và alias), bỏ qua trạng thái đã cache trong
    session. Dùng sau khi ghi để dựng response; không khoá dòng."""
    stmt = select(User).where(User.id == user_id).execution_options(populate_existing=True)
    user = (await session.execute(stmt)).scalars().unique().one_or_none()
    if user is None:
        raise NotFoundError(f"Không tìm thấy user {user_id}")
    return user


async def _load_locked(session: AsyncSession, user_id: uuid.UUID) -> User:
    """Khoá dòng user và đọc trạng thái mới nhất (kể cả sau khi chờ khoá của người khác)."""
    stmt = (
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user = (await session.execute(stmt)).scalars().unique().one_or_none()
    if user is None:
        raise NotFoundError(f"Không tìm thấy user {user_id}")
    return user


async def list_users(
    session: AsyncSession,
    *,
    q: str | None = None,
    role: UserRole | None = None,
    status: UserStatus | None = None,
    auth_provider: AuthProvider | None = None,
    locked: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[User], int]:
    """Trang người dùng mới tạo trước. Alias nạp `selectin` (không N+1). `q` tìm không phân
    biệt hoa thường theo email/username/tên, đã escape `%` và `_`."""
    conditions = []
    if q and q.strip():
        needle = q.strip()
        conditions.append(
            User.email.icontains(needle, autoescape=True)
            | User.username.icontains(needle, autoescape=True)
            | User.name.icontains(needle, autoescape=True)
        )
    if role is not None:
        conditions.append(User.role == role)
    if status is not None:
        conditions.append(User.status == status)
    if auth_provider is not None:
        conditions.append(User.auth_provider == auth_provider)
    if locked is not None:
        now = now_utc()
        if locked:
            conditions.append(User.locked_until > now)
        else:
            conditions.append(User.locked_until.is_(None) | (User.locked_until <= now))
    total = await session.scalar(select(func.count()).select_from(User).where(*conditions))
    rows = await session.execute(
        select(User)
        .where(*conditions)
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars().unique().all()), int(total or 0)


async def count_active_admins(session: AsyncSession, *, excluding: uuid.UUID | None = None) -> int:
    """Số admin hoạt động (`role=admin AND status=active`). Khoá tạm và ép đổi mật khẩu vẫn
    tính là hoạt động."""
    stmt = (
        select(func.count())
        .select_from(User)
        .where(User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE)
    )
    if excluding is not None:
        stmt = stmt.where(User.id != excluding)
    return int(await session.scalar(stmt) or 0)


# ═══════════════════════════════════════════════════════════════════════
#  Quy tắc khoá admin
# ═══════════════════════════════════════════════════════════════════════


async def _take_admin_guard(session: AsyncSession) -> None:
    """Xếp hàng mọi thao tác có thể làm giảm số admin hoạt động.

    Phải lấy TRƯỚC khi khoá dòng user: nếu không, hai admin hạ quyền nhau cùng lúc đều thấy
    "còn một admin khác" và cùng thành công, để lại hệ thống không còn admin nào.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": _ADMIN_GUARD_LOCK}
    )


async def _guard_demotion(
    session: AsyncSession,
    user: User,
    *,
    actor_user_id: uuid.UUID | None,
    enforce: bool,
    demoting: bool,
) -> None:
    """409 `self_lockout` | `env_admin` | `last_admin` khi thao tác làm user mất tư cách admin
    hoạt động (hạ role, khoá, xoá). Thứ tự kiểm cố định: self_lockout, env_admin, last_admin."""
    if not enforce or not demoting:
        return
    if actor_user_id is not None and actor_user_id == user.id:
        raise ConflictError(
            "Bạn không thể tự hạ quyền, khoá hay xoá chính mình", code="self_lockout"
        )
    if user.email in settings.admin_emails:
        raise ConflictError(
            "Tài khoản này thuộc ADMIN_EMAILS, đổi trong cấu hình môi trường", code="env_admin"
        )
    is_active_admin = user.role is UserRole.ADMIN and user.status is UserStatus.ACTIVE
    if is_active_admin and await count_active_admins(session, excluding=user.id) == 0:
        raise ConflictError("Phải còn ít nhất một quản trị viên", code="last_admin")


async def _flush_unique(session: AsyncSession) -> None:
    """Flush; đổi vi phạm UNIQUE của email/username/alias (đua nhau) thành 409 có mã."""
    try:
        await session.flush()
    except IntegrityError as exc:
        name = constraint_name(exc)
        if name == "uq_users_email":
            raise ConflictError("Email này đã được dùng", code="email_exists") from exc
        if name == "uq_users_username":
            raise ConflictError("Tên đăng nhập đã được dùng", code="username_exists") from exc
        if name == "uq_user_aliases_source_alias":
            raise ConflictError("Alias đã thuộc user khác", code="alias_taken") from exc
        raise


def _audit_user(
    session: AsyncSession,
    action: AuditAction,
    user: User,
    *,
    actor_user_id: uuid.UUID | None,
    details: dict[str, Any],
) -> None:
    audit_service.record(
        session,
        action,
        actor_user_id=actor_user_id,
        target_type="user",
        target_id=user.id,
        details=details,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Tạo, sửa, xoá
# ═══════════════════════════════════════════════════════════════════════


async def invite_user(
    session: AsyncSession,
    email: str,
    role: UserRole = UserRole.MEMBER,
    *,
    name: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    via: str = "api",
) -> User:
    """`invite` kèm audit `user_invited`. CLI có audit riêng nên vẫn gọi `invite` trực tiếp."""
    user = await invite(session, email, role, name=name, invited_by=actor_user_id)
    _audit_user(
        session,
        AuditAction.USER_INVITED,
        user,
        actor_user_id=actor_user_id,
        details={"role": user.role.value, "via": via},
    )
    return user


async def create_local_user(
    session: AsyncSession,
    *,
    username: str,
    email: str,
    name: str | None = None,
    role: UserRole = UserRole.MEMBER,
    actor_user_id: uuid.UUID | None = None,
    via: str = "api",
) -> tuple[User, str]:
    """Tạo tài khoản nội bộ `active` với mật khẩu tạm; trả `(user, mật_khẩu_tạm)`.

    Mật khẩu tạm chỉ được trả cho người gọi một lần, trong response `no-store` hoặc stdout của
    CLI; ở DB chỉ có hash. `must_change_password=true` nên mật khẩu này chỉ đủ để đổi mật khẩu.

    Raises:
        ConflictError: 409 `email_exists` | `username_exists`.
        ValidationError: 422 email/username dị dạng.
    """
    clean_username = normalize_username(username)
    clean_email = normalize_email(email)
    if await get_by_email(session, clean_email) is not None:
        raise ConflictError("Email này đã được dùng", code="email_exists")
    if await get_by_username(session, clean_username) is not None:
        raise ConflictError("Tên đăng nhập đã được dùng", code="username_exists")

    temporary = passwords.generate_temporary_password()
    now = now_utc()
    user = User(
        auth_provider=AuthProvider.LOCAL,
        username=clean_username,
        email=clean_email,
        name=(name or "").strip()[:MAX_NAME_LEN] or None,
        role=role,
        status=UserStatus.ACTIVE,
        password_hash=await passwords.hash_password(temporary),
        must_change_password=True,
        password_changed_at=now,
        invited_by=actor_user_id,
    )
    session.add(user)
    await _flush_unique(session)
    _audit_user(
        session,
        AuditAction.USER_CREATED,
        user,
        actor_user_id=actor_user_id,
        details={"provider": "local", "role": role.value, "via": via},
    )
    return user, temporary


async def update_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    changes: dict[str, Any],
    *,
    actor_user_id: uuid.UUID | None = None,
    via: str = "api",
    enforce: bool = True,
) -> User:
    """Đổi role / status / tên / email / username trong MỘT transaction, mỗi loại một dòng audit.

    `changes` chỉ chứa khoá có trong `{"role", "status", "name", "email", "username"}`; `status`
    là "active" | "disabled". Không có thay đổi thật thì không ghi gì.

    Quy tắc trạng thái: `disabled` tăng `session_version` (mọi phiên chết ngay); `active` cho
    tài khoản Google chưa gắn `google_sub` được lưu thành `invited` (chưa có đường vào nào khác).

    Raises:
        ConflictError: `self_lockout`, `env_admin`, `last_admin`, `not_local_account`,
            `email_exists`, `username_exists`.
        NotFoundError: không có user.
    """
    if enforce:
        await _take_admin_guard(session)
    user = await _load_locked(session, user_id)
    is_local = user.auth_provider is AuthProvider.LOCAL

    if ("email" in changes or "username" in changes) and not is_local:
        raise ConflictError(
            "Chỉ sửa được email/tên đăng nhập của tài khoản nội bộ", code="not_local_account"
        )

    new_role: UserRole = changes.get("role", user.role)
    new_status = user.status
    if "status" in changes:
        if changes["status"] == UserStatus.DISABLED.value:
            new_status = UserStatus.DISABLED
        elif is_local or user.google_sub:
            new_status = UserStatus.ACTIVE
        else:
            new_status = UserStatus.INVITED

    role_drop = user.role is UserRole.ADMIN and new_role is not UserRole.ADMIN
    disabling = new_status is UserStatus.DISABLED and user.status is not UserStatus.DISABLED
    await _guard_demotion(
        session, user, actor_user_id=actor_user_id, enforce=enforce, demoting=role_drop or disabling
    )

    if new_role is not user.role:
        old_role, user.role = user.role, new_role
        _audit_user(
            session,
            AuditAction.USER_ROLE_CHANGED,
            user,
            actor_user_id=actor_user_id,
            details={"from": old_role.value, "to": new_role.value, "via": via},
        )
    if new_status is not user.status:
        old_status, user.status = user.status, new_status
        if new_status is UserStatus.DISABLED:
            # Token đã cấp chết ngay, kể cả khi sau này mở khoá lại.
            user.session_version += 1
        _audit_user(
            session,
            AuditAction.USER_STATUS_CHANGED,
            user,
            actor_user_id=actor_user_id,
            details={"from": old_status.value, "to": new_status.value, "via": via},
        )

    fields: list[str] = []
    if "name" in changes:
        name = (changes["name"] or "").strip()[:MAX_NAME_LEN] or None
        if name != user.name:
            user.name = name
            fields.append("name")
    if "email" in changes:
        email = normalize_email(changes["email"])
        if email != user.email:
            if await get_by_email(session, email) is not None:
                raise ConflictError("Email này đã được dùng", code="email_exists")
            user.email = email
            fields.append("email")
    if "username" in changes:
        username = normalize_username(changes["username"])
        if username != user.username:
            if await get_by_username(session, username) is not None:
                raise ConflictError("Tên đăng nhập đã được dùng", code="username_exists")
            user.username = username
            fields.append("username")
    if fields:
        # Chỉ ghi TÊN trường, không ghi giá trị cũ/mới của email (PII).
        _audit_user(
            session,
            AuditAction.USER_UPDATED,
            user,
            actor_user_id=actor_user_id,
            details={"fields": fields, "via": via},
        )
    await _flush_unique(session)
    return user


async def revoke_sessions(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    via: str = "api",
) -> User:
    """Đăng xuất mọi thiết bị (`session_version + 1`). Tự thu hồi phiên của mình được phép."""
    user = await _load_locked(session, user_id)
    user.session_version += 1
    _audit_user(
        session,
        AuditAction.SESSIONS_REVOKED,
        user,
        actor_user_id=actor_user_id,
        details={"via": via},
    )
    await session.flush()
    return user


async def unlock(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    via: str = "api",
) -> User:
    """Mở khoá tạm: xoá bộ đếm sai và `locked_until`. Không đổi `session_version`."""
    user = await _load_locked(session, user_id)
    user.failed_login_count = 0
    user.locked_until = None
    _audit_user(
        session, AuditAction.USER_UNLOCKED, user, actor_user_id=actor_user_id, details={"via": via}
    )
    await session.flush()
    return user


async def reset_password(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    via: str = "api",
) -> tuple[User, str]:
    """Admin đặt lại mật khẩu: sinh mật khẩu tạm mới, ép đổi, thu hồi mọi phiên. Trả
    `(user, mật_khẩu_tạm)`; mật khẩu tạm chỉ hiện một lần.

    Cũng xoá khoá tạm: admin vừa cấp mật khẩu mới thì người dùng phải thử được ngay.

    Raises:
        ConflictError: 409 `not_local_account` (tài khoản Google), `self_action` (tự đặt lại
            qua API: dùng `/me/password`).
    """
    user = await _load_locked(session, user_id)
    if user.auth_provider is not AuthProvider.LOCAL:
        raise ConflictError("Chỉ đặt lại được mật khẩu tài khoản nội bộ", code="not_local_account")
    if actor_user_id is not None and actor_user_id == user.id:
        raise ConflictError("Hãy tự đổi mật khẩu ở trang cá nhân", code="self_action")
    temporary = passwords.generate_temporary_password()
    user.password_hash = await passwords.hash_password(temporary)
    user.must_change_password = True
    user.password_changed_at = now_utc()
    user.failed_login_count = 0
    user.locked_until = None
    user.session_version += 1
    _audit_user(
        session, AuditAction.PASSWORD_RESET, user, actor_user_id=actor_user_id, details={"via": via}
    )
    await session.flush()
    return user, temporary


async def change_own_password(
    session: AsyncSession,
    user_id: uuid.UUID,
    current_password: str,
    new_password: str,
    *,
    client_ip: str | None = None,
) -> int:
    """Tự đổi mật khẩu; trả `session_version` mới. Mọi thiết bị khác bị đăng xuất.

    Lỗi mật khẩu hiện tại là 422, KHÔNG phải 401: web coi 401 là hết phiên và đá ra đăng nhập.

    Raises:
        ConflictError: 409 `not_local_account`.
        ValidationError: 422 `current_password_invalid` | `weak_password`.
    """
    user = await _load_locked(session, user_id)
    if user.auth_provider is not AuthProvider.LOCAL:
        raise ConflictError("Tài khoản Google đổi mật khẩu ở Google", code="not_local_account")
    result = await passwords.verify_password(user.password_hash, current_password)
    if not result.ok:
        raise ValidationError("Mật khẩu hiện tại không đúng", code="current_password_invalid")
    reasons = passwords.policy_violations(
        new_password,
        username=user.username,
        email=user.email,
        current_password=current_password,
    )
    if reasons:
        raise ValidationError("Mật khẩu mới không đạt: " + "; ".join(reasons), code="weak_password")
    user.password_hash = await passwords.hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = now_utc()
    user.failed_login_count = 0
    user.locked_until = None
    user.session_version += 1
    audit_service.record(
        session,
        AuditAction.PASSWORD_CHANGED,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        client_ip=client_ip,
    )
    await session.flush()
    return user.session_version


async def delete_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    via: str = "api",
    enforce: bool = True,
) -> None:
    """Xoá cứng user. Không có xoá mềm: "khoá" là cách chính, xoá chỉ cho tài khoản chưa có dữ liệu.

    Raises:
        ConflictError: `has_data` (còn task/note có `owner_id` là user này, kể cả trong thùng
            rác), `self_lockout`, `env_admin`, `last_admin`.
    """
    if enforce:
        await _take_admin_guard(session)
    user = await _load_locked(session, user_id)
    await _guard_demotion(
        session, user, actor_user_id=actor_user_id, enforce=enforce, demoting=True
    )
    owns_task = await session.scalar(select(exists().where(Task.owner_id == user.id)))
    owns_note = await session.scalar(select(exists().where(Note.owner_id == user.id)))
    if owns_task or owns_note:
        raise ConflictError(
            "User còn task hoặc note (kể cả trong thùng rác): hãy khoá thay vì xoá",
            code="has_data",
        )
    # Ghi TRƯỚC khi xoá; audit_log không có FK tới target_id nên dòng này còn mãi.
    _audit_user(
        session,
        AuditAction.USER_DELETED,
        user,
        actor_user_id=actor_user_id,
        details={"provider": user.auth_provider.value, "role": user.role.value, "via": via},
    )
    await session.delete(user)
    await session.flush()


async def replace_aliases(
    session: AsyncSession,
    user_id: uuid.UUID,
    names: Iterable[str],
    *,
    actor_user_id: uuid.UUID | None = None,
    via: str = "api",
) -> User:
    """Thay toàn bộ alias Jira của user. Khác `set_aliases`: tên đang thuộc user khác là LỖI
    409 `alias_taken` (kèm email người giữ), không lặng lẽ bỏ qua, vì admin cần biết."""
    user = await _load_locked(session, user_id)
    desired = _clean_names(names)
    if desired:
        clash = (
            await session.execute(
                select(UserAlias.alias, User.email)
                .join(User, User.id == UserAlias.user_id)
                .where(
                    UserAlias.source == AliasSource.JIRA,
                    UserAlias.alias.in_(desired),
                    UserAlias.user_id != user.id,
                )
            )
        ).first()
        if clash is not None:
            raise ConflictError(f"Alias {clash[0]!r} đang thuộc {clash[1]}", code="alias_taken")
    added, removed, _skipped = await set_aliases(session, user.id, AliasSource.JIRA, desired)
    if added or removed:
        _audit_user(
            session,
            AuditAction.USER_ALIASES_CHANGED,
            user,
            actor_user_id=actor_user_id,
            details={
                "source": AliasSource.JIRA.value,
                "added": len(added),
                "removed": len(removed),
                "via": via,
            },
        )
    await _flush_unique(session)
    return user
