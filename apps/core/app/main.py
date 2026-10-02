from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
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
