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
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from app.core.auth import CurrentUser

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
# Khoá ký JWT người dùng (khác API_KEY); thiếu biến này core không khởi động.
os.environ["CORE_JWT_SECRET"] = "test-core-jwt-secret-0123456789-abcdef"  # noqa: S105
os.environ.pop("IMPORT_COMMIT_SECRET", None)
os.environ["ADMIN_EMAILS"] = ""
os.environ["GOOGLE_ALLOWED_HD"] = ""
# Khoá Fernet cố định CHỈ cho test (đủ 32 byte base64 url-safe). Test thiếu khoá tự xoá
# bằng monkeypatch.
os.environ["INTEGRATION_SECRET_KEY"] = "aW50ZWdyYXRpb24tdGVzdC1rZXktMDEyMzQ1Njc4OTA="  # noqa: S105

API_KEY = os.environ["API_KEY"]

# Danh sách bảng cố định: thêm bảng mới thì phải thêm vào đây, nếu không dữ liệu
# của test này rò sang test sau. import_audit/import_runs là sổ cái của chức năng nhập.
_TRUNCATE_SQL = (
    "TRUNCATE task_events, tasks, notes, projects, import_audit, import_runs, "
    "app_settings, integration_connections, user_aliases, audit_log, users "
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


@dataclass
class Persona:
    """Một user test đã nằm trong DB (active, đã gắn google_sub)."""

    user: CurrentUser
    session_version: int = 0

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def email(self) -> str:
        return self.user.email

    @property
    def headers(self) -> dict[str, str]:
        """Header đầy đủ cho một request: API key + JWT mới (sống 60 giây)."""
        from app.core.auth import mint_token

        token = mint_token(self.user.id, self.session_version)
        return {"X-API-Key": API_KEY, "Authorization": f"Bearer {token}"}


async def create_persona(
    email: str,
    role: object | None = None,
    aliases: tuple[str, ...] = (),
    *,
    status: object | None = None,
) -> Persona:
    """Tạo user trực tiếp bằng SQLAlchemy (không qua /auth/login) và trả `Persona`."""
    from app.core.auth import CurrentUser
    from app.db.session import SessionFactory
    from app.models.enums import AliasSource, UserRole, UserStatus
    from app.models.user import User, UserAlias

    role = role or UserRole.MEMBER
    status = status or UserStatus.ACTIVE
    async with SessionFactory() as s:
        user = User(
            email=email,
            role=role,
            status=status,
            google_sub=f"sub-{uuid.uuid4().hex}" if status is UserStatus.ACTIVE else None,
        )
        s.add(user)
        await s.flush()
        for alias in aliases:
            s.add(UserAlias(user_id=user.id, source=AliasSource.JIRA, alias=alias))
        await s.commit()
    return Persona(
        user=CurrentUser(
            id=user.id,
            email=email,
            name=None,
            role=role,
            aliases=frozenset(aliases),
        )
    )


async def add_aliases(persona: Persona, *names: str) -> None:
    """Đặt alias Jira của user (thay toàn bộ) trực tiếp trong DB.

    `current_user` đọc alias từ DB mỗi request nên có hiệu lực ngay, không cần tạo lại token.
    """
    from sqlalchemy import delete

    from app.db.session import SessionFactory
    from app.models.enums import AliasSource
    from app.models.user import UserAlias

    async with SessionFactory() as s:
        await s.execute(delete(UserAlias).where(UserAlias.user_id == persona.id))
        for name in names:
            s.add(UserAlias(user_id=persona.id, source=AliasSource.JIRA, alias=name))
        await s.commit()
    persona.user = replace(persona.user, aliases=frozenset(names))


@pytest_asyncio.fixture
async def default_user(migrated_db: None) -> AsyncIterator[Persona]:
    """User admin mặc định: `client` và test service dùng chung. Admin để các test cũ (vốn không
    biết đến phân quyền) vẫn chạm được mọi endpoint; test phân quyền dùng `make_persona`."""
    from sqlalchemy import text

    from app.db.session import SessionFactory
    from app.models.enums import UserRole

    # Dọn lúc SETUP (không phải teardown): teardown của `default_user` chạy TRƯỚC teardown của
    # `session`, mà session còn giữ transaction mở nên TRUNCATE ở teardown sẽ treo (deadlock).
    # Dữ liệu rò từ test trước (kể cả test đồng bộ không có fixture dọn) bị xoá ở đây.
    async with SessionFactory() as s:
        await s.execute(text(_TRUNCATE_SQL))
        await s.commit()
    yield await create_persona("default-admin@test.local", UserRole.ADMIN)


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
async def client(default_user: Persona) -> AsyncIterator[object]:
    """HTTP client gọi thẳng ASGI app, đã đăng nhập bằng `default_user` (admin).

    Header Authorization là JWT 60 giây ký lúc tạo fixture: test chạy dưới 60 giây nên đủ.
    Test cần user khác gửi header riêng qua `persona.headers` (ghi đè theo từng request).
    """
    import httpx
    from sqlalchemy import text

    from app.db.session import SessionFactory
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers=default_user.headers
    ) as c:
        yield c

    async with SessionFactory() as s:
        await s.execute(text(_TRUNCATE_SQL))
        await s.commit()


@pytest_asyncio.fixture
async def anon_client(migrated_db: None) -> AsyncIterator[object]:
    """Client chỉ có API key (không JWT): cho test đăng nhập và test 401."""
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
