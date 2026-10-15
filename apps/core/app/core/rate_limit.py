"""Rate limit theo cửa sổ cố định (fixed window), lưu đếm ở Redis.

Mọi request từ web dùng CHUNG một API key, nên đếm theo key thì mọi user chung một bucket.
Định danh vì vậy ưu tiên `user:<sub>` lấy từ JWT (đã kiểm chữ ký, không chạm DB), rồi mới tới
API key. Request không có gì coi như vô danh, đếm theo IP — vẫn phải chặn vì nếu không thì
endpoint tự xác thực (/api/v1/*) có thể bị spam request thiếu key để dò hoặc gây tải, trước
khi tới được bước require_api_key.

`POST /auth/login` có thêm bucket riêng (theo client_ip do web chuyển và toàn cục), kiểm trong
chính handler vì IP nằm trong body.

Chủ động fail-open khi Redis lỗi: readiness probe đã giám sát Redis riêng
(xem api/health.py), rate limiter không phải là nguồn xác thực nên không
được phép làm sập toàn bộ API chỉ vì Redis tạm mất kết nối.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.auth import peek_subject
from app.core.config import settings
from app.core.identifier_hash import identifier_digest
from app.db.redis import get_redis
from app.services.errors import TooManyRequestsError

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
#  Cấu hình cửa sổ
# ═══════════════════════════════════════════════════════════════════════

_WINDOW_SECONDS = 60
# Các path không tính rate limit: probe và tài liệu, không mang nghiệp vụ.
_EXEMPT_PATHS = {"/health", "/health/live", "/health/ready", "/metrics", "/docs", "/openapi.json"}
# Đăng nhập: chặn dò email được mời và spam. Theo IP của browser (web chuyển) và toàn cục.
LOGIN_LIMIT_PER_IP = 20
LOGIN_LIMIT_GLOBAL = 60
# Đăng nhập bằng mật khẩu (spec admin-users-local-login 3.4): theo IP, theo identifier (băm),
# và toàn cục. Lớp chính chống đoán mật khẩu vẫn là khoá theo tài khoản ở DB.
PASSWORD_LOGIN_LIMIT_PER_IP = 10
PASSWORD_LOGIN_LIMIT_PER_IDENTIFIER = 10
# Toàn cục chỉ là cầu chì chống flood; nới rộng để một kẻ spam không dễ khoá cả người dùng thật.
PASSWORD_LOGIN_LIMIT_GLOBAL = 300
# Tự đổi mật khẩu: 5 lần mỗi 15 phút theo user (chặn đoán mật khẩu hiện tại bằng JWT đã có).
PASSWORD_CHANGE_LIMIT = 5
PASSWORD_CHANGE_WINDOW_SECONDS = 15 * 60


def _identity(request: Request) -> str:
    """Định danh để đếm: user trong JWT hợp lệ, rồi API key, fallback IP.

    Middleware này chạy TRƯỚC mọi dependency xác thực (nó bọc toàn bộ app), nên không thể giả
    định header luôn hợp lệ hoặc có mặt. JWT chỉ được tin để chọn bucket khi chữ ký hợp lệ,
    nên không thể giả `sub` để đẩy tải sang bucket người khác.
    """
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        subject = peek_subject(token.strip())
        if subject is not None:
            return f"user:{subject}"
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"key:{api_key}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


async def _hit_window(key: str, window: int) -> int | None:
    """Tăng bộ đếm của cửa sổ `window` giây hiện tại; None nếu Redis lỗi (fail-open)."""
    bucket = int(time.time() // window)
    full_key = f"ratelimit:{key}:{bucket}"
    try:
        redis = get_redis()
        count = await redis.incr(full_key)
        if count == 1:
            # +5s đệm để tránh key hết hạn đúng lúc client gửi request
            # sát ranh cửa sổ, dẫn tới đếm lại từ 0 ở request kế tiếp.
            await redis.expire(full_key, window + 5)
    except Exception:  # fail-open theo chủ đích, xem docstring module
        logger.warning("rate_limit_redis_error", exc_info=True)
        return None
    return int(count)


async def _hit(key: str) -> int | None:
    """Cửa sổ 60 giây chuẩn; trả số đếm, hoặc None nếu Redis lỗi (fail-open)."""
    return await _hit_window(key, _WINDOW_SECONDS)


async def enforce_login_limits(client_ip: str | None) -> None:
    """Giới hạn tốc độ riêng cho /auth/login: 20/phút theo IP và 60/phút toàn cục (429).

    Gọi trong handler (IP nằm trong body). Tắt khi RATE_LIMIT_ENABLED=false (test).
    """
    if not settings.rate_limit_enabled:
        return
    for key, limit in (
        (f"login-ip:{client_ip or 'unknown'}", LOGIN_LIMIT_PER_IP),
        ("login-global", LOGIN_LIMIT_GLOBAL),
    ):
        count = await _hit(key)
        if count is not None and count > limit:
            raise TooManyRequestsError("Quá nhiều lần đăng nhập, thử lại sau")


async def enforce_password_login_limits(client_ip: str | None, identifier: str) -> None:
    """Giới hạn riêng cho `/auth/login/password`, chạy TRƯỚC khi chạm DB hay băm (429).

    Khoá Redis chứa HMAC-SHA256 của identifier chuẩn hoá, không chứa tên đăng nhập hay email.
    Khi web chạy qua tunnel `client_ip` là null nên bucket IP thành bucket chung: chấp nhận (Q13).
    """
    if not settings.rate_limit_enabled:
        return
    digest = identifier_digest(identifier)
    for key, limit in (
        (f"login-pw-ip:{client_ip or 'unknown'}", PASSWORD_LOGIN_LIMIT_PER_IP),
        (f"login-pw-id:{digest}", PASSWORD_LOGIN_LIMIT_PER_IDENTIFIER),
        ("login-pw-global", PASSWORD_LOGIN_LIMIT_GLOBAL),
    ):
        count = await _hit(key)
        if count is not None and count > limit:
            if key == "login-pw-global":
                # Không log identifier hay IP: chỉ cần biết cầu chì đã nhảy.
                logger.warning("login_global_limit_hit")
            raise TooManyRequestsError("Quá nhiều lần đăng nhập, thử lại sau")


async def enforce_password_change_limit(user_id: uuid.UUID) -> None:
    """5 lần đổi mật khẩu mỗi 15 phút cho mỗi user (429). KHÔNG khoá tài khoản."""
    if not settings.rate_limit_enabled:
        return
    count = await _hit_window(f"pwchange:{user_id}", PASSWORD_CHANGE_WINDOW_SECONDS)
    if count is not None and count > PASSWORD_CHANGE_LIMIT:
        raise TooManyRequestsError("Quá nhiều lần đổi mật khẩu, thử lại sau")


# ═══════════════════════════════════════════════════════════════════════
#  Middleware
# ═══════════════════════════════════════════════════════════════════════


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Đếm request trong cửa sổ 60s hiện tại ở Redis, chặn 429 nếu vượt limit.

        Cửa sổ cố định (không phải sliding window) đổi lấy đơn giản: cho phép
        burst gấp đôi limit ở đúng ranh giữa hai cửa sổ (vd 119 request ở giây
        cuối cửa sổ A + 119 request ở giây đầu cửa sổ B). Chấp nhận được vì
        mục tiêu là chặn client lỗi gọi lặp vô hạn, không phải giới hạn chính
        xác tới từng request.
        """
        if not settings.rate_limit_enabled or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        limit = settings.rate_limit_requests_per_minute
        count = await _hit(_identity(request))
        if count is None:
            return await call_next(request)

        if count > limit:
            retry_after = _WINDOW_SECONDS - int(time.time() % _WINDOW_SECONDS)
            return JSONResponse(
                status_code=429,
                content={"detail": "Quá số lượng request cho phép, thử lại sau"},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)


def setup_rate_limit(app: FastAPI) -> None:
    """Gắn middleware. Gọi sau setup_metrics() trong main.py.

    Thứ tự add_middleware không quan trọng về mặt chức năng ở đây (hai
    middleware không phụ thuộc nhau), chỉ cần rate limit chạy trước khi
    request chạm tới route handler thật — add_middleware luôn đảm bảo điều
    đó cho mọi thứ tự gọi.
    """
    app.add_middleware(RateLimitMiddleware)
