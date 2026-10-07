"""Hàm thuần của chức năng nhập: chuẩn hoá key/màu/category và diff. Không cần DB."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.models.enums import AiLogCategory, TaskStatus
from app.services.import_service import (
    TASK_FIELDS,
    diff_fields,
    map_ai_log_category,
    normalize_color,
    normalize_project_key,
)

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ONE NEXUS", "ONE_NEXUS"),
        ("SAO MỘC", "SAO_MOC"),
        ("KHÁC", "KHAC"),
        ("đường", "DUONG"),
        ("Đà Nẵng", "DA_NANG"),
        ("1ABC", "P_1ABC"),
        ("OMC", "OMC"),
        ("  a - b  ", "A_B"),
    ],
)
def test_normalize_key(raw: str, expected: str) -> None:
    out = normalize_project_key(raw)
    assert out == expected
    assert KEY_RE.match(out)


def test_normalize_key_truncates_and_stays_valid() -> None:
    out = normalize_project_key("MOT TEN PROJECT RAT RAT DAI VA DUNG")
    assert len(out) <= 20
    assert KEY_RE.match(out)
    assert not out.endswith("_")


@pytest.mark.parametrize("raw", ["", "   ", "!!!", "@#$%", "A", "___"])
def test_normalize_key_rejects_unusable(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_project_key(raw)


def test_normalize_color() -> None:
    hsl = normalize_color("hsl(253, 70%, 65%)")
    assert hsl is not None
    assert re.fullmatch(r"#[0-9a-f]{6}", hsl)
    assert normalize_color("#2563EB") == "#2563eb"
    assert normalize_color("#abc") == "#aabbcc"
    assert normalize_color("red") is None
    assert normalize_color(None) is None
    assert normalize_color(123) is None
    # hsl(0, 100%, 50%) là đỏ thuần
    assert normalize_color("hsl(0, 100%, 50%)") == "#ff0000"


def test_map_ai_log_category() -> None:
    assert map_ai_log_category("TOOL") is AiLogCategory.TOOL
    assert map_ai_log_category("UI/UX") is AiLogCategory.WEB
    assert map_ai_log_category("DOCS") is AiLogCategory.OTHER
    assert map_ai_log_category(None) is AiLogCategory.OTHER
    assert map_ai_log_category("") is AiLogCategory.OTHER


def test_diff_ignores_updated_created_and_raw_payload() -> None:
    db = {"title": "a", "updated_at": datetime(2026, 1, 1, tzinfo=UTC), "raw_payload": {"x": 1}}
    file = {"title": "a", "updated_at": datetime(2026, 2, 2, tzinfo=UTC), "raw_payload": None}
    assert diff_fields(db, file, ["title", "updated_at", "created_at", "raw_payload"]) == []


def test_diff_compares_datetimes_by_instant() -> None:
    utc = datetime(2026, 10, 7, 5, 0, tzinfo=UTC)
    vn = utc.astimezone(timezone(timedelta(hours=7)))
    assert diff_fields({"due_at": utc}, {"due_at": vn}, ["due_at"]) == []
    changes = diff_fields({"due_at": utc}, {"due_at": utc + timedelta(minutes=1)}, ["due_at"])
    assert [c.field for c in changes] == ["due_at"]


def test_diff_normalizes_tags_and_enums() -> None:
    assert diff_fields({"tags": ["a-b", "c"]}, {"tags": [" A B ", "C"]}, ["tags"]) == []
    assert diff_fields({"status": TaskStatus.DONE}, {"status": "done"}, ["status"]) == []
    changes = diff_fields({"status": TaskStatus.DONE}, {"status": TaskStatus.TODO}, ["status"])
    assert changes[0].old == "done"
    assert changes[0].new == "todo"


def test_diff_truncates_long_strings_in_report() -> None:
    changes = diff_fields({"description": "x" * 1000}, {"description": "y"}, ["description"])
    assert len(changes[0].old) == 200


def test_task_fields_exclude_protected_columns() -> None:
    assert not {"id", "created_at", "updated_at", "raw_payload", "deleted_at"} & set(TASK_FIELDS)
