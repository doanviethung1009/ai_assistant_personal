"""Hàm thuần của chức năng nhập: chuẩn hoá key/màu/category và diff. Không cần DB."""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.models.enums import TaskStatus
from app.services.import_service import (
    _HSL_RE,
    TASK_FIELDS,
    _raise_if_lock_timeout,
    diff_fields,
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
        ("PROJ", "PROJ"),
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


def test_reporter_is_an_importable_task_field() -> None:
    assert "reporter" in TASK_FIELDS


def test_import_task_reporter_is_cleaned_and_bounded() -> None:
    from pydantic import ValidationError

    from app.schemas.imports import ImportTask

    base = {"id": "aaaaaaa1-0000-4000-8000-000000000001", "title": "t"}
    assert ImportTask.model_validate({**base, "reporter": "  Lan "}).reporter == "Lan"
    assert ImportTask.model_validate({**base, "reporter": "  "}).reporter is None
    assert ImportTask.model_validate(base).reporter is None
    with pytest.raises(ValidationError):
        ImportTask.model_validate({**base, "reporter": "x" * 201})


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


@pytest.mark.parametrize(
    "payload",
    [
        "hsl(1" + " " * 8000,
        "hsl(1" + " " * 8000 + "x",
        "hsl(1 1%" + " " * 8000,
        "hsl(1 1% 1%" + " " * 8000,
        "hsl(1" + " 1" * 4000,
        "hsl(1deg" + " " * 8000 + "%",
    ],
)
def test_hsl_regex_is_not_redos_prone(payload: str) -> None:
    """Gọi THẲNG regex (không qua normalize_color): kiểm giới hạn độ dài sẽ che mất lỗi.

    Regex cũ `\\s*[, ]\\s*` backtrack bậc hai: 8000 dấu cách mất ~0,4s, test này đỏ.
    """
    start = time.perf_counter()
    _HSL_RE.fullmatch(payload)
    assert (time.perf_counter() - start) < 0.05


def test_normalize_color_short_adversarial_input_is_fast() -> None:
    # Ngắn hơn MAX_COLOR_LEN nên thật sự đi qua regex.
    payload = "hsl(1" + " " * 55
    assert len(payload) <= 64
    start = time.perf_counter()
    assert normalize_color(payload) is None
    assert normalize_color("hsl(1" + " " * 100_000) is None  # bị chặn bởi giới hạn độ dài
    assert (time.perf_counter() - start) < 0.05


def test_retryable_lock_codes_become_conflict() -> None:
    from sqlalchemy.exc import DBAPIError

    from app.services.errors import ConflictError

    class FakeOrig(Exception):
        def __init__(self, sqlstate: str) -> None:
            super().__init__("x")
            self.sqlstate = sqlstate

    for code in ("55P03", "40P01"):
        with pytest.raises(ConflictError):
            _raise_if_lock_timeout(DBAPIError("stmt", {}, FakeOrig(code)))
    # Mã khác không bị nuốt: hàm không ném gì để caller xử lý như lỗi dữ liệu.
    _raise_if_lock_timeout(DBAPIError("stmt", {}, FakeOrig("23514")))


def test_short_jwt_secret_is_rejected_and_not_leaked() -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    short = "ngan-lo-ra-x"
    with pytest.raises(ValidationError) as info:
        Settings(core_jwt_secret=short)  # type: ignore[call-arg]
    assert short not in str(info.value)


def test_missing_jwt_secret_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail closed: thiếu CORE_JWT_SECRET thì cấu hình không dựng được, core không lên."""
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.delenv("CORE_JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_admin_emails_and_hd_are_split_and_lowercased() -> None:
    from app.core.config import Settings

    cfg = Settings(admin_emails=" A@X.com, b@y.com ,, ", google_allowed_hd="Corp.COM")  # type: ignore[call-arg]
    assert cfg.admin_emails == ["a@x.com", "b@y.com"]
    assert cfg.google_allowed_hd == ["corp.com"]
    assert "test-core-jwt-secret" not in repr(cfg)


def test_normalize_color_rejects_overlong_input() -> None:
    long_but_valid_shape = "hsl(" + "1" * 200 + ", 50%, 50%)"
    assert normalize_color(long_but_valid_shape) is None
    assert normalize_color("#" + "a" * 70) is None


def test_normalize_color_hsl_separators() -> None:
    assert normalize_color("hsl(0 100% 50%)") == "#ff0000"
    assert normalize_color("HSL(0,100%,50%)") == "#ff0000"
    assert normalize_color("hsl(0deg, 100%, 50%)") == "#ff0000"


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
