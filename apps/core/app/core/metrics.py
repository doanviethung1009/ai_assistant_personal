"""Metrics cho Prometheus.

Chỉ ghi label theo route template (ví dụ /api/v1/tasks/{task_id}), không ghi
URL thật, để tránh nổ cardinality vì UUID.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

REQUESTS = Counter(
    "http_requests_total",
    "Tổng số HTTP request",
    labelnames=("method", "path", "status"),
)

LATENCY = Histogram(
    "http_request_duration_seconds",
    "Thời gian xử lý request",
    labelnames=("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Số request đang xử lý",
)

BUILD_INFO = Gauge("build_info", "Thông tin build", labelnames=("version", "environment"))


def _route_template(request: Request) -> str:
    """Tìm route template khớp với request, fallback về 'unmatched'."""
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match is Match.FULL:
            return getattr(route, "path", request.url.path)
    return "unmatched"


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        path = _route_template(request)
        started = time.perf_counter()
        IN_FLIGHT.inc()
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            IN_FLIGHT.dec()
            LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
            REQUESTS.labels(request.method, path, str(status_code)).inc()


def setup_metrics(app: FastAPI, *, version: str, environment: str) -> None:
    BUILD_INFO.labels(version, environment).set(1)
    app.add_middleware(MetricsMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
