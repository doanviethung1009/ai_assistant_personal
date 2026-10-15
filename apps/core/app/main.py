from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import health
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.metrics import setup_metrics
from app.core.rate_limit import setup_rate_limit
from app.db.redis import close_redis
from app.db.session import SessionFactory, engine
from app.services import user_service
from app.services.errors import DomainError

logger = logging.getLogger(__name__)


async def _sync_admin_emails() -> None:
    """Upsert `ADMIN_EMAILS` thành admin khi khởi động (đường "phá kính" khi lỡ khoá hết admin).

    Lỗi (vd chưa chạy `make migrate` nên chưa có bảng users) chỉ được ghi log, KHÔNG chặn core
    khởi động: nếu chặn thì không dựng được stack mới để chạy migrate. Hậu quả: chưa có admin
    nào cho tới khi migrate rồi khởi động lại, hoặc chạy `python -m app.cli.auth bootstrap`.
    """
    if not settings.admin_emails:
        return
    try:
        async with SessionFactory() as session:
            changed = await user_service.sync_admin_emails(session, settings.admin_emails)
            await session.commit()
        logger.info("đã đồng bộ ADMIN_EMAILS", extra={"changed": changed})
    except Exception:
        logger.exception("không đồng bộ được ADMIN_EMAILS (đã chạy migrate chưa?)")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(settings.log_level)
    logger.info(
        "khởi động",
        extra={"version": __version__, "environment": settings.environment},
    )
    if os.environ.get("IMPORT_COMMIT_SECRET"):
        # Mật khẩu nhập đã bị thay bằng quyền `data:import` của admin; biến còn sót là vô hiệu.
        logger.warning("IMPORT_COMMIT_SECRET đã bỏ, không còn tác dụng: hãy xoá khỏi môi trường")
    await _sync_admin_emails()
    yield
    await close_redis()
    await engine.dispose()
    logger.info("đã dừng")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Core API của Builder AI Assistant. Phase 1: task store nhập tay.\n\n"
        "Xác thực: header `X-API-Key` cho mọi endpoint dưới `/api/v1` (chứng minh request đến "
        "từ web), cộng `Authorization: Bearer <JWT 60 giây>` cho mọi endpoint trừ "
        "`/api/v1/auth/login`. "
        "Các endpoint `/health/*` và `/metrics` mở để probe gọi được."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)

setup_metrics(app, version=__version__, environment=settings.environment)
setup_rate_limit(app)


@app.exception_handler(DomainError)
async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    content: dict[str, str] = {"detail": exc.message}
    if exc.code is not None:
        content["code"] = exc.code
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(status_code=exc.status_code, content=content, headers=headers)


SETTINGS_PATH_PREFIX = "/api/v1/settings"
# Các route có dữ liệu nhạy cảm (URL đồng bộ, token) trong body: 422 không được echo lại `input`.
_NO_ECHO_PREFIXES = (
    SETTINGS_PATH_PREFIX,
    # Body có API token của integration: 422 mà echo `input` là lộ token.
    "/api/v1/integrations",
    # Claim Google (email, sub) trong body đăng nhập: 422 không được echo lại.
    "/api/v1/auth",
    # Mật khẩu hiện tại/mới trong body đổi mật khẩu; admin tạo user và nhận mật khẩu tạm.
    "/api/v1/me/password",
    "/api/v1/admin",
    # raw_payload của nguồn ngoài có thể mang token/cookie: không echo lại trong 422.
    "/api/v1/tasks/upsert-batch",
)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Lỗi 422 mặc định; riêng các route nhạy cảm (xem _NO_ECHO_PREFIXES) bỏ `input`, `ctx`.

    Mặc định FastAPI echo lại giá trị đầu vào, mà ở đây đó là URL đồng bộ (link chia sẻ
    mang token trong query) hay tên người dùng, rồi đi vào log của proxy/client. Phạm vi
    CỐ Ý hẹp ở /settings để không đổi schema lỗi của các route khác.
    """
    if not request.url.path.startswith(_NO_ECHO_PREFIXES):
        return await request_validation_exception_handler(request, exc)
    safe = [
        {"type": err.get("type"), "loc": err.get("loc"), "msg": err.get("msg")}
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(safe)})


app.include_router(health.router)
app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/health/ready",
    }
