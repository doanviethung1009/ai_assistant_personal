"""Engine và session async."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    # Traceback/log của SQLAlchemy không in tham số câu lệnh: tham số có thể là token mã
    # hoá, URL đồng bộ hay nội dung ghi chú. Đổi lại: khó debug lỗi DB hơn.
    hide_parameters=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=5,
    pool_recycle=1800,
)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency của FastAPI. Commit khi handler chạy xong, rollback nếu lỗi.

    Chỉ commit trước khi gửi response khi được khai với scope="function" (xem SessionDep
    ở api/deps.py); đừng dùng get_session trực tiếp trong Depends().
    """
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
