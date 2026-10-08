"""Logic lịch sử duyệt web: chuẩn hoá URL, upsert không bao giờ giảm, tìm kiếm, xoá.

Nguyên tắc: nguồn gốc dữ liệu là file `History` của Chrome ở máy chạy web, bảng này chỉ
là bản sao tích luỹ. Vì vậy mọi đường ghi đều là upsert theo `(profile, url_hash)` lấy
số LỚN HƠN: gửi lại lô cũ, gửi lô chồng lấn, hay nhập lại file cũ đều không thể làm
`visit_count` hay `last_visit_at` lùi.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import and_, case, delete, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.browser_history import BrowserHistory
from app.schemas.browser_history import (
    BrowserHistoryBatchResult,
    BrowserHistoryImportReport,
    BrowserHistoryItem,
    ChromeHistoryFile,
    ChromeHistoryRow,
    clean_profile,
)
from app.services import clock
from app.services.errors import ValidationError

logger = logging.getLogger(__name__)

MAX_URL_LEN = 4096
MAX_TITLE_LEN = 2000
# asyncpg giới hạn 32 767 tham số mỗi câu lệnh; mỗi dòng 8 tham số (7 cột + id).
_CHUNK = 2000
_PARAMS_PER_ROW = 8
assert _CHUNK * _PARAMS_PER_ROW <= 32767
_DEFAULT_PORTS = {"http": 80, "https": 443}

# ═══════════════════════════════════════════════════════════════════════
#  Chuẩn hoá (hàm thuần, không chạm DB)
# ═══════════════════════════════════════════════════════════════════════


def normalize_profile(value: str) -> str:
    """Như `clean_profile` nhưng báo lỗi dạng DomainError cho đường query (DELETE/import)."""
    try:
        return clean_profile(value)
    except ValueError as exc:
        raise ValidationError(f"profile không hợp lệ: {exc}") from exc


def normalize_url(raw: str) -> str | None:
    """Trả URL đã bỏ query, fragment, userinfo; None nếu không nhận.

    CHỈ http/https. Các scheme khác (`javascript:`, `data:`, `file:`, `chrome:`) hoặc
    không có host đều bị loại: chúng không phải lịch sử duyệt web có ích, và `javascript:`
    sẽ thành link nguy hiểm khi UI render. Userinfo (`user:pass@`) bị bỏ vì là credential.
    """
    candidate = raw.strip()
    if not candidate or len(candidate) > MAX_URL_LEN:
        return None
    # Khoảng trắng/điều khiển giữa URL: URL hợp lệ đã được percent-encode. NUL còn làm
    # Postgres từ chối cả lô.
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
        return None
    try:
        parts = urlsplit(candidate)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS or not host:
        return None
    try:
        is_v6 = ipaddress.ip_address(host).version == 6
    except ValueError:
        is_v6 = False
    netloc = f"[{host}]" if is_v6 else host
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        netloc = f"{netloc}:{port}"
    return f"{scheme}://{netloc}{parts.path or '/'}"


def url_hash(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def to_utc(value: datetime) -> datetime:
    """Không múi giờ = giờ địa phương theo `display_timezone` (đúng định dạng file Chrome).

    CẠM BẪY DST: giờ trùng/không tồn tại quanh lúc chuyển giờ được giải theo `fold=0`.
    Múi Asia/Ho_Chi_Minh không có DST nên không ảnh hưởng mặc định.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=clock.display_tz())
    return value.astimezone(UTC)


def escape_like(term: str) -> str:
    r"""Escape `\`, `%`, `_` để người dùng gõ ký tự đó thì tìm đúng ký tự, không thành wildcard."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ═══════════════════════════════════════════════════════════════════════
#  Ghi
# ═══════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class _Row:
    url: str
    title: str
    visit_count: int
    last_visit_at: datetime


def _clean_title(value: str | None) -> str:
    # NUL làm Postgres từ chối cả lô; cắt độ dài để một tiêu đề khổng lồ không phình bảng.
    return (value or "").replace("\x00", "").strip()[:MAX_TITLE_LEN]


def _merge(rows: dict[str, _Row], key: str, new: _Row) -> None:
    """Gộp trùng trong cùng lô: ON CONFLICT không được đụng một dòng hai lần."""
    old = rows.get(key)
    if old is None:
        rows[key] = new
        return
    newer = new.last_visit_at >= old.last_visit_at
    old.visit_count = max(old.visit_count, new.visit_count)
    if newer and new.title:
        old.title = new.title
    old.last_visit_at = max(old.last_visit_at, new.last_visit_at)


async def _upsert(
    session: AsyncSession, profile: str, rows: dict[str, _Row], synced_at: datetime
) -> tuple[int, int]:
    """Upsert theo `(profile, url_hash)`; trả (created, updated).

    DO UPDATE chỉ chạy khi có số liệu mới hơn, nên dòng không đổi không sinh bản ghi
    chết (dead tuple) và không xuất hiện trong RETURNING. `xmax = 0` là mẹo của Postgres
    để phân biệt INSERT với UPDATE trong RETURNING.
    """
    created = updated = 0
    # Sắp theo url_hash: hai lô cùng profile chạy song song khoá dòng theo cùng một thứ tự
    # nên không thể chờ nhau vòng tròn (deadlock).
    items = sorted(rows.items())
    for start in range(0, len(items), _CHUNK):
        values = [
            {
                "profile": profile,
                "url": r.url,
                "url_hash": h,
                "title": r.title,
                "visit_count": r.visit_count,
                "last_visit_at": r.last_visit_at,
                "synced_at": synced_at,
            }
            for h, r in items[start : start + _CHUNK]
        ]
        stmt = pg_insert(BrowserHistory).values(values)
        ex = stmt.excluded
        tbl = BrowserHistory.__table__
        stmt = stmt.on_conflict_do_update(
            constraint="uq_browser_history_profile_url_hash",
            set_={
                "visit_count": func.greatest(tbl.c.visit_count, ex.visit_count),
                "last_visit_at": func.greatest(tbl.c.last_visit_at, ex.last_visit_at),
                # Tiêu đề lấy từ lần ghé mới nhất; không để tiêu đề rỗng đè tiêu đề cũ.
                "title": case(
                    (
                        and_(ex.title != "", ex.last_visit_at >= tbl.c.last_visit_at),
                        ex.title,
                    ),
                    else_=tbl.c.title,
                ),
                "synced_at": ex.synced_at,
            },
            where=or_(
                ex.visit_count > tbl.c.visit_count,
                ex.last_visit_at > tbl.c.last_visit_at,
            ),
        ).returning(literal_column("(xmax = 0)").label("inserted"))
        result = await session.execute(stmt)
        for inserted in result.scalars():
            if inserted:
                created += 1
            else:
                updated += 1
    return created, updated


async def upsert_batch(
    session: AsyncSession,
    profile: str,
    items: Sequence[BrowserHistoryItem],
    *,
    synced_at: datetime | None = None,
) -> BrowserHistoryBatchResult:
    """Đường ghi chung của `/batch`. Gửi lại cùng lô là no-op (toàn bộ vào `unchanged`)."""
    merged: dict[str, _Row] = {}
    invalid = 0
    for item in items:
        normalized = normalize_url(item.url)
        if normalized is None:
            invalid += 1
            continue
        _merge(
            merged,
            url_hash(normalized),
            _Row(
                normalized, _clean_title(item.title), item.visit_count, to_utc(item.last_visit_at)
            ),
        )
    valid = len(items) - invalid
    created, updated = await _upsert(session, profile, merged, synced_at or clock.now_utc())
    return BrowserHistoryBatchResult(
        received=len(items),
        created=created,
        updated=updated,
        unchanged=valid - created - updated,
        invalid=invalid,
    )


async def import_chrome_history(
    session: AsyncSession,
    envelope: ChromeHistoryFile,
    *,
    profile: str,
    dry_run: bool,
    file_sha256: str,
    client_ip: str | None = None,
) -> BrowserHistoryImportReport:
    """Nhập `chrome-history.json`. Dry-run chạy đúng đường ghi rồi ROLLBACK.

    Chạy thật để đếm (thay vì tự đoán bằng SELECT) đảm bảo báo cáo dry-run khớp tuyệt đối
    với lần nhập thật. Không có audit/hoàn tác như B1 vì thao tác chỉ làm số liệu tăng.
    """
    items: list[BrowserHistoryItem] = []
    invalid = 0
    for raw in envelope.items:
        try:
            row = ChromeHistoryRow.model_validate(raw)
        except PydanticValidationError:
            invalid += 1
            continue
        items.append(
            BrowserHistoryItem(
                url=row.url,
                title=row.title,
                visit_count=row.visit_count,
                last_visit_at=row.last_visit_time,
            )
        )
    result = await upsert_batch(
        session, profile, items, synced_at=_parse_synced_at(envelope.synced_at)
    )
    if dry_run:
        await session.rollback()
    else:
        # Không log URL hay secret: chỉ số liệu và dấu vết file để điều tra.
        logger.info(
            "nhập lịch sử duyệt web: profile=%s created=%d updated=%d unchanged=%d "
            "invalid=%d file_sha256=%s client=%s",
            profile,
            result.created,
            result.updated,
            result.unchanged,
            result.invalid + invalid,
            file_sha256,
            client_ip or "không rõ",
        )
    return BrowserHistoryImportReport(
        received=len(envelope.items),
        created=result.created,
        updated=result.updated,
        unchanged=result.unchanged,
        invalid=result.invalid + invalid,
        dry_run=dry_run,
        committed=not dry_run,
        profile=profile,
        file_sha256=file_sha256,
    )


def _parse_synced_at(value: str | None) -> datetime:
    """`synced_at` của file nếu đọc được, không thì bây giờ. Không bao giờ làm hỏng cả lần nhập."""
    if value:
        try:
            return to_utc(datetime.fromisoformat(value))
        except ValueError:
            pass
    return clock.now_utc()


# ═══════════════════════════════════════════════════════════════════════
#  Đọc / xoá
# ═══════════════════════════════════════════════════════════════════════


async def list_history(
    session: AsyncSession, *, q: str | None, profile: str | None, limit: int, offset: int
) -> tuple[list[BrowserHistory], int]:
    base = select(BrowserHistory)
    if profile:
        profile = normalize_profile(profile)
        base = base.where(BrowserHistory.profile == profile)
    term = (q or "").strip()
    if term:
        pattern = f"%{escape_like(term)}%"
        base = base.where(
            or_(
                BrowserHistory.url.ilike(pattern, escape="\\"),
                BrowserHistory.title.ilike(pattern, escape="\\"),
            )
        )
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    # id làm khoá phụ: nhiều dòng cùng last_visit_at thì trang không được trùng/sót.
    stmt = (
        base.order_by(BrowserHistory.last_visit_at.desc(), BrowserHistory.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def delete_profile(session: AsyncSession, profile: str) -> int:
    result: Any = await session.execute(
        delete(BrowserHistory).where(BrowserHistory.profile == profile)
    )
    return int(result.rowcount or 0)
