"""Test không cần DB: logic thuần, schema, xác thực."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from app.schemas.ai_log import AiLogCreate
from app.schemas.common import MAX_TAGS, normalize_tags
from app.schemas.task import TaskCreate

from .conftest import API_KEY


def test_normalize_tags_lowercase_dedup_keep_order() -> None:
    assert normalize_tags([" Foo Bar ", "foo-bar", "Baz"]) == ["foo-bar", "baz"]


def test_normalize_tags_drops_empty_and_too_long() -> None:
    assert normalize_tags(["", "   ", "x" * 65, "ok"]) == ["ok"]


def test_normalize_tags_limit() -> None:
    with pytest.raises(ValueError, match="tối đa"):
        normalize_tags([f"t{i}" for i in range(MAX_TAGS + 1)])


def test_task_title_is_stripped_and_not_blank() -> None:
    assert TaskCreate(title="  làm báo cáo  ").title == "làm báo cáo"
    with pytest.raises(ValidationError):
        TaskCreate(title="   ")


def test_ai_log_requires_non_empty_fields() -> None:
    with pytest.raises(ValidationError):
        AiLogCreate(prompt="", handling="x", response="y")


async def test_api_rejects_missing_and_wrong_key() -> None:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        missing = await c.get("/api/v1/ai-logs")
        wrong = await c.get("/api/v1/ai-logs", headers={"X-API-Key": "sai-khoa-0000000000"})
    assert missing.status_code == 401
    assert wrong.status_code == 403
    assert API_KEY != "sai-khoa-0000000000"


def test_app_imports_and_exposes_ai_logs_routes() -> None:
    """Chặn lặp lại lỗi router import module không tồn tại làm sập cả API."""
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/v1/ai-logs" in paths
    assert "/api/v1/tasks" in paths
    assert "/api/v1/notes" in paths


def test_refuses_database_without_test_suffix() -> None:
    """Hàng rào chống TRUNCATE nhầm database thật."""
    from .conftest import _require_test_database

    with pytest.raises(pytest.exit.Exception):
        _require_test_database("postgresql+asyncpg://u:p@localhost:5432/builder_ai")
    _require_test_database("postgresql+asyncpg://u:p@localhost:5432/builder_ai_test")
