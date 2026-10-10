"""Hạn cả ngày (due_all_day): quy tắc quá hạn theo NGÀY ở múi giờ người dùng.

Chạy với hai múi giờ lệch nhau 26 giờ (+14 và -12) để bắt lỗi lệch ngày.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.db.session import SessionFactory
from app.models.enums import TaskStatus
from app.models.task import Task

pytestmark = pytest.mark.db

TZ_URL = "/api/v1/settings/display-timezone"
EXTREME_TZ = ["Pacific/Kiritimati", "Etc/GMT+12"]


async def _add(title: str, **over: Any) -> str:
    async with SessionFactory() as s:
        task = Task(title=title, **over)
        s.add(task)
        await s.commit()
        return str(task.id)


def _midnight(day: Any) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


async def _seed(tz: str) -> None:
    today = datetime.now(ZoneInfo(tz)).date()
    await _add("hôm nay", due_at=_midnight(today), due_all_day=True)
    await _add("hôm qua", due_at=_midnight(today - timedelta(days=1)), due_all_day=True)
    await _add("tuần sau", due_at=_midnight(today + timedelta(days=3)), due_all_day=True)
    now = datetime.now(UTC)
    await _add("có giờ đã qua", due_at=now - timedelta(hours=1))
    await _add("có giờ sắp tới", due_at=now + timedelta(hours=3))


def _titles(items: list[dict[str, Any]]) -> set[str]:
    return {item["title"] for item in items}


@pytest.mark.parametrize("tz", EXTREME_TZ)
async def test_all_day_due_today_is_due_soon_not_overdue(
    client: httpx.AsyncClient, tz: str
) -> None:
    assert (await client.put(TZ_URL, json={"timezone": tz})).status_code == 200
    await _seed(tz)

    agenda = (await client.get("/api/v1/tasks/agenda")).json()
    assert agenda["reference_date"] == datetime.now(ZoneInfo(tz)).date().isoformat()
    assert _titles(agenda["overdue"]) == {"hôm qua", "có giờ đã qua"}
    assert _titles(agenda["due_soon"]) == {"hôm nay", "tuần sau", "có giờ sắp tới"}
    assert all(t["is_overdue"] for t in agenda["overdue"])
    assert not any(t["is_overdue"] for t in agenda["due_soon"])

    stats = (await client.get("/api/v1/tasks/stats")).json()
    assert stats["overdue_total"] == 2

    # is_overdue của danh sách (serialize cùng múi giờ với request) khớp agenda.
    listing = (await client.get("/api/v1/tasks?limit=50")).json()
    overdue = {t["title"] for t in listing["items"] if t["is_overdue"]}
    assert overdue == {"hôm qua", "có giờ đã qua"}
    assert all(t["due_all_day"] for t in listing["items"] if t["title"] in ("hôm nay", "hôm qua"))


async def test_closed_all_day_task_is_never_overdue(client: httpx.AsyncClient) -> None:
    await client.put(TZ_URL, json={"timezone": "Etc/GMT+12"})
    today = datetime.now(ZoneInfo("Etc/GMT+12")).date()
    await _add(
        "đã xong",
        due_at=_midnight(today - timedelta(days=5)),
        due_all_day=True,
        status=TaskStatus.DONE,
    )
    stats = (await client.get("/api/v1/tasks/stats")).json()
    assert stats["overdue_total"] == 0


async def test_patch_due_at_clears_all_day_flag(client: httpx.AsyncClient) -> None:
    today = datetime.now(UTC).date()
    task_id = await _add("jira", due_at=_midnight(today), due_all_day=True)
    new_due = (_midnight(today) + timedelta(hours=10)).isoformat()
    resp = await client.patch(f"/api/v1/tasks/{task_id}", json={"due_at": new_due})
    assert resp.status_code == 200
    assert resp.json()["due_all_day"] is False


async def test_db_check_rejects_all_day_not_at_midnight(client: httpx.AsyncClient) -> None:
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError) as exc:
        await _add("sai", due_at=datetime(2026, 10, 9, 10, tzinfo=UTC), due_all_day=True)
    assert "ck_tasks_due_all_day_midnight" in str(exc.value)
    with pytest.raises(IntegrityError):
        await _add("không hạn", due_all_day=True)
