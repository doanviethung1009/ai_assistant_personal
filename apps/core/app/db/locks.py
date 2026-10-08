"""Khoá DB dùng chung: advisory lock của luồng nhập và xử lý lỗi khoá/ràng buộc.

WHY tách riêng: trước đây `_take_write_lock` nằm trong settings_service và bị
task_sync_service import "private" chéo. Ba nơi ghi (nhập JSON, ghi cài đặt, upsert-batch
của tích hợp) phải xếp hàng sau CÙNG một khoá, nên tên khoá và cách xử lý timeout cần một
nguồn duy nhất.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.errors import ConflictError

# Cùng khoá advisory với import_service. Ai ghi hàng loạt đều phải xếp hàng sau nó: nếu
# không, ghi chen giữa lúc nhập đã lập kế hoạch sẽ làm sổ audit mô tả sai trạng thái cũ.
IMPORT_LOCK_NAME = "builder:import"
# Chờ khoá tối đa bấy lâu rồi 409, thay vì treo request khi có lần nhập lớn đang chạy.
DEFAULT_LOCK_TIMEOUT = "5s"

_LOCK_NOT_AVAILABLE = "55P03"


def _driver_error(exc: DBAPIError) -> tuple[object | None, object | None]:
    """(orig, cause): asyncpg bọc lỗi gốc hai tầng nên thuộc tính có thể nằm ở một trong hai."""
    orig = getattr(exc, "orig", None)
    return orig, getattr(orig, "__cause__", None)


def sqlstate(exc: DBAPIError) -> str | None:
    orig, cause = _driver_error(exc)
    for obj in (orig, cause):
        code = getattr(obj, "sqlstate", None) or getattr(obj, "pgcode", None)
        if code:
            return str(code)
    return None


def constraint_name(exc: DBAPIError) -> str | None:
    """Tên constraint bị vi phạm (IntegrityError), None nếu driver không cho biết."""
    orig, cause = _driver_error(exc)
    for obj in (orig, cause):
        name = getattr(obj, "constraint_name", None)
        if name:
            return str(name)
    return None


def is_lock_timeout(exc: DBAPIError) -> bool:
    return sqlstate(exc) == _LOCK_NOT_AVAILABLE


async def set_lock_timeout(session: AsyncSession, value: str = DEFAULT_LOCK_TIMEOUT) -> None:
    """Đặt lock_timeout cho transaction hiện tại (`is_local=true`, tự hết khi commit)."""
    await session.execute(text("SELECT set_config('lock_timeout', :v, true)"), {"v": value})


@asynccontextmanager
async def conflict_on_lock_timeout(session: AsyncSession, message: str) -> AsyncIterator[None]:
    """Đổi lỗi hết hạn chờ khoá (55P03) thành ConflictError 409; lỗi khác giữ nguyên.

    Transaction đã bị huỷ sau lỗi nên rollback tại đây để session dùng lại được.
    """
    try:
        yield
    except DBAPIError as exc:
        if not is_lock_timeout(exc):
            raise
        await session.rollback()
        raise ConflictError(message) from exc


async def take_import_write_lock(session: AsyncSession, *, lock_timeout: str | None = None) -> None:
    """Lấy advisory lock của nhập (dạng CHỜ); hết hạn thì 409.

    Lock theo transaction nên tự nhả khi request commit/rollback. Hai bên ghi đồng thời
    được tuần tự hoá qua đây (cuối cùng thắng, không xen kẽ). Đồng thời đặt lock_timeout
    cho các câu `FOR UPDATE` về sau trong cùng transaction.
    """
    await set_lock_timeout(session, lock_timeout or DEFAULT_LOCK_TIMEOUT)
    async with conflict_on_lock_timeout(session, "Đang có lần nhập dữ liệu chạy, hãy thử lại sau."):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": IMPORT_LOCK_NAME}
        )
