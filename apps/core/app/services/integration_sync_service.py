"""Chạy đồng bộ Jira theo yêu cầu: khoá, gọi Jira, upsert theo lô, ghi `last_sync_at`.

══════════════════════════════════════════════════════════════════════
 CHẠM SECRET. Token được giải mã ngay trước khi gọi, giữ trong biến cục bộ của
 `run_sync`/JiraClient, không gán vào đối tượng sống lâu, không log, không vào response
 hay message lỗi. Audit chỉ ghi id kết nối và số liệu.
══════════════════════════════════════════════════════════════════════

Thiết kế giao dịch (WHY): gọi Jira có thể mất hàng phút. Giữ một transaction DB mở suốt
thời gian đó sẽ giữ khoá hàng/advisory lock và một connection pool, chặn nhập dữ liệu và
sửa task của User. Vì vậy:
  1. Transaction NGẮN để đọc kết nối + current_users, rồi đóng.
  2. Khoá "một sync mỗi kết nối" là advisory lock cấp SESSION trên một connection riêng
     chế độ AUTOCOMMIT (không nằm trong transaction nào). Process chết thì connection đóng
     và Postgres tự nhả khoá. Connection này bị HUỶ (invalidate) thay vì trả về pool để
     chắc chắn không mang khoá còn sót vào request khác.
  3. Gọi Jira, ánh xạ từng trang; GHI NGAY mỗi khi đủ 1000 item rồi giải phóng, nên bộ nhớ
     bị chặn bởi một lô + một trang (không gom 100 trang).
  4. Mỗi lô <= 1000 task một transaction ngắn (task_sync_service.upsert_batch). Lỗi giữa
     chừng để lại các lô đã ghi; an toàn vì upsert idempotent. Lỗi kèm câu "đã ghi N task".
  5. Transaction ngắn riêng cập nhật `last_sync_at` CHỈ khi xong trọn vẹn.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import anyio
import httpx
from sqlalchemy import select, text, update

from app.core.secrets import decrypt_token
from app.db.session import SessionFactory, engine
from app.models.enums import IntegrationKind, TaskSource
from app.models.integration import IntegrationConnection
from app.models.project import Project
from app.schemas.integration import SyncMessage, SyncResult
from app.schemas.task_upsert import MAX_BATCH_ITEMS, TaskUpsert, TaskUpsertResult
from app.services import clock, jira_client, jira_mapping, settings_service, task_sync_service
from app.services.errors import ConflictError, DomainError, NotFoundError
from app.services.import_service import normalize_project_key
from app.services.jira_client import JiraSyncError
from app.services.ssrf_guard import PinnedTransport

logger = logging.getLogger(__name__)

_LOCK_NAMESPACE = "builder:integration-sync:"
# Trường chỉ ghi khi TẠO task (không đè task đã có): giữ giá trị User sửa tay, và task cũ
# không bị chuyển project. Cùng ngữ nghĩa chế độ file (apps/web/app/jira-actions.ts).
CREATE_ONLY = frozenset({"priority", "assignee", "project_key"})
# Tên project do Jira điều khiển; trần số project MỚI mỗi lần sync để dữ liệu Jira (hoặc kẻ
# giả Jira) không tràn danh sách project cục bộ.
MAX_NEW_PROJECTS = 50
# Giới hạn số thông báo trả về để response không phình theo số issue.
MAX_MESSAGES = 200


@dataclass(frozen=True, slots=True)
class _ConnectionSnapshot:
    """Bản chụp các trường cần dùng, để đóng session trước khi gọi mạng."""

    id: uuid.UUID
    name: str
    base_url: str
    account_email: str
    ciphertext: bytes | None
    jql: str | None
    project_key: str | None
    project_name: str | None


def build_transport(host: str) -> httpx.AsyncBaseTransport:
    """Transport production: kiểm IP + ghim IP + chỉ `host`. Test thay hàm này để giả mạng."""
    return PinnedTransport(host)


def _audit(action: str, connection_id: uuid.UUID, **fields: Any) -> None:
    """Một dòng log có cấu trúc. Chỉ số liệu và id; KHÔNG token, URL, body Jira."""
    logger.info(
        "integration_sync action=%s id=%s %s",
        action,
        connection_id,
        " ".join(f"{k}={v}" for k, v in fields.items()),
        extra={
            "audit": "integration_sync",
            "audit_action": action,
            "connection_id": str(connection_id),
            **fields,
        },
    )


async def _load(connection_id: uuid.UUID) -> tuple[_ConnectionSnapshot, list[str]]:
    async with SessionFactory() as session:
        conn = await session.get(IntegrationConnection, connection_id)
        if conn is None:
            raise NotFoundError(f"Không tìm thấy kết nối {connection_id}")
        if conn.kind is not IntegrationKind.JIRA:
            raise ConflictError("Loại kết nối này chưa hỗ trợ đồng bộ.")
        users = await settings_service.get_current_users(session)
        config = conn.config or {}
        snapshot = _ConnectionSnapshot(
            id=conn.id,
            name=conn.name,
            base_url=conn.base_url,
            account_email=conn.account_email,
            ciphertext=conn.secret_ciphertext,
            jql=config.get("jql"),
            project_key=config.get("project_key"),
            project_name=config.get("project_name"),
        )
        await session.rollback()  # chỉ đọc: kết thúc transaction ngay
        return snapshot, users


@asynccontextmanager
async def _exclusive(connection_id: uuid.UUID) -> AsyncIterator[None]:
    """Một sync mỗi kết nối: advisory lock cấp session, không giữ transaction.

    Raises:
        ConflictError: đã có lần sync khác của kết nối này đang chạy (409).
    """
    key = _LOCK_NAMESPACE + str(connection_id)
    async with engine.connect() as conn:
        try:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            got = await conn.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:k, 0))"), {"k": key}
            )
            if not got:
                raise ConflictError("Kết nối này đang được đồng bộ, hãy thử lại sau khi xong.")
            yield
        finally:
            # Shield: request bị huỷ (client ngắt) nên CancelledError đang bay; không shield
            # thì các `await` dưới đây bị huỷ ngay và khoá cấp session ở lại connection.
            # Huỷ connection thay vì trả về pool: nếu việc nhả khoá lỡ lỗi, khoá còn sót sẽ
            # nằm trên connection được tái sử dụng và chặn sync của kết nối này vĩnh viễn.
            with anyio.CancelScope(shield=True):
                try:
                    await conn.scalar(
                        text("SELECT pg_advisory_unlock(hashtextextended(:k, 0))"), {"k": key}
                    )
                except Exception as exc:
                    logger.warning("integration_sync unlock_failed error=%s", type(exc).__name__)
                finally:
                    await conn.invalidate()


async def _write_batch(items: list[TaskUpsert], actor: str, owner_host: str) -> TaskUpsertResult:
    async with SessionFactory() as session:
        try:
            result = await task_sync_service.upsert_batch(
                session,
                TaskSource.JIRA,
                items,
                actor=actor,
                create_only=CREATE_ONLY,
                owner_host=owner_host,
                due_baseline=jira_mapping.previous_due,
            )
            await session.commit()
        except BaseException:
            # Shield: nếu đang bị huỷ, rollback vẫn phải xong để trả connection sạch về pool.
            with anyio.CancelScope(shield=True):
                await session.rollback()
            raise
    return result


async def _mark_synced(connection_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        # updated_at giữ nguyên: đây không phải thay đổi cấu hình của kết nối.
        await session.execute(
            update(IntegrationConnection)
            .where(IntegrationConnection.id == connection_id)
            .values(last_sync_at=clock.now_utc(), updated_at=IntegrationConnection.updated_at)
        )
        await session.commit()


async def _existing_project_keys(keys: set[str]) -> set[str]:
    if not keys:
        return set()
    async with SessionFactory() as session:
        rows = await session.execute(select(Project.key).where(Project.key.in_(keys)))
        found = set(rows.scalars())
        await session.rollback()
    return found


@dataclass(slots=True)
class _Progress:
    """Số liệu và thông báo gộp qua các lô của một lần sync."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_personal: int = 0
    kept_manual_due: int = 0
    errors: list[SyncMessage] = field(default_factory=list)
    warnings: list[SyncMessage] = field(default_factory=list)
    error_overflow: int = 0
    warning_overflow: int = 0
    new_projects: set[str] = field(default_factory=set)

    @property
    def written(self) -> int:
        return self.added + self.updated

    def error(self, message: SyncMessage) -> None:
        if len(self.errors) < MAX_MESSAGES:
            self.errors.append(message)
        else:
            self.error_overflow += 1

    def warn(self, message: SyncMessage) -> None:
        if len(self.warnings) < MAX_MESSAGES:
            self.warnings.append(message)
        else:
            self.warning_overflow += 1


async def _cap_new_projects(
    items: list[TaskUpsert],
    origin: list[int],
    progress: _Progress,
    snapshot: _ConnectionSnapshot,
) -> list[TaskUpsert]:
    """Giới hạn số project MỚI mỗi lần sync; item vượt trần dùng project dự phòng.

    WHY: tên project lấy từ custom field do Jira điều khiển; không có trần thì một Jira
    độc hại/cấu hình sai tạo hàng nghìn project cục bộ. Dự phòng = project mặc định của kết
    nối (config.project_key) nếu có, không thì không gắn project.
    """
    keys = {i.project_key for i in items if i.project_key}
    fresh = keys - progress.new_projects
    if not fresh:
        return items
    fresh -= await _existing_project_keys(fresh)
    fallback_key: str | None = None
    if snapshot.project_key:
        try:
            fallback_key = normalize_project_key(snapshot.project_key)
        except ValueError:
            fallback_key = None
    out: list[TaskUpsert] = []
    for item, index in zip(items, origin, strict=True):
        key = item.project_key
        if key and key in fresh and key not in progress.new_projects:
            if len(progress.new_projects) < MAX_NEW_PROJECTS:
                progress.new_projects.add(key)
            else:
                item = item.model_copy(
                    update={
                        "project_key": fallback_key,
                        "project_name": snapshot.project_name if fallback_key else None,
                    }
                )
                progress.warn(
                    SyncMessage(
                        index=index,
                        external_id=item.external_id,
                        reason=(
                            f"Vượt trần {MAX_NEW_PROJECTS} project mới mỗi lần sync; "
                            "issue này dùng project dự phòng."
                        ),
                    )
                )
        out.append(item)
    return out


async def _flush(
    items: list[TaskUpsert],
    origin: list[int],
    progress: _Progress,
    snapshot: _ConnectionSnapshot,
    owner_host: str,
) -> None:
    """Ghi một lô (<= 1000) trong một transaction ngắn, cộng dồn số liệu vào `progress`."""
    if not items:
        return
    chunk = await _cap_new_projects(items, origin, progress, snapshot)
    result = await _write_batch(chunk, f"integration:{snapshot.name}", owner_host)
    progress.added += result.added
    progress.updated += result.updated
    progress.unchanged += result.unchanged
    progress.skipped_personal += result.skipped_personal
    progress.kept_manual_due += result.kept_manual_due
    for err in result.errors:
        progress.error(
            SyncMessage(
                index=origin[err.index], external_id=chunk[err.index].external_id, reason=err.reason
            )
        )
    for warn in result.warnings:
        progress.warn(
            SyncMessage(
                index=origin[warn.index],
                external_id=chunk[warn.index].external_id,
                reason=warn.reason,
            )
        )


def _ordered(messages: list[SyncMessage], overflow: int, what: str) -> list[SyncMessage]:
    out = sorted(messages, key=lambda m: (m.index is None, m.index or 0))
    if overflow:
        out.append(SyncMessage(reason=f"... và {overflow} {what} nữa (đã lược bớt)"))
    return out


async def run_sync(
    connection_id: uuid.UUID,
    since: str | None = None,
    *,
    client_ip: str | None = None,
    assignees: list[str] | None = None,
) -> SyncResult:
    """Đồng bộ một kết nối Jira. Xem docstring module về giao dịch và khoá.

    Mọi lần gọi đều có một dòng audit kết quả (done/failed/cancelled), kể cả bị từ chối
    trước khi lấy khoá (404, thiếu token, since sai): kèm IP client và `since` đã parse.

    Raises:
        ValidationError: `since` sai định dạng, hoặc không có JQL lẫn current_users (422).
        NotFoundError: kết nối không tồn tại (404).
        ConflictError: thiếu token (409) hoặc đang có sync khác của kết nối (409).
        SecretsUnavailableError: không giải mã được token (503, bảo nhập lại token).
        JiraSyncError / NetworkUnavailableError: lỗi Jira hoặc mạng, message tự viết.
    """
    started = time.monotonic()
    client = client_ip or "-"
    since_minutes: int | None = None
    try:
        since_minutes = jira_client.parse_since(since)
        return await _run(connection_id, since_minutes, client, started, assignees)
    except asyncio.CancelledError:
        _audit(
            "cancelled",
            connection_id,
            client=client,
            since_minutes=since_minutes,
            seconds=round(time.monotonic() - started, 2),
        )
        raise
    except Exception as exc:
        _audit(
            "failed",
            connection_id,
            client=client,
            since_minutes=since_minutes,
            error=type(exc).__name__,
            status=getattr(exc, "status_code", 500),
            seconds=round(time.monotonic() - started, 2),
        )
        raise


async def _run(
    connection_id: uuid.UUID,
    since_minutes: int | None,
    client_ip: str,
    started: float,
    assignees: list[str] | None = None,
) -> SyncResult:
    snapshot, users = await _load(connection_id)
    if snapshot.ciphertext is None:
        raise ConflictError(
            "Kết nối chưa có API token. Mở kết nối, nhập token (PATCH /integrations/{id}) "
            "rồi đồng bộ lại."
        )
    jql = jira_client.build_jql(snapshot.jql, users, since_minutes, assignees)
    host = snapshot.base_url.removeprefix("https://").rstrip("/")
    progress = _Progress()

    async with _exclusive(connection_id):
        _audit(
            "start",
            connection_id,
            client=client_ip,
            since_minutes=since_minutes,
            assignee_count=len(assignees or []),
        )
        # Giải mã ngay trước khi dùng; lỗi khoá thì 503 "nhập lại token", không crash.
        token = decrypt_token(
            snapshot.ciphertext, connection_id=snapshot.id, base_url=snapshot.base_url
        )
        jira = jira_client.JiraClient(
            snapshot.base_url, snapshot.account_email, token, build_transport(host)
        )
        del token

        items: list[TaskUpsert] = []
        origin: list[int] = []  # vị trí issue (trong dữ liệu đã tải) của từng item
        seen: set[str] = set()
        fetched = duplicates = 0
        try:
            async with aclosing(jira.search(jql)) as pages:
                async for page in pages:
                    for issue in page.issues:
                        index = fetched
                        fetched += 1
                        notes: list[str] = []
                        try:
                            item = jira_mapping.map_issue(
                                issue,
                                base_url=snapshot.base_url,
                                field_names=page.field_names,
                                fallback_project_key=snapshot.project_key,
                                fallback_project_name=snapshot.project_name,
                                notes=notes,
                            )
                        except jira_mapping.MappingError as exc:
                            progress.error(SyncMessage(index=index, reason=str(exc)))
                            continue
                        if item.external_id in seen:
                            duplicates += 1  # Jira có thể lặp issue giữa các trang
                            continue
                        seen.add(item.external_id)
                        for note in notes:
                            progress.warn(
                                SyncMessage(index=index, external_id=item.external_id, reason=note)
                            )
                        items.append(item)
                        origin.append(index)
                        if len(items) >= MAX_BATCH_ITEMS:
                            await _flush(items, origin, progress, snapshot, host)
                            items, origin = [], []
            await _flush(items, origin, progress, snapshot, host)
        except DomainError as exc:
            if progress.written:
                # Báo rõ phần đã ghi để người dùng biết trạng thái dở dang (last_sync_at
                # không đổi; chạy lại an toàn vì upsert idempotent).
                raise JiraSyncError(
                    f"{exc.message} (Đã ghi {progress.written} task trước khi lỗi; "
                    "last_sync_at giữ nguyên, có thể chạy lại.)",
                    status_code=exc.status_code,
                ) from None
            raise

        if progress.kept_manual_due:
            # Đếm gộp, không liệt kê nội dung Jira.
            progress.warn(
                SyncMessage(
                    reason=(
                        f"Giữ hạn đã sửa tay ở {progress.kept_manual_due} task "
                        "(hạn trên Jira khác nhưng không ghi đè)."
                    )
                )
            )
        if duplicates:
            progress.warn(SyncMessage(reason=f"{duplicates} issue lặp giữa các trang đã bỏ qua"))
        for note in jira.notes:
            progress.warn(SyncMessage(reason=note))
        if jira.truncated:
            limit = (
                f"{jira_client.MAX_PAGES} trang"
                if jira.truncated_reason == "pages"
                else f"{jira_client.MAX_TOTAL_BYTES // (1024 * 1024)} MB dữ liệu"
            )
            progress.warn(
                SyncMessage(
                    reason=(
                        f"Chạm trần {limit}, chưa lấy hết issue. Thu hẹp JQL hoặc dùng since; "
                        "mốc last_sync_at KHÔNG được cập nhật."
                    )
                )
            )
        elif assignees:
            # Lượt lọc theo người chỉ phủ một phần: không được coi là mốc "đã đồng bộ hết".
            progress.warn(
                SyncMessage(reason="Lượt kéo theo người: last_sync_at KHÔNG được cập nhật.")
            )
        else:
            await _mark_synced(connection_id)

    seconds = round(time.monotonic() - started, 2)
    _audit(
        "done",
        connection_id,
        client=client_ip,
        since_minutes=since_minutes,
        fetched=fetched,
        pages=jira.pages,
        added=progress.added,
        updated=progress.updated,
        unchanged=progress.unchanged,
        skipped_personal=progress.skipped_personal,
        errors=len(progress.errors) + progress.error_overflow,
        truncated=jira.truncated,
        seconds=seconds,
    )
    return SyncResult(
        fetched=fetched,
        pages=jira.pages,
        added=progress.added,
        updated=progress.updated,
        unchanged=progress.unchanged,
        skipped_personal=progress.skipped_personal,
        errors=_ordered(progress.errors, progress.error_overflow, "lỗi"),
        warnings=_ordered(progress.warnings, progress.warning_overflow, "cảnh báo"),
        truncated=jira.truncated,
    )
