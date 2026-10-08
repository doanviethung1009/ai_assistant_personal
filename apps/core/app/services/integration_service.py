"""Logic kết nối tích hợp (CRUD) với token mã hoá.

══════════════════════════════════════════════════════════════════════
 CHẠM SECRET. Quy tắc: token chỉ đi vào `encrypt_token`; không log, không đưa vào
 message lỗi, không gán vào bất kỳ thứ gì được trả ra. Log chỉ ghi id/kind/tên field.

 Audit: mỗi thao tác ghi một dòng log có cấu trúc (xem `_audit`), KHÔNG kèm giá trị. Chưa
 có bảng audit riêng; nếu cần truy vết lâu dài thì làm ở B4b.
══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import encrypt_token, last4
from app.db import locks
from app.models.integration import IntegrationConnection
from app.schemas.integration import IntegrationCreate, IntegrationUpdate
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.services.import_service import normalize_project_key

logger = logging.getLogger(__name__)

# Tên constraint (đặt tường minh ở migration) để phân loại IntegrityError chính xác.
_UNIQUE_NAME = "uq_integration_connections_kind_name"
_CHECK_PREFIX = "ck_integration_connections_"
# Chờ khoá dòng tối đa bấy lâu rồi 409 thay vì treo request.
_ROW_LOCK_TIMEOUT = "5s"


def _audit(
    action: str,
    connection_id: uuid.UUID,
    *,
    fields: Iterable[str] = (),
    secret_before: bool | None = None,
    secret_after: bool | None = None,
) -> None:
    """Một dòng log có cấu trúc cho thao tác với kết nối (tạo/sửa/xoá, đổi host, token).

    Chỉ ghi TÊN field đổi và cờ có-token trước/sau, tuyệt đối không giá trị (kể cả host
    hay email). Cần cho điều tra: "ai đó đổi base_url rồi xoay token lúc nào".
    """
    changed = sorted(fields)
    logger.info(
        "integration_audit action=%s id=%s fields=%s has_secret=%s->%s",
        action,
        connection_id,
        ",".join(changed) or "-",
        secret_before,
        secret_after,
        extra={
            "audit": "integration",
            "audit_action": action,
            "connection_id": str(connection_id),
            "changed_fields": changed,
            "has_secret_before": secret_before,
            "has_secret_after": secret_after,
        },
    )


def _config_dict(config: Any) -> dict[str, Any]:
    """Config đã validate -> dict để lưu JSONB; project_key chuẩn hoá bằng hàm của B1."""
    data: dict[str, Any] = {k: v for k, v in config.model_dump().items() if v is not None}
    if "project_key" in data:
        try:
            data["project_key"] = normalize_project_key(data["project_key"])
        except ValueError:
            raise ValidationError("config.project_key không hợp lệ") from None
    return data


async def _flush_or_classify(session: AsyncSession, conflict_message: str) -> None:
    """Flush; đổi IntegrityError thành lỗi nghiệp vụ ĐÚNG loại theo tên constraint.

    WHY: trước đây mọi IntegrityError đều thành 409 "trùng tên", che mất lỗi khác (vd. vi
    phạm CHECK) bằng một thông báo sai. Chỉ unique (kind, name) mới là trùng tên.
    """
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        name = locks.constraint_name(exc)
        if name == _UNIQUE_NAME:
            raise ConflictError(conflict_message) from None
        if name is not None and name.startswith(_CHECK_PREFIX):
            raise ValidationError("Dữ liệu kết nối vi phạm ràng buộc của cơ sở dữ liệu") from None
        raise


async def list_connections(
    session: AsyncSession, *, limit: int, offset: int
) -> tuple[list[IntegrationConnection], int]:
    total = await session.scalar(select(func.count()).select_from(IntegrationConnection))
    stmt = (
        select(IntegrationConnection)
        .order_by(IntegrationConnection.created_at, IntegrationConnection.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def get_connection(
    session: AsyncSession, connection_id: uuid.UUID, *, for_update: bool = False
) -> IntegrationConnection:
    """Đọc một kết nối; `for_update` khoá dòng cho PATCH/DELETE.

    Khoá dòng để hai PATCH/DELETE cùng kết nối được tuần tự hoá (không mất cập nhật,
    không ghi token chồng nhau). Chờ quá 5s thì 409 thay vì treo request.
    """
    stmt = select(IntegrationConnection).where(IntegrationConnection.id == connection_id)
    if for_update:
        await locks.set_lock_timeout(session, _ROW_LOCK_TIMEOUT)
        stmt = stmt.with_for_update()
    async with locks.conflict_on_lock_timeout(
        session, "Kết nối đang được thao tác khác, hãy thử lại sau."
    ):
        row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Không tìm thấy kết nối {connection_id}")
    return row


async def create_connection(
    session: AsyncSession, payload: IntegrationCreate
) -> IntegrationConnection:
    """Tạo kết nối; token (nếu có) được mã hoá, gắn với id + base_url của kết nối này.

    Id sinh sẵn ở đây vì ciphertext phải biết id trước khi flush. Mã hoá chạy TRƯỚC khi
    chạm DB: thiếu khoá thì 503 mà không để lại dòng nào.
    """
    connection_id = uuid.uuid4()
    conn = IntegrationConnection(
        id=connection_id,
        kind=payload.kind,
        name=payload.name,
        base_url=payload.base_url,
        account_email=payload.account_email,
        config=_config_dict(payload.config),
    )
    if payload.token is not None:
        token = payload.token.get_secret_value()
        conn.secret_ciphertext = encrypt_token(
            token, connection_id=connection_id, base_url=conn.base_url
        )
        conn.secret_last4 = last4(token)
    session.add(conn)
    await _flush_or_classify(session, f"Đã có kết nối {payload.kind.value} tên '{payload.name}'")
    await session.refresh(conn)
    _audit("create", conn.id, secret_before=False, secret_after=conn.has_secret)
    return conn


async def update_connection(
    session: AsyncSession, connection_id: uuid.UUID, payload: IntegrationUpdate
) -> IntegrationConnection:
    """Sửa bán phần một kết nối.

    Chốt an toàn: token cũ gắn với host cũ, nên đổi `base_url` bắt buộc đi kèm token mới
    hoặc `clear_token`; nếu không, ai có API key chỉ cần trỏ base_url sang host của mình
    là B4b sẽ gửi token Jira tới đó. Ciphertext còn bị gắn (id, base_url) nên chép sang
    kết nối khác cũng không giải mã được.
    """
    conn = await get_connection(session, connection_id, for_update=True)
    sent = payload.model_fields_set
    had_secret = conn.has_secret
    changed: set[str] = set()

    host_changed = "base_url" in sent and payload.base_url != conn.base_url
    new_base_url = payload.base_url if "base_url" in sent and payload.base_url else conn.base_url
    new_secret: tuple[bytes, str] | None = None
    if payload.token is not None:
        token = payload.token.get_secret_value()
        new_secret = (
            encrypt_token(token, connection_id=conn.id, base_url=new_base_url),
            last4(token),
        )

    if host_changed and conn.has_secret and new_secret is None and not payload.clear_token:
        raise ValidationError(
            "Đổi base_url phải gửi kèm token mới (hoặc clear_token=true), "
            "để token cũ không bị dùng cho host khác."
        )

    if "name" in sent and payload.name and payload.name != conn.name:
        conn.name = payload.name
        changed.add("name")
    if host_changed and payload.base_url is not None:
        conn.base_url = payload.base_url
        changed.add("base_url")
    new_email = payload.account_email if "account_email" in sent else None
    if new_email is not None and new_email != conn.account_email:
        conn.account_email = new_email
        changed.add("account_email")
    if "config" in sent and payload.config is not None:
        new_config = _config_dict(payload.config)
        if new_config != conn.config:
            conn.config = new_config
            changed.add("config")
    if new_secret is not None:
        conn.secret_ciphertext, conn.secret_last4 = new_secret
        changed.add("token")
    elif payload.clear_token and had_secret:
        conn.secret_ciphertext = None
        conn.secret_last4 = None
        changed.add("token")
    # Không gửi token (hoặc token rỗng) = giữ nguyên ciphertext đang lưu.

    await _flush_or_classify(session, "Đã có kết nối cùng loại và cùng tên")
    await session.refresh(conn)
    _audit(
        "update",
        conn.id,
        fields=changed,
        secret_before=had_secret,
        secret_after=conn.has_secret,
    )
    return conn


async def delete_connection(session: AsyncSession, connection_id: uuid.UUID) -> None:
    """Xoá kết nối cùng ciphertext (xoá cứng: không giữ token đã mã hoá lại ở đâu cả)."""
    conn = await get_connection(session, connection_id, for_update=True)
    had_secret = conn.has_secret
    await session.delete(conn)
    await session.flush()
    _audit("delete", connection_id, secret_before=had_secret, secret_after=False)
