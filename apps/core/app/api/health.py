"""Healthcheck.

Tách liveness và readiness vì hai câu hỏi khác nhau:
  - live  : process còn sống? Nếu fail thì restart container.
  - ready : phụ thuộc (DB, Redis) có dùng được? Nếu fail thì rút khỏi load balancer
            nhưng KHÔNG restart.

Cả hai không yêu cầu API key để probe của Prometheus/blackbox gọi được.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.core.config import settings
from app.db.redis import get_redis
from app.db.session import SessionFactory

router = APIRouter(tags=["health"])

_CHECK_TIMEOUT_SECONDS = 3.0


class ComponentHealth(BaseModel):
    status: Literal["ok", "error"]
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    components: dict[str, ComponentHealth]


async def _check_database() -> ComponentHealth:
    started = time.perf_counter()
    try:
        async with SessionFactory() as session:
            await asyncio.wait_for(
                session.execute(text("SELECT 1")), timeout=_CHECK_TIMEOUT_SECONDS
            )
        return ComponentHealth(
            status="ok", latency_ms=round((time.perf_counter() - started) * 1000, 2)
        )
    except Exception as exc:
        return ComponentHealth(status="error", error=f"{type(exc).__name__}: {exc}")


async def _check_redis() -> ComponentHealth:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(get_redis().ping(), timeout=_CHECK_TIMEOUT_SECONDS)
        return ComponentHealth(
            status="ok", latency_ms=round((time.perf_counter() - started) * 1000, 2)
        )
    except Exception as exc:
        return ComponentHealth(status="error", error=f"{type(exc).__name__}: {exc}")


@router.get("/health/live", summary="Liveness probe")
async def liveness() -> dict[str, Any]:
    return {"status": "ok", "version": __version__}


@router.get("/health/ready", response_model=HealthResponse, summary="Readiness probe")
async def readiness(response: Response) -> HealthResponse:
    database, redis_health = await asyncio.gather(_check_database(), _check_redis())
    components = {"database": database, "redis": redis_health}

    healthy = all(component.status == "ok" for component in components.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=__version__,
        environment=settings.environment,
        components=components,
    )


@router.get("/health", response_model=HealthResponse, summary="Tổng hợp")
async def health(response: Response) -> HealthResponse:
    return await readiness(response)
