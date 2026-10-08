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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine
from app.schemas.imports import AiLogsEnvelope, DataFileEnvelope, ImportReport
from app.services import import_service
from app.services.errors import ConflictError, ValidationError
from app.services.import_service import normalize_project_key

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
    include_personal: bool = False,
) -> ImportReport:
    envelope = DataFileEnvelope.model_validate(data if data is not None else _load())
    return await import_service.import_datafile(
        session,
        envelope,
        include_personal=include_personal,
        dry_run=dry_run,
        expect_replaced=None if dry_run else expect,
        expect_sha256=None if dry_run else SHA,
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
        ("PROJ ALPHA", "PROJ_ALPHA"),
        ("ĐỀ TÀI MỚI", "DE_TAI_MOI"),
        ("beta", "BETA"),
    }
    assert "raw_payload" in report.ignored_fields["task"]
    assert "project" in report.ignored_fields["task"]
    assert "is_overdue" in report.ignored_fields["task"]
    assert {"unknown_top_level", "meta"} <= set(report.ignored_fields["file"])

    # Project: id giữ nguyên, key và màu được chuẩn hoá.
    row = (
        await session.execute(text("SELECT key, color FROM projects WHERE id = :i"), {"i": P1})
    ).one()
    assert row.key == "PROJ_ALPHA"
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
    # 3 project + 3 task + 2 event từ file + 3 event `synced` do lần nhập sinh + 1 note
    assert counts["import_audit"] == 12
    actions = await session.scalar(
        text("SELECT count(*) FROM import_audit WHERE action = 'created'")
    )
    assert actions == 12
    # Mọi event có import_id trong payload đều phải có dòng audit tương ứng.
    orphan = await session.scalar(
        text(
            "SELECT count(*) FROM task_events e WHERE e.payload->>'import_id' IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM import_audit a WHERE a.entity = 'task_event' "
            "AND a.entity_id = e.id)"
        )
    )
    assert orphan == 0
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
    # T3 là task nhập tay => scope personal => được bảo vệ, tính skipped_personal
    # chứ không phải unchanged (spec task-scope S8).
    assert second.counts["tasks"].unchanged == 2
    assert second.counts["tasks"].skipped_personal == 1
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
        text("INSERT INTO projects (id, key, name) VALUES (:i, 'BETA', 'Ten khac trong DB')"),
        {"i": db_project},
    )
    await session.execute(
        text(
            "INSERT INTO tasks (id, title, source, scope, external_id) "
            "VALUES (:i, 'Tieu de DB', 'jira', 'work', 'DEMO-2')"
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
    assert await session.scalar(text("SELECT count(*) FROM projects WHERE key = 'BETA'")) == 1
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
        expect_sha256=None if dry_run else SHA,
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
#  Rào chắn bổ sung: sha256, giá trị dự phòng, rollback, khoá dòng
# ═══════════════════════════════════════════════════════════════════════


async def test_sha256_mismatch_blocks_commit(session: AsyncSession) -> None:
    before = await _row_counts(session)
    report = await import_service.import_datafile(
        session,
        DataFileEnvelope.model_validate(_load()),
        dry_run=False,
        expect_replaced=0,
        expect_sha256="f" * 64,
        file_sha256=SHA,
    )
    assert not report.committed
    assert "file_changed_since_dry_run" in {i.code for i in report.issues}
    assert await _row_counts(session) == before


async def test_real_import_requires_expect_sha256(session: AsyncSession) -> None:
    with pytest.raises(ValidationError):
        await import_service.import_datafile(
            session,
            DataFileEnvelope.model_validate(_load()),
            dry_run=False,
            expect_replaced=0,
            expect_sha256=None,
            file_sha256=SHA,
        )


async def test_replace_keeps_archived_at_when_file_lacks_the_key(session: AsyncSession) -> None:
    await _import(session)
    archived = _utc(2026, 9, 30, 12)
    await session.execute(
        text("UPDATE notes SET archived_at = :a, title = 'Sua tay' WHERE id = :i"),
        {"a": archived, "i": N1},
    )
    await session.commit()

    # File cũ không có khoá archived_at: không có nghĩa là "bỏ lưu trữ".
    data = _load()
    del data["notes"][0]["archived_at"]
    report = await _import(session, data, expect=1)
    assert report.committed, report.issues
    assert report.counts["notes"].replaced == 1
    assert {c.field for c in report.replacements[0].changes} == {"title"}
    row = (
        await session.execute(text("SELECT archived_at, title FROM notes WHERE id = :i"), {"i": N1})
    ).one()
    assert row.archived_at == archived
    assert row.title == "Ghi chu lenh"


async def test_replace_keeps_real_completed_at_when_file_lacks_it(session: AsyncSession) -> None:
    await _import(session)
    real_done = _utc(2026, 9, 18, 7)
    await session.execute(
        text("UPDATE tasks SET completed_at = :c, title = 'Sua tay' WHERE id = :i"),
        {"c": real_done, "i": T1},
    )
    await session.commit()

    # Fixture: task done thiếu completed_at => file chỉ có giá trị backfill từ updated_at.
    report = await _import(session, expect=1)
    assert report.committed, report.issues
    assert {c.field for c in report.replacements[0].changes} == {"title"}
    assert (await _task(session, T1))["completed_at"] == real_done


async def test_replace_keeps_project_when_file_cannot_map_it(session: AsyncSession) -> None:
    await _import(session)
    p2 = uuid.UUID("22222222-2222-4222-8222-222222222222")
    assert (await _task(session, T3))["project_id"] == p2

    data = _load()
    data["tasks"][2]["project_id"] = str(uuid.uuid4())  # project không tồn tại ở đâu cả
    data["tasks"][2]["title"] = "Doi tieu de"
    # T3 là task nhập tay (personal) nên phải bật include_personal mới ghi đè được.
    report = await _import(session, data, expect=1, include_personal=True)
    assert report.committed, report.issues
    assert "project_unlinked" in {i.code for i in report.issues}
    assert {c.field for c in report.replacements[0].changes} == {"title"}
    row = await _task(session, T3)
    assert row["project_id"] == p2
    assert row["title"] == "Doi tieu de"


async def test_unsafe_external_url_is_dropped_and_not_overwriting(session: AsyncSession) -> None:
    data = _load()
    data["tasks"][0]["external_url"] = "javascript:alert(1)"
    report = await _import(session, data)
    assert report.committed
    assert "external_url_dropped" in {i.code for i in report.issues}
    assert (await _task(session, T1))["external_url"] is None

    await session.execute(
        text("UPDATE tasks SET external_url = 'https://ok.example/x', title = 'Sua' WHERE id = :i"),
        {"i": T1},
    )
    await session.commit()
    again = await _import(session, data, expect=1)
    assert again.committed
    assert (await _task(session, T1))["external_url"] == "https://ok.example/x"


async def test_file_event_actor_is_prefixed(session: AsyncSession) -> None:
    await _import(session)
    actors = {
        r[0]
        for r in (
            await session.execute(
                text(
                    "SELECT actor FROM task_events "
                    "WHERE event_type IN ('created', 'status_changed')"
                )
            )
        ).all()
    }
    assert actors == {"import:user"}


async def test_data_error_in_write_rolls_back_everything(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = import_service._apply_plan

    async def failing_apply(sess: AsyncSession, table: Any, plan: Any) -> None:
        await original(sess, table, plan)
        if table.name == "tasks":
            # Vi phạm CHECK title_not_blank sau khi project/task đã được ghi.
            await sess.execute(
                text("INSERT INTO tasks (id, title) VALUES (:i, '   ')"), {"i": uuid.uuid4()}
            )

    monkeypatch.setattr(import_service, "_apply_plan", failing_apply)
    before = await _row_counts(session)
    report = await _import(session)
    assert not report.committed
    assert "db_constraint" in {i.code for i in report.issues}
    assert await _row_counts(session) == before


async def test_row_lock_timeout_becomes_conflict(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _import(session)
    monkeypatch.setattr(import_service, "LOCK_TIMEOUT", "200ms")
    async with engine.connect() as other:
        await other.execute(text("SELECT id FROM tasks WHERE id = :i FOR UPDATE"), {"i": T1})
        try:
            with pytest.raises(ConflictError):
                await _import(session)
        finally:
            await other.rollback()
    # Khoá nhả rồi thì nhập bình thường.
    assert (await _import(session)).committed


async def test_missing_created_at_warns(session: AsyncSession) -> None:
    data = _load()
    del data["tasks"][1]["created_at"]
    report = await _import(session, data)
    assert report.committed
    warned = [i for i in report.issues if i.code == "timestamps_defaulted"]
    assert [(w.entity, w.id) for w in warned] == [("task", str(T2))]


async def test_event_id_owned_by_other_task_warns(session: AsyncSession) -> None:
    await _import(session)
    data = _load()
    moved = data["tasks"][0]["events"].pop(0)
    data["tasks"][1]["events"].append(moved)
    report = await _import(session, data)
    assert report.committed
    assert "event_id_other_task" in {i.code for i in report.issues}
    owner = await session.scalar(
        text("SELECT task_id FROM task_events WHERE id = :i"), {"i": moved["id"]}
    )
    assert owner == T1  # event không bị chuyển chủ


async def test_unknown_keys_are_capped_in_report(session: AsyncSession) -> None:
    data = _load()
    data["tasks"][1].update({f"khoa_la_{i}_" + "x" * 100: 1 for i in range(200)})
    long_key = "k" * 100
    data["projects"][0]["key"] = long_key
    report = await _import(session, data, dry_run=True)
    names = report.ignored_fields["task"]
    assert len(names) <= 50
    assert all(len(n) <= 64 for n in names)
    assert all(len(k.original) <= 40 for k in report.project_key_changes)


async def test_project_key_over_100_chars_is_row_error(session: AsyncSession) -> None:
    data = _load()
    data["projects"][0]["key"] = "k" * 101
    report = await _import(session, data, dry_run=True)
    assert report.errors >= 1
    assert report.counts["projects"].invalid == 1


async def test_non_string_or_overlong_color_is_dropped_not_fatal(session: AsyncSession) -> None:
    data = _load()
    data["projects"][0]["color"] = 123
    data["projects"][1]["color"] = "x" * 100
    report = await _import(session, data)
    assert report.committed, report.issues
    assert report.errors == 0
    assert report.counts["projects"].invalid == 0
    # 123, chuỗi quá dài, và "red" của project thứ ba trong fixture.
    assert sum(1 for i in report.issues if i.code == "color_dropped") == 3
    colors = (
        await session.execute(text("SELECT color FROM projects WHERE color IS NOT NULL"))
    ).all()
    assert colors == []


async def test_check_constraints_reject_unknown_values(session: AsyncSession) -> None:
    """Chứng minh CHECK thật sự chặn ở DB, không chỉ khai trong model."""
    report = await _import(session)
    run_id = report.import_id
    bad_statements = [
        (
            "INSERT INTO import_runs (id, kind, file_sha256, schema_version, counts, actor) "
            "VALUES (:i, 'x', :s, 1, CAST('{}' AS jsonb), 'a')",
            {"i": uuid.uuid4(), "s": "0" * 64},
        ),
        (
            "INSERT INTO import_audit (id, import_id, entity, entity_id, action) "
            "VALUES (:i, :r, 'lạ', :e, 'created')",
            {"i": uuid.uuid4(), "r": run_id, "e": uuid.uuid4()},
        ),
        (
            "INSERT INTO import_audit (id, import_id, entity, entity_id, action) "
            "VALUES (:i, :r, 'task', :e, 'deleted')",
            {"i": uuid.uuid4(), "r": run_id, "e": uuid.uuid4()},
        ),
    ]
    for sql, params in bad_statements:
        with pytest.raises(IntegrityError):
            await session.execute(text(sql), params)
        await session.rollback()


async def test_replace_to_non_done_clears_completed_at(session: AsyncSession) -> None:
    await _import(session)
    assert (await _task(session, T1))["completed_at"] is not None

    data = _load()
    data["tasks"][0]["status"] = "todo"
    del data["tasks"][0]["completed_at"]  # khoá vắng mặt
    report = await _import(session, data, expect=1)
    assert report.committed, report.issues
    assert {c.field for c in report.replacements[0].changes} == {"status", "completed_at"}
    row = await _task(session, T1)
    assert row["status"] == "todo"
    assert row["completed_at"] is None


async def test_cancelled_task_keeps_completed_at_and_reimport_is_idempotent(
    session: AsyncSession,
) -> None:
    """File thật có task cancelled kèm completed_at (thời điểm đóng): không được xoá."""
    data = _load()
    data["tasks"][1]["status"] = "cancelled"
    data["tasks"][1]["completed_at"] = "2026-09-21T10:00:00.000Z"
    await _import(session, data)
    again = await _import(session, data)
    assert again.counts["tasks"].replaced == 0
    assert (await _task(session, T2))["completed_at"] == _utc(2026, 9, 21, 10)


async def test_missing_status_key_keeps_done_and_its_completed_at(session: AsyncSession) -> None:
    await _import(session)
    real_done = _utc(2026, 9, 18, 7)
    await session.execute(
        text("UPDATE tasks SET completed_at = :c WHERE id = :i"), {"c": real_done, "i": T1}
    )
    await session.commit()

    data = _load()
    del data["tasks"][0]["status"]  # DB giữ done
    data["tasks"][0]["completed_at"] = None  # null tường minh
    data["tasks"][0]["title"] = "Doi tieu de"
    report = await _import(session, data, expect=1)
    assert report.committed, report.issues
    row = await _task(session, T1)
    assert row["status"] == "done"
    assert row["completed_at"] == real_done
    assert row["title"] == "Doi tieu de"


async def test_source_and_external_id_are_treated_as_a_pair(session: AsyncSession) -> None:
    await _import(session)
    # Một task khác trong DB đang giữ khoá (jira, DEMO-2) sau khi T2 đổi external_id.
    thief = uuid.uuid4()
    await session.execute(
        text("UPDATE tasks SET external_id = 'DEMO-2-OLD' WHERE id = :i"), {"i": T2}
    )
    await session.execute(
        text(
            "INSERT INTO tasks (id, title, source, external_id) "
            "VALUES (:i, 'Giu khoa', 'jira', 'DEMO-2')"
        ),
        {"i": thief},
    )
    await session.commit()

    data = _load()
    del data["tasks"][1]["external_id"]  # thiếu một khoá của cặp
    data["tasks"][1]["title"] = "Doi tieu de"
    report = await _import(session, data, expect=1)
    # Không có natural_key_conflict (cũng không có lỗi ràng buộc DB): cặp bị bỏ qua.
    assert report.committed, report.issues
    assert {c.field for c in report.replacements[0].changes} == {"title"}
    row = await _task(session, T2)
    assert (row["source"], row["external_id"]) == ("jira", "DEMO-2-OLD")
    assert row["title"] == "Doi tieu de"


async def test_replace_audits_generated_events(session: AsyncSession) -> None:
    await _import(session)
    await session.execute(text("UPDATE tasks SET title = 'Sua' WHERE id = :i"), {"i": T1})
    await session.commit()
    report = await _import(session, expect=1)
    updated_event = await session.scalar(
        text("SELECT id FROM task_events WHERE payload->>'import_id' = :r"),
        {"r": str(report.import_id)},
    )
    audited = await session.scalar(
        text(
            "SELECT count(*) FROM import_audit WHERE import_id = :r AND entity = 'task_event' "
            "AND entity_id = :e AND action = 'created'"
        ),
        {"r": report.import_id, "e": updated_event},
    )
    assert audited == 1


# ═══════════════════════════════════════════════════════════════════════
#  scope (epic task-scope)
# ═══════════════════════════════════════════════════════════════════════


async def _scope(session: AsyncSession, task_id: uuid.UUID) -> str:
    return str(await session.scalar(text("SELECT scope FROM tasks WHERE id = :i"), {"i": task_id}))


async def _insert_personal_t1(session: AsyncSession, task_id: uuid.UUID = T1) -> None:
    """Task DB `personal` có khoá tự nhiên (jira, DEMO-1) giống T1 trong fixture."""
    await session.execute(
        text(
            "INSERT INTO tasks (id, title, source, scope, external_id) "
            "VALUES (:i, 'Cua rieng User', 'jira', 'personal', 'DEMO-1')"
        ),
        {"i": task_id},
    )
    await session.commit()


async def test_import_run_records_include_personal_flag(session: AsyncSession) -> None:
    await _import(session)
    await _import(session, include_personal=True)
    flags = (
        await session.scalars(
            text(
                "SELECT counts -> 'options' ->> 'include_personal' "
                "FROM import_runs ORDER BY created_at"
            )
        )
    ).all()
    assert list(flags) == ["false", "true"]
    # Dry-run không ghi sổ cái.
    await _import(session, dry_run=True, include_personal=True)
    assert await session.scalar(text("SELECT count(*) FROM import_runs")) == 2


async def test_file_assignee_is_normalized(session: AsyncSession) -> None:
    data = _load()
    data["tasks"][0]["assignee"] = "  Hung  "
    data["tasks"][1]["assignee"] = "   "
    report = await _import(session, data)
    assert report.committed, report.issues
    assert (await _task(session, T1))["assignee"] == "Hung"
    assert (await _task(session, T2))["assignee"] is None


async def test_file_without_scope_derives_from_source(session: AsyncSession) -> None:
    data = _load()
    assert all("scope" not in t for t in data["tasks"])
    report = await _import(session, data)
    assert report.committed, report.issues
    assert await _scope(session, T1) == "work"
    assert await _scope(session, T2) == "work"
    assert await _scope(session, T3) == "personal"


async def test_file_with_explicit_scope_is_respected_and_not_ignored(
    session: AsyncSession,
) -> None:
    data = _load()
    data["schema_version"] = 5
    data["tasks"][0]["scope"] = "personal"
    data["tasks"][2]["scope"] = "work"
    data["tasks"][1]["scope"] = None  # null = file không nói gì => suy từ source
    report = await _import(session, data)
    assert report.committed, report.issues
    assert "scope" not in report.ignored_fields.get("task", [])
    assert await _scope(session, T1) == "personal"
    assert await _scope(session, T3) == "work"
    assert await _scope(session, T2) == "work"


async def test_unknown_scope_value_in_file_is_reported(session: AsyncSession) -> None:
    data = _load()
    data["tasks"][0]["scope"] = "team"
    report = await _import(session, data, dry_run=True)
    assert report.errors >= 1
    assert "invalid_enum" in {i.code for i in report.issues}


async def test_personal_task_in_db_is_protected_from_old_file(session: AsyncSession) -> None:
    await _import(session)
    await session.execute(
        text("UPDATE tasks SET scope = 'personal', title = 'Sua tay' WHERE id = :i"), {"i": T1}
    )
    await session.commit()
    events_before = await session.scalar(
        text("SELECT count(*) FROM task_events WHERE task_id = :i"), {"i": T1}
    )
    before = await _task(session, T1)

    # File v4 (không có scope) khớp T1 theo id. T3 (nhập tay) cũng là personal.
    report = await _import(session, expect=0)
    assert report.committed, report.issues
    assert report.counts["tasks"].skipped_personal == 2
    assert report.counts["tasks"].replaced == 0
    assert "skipped_personal" in {i.code for i in report.issues}
    assert await _task(session, T1) == before
    assert (
        await session.scalar(text("SELECT count(*) FROM task_events WHERE task_id = :i"), {"i": T1})
        == events_before
    )


async def test_include_personal_overwrites_but_keeps_scope(session: AsyncSession) -> None:
    await _import(session)
    await session.execute(
        text("UPDATE tasks SET scope = 'personal', title = 'Sua tay' WHERE id = :i"), {"i": T1}
    )
    await session.commit()

    report = await _import(session, expect=1, include_personal=True)
    assert report.committed, report.issues
    assert report.counts["tasks"].skipped_personal == 0
    assert {c.field for c in report.replacements[0].changes} == {"title"}
    row = await _task(session, T1)
    assert row["title"] == "Task tong hop 1"
    # File thiếu scope => giá trị dự phòng, DB giữ lựa chọn của User.
    assert row["scope"] == "personal"


async def test_explicit_personal_in_file_overwrites_work_in_db(session: AsyncSession) -> None:
    await _import(session)
    data = _load()
    data["schema_version"] = 5
    data["tasks"][0]["scope"] = "personal"
    report = await _import(session, data, expect=1)
    assert report.committed, report.issues
    change = report.replacements[0].changes[0]
    assert (change.field, change.old, change.new) == ("scope", "work", "personal")
    assert await _scope(session, T1) == "personal"


async def test_natural_key_match_to_personal_task_is_skipped_without_duplicate(
    session: AsyncSession,
) -> None:
    other_id = uuid.uuid4()
    await _insert_personal_t1(session, other_id)

    report = await _import(session)
    assert report.committed, report.issues
    assert report.counts["tasks"].skipped_personal == 1
    assert report.counts["tasks"].created == 2  # T2 và T3; T1 bị bỏ qua
    assert "db_constraint" not in {i.code for i in report.issues}
    assert (
        await session.scalar(text("SELECT count(*) FROM tasks WHERE external_id = 'DEMO-1'")) == 1
    )
    assert await session.scalar(text("SELECT count(*) FROM tasks WHERE id = :i"), {"i": T1}) == 0
    assert (await _task(session, other_id))["title"] == "Cua rieng User"


async def test_events_of_skipped_personal_task_are_not_inserted(session: AsyncSession) -> None:
    await _insert_personal_t1(session)

    report = await _import(session)
    assert report.committed, report.issues
    # T1 có 2 event trong file; cả hai bị bỏ cùng task.
    assert report.counts["task_events"].skipped_personal == 2
    assert (
        await session.scalar(text("SELECT count(*) FROM task_events WHERE task_id = :i"), {"i": T1})
        == 0
    )


async def test_include_personal_mismatch_between_dry_run_and_commit(
    session: AsyncSession,
) -> None:
    await _import(session)
    await session.execute(text("UPDATE tasks SET title = 'Sua tay' WHERE id = :i"), {"i": T3})
    await session.commit()

    dry = await _import(session, dry_run=True)  # không bật include_personal
    assert dry.counts["tasks"].replaced == 0
    assert dry.counts["tasks"].skipped_personal == 1

    # Nhập thật bật include_personal: T3 sẽ bị ghi đè nên số lệch với dry-run => huỷ.
    report = await _import(session, expect=dry.counts["tasks"].replaced, include_personal=True)
    assert not report.committed
    assert "replace_count_mismatch" in {i.code for i in report.issues}
    assert (await _task(session, T3))["title"] == "Sua tay"


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
async def test_real_file_datafile(session: AsyncSession, client: Any) -> None:
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
            expect_sha256=None if dry_run else sha_before,
            file_sha256=sha_before,
        )

    # Kỳ vọng suy ra từ chính nội dung file (file thật được User sửa theo thời gian,
    # số cứng như "14 project" chỉ đúng tại một ngày).
    raw = json.loads(body)
    n_projects = len(raw["projects"])
    n_tasks = sum(1 for t in raw["tasks"] if t.get("deleted_at") is None)
    n_hsl = sum(1 for p in raw["projects"] if str(p.get("color", "")).lower().startswith("hsl"))
    n_key_changes = sum(1 for p in raw["projects"] if normalize_project_key(p["key"]) != p["key"])

    dry = await run(True)
    assert dry.file_sha256 == sha_before
    assert dry.errors == 0, [i for i in dry.issues if i.level == "error"][:5]
    assert dry.counts["projects"].received == n_projects
    assert dry.counts["tasks"].received == len(raw["tasks"])
    assert len(dry.project_key_changes) == n_key_changes
    assert sum(1 for i in dry.issues if i.code == "color_converted") == n_hsl
    assert sum(c.replaced for c in dry.counts.values()) == 0

    real = await run(False)
    assert real.committed, real.issues[:5]
    assert real.counts["projects"].created == n_projects
    assert real.counts["tasks"].created == n_tasks

    again = await run(False)
    assert again.committed
    assert again.counts["projects"].created == again.counts["projects"].replaced == 0
    assert again.counts["tasks"].created == again.counts["tasks"].replaced == 0
    assert again.counts["projects"].unchanged == n_projects
    # Task cá nhân (nếu file có) được bảo vệ nên tính skipped_personal thay vì unchanged.
    assert again.counts["tasks"].unchanged + again.counts["tasks"].skipped_personal == n_tasks

    # scope: kỳ vọng tính từ nội dung file theo quy tắc nguồn (spec task-scope 6.1).
    work_sources = {"jira", "github", "gitlab"}
    live = [t for t in raw["tasks"] if t.get("deleted_at") is None]
    n_work = sum(1 for t in live if t.get("source", "manual") in work_sources)
    n_work_db = await session.scalar(text("SELECT count(*) FROM tasks WHERE scope = 'work'"))
    n_personal_db = await session.scalar(
        text("SELECT count(*) FROM tasks WHERE scope = 'personal'")
    )
    assert n_work_db == n_work
    assert n_personal_db == len(live) - n_work
    # Kết thúc transaction đọc của `session`: teardown của `client` TRUNCATE cần khoá
    # độc quyền, nếu transaction này còn mở thì test treo.
    await session.rollback()

    # "Việc của tôi" theo QUY TẮC CŨ của web (isMyTask) viết lại trên JSON thô. Chỉ so
    # được khi file không có task personal có assignee lạ (quy tắc cũ khác ở đúng chỗ đó).
    users = raw.get("meta", {}).get("current_users") or []
    expected_mine = sum(
        1
        for t in live
        if (t.get("assignee") in users if t.get("assignee") else t.get("source") != "jira")
    )
    resp = await client.get(
        "/api/v1/tasks/stats",
        params={"view": "mine", "owner": users} if users else {"view": "mine"},
    )
    assert resp.status_code == 200
    assert sum(resp.json()["by_status"].values()) == expected_mine

    sha_after, mtime_after, _ = _read_only_fingerprint(path)
    assert (sha_after, mtime_after) == (sha_before, mtime_before)


@pytest.mark.skipif(not REAL_AILOGS, reason="cần IMPORT_REAL_AILOGS")
async def test_real_file_ai_logs(session: AsyncSession, client: Any) -> None:
    assert REAL_AILOGS
    path = Path(REAL_AILOGS)
    sha_before, mtime_before, body = _read_only_fingerprint(path)
    raw = json.loads(body)
    envelope = AiLogsEnvelope.model_validate(raw)
    # File ai-logs thật được công cụ log append liên tục: không ghi cứng số lượng.
    n = len(raw["ai_logs"])

    dry = await import_service.import_ai_logs(
        session, envelope, dry_run=True, expect_replaced=None, file_sha256=sha_before
    )
    assert dry.errors == 0
    assert dry.counts["ai_logs"].received == n

    real = await import_service.import_ai_logs(
        session,
        envelope,
        dry_run=False,
        expect_replaced=0,
        expect_sha256=sha_before,
        file_sha256=sha_before,
    )
    assert real.committed
    assert real.counts["ai_logs"].created == n
    # Sau khi nhập, endpoint đọc phải trả 200 (handling thiếu đã được điền).
    resp = await client.get("/api/v1/ai-logs", params={"limit": 100})
    assert resp.status_code == 200
    assert resp.json()["total"] == n

    sha_after, mtime_after, _ = _read_only_fingerprint(path)
    assert (sha_after, mtime_after) == (sha_before, mtime_before)
