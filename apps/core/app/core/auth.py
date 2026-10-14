"""Xác thực người dùng ở core: kiểm JWT do web ký, rồi đọc `users` theo khoá chính.

Mô hình: web xác thực với Google (Auth.js), core QUYẾT ĐỊNH quyền. Mỗi request web gửi
`X-API-Key` (chứng minh đến từ web) cộng `Authorization: Bearer <JWT 60 giây>` (người dùng nào).
Chữ ký JWT chỉ chứng minh "web nói đây là user X"; việc user X còn được dùng hay không do DB
quyết định MỖI request (không cache), nên khoá tài khoản hay thu hồi phiên có hiệu lực ngay và
không phải lo vô hiệu cache giữa nhiều worker.

KHÔNG log token, header Authorization hay email ở đây: chỉ `user_id` nếu cần.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.permissions import Permission, permissions_for
from app.db.session import SessionFactory
from app.models.enums import AliasSource, UserRole, UserStatus
from app.models.user import User
from app.services.errors import ForbiddenError, UnauthorizedError

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "builder-web"
JWT_AUDIENCE = "builder-core"
# Lệch đồng hồ giữa web và core.
JWT_LEEWAY_SECONDS = 10
# Token sống tối đa 60 giây; chấp nhận tới 120 để dư chỗ cho lệch giờ, dài hơn thì từ chối
# (web bị lỗi hoặc ai đó ký token sống lâu).
JWT_MAX_LIFETIME_SECONDS = 120
JWT_DEFAULT_TTL_SECONDS = 60

_REQUIRED_CLAIMS = ["exp", "iat", "sub", "sv", "jti", "iss", "aud"]

bearer_scheme = HTTPBearer(
    auto_error=False,
    description=(
        "JWT HS256 60 giây do web ký (sub = user id, sv = session_version). "
        "Dev/CLI: `python -m app.cli.auth token --email <email>`."
    ),
)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """Người đang gọi API, đọc từ DB trong chính request này (không cache).

    Không có `__repr__` tuỳ biến nhưng cũng không bao giờ được log nguyên object: có email.
    """

    id: uuid.UUID
    email: str
    name: str | None
    role: UserRole
    timezone: str | None
    # Alias nguồn Jira của user, so khớp chính xác (phân biệt hoa thường) với Task.assignee.
    aliases: frozenset[str]

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.role)

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions

    @property
    def actor(self) -> str:
        """Giá trị ghi vào `task_events.actor` cho hành động của user này."""
        return f"user:{self.id}"


def _secret() -> str:
    return settings.core_jwt_secret.get_secret_value()


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: uuid.UUID
    session_version: int


def mint_token(
    user_id: uuid.UUID, session_version: int, *, ttl: int = JWT_DEFAULT_TTL_SECONDS
) -> str:
    """Ký một JWT như web làm. Dùng cho CLI `token` (dev, smoke test) và test.

    Ai chạy được lệnh này (vào được container core) vốn đã có toàn quyền trên máy đó, nên
    không thêm lớp bảo vệ riêng.
    """
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": str(user_id),
        "sv": session_version,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> TokenClaims:
    """Kiểm chữ ký và claim. Mọi lỗi đều là 401 `token_invalid` với thông báo chung.

    Ghim `algorithms=["HS256"]`: không tin header `alg` của token (chặn `alg=none` và nhầm
    thuật toán). Không lộ lý do chi tiết cho client.
    """
    try:
        data = jwt.decode(
            token,
            _secret(),
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            leeway=JWT_LEEWAY_SECONDS,
            options={"require": _REQUIRED_CLAIMS},
        )
        exp, iat = int(data["exp"]), int(data["iat"])
        if exp - iat > JWT_MAX_LIFETIME_SECONDS:
            raise ValueError("token sống quá lâu")
        sv = data["sv"]
        if isinstance(sv, bool) or not isinstance(sv, int):
            raise ValueError("sv không hợp lệ")
        return TokenClaims(user_id=uuid.UUID(str(data["sub"])), session_version=sv)
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise UnauthorizedError("Token không hợp lệ hoặc đã hết hạn", code="token_invalid") from exc


def peek_subject(token: str) -> str | None:
    """`sub` của token nếu chữ ký và hạn hợp lệ, không thì None. KHÔNG chạm DB.

    Cho rate limiter đếm theo user: chạy trước mọi dependency nên không dùng được
    `current_user`. Token giả không qua được bước này, nên không thể giả `sub` để đẩy tải
    sang bucket của người khác.
    """
    try:
        return str(decode_token(token).user_id)
    except UnauthorizedError:
        return None


def _inactive() -> UnauthorizedError:
    # Cùng một thông báo cho "không tồn tại", "bị khoá", "phiên bị thu hồi": không cho biết
    # lý do cụ thể.
    return UnauthorizedError("Tài khoản không còn hiệu lực", code="user_inactive")


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
) -> CurrentUser:
    """Dependency: user của request, hoặc 401.

    Đọc `users` theo PK MỖI request bằng session riêng ngắn hạn (đóng trước khi handler chạy):
    route sync Jira cố ý không giữ session suốt request, và FastAPI cache dependency trong một
    request nên handler dùng lại kết quả này, không truy vấn lần hai.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Thiếu Authorization: Bearer", code="token_invalid")
    claims = decode_token(credentials.credentials)
    async with SessionFactory() as session:
        user = await session.get(User, claims.user_id)
        if (
            user is None
            or user.status is not UserStatus.ACTIVE
            or user.session_version != claims.session_version
        ):
            raise _inactive()
        return CurrentUser(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            timezone=user.timezone,
            aliases=frozenset(a.alias for a in user.aliases if a.source is AliasSource.JIRA),
        )


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]


def require_permission(permission: Permission) -> Callable[..., Awaitable[CurrentUser]]:
    """Dependency factory: 403 `forbidden` nếu user thiếu permission.

    Dùng trong `dependencies=[Depends(require_permission(...))]` của route hoặc router. Chạy sau
    `current_user` (cùng cache) nên không thêm truy vấn.
    """

    async def _check(user: CurrentUserDep) -> CurrentUser:
        if not user.has(permission):
            raise ForbiddenError("Bạn không có quyền thực hiện thao tác này")
        return user

    return _check
