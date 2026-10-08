"""Route đọc body có TRẦN kích thước theo luồng (413 trước khi nạp hết vào RAM).

WHY không dùng cách của imports.py (đọc thô rồi tự parse): endpoint upsert-batch cần body
kiểu Pydantic để OpenAPI/`make gen-types` vẫn sinh đúng schema. Thay vào đó bọc `Request`:
FastAPI đọc body qua `request.body()` -> `stream()`, nên chặn ở `stream()` là đủ, kể cả khi
client gửi chunked (không có Content-Length) hay nói dối Content-Length.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute

# Trần body của POST /tasks/upsert-batch: 1000 item x (description 32 000 + payload 64 KB)
# về lý thuyết lớn hơn nhiều, nhưng ngân sách raw_payload của lô (task_sync_service) đã
# cắt phần payload; 20 MB đủ cho lô hợp lệ lớn nhất và vẫn chặn được body thù địch.
MAX_UPSERT_BODY_BYTES = 20 * 1024 * 1024


class _CappedRequest(Request):
    async def stream(self) -> AsyncIterator[bytes]:
        limit = MAX_UPSERT_BODY_BYTES  # đọc lúc gọi để test chỉnh được
        declared = self.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise HTTPException(status_code=413, detail=_too_big(limit))
        size = 0
        async for chunk in super().stream():
            size += len(chunk)
            if size > limit:
                raise HTTPException(status_code=413, detail=_too_big(limit))
            yield chunk


def _too_big(limit: int) -> str:
    return f"Body vượt giới hạn {limit // (1024 * 1024)} MB."


class CappedBodyRoute(APIRoute):
    """Dùng qua `router.add_api_route(..., route_class_override=CappedBodyRoute)`."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            return await original(_CappedRequest(request.scope, request.receive))

        return handler
