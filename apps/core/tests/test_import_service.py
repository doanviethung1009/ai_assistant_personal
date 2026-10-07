"""Service nhập dữ liệu trên Postgres thật: ánh xạ, idempotent, replace, rào chắn.

Fixture trong tests/fixtures/ là dữ liệu TỔNG HỢP. Test với file thật của User nằm
ở cuối file, chỉ chạy khi có biến môi trường và chỉ mở file ở chế độ đọc.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine
from app.schemas.imports import AiLogsEnvelope, DataFileEnvelope, ImportReport
from app.services import import_service
from app.services.errors import ConflictError, ValidationError

pytestmark = pytest.mark.db

FIXTURES = Path(__file__).parent / "fixtures"
SHA = "0" * 64

P1 = uuid.UUID("11111111-1111-4111-8111-111111111111")
P3 = uuid.UUID("33333333-3333-4333-8333-333333333333")
T1 = uuid.UUID("aaaaaaa1-0000-4000-8000-000000000001")
T2 = uuid.UUID("aaaaaaa2-0000-4000-8000-000000000002")
T3 = uuid.UUID("aaaaaaa3-0000-4000-8000-000000000003")
T_TRASH = uuid.UUID("aaaaaaa4-0000-4000-8000-000000000004")
N1 = uuid.UUID("bbbbbbb1-0000-4000-8000-000000000001")

TABLES = [
    "projects",
    "tasks",
    "task_events",
    "notes",
    "ai_logs",
    "import_runs",
    "import_audit",
]


def _load(name: str = "datafile_sample.json") -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


async def _import(
    session: AsyncSession,
    data: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    expect: int | None = 0,
) -> ImportReport:
    envelope = DataFileEnvelope.model_validate(data if data is not None else _load())
    return await import_service.import_datafile(
        session,
        envelope,
        dry_run=dry_run,
        expect_replaced=None if dry_run else expect,
        file_sha256=SHA,
    )


async def _row_counts(session: AsyncSession) -> dict[str, int]:
    out: dict[str, int] = {}
    for table in TABLES:
        out[table] = int(await session.scalar(text(f"SELECT count(*) FROM {table}")) or 0)  # noqa: S608
    return out


async def _task(session: AsyncSession, task_id: uuid.UUID) -> dict[str, Any]:
    result = await session.execute(text("SELECT * FROM tasks WHERE id = :id"), {"id": task_id})
    return dict(result.mappings().one())


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# ── Nhập vào DB rỗng ────────────────────────────────────────────────


async def test_import_into_empty_db(session: AsyncSession) -> None:
    report = await _import(session)
    assert report.committed, report.issues
    assert report.errors == 0
    c = report.counts
    assert (c["projects"].received, c["projects"].created) == (3, 3)
    assert (c["tasks"].received, c["tasks"].created, c["tasks"].skipped_trash) == (4, 3, 1)
    assert c["task_events"].created == 2
    assert c["task_events"].skipped_trash == 1
    assert (c["notes"].received, c["notes"].created, c["notes"].skipped_trash) == (2, 1, 1)
    assert sum(x.replaced for x in c.values()) == 0
    assert {(k.original, k.normalized) for k in report.project_key_changes} == {
        ("ONE NEXUS", "ONE_NEXUS"),
        ("SAO MỘC", "SAO_MOC"),
    }
    assert "raw_payload" in report.ignored_fields["task"]
    assert "project" in report.ignored_fields["task"]
    assert "is_overdue" in report.ignored_fields["task"]
    assert {"unknown_top_level", "meta"} <= set(report.ignored_fields["file"])

    # Project: id giữ nguyên, key và màu được chuẩn hoá.
    row = (
        await session.execute(text("SELECT key, color FROM projects WHERE id = :i"), {"i": P1})
    ).one()
    assert row.key == "ONE_NEXUS"
    assert row.color and row.color.startswith("#") and len(row.color) == 7
    red = await session.scalar(text("SELECT color FROM projects WHERE id = :i"), {"i": P3})
    assert red is None

    t1 = await _task(session, T1)
    assert t1["project_id"] == P1
    assert t1["assignee"] == "Nguoi Mot"
    assert t1["source"] == "jira"
    assert t1["external_id"] == "DEMO-1"
    assert t1["spent_minutes"] == 30
    assert t1["tags"] == ["backend", "api"]
    assert t1["created_at"] == _utc(2026, 9, 10, 9)
    assert t1["updated_at"] == _utc(2026, 9, 20, 9)
    # done mà thiếu completed_at: lấy theo updated_at, không lấy giờ nhập.
    assert t1["completed_at"] == _utc(2026, 9, 20, 9)
    assert t1["raw_payload"] is None

    # Task không có project_id nhưng có project.key nhúng: liên kết qua key.
    assert (await _task(session, T2))["project_id"] == P3
    assert (await _task(session, T3))["source"] == "manual"
    assert (
        await session.scalar(text("SELECT count(*) FROM tasks WHERE id = :i"), {"i": T_TRASH}) == 0
    )

    # Event gốc giữ id; mỗi task mới có thêm một event `synced` mang import_id.
    ev_ids = {r[0] for r in (await session.execute(text("SELECT id FROM task_events"))).all()}
    assert uuid.UUID("eeeeeee1-0000-4000-8000-000000000001") in ev_ids
    synced = (
        await session.execute(
            text(
                "SELECT payload->>'import_id' AS iid, actor FROM task_events "
                "WHERE event_type = 'synced'"
            )
        )
    ).all()
    assert len(synced) == 3
    assert {r.iid for r in synced} == {str(report.import_id)}
    assert {r.actor for r in synced} == {"import:datafile"}

    counts = await _row_counts(session)
    assert counts["import_runs"] == 1
    # 3 project + 3 task + 2 event + 1 note
    assert counts["import_audit"] == 9
    actions = await session.scalar(
        text("SELECT count(*) FROM import_audit WHERE action = 'created'")
    )
    assert actions == 9
    run = (await session.execute(text("SELECT kind, file_sha256, actor FROM import_runs"))).one()
    assert (run.kind, run.file_sha256, run.actor) == ("datafile", SHA, "import:datafile")


async def test_import_is_idempotent(session: AsyncSession) -> None:
    first = await _import(session)
    assert first.committed
    before = await _row_counts(session)

    second = await _import(session)
    assert second.committed
    assert second.errors == 0
    for key in ("projects", "tasks", "notes"):
        assert second.counts[key].created == 0
        assert second.counts[key].replaced == 0
    assert second.counts["projects"].unchanged == 3
    assert second.counts["tasks"].unchanged == 3
    assert second.counts["task_events"].created == 0
    assert second.counts["task_events"].unchanged == 2
    after = await _row_counts(session)
    # Chỉ thêm một dòng import_runs, không thêm bản ghi nghiệp vụ hay event nào.
    assert after["import_runs"] == before["import_runs"] + 1
    assert {k: v for k, v in after.items() if k != "import_runs"} == {
        k: v for k, v in before.items() if k != "import_runs"
    }


# ── Dry-run ─────────────────────────────────────────────────────────


async def test_dry_run_writes_nothing_and_matches_real_run(session: AsyncSession) -> None:
    await _import(session)
    await session.execute(
        text("UPDATE tasks SET status = 'todo', title = 'Sua tay' WHERE id = :i"), {"i": T1}
    )
    await session.commit()
    before = await _row_counts(session)

    dry = await _import(session, dry_run=True)
    assert dry.dry_run and not dry.committed
    assert await _row_counts(session) == before
    assert (await _task(session, T1))["title"] == "Sua tay"

    real = await _import(session, expect=dry.counts["tasks"].replaced)
    assert real.committed
    assert {k: v.model_dump() for k, v in real.counts.items()} == {
        k: v.model_dump() for k, v in dry.counts.items()
    }
    assert [r.model_dump(exclude={"changes"}) for r in real.replacements] == [
        r.model_dump(exclude={"changes"}) for r in dry.replacements
    ]
    assert [r.changes for r in real.replacements] == [r.changes for r in dry.replacements]


# ── Replace ─────────────────────────────────────────────────────────


async def test_replace_overwrites_with_file_and_keeps_audit(session: AsyncSession) -> None:
    await _import(session)
    await session.execute(
        text(
            "UPDATE tasks SET status = 'todo', title = 'Sua tay', "
            "raw_payload = CAST(:rp AS jsonb), updated_at = :ua WHERE id = :i"
        ),
        {"rp": '{"giu": "nguyen"}', "ua": _utc(2027, 1, 1), "i": T1},
    )
    await session.commit()

    dry = await _import(session, dry_run=True)
    assert dry.counts["tasks"].replaced == 1
    assert dry.counts["tasks"].replaced_older == 1
    (rep,) = dry.replacements
    assert rep.entity == "task"
    assert rep.id == T1
    assert rep.matched_by == "id"
    assert rep.file_older_than_db is True
    assert {c.field for c in rep.changes} == {"status", "title"}

    report = await _import(session, expect=1)
    assert report.committed
    t1 = await _task(session, T1)
    assert t1["status"] == "done"
    assert t1["title"] == "Task tong hop 1"
    # updated_at lấy từ file, không bị onupdate=now() đè.
    assert t1["updated_at"] == _utc(2026, 9, 20, 9)
    assert t1["raw_payload"] == {"giu": "nguyen"}

    updated = (
        await session.execute(
            text(
                "SELECT actor, payload FROM task_events "
                "WHERE task_id = :i AND event_type = 'updated'"
            ),
            {"i": T1},
        )
    ).one()
    assert updated.actor == "import:datafile"
    assert updated.payload["import_id"] == str(report.import_id)
    assert set(updated.payload["changes"]) == {"status", "title"}
    assert updated.payload["changes"]["title"] == {"old": "Sua tay", "new": "Task tong hop 1"}

    audit = (
        await session.execute(
            text(
                "SELECT before, changed_fields FROM import_audit "
                "WHERE import_id = :r AND entity = 'task' AND action = 'replaced'"
            ),
            {"r": report.import_id},
        )
    ).one()
    assert audit.before["title"] == "Sua tay"
    assert audit.before["status"] == "todo"
    assert sorted(audit.changed_fields) == ["status", "title"]


async def test_replace_matches_by_natural_key(session: AsyncSession) -> None:
    db_project = uuid.uuid4()
    db_task = uuid.uuid4()
    await session.execute(
        text("INSERT INTO projects (id, key, name) VALUES (:i, 'OMC', 'Ten khac trong DB')"),
        {"i": db_project},
    )
    await session.execute(
        text(
            "INSERT INTO tasks (id, title, source, external_id) "
            "VALUES (:i, 'Tieu de DB', 'jira', 'DEMO-2')"
        ),
        {"i": db_task},
    )
    await session.commit()

    dry = await _import(session, dry_run=True)
    by_entity = {r.entity: r for r in dry.replacements}
    assert by_entity["project"].matched_by == "natural_key"
    assert by_entity["project"].id == db_project
    assert by_entity["project"].file_id == P3
    assert by_entity["task"].matched_by == "natural_key"
    assert by_entity["task"].id == db_task
    assert by_entity["task"].file_id == T2

    report = await _import(session, expect=dry.counts["projects"].replaced + 1)
    assert report.committed, report.issues
    # Không tạo bản mới với id của file; project có đúng 3 dòng (1 của DB + 2 mới).
    assert await session.scalar(text("SELECT count(*) FROM projects WHERE key = 'OMC'")) == 1
    assert await session.scalar(text("SELECT count(*) FROM projects WHERE id = :i"), {"i": P3}) == 0
    assert await session.scalar(text("SELECT count(*) FROM projects")) == 3
    assert await session.scalar(text("SELECT count(*) FROM tasks WHERE id = :i"), {"i": T2}) == 0
    row = await _task(session, db_task)
    assert row["title"] == "Task tong hop 2"
    # Task trỏ về id project của DB chứ không phải id trong file.
    assert row["project_id"] == db_project
    # Event của task khớp được gắn vào id DB (ở đây có 1 event `updated` do chính lần nhập sinh).
    assert (
        await session.scalar(
            text("SELECT count(*) FROM task_events WHERE task_id = :i"), {"i": db_task}
        )
        == 1
    )


# ── Thùng rác, không xoá ────────────────────────────────────────────


async def test_trash_in_db_is_not_resurrected_or_overwritten(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO tasks (id, title, source, deleted_at) "
            "VALUES (:i, 'Da xoa trong DB', 'manual', :d)"
        ),
        {"i": T1, "d": _utc(2026, 9, 30)},
    )
    await session.commit()

    report = await _import(session)
    assert report.committed
    assert report.counts["tasks"].skipped_trash_in_db == 1
    assert report.counts["tasks"].created == 2
    row = await _task(session, T1)
    assert row["deleted_at"] == _utc(2026, 9, 30)
    assert row["title"] == "Da xoa trong DB"
    # Event của task bị bỏ qua cũng không được chèn.
    assert (
        await session.scalar(text("SELECT count(*) FROM task_events WHERE task_id = :i"), {"i": T1})
        == 0
    )


async def test_trashed_in_file_leaves_db_row_untouched(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO tasks (id, title, source, external_id) "
            "VALUES (:i, 'Con song trong DB', 'jira', 'DEMO-TRASH')"
        ),
        {"i": T_TRASH},
    )
    await session.commit()

    report = await _import(session)
    assert report.committed
    assert report.counts["tasks"].skipped_trash == 1
    row = await _task(session, T_TRASH)
    assert row["deleted_at"] is None
    assert row["title"] == "Con song trong DB"


async def test_import_never_deletes_db_only_rows(session: AsyncSession) -> None:
    extra_project, extra_task = uuid.uuid4(), uuid.uuid4()
    await session.execute(
        text("INSERT INTO projects (id, key, name) VALUES (:i, 'ONLYDB', 'Chi co trong DB')"),
        {"i": extra_project},
    )
    await session.execute(
        text("INSERT INTO tasks (id, title) VALUES (:i, 'Chi co trong DB')"), {"i": extra_task}
    )
    await session.commit()

    report = await _import(session)
    assert report.committed
    assert (
        await session.scalar(
            text("SELECT count(*) FROM projects WHERE id = :i"), {"i": extra_project}
        )
        == 1
    )
    assert (
        await session.scalar(text("SELECT count(*) FROM tasks WHERE id = :i"), {"i": extra_task})
        == 1
    )


# ── Rào chắn ────────────────────────────────────────────────────────


async def test_expect_replaced_mismatch_rolls_back(session: AsyncSession) -> None:
    await _import(session)
    await session.execute(text("UPDATE tasks SET title = 'Sua 1' WHERE id = :i"), {"i": T1})
    await session.commit()
    dry = await _import(session, dry_run=True)
    assert dry.counts["tasks"].replaced == 1

    # DB đổi thêm sau dry-run.
    await session.execute(text("UPDATE tasks SET title = 'Sua 2' WHERE id = :i"), {"i": T2})
    await session.commit()
    before = await _row_counts(session)

    report = await _import(session, expect=1)
    assert not report.committed
    assert "replace_count_mismatch" in {i.code for i in report.issues}
    assert await _row_counts(session) == before
    assert (await _task(session, T1))["title"] == "Sua 1"
    assert (await _task(session, T2))["title"] == "Sua 2"


async def test_real_import_requires_expect_replaced(session: AsyncSession) -> None:
    with pytest.raises(ValidationError):
        await import_service.import_datafile(
            session,
            DataFileEnvelope.model_validate(_load()),
            dry_run=False,
            expect_replaced=None,
            file_sha256=SHA,
        )


async def test_all_or_nothing_on_invalid_row(session: AsyncSession) -> None:
    data = _load()
    bad = deepcopy(data["tasks"][2])
    bad["id"] = str(uuid.uuid4())
    bad["status"] = "khong-co-trang-thai-nay"
    bad["external_id"] = None
    data["tasks"].append(bad)
    before = await _row_counts(session)

    report = await _import(session, data)
    assert not report.committed
    assert report.errors >= 1
    assert "invalid_enum" in {i.code for i in report.issues}
    assert report.counts["tasks"].invalid == 1
    assert await _row_counts(session) == before


async def test_duplicate_external_id_in_file_is_error(session: AsyncSession) -> None:
    data = _load()
    clone = deepcopy(data["tasks"][1])
    clone["id"] = str(uuid.uuid4())
    data["tasks"].append(clone)  # cùng (jira, DEMO-2) với task thứ hai
    report = await _import(session, data)
    assert not report.committed
    assert "duplicate_external_id" in {i.code for i in report.issues}


async def test_replace_that_collides_with_another_live_row_is_error(
    session: AsyncSession,
) -> None:
    await _import(session)
    # Task T2 trong DB đổi external_id; file vẫn nói DEMO-2 và id T2 khớp bằng id.
    # Bản DEMO-2 hiện thuộc về một task khác => ghi đè T2 sẽ trùng khoá tự nhiên.
    thief = uuid.uuid4()
    await session.execute(
        text("UPDATE tasks SET external_id = 'DEMO-2-OLD' WHERE id = :i"), {"i": T2}
    )
    await session.execute(
        text(
            "INSERT INTO tasks (id, title, source, external_id) "
            "VALUES (:i, 'Trom khoa', 'jira', 'DEMO-2')"
        ),
        {"i": thief},
    )
    await session.commit()
    before = await _row_counts(session)

    report = await _import(session)
    assert not report.committed
    assert "natural_key_conflict" in {i.code for i in report.issues}
    assert await _row_counts(session) == before


async def test_advisory_lock_held_elsewhere_raises_conflict(session: AsyncSession) -> None:
    async with engine.connect() as other:
        await other.execute(text("SELECT pg_advisory_lock(hashtext('builder:import'))"))
        try:
            with pytest.raises(ConflictError):
                await _import(session, dry_run=True)
        finally:
            await other.execute(text("SELECT pg_advisory_unlock(hashtext('builder:import'))"))
    # Khoá đã nhả: chạy lại bình thường.
    assert (await _import(session, dry_run=True)).errors == 0


# ── ai_logs ─────────────────────────────────────────────────────────


async def _import_logs(
    session: AsyncSession, data: dict[str, Any] | None = None, *, dry_run: bool = False
) -> ImportReport:
    envelope = AiLogsEnvelope.model_validate(
        data if data is not None else _load("ai_logs_sample.json")
    )
    return await import_service.import_ai_logs(
        session,
        envelope,
        dry_run=dry_run,
        expect_replaced=None if dry_run else 0,
        file_sha256=SHA,
    )


async def test_import_ai_logs_maps_category_and_fills_handling(session: AsyncSession) -> None:
    report = await _import_logs(session)
    assert report.committed, report.issues
    assert report.counts["ai_logs"].created == 4
    rows = (
        await session.execute(
            text("SELECT category, handling, prompt FROM ai_logs ORDER BY prompt")
        )
    ).all()
    assert [r.category for r in rows] == ["tool", "web", "other", "web"]
    assert rows[1].handling == "(không ghi nhận)"
    assert rows[0].handling == "Da xu ly 1"
    assert "category_unknown" in {i.code for i in report.issues}

    again = await _import_logs(session)
    assert again.counts["ai_logs"].created == 0
    assert again.counts["ai_logs"].replaced == 0
    assert again.counts["ai_logs"].unchanged == 4
    assert await session.scalar(text("SELECT count(*) FROM ai_logs")) == 4


async def test_ai_log_replace(session: AsyncSession) -> None:
    await _import_logs(session)
    await session.execute(
        text("UPDATE ai_logs SET response = 'Sua tay' WHERE prompt = 'Prompt tong hop 1'")
    )
    await session.commit()
    dry = await _import_logs(session, dry_run=True)
    assert dry.counts["ai_logs"].replaced == 1
    assert dry.replacements[0].changes[0].field == "response"


# ═══════════════════════════════════════════════════════════════════════
#  File thật của User (chỉ đọc, bỏ qua khi thiếu biến môi trường)
# ═══════════════════════════════════════════════════════════════════════

REAL_DATAFILE = os.environ.get("IMPORT_REAL_DATAFILE")
REAL_AILOGS = os.environ.get("IMPORT_REAL_AILOGS")


def _read_only_fingerprint(path: Path) -> tuple[str, float, bytes]:
    """Đọc file bằng 'rb' và trả (sha256, mtime, bytes). Tuyệt đối không ghi."""
    with path.open("rb") as handle:
        body = handle.read()
    return hashlib.sha256(body).hexdigest(), path.stat().st_mtime, body


@pytest.mark.skipif(not REAL_DATAFILE, reason="cần IMPORT_REAL_DATAFILE")
async def test_real_file_datafile(session: AsyncSession) -> None:
    assert REAL_DATAFILE
    path = Path(REAL_DATAFILE)
    sha_before, mtime_before, body = _read_only_fingerprint(path)
    envelope = DataFileEnvelope.model_validate(json.loads(body))

    async def run(dry_run: bool) -> ImportReport:
        return await import_service.import_datafile(
            session,
            envelope,
            dry_run=dry_run,
            expect_replaced=None if dry_run else 0,
            file_sha256=sha_before,
        )

    dry = await run(True)
    print(
        "\n[real datafile dry-run]",
        {k: v.model_dump() for k, v in dry.counts.items()},
        "errors", dry.errors, "warnings", dry.warnings,
        "key_changes", [(k.original, k.normalized) for k in dry.project_key_changes],
        "color_warnings", sum(1 for i in dry.issues if i.code == "color_converted"),
        "ignored", dry.ignored_fields,
    )  # fmt: skip
    assert dry.errors == 0, [i for i in dry.issues if i.level == "error"][:5]
    assert dry.counts["projects"].received == 14
    assert dry.counts["tasks"].received == 498
    assert dry.counts["notes"].received == 0
    assert len(dry.project_key_changes) == 3
    assert sum(1 for i in dry.issues if i.code == "color_converted") == 14
    assert sum(c.replaced for c in dry.counts.values()) == 0

    real = await run(False)
    assert real.committed, real.issues[:5]
    assert real.counts["projects"].created == 14
    assert real.counts["tasks"].created == 498

    again = await run(False)
    assert again.committed
    assert again.counts["projects"].created == again.counts["projects"].replaced == 0
    assert again.counts["tasks"].created == again.counts["tasks"].replaced == 0
    assert again.counts["projects"].unchanged == 14
    assert again.counts["tasks"].unchanged == 498

    sha_after, mtime_after, _ = _read_only_fingerprint(path)
    assert (sha_after, mtime_after) == (sha_before, mtime_before)


@pytest.mark.skipif(not REAL_AILOGS, reason="cần IMPORT_REAL_AILOGS")
async def test_real_file_ai_logs(session: AsyncSession, client: Any) -> None:
    assert REAL_AILOGS
    path = Path(REAL_AILOGS)
    sha_before, mtime_before, body = _read_only_fingerprint(path)
    envelope = AiLogsEnvelope.model_validate(json.loads(body))

    dry = await import_service.import_ai_logs(
        session, envelope, dry_run=True, expect_replaced=None, file_sha256=sha_before
    )
    print("\n[real ai-logs dry-run]", dry.counts["ai_logs"].model_dump(), "errors", dry.errors)
    assert dry.errors == 0
    assert dry.counts["ai_logs"].received == 61

    real = await import_service.import_ai_logs(
        session, envelope, dry_run=False, expect_replaced=0, file_sha256=sha_before
    )
    assert real.committed
    assert real.counts["ai_logs"].created == 61
    # Sau khi nhập, endpoint đọc phải trả 200 (handling thiếu đã được điền).
    resp = await client.get("/api/v1/ai-logs", params={"limit": 100})
    assert resp.status_code == 200
    assert resp.json()["total"] == 61

    sha_after, mtime_after, _ = _read_only_fingerprint(path)
    assert (sha_after, mtime_after) == (sha_before, mtime_before)
