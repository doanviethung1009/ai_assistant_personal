"""Fixture dùng chung cho test backend.

Hai nhóm test:
- **Unit** (không cần DB): chạy ở mọi nơi, kể cả máy không có Postgres.
- **DB** (đánh dấu `db`): cần Postgres thật, chỉ chạy khi có `TEST_DATABASE_URL`.
  Không dùng SQLite vì model dùng JSONB, ARRAY, GIN và partial index; test trên
  SQLite sẽ xanh giả. Schema được dựng bằng `alembic upgrade head`, nên test
  cũng kiểm luôn migration.

CẢNH BÁO: test DB XOÁ SẠCH các bảng nghiệp vụ. Chỉ trỏ `TEST_DATABASE_URL` vào
database dùng riêng cho test, tuyệt đối không phải database thật.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _require_test_database(url: str) -> None:
    """Từ chối chạy nếu tên database không kết thúc bằng `_test`.

    Test DB TRUNCATE các bảng nghiệp vụ. Đây là hàng rào cuối cùng chống việc
    TEST_DATABASE_URL vô tình trỏ vào database dev/thật (URL có query string,
    sed đổi tên không khớp, tự đặt tay sai...).
    """
    from sqlalchemy.engine import make_url

    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.exit(
            f"TEST_DATABASE_URL trỏ vào database '{name}'. Tên phải kết thúc bằng '_test' "
            "để chắc chắn không phải database thật.",
            returncode=2,
        )


# Phải đặt TRƯỚC khi import app.*: Settings đọc env ngay khi module nạp.
if TEST_DATABASE_URL:
    _require_test_database(TEST_DATABASE_URL)
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("API_KEY", "test-api-key-0123456789")
# Test không có Redis; rate limit fail-open nhưng chờ timeout 3s mỗi request.
os.environ["RATE_LIMIT_ENABLED"] = "false"
# Mật khẩu nhập dữ liệu thật: test API nhập thật gửi đúng giá trị này.
IMPORT_SECRET = "test-import-secret-0123456789"  # noqa: S105
os.environ["IMPORT_COMMIT_SECRET"] = IMPORT_SECRET
# Khoá Fernet cố định CHỈ cho test (đủ 32 byte base64 url-safe). Test thiếu khoá tự xoá
# bằng monkeypatch.
os.environ["INTEGRATION_SECRET_KEY"] = "aW50ZWdyYXRpb24tdGVzdC1rZXktMDEyMzQ1Njc4OTA="  # noqa: S105

API_KEY = os.environ["API_KEY"]

# Danh sách bảng cố định: thêm bảng mới thì phải thêm vào đây, nếu không dữ liệu
# của test này rò sang test sau. import_audit/import_runs là sổ cái của chức năng nhập.
_TRUNCATE_SQL = (
    "TRUNCATE ai_logs, task_events, tasks, notes, projects, import_audit, import_runs, "
    "app_settings, browser_history, integration_connections "
    "RESTART IDENTITY CASCADE"
)
ROOT = Path(__file__).resolve().parents[1]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(reason="cần TEST_DATABASE_URL trỏ tới Postgres dành riêng cho test")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_db() -> None:
    """Dựng schema bằng Alembic một lần cho cả phiên test."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def session(migrated_db: None) -> AsyncIterator[object]:
    """Session mới cho mỗi test; dọn sạch dữ liệu sau test."""
    from sqlalchemy import text

    from app.db.session import SessionFactory

    async with SessionFactory() as s:
        yield s
        await s.rollback()
        await s.execute(text(_TRUNCATE_SQL))
        await s.commit()


@pytest_asyncio.fixture
async def client(migrated_db: None) -> AsyncIterator[object]:
    """HTTP client gọi thẳng ASGI app, kèm API key hợp lệ."""
    import httpx
    from sqlalchemy import text

    from app.db.session import SessionFactory
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-API-Key": API_KEY}
    ) as c:
        yield c

    async with SessionFactory() as s:
        await s.execute(text(_TRUNCATE_SQL))
        await s.commit()
