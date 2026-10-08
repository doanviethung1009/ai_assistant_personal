from __future__ import annotations

import logging
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
from app.db.session import engine
from app.services.errors import DomainError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(settings.log_level)
    logger.info(
        "khởi động",
        extra={"version": __version__, "environment": settings.environment},
    )
    yield
    await close_redis()
    await engine.dispose()
    logger.info("đã dừng")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Core API của Builder AI Assistant. Phase 1: task store nhập tay.\n\n"
        "Xác thực bằng header `X-API-Key` cho mọi endpoint dưới `/api/v1`. "
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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)

setup_metrics(app, version=__version__, environment=settings.environment)
setup_rate_limit(app)


@app.exception_handler(DomainError)
async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


SETTINGS_PATH_PREFIX = "/api/v1/settings"
# Các route có URL duyệt web (có thể mang token) trong body: 422 không được echo lại `input`.
_NO_ECHO_PREFIXES = (
    SETTINGS_PATH_PREFIX,
    "/api/v1/browser-history",
    "/api/v1/import/browser-history",
)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Lỗi 422 mặc định; riêng /settings và browser-history bỏ `input`, `ctx` khỏi chi tiết lỗi.

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
