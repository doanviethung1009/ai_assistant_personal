"""Quy tắc đồng bộ tag (docs/specs/tag-rules.md): hàm thuần, ghi rule, áp rule khi sync, API."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.db.session import SessionFactory
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.tag_rule import TagRule
from app.models.task import Task
from app.services.jira_mapping import map_issue
from app.services.tag_rule_service import apply_rules
from tests.conftest import Persona, create_persona

TAGS = "/api/v1/tags"
RULES = "/api/v1/tag-rules"
UPSERT = "/api/v1/tasks/upsert-batch"


# ── Hàm thuần ───────────────────────────────────────────────────────


def test_apply_rules_alias_block_order_and_dedupe() -> None:
    rules = {"a": "b", "x": None}
    assert apply_rules(["a", "c"], rules) == ["b", "c"]
    assert apply_rules(["x", "c"], rules) == ["c"]
    # Bỏ trùng sau khi đổi: [a, b] với a -> b chỉ còn [b].
    assert apply_rules(["a", "b"], rules) == ["b"]
    assert apply_rules(["b", "a"], rules) == ["b"]
    assert apply_rules(["keep"], rules) == ["keep"]
    assert apply_rules([], rules) == []
    assert apply_rules(["a", "a"], {}) == ["a"]


def test_apply_rules_idempotent() -> None:
    rules = {"a": "b", "x": None}
    once = apply_rules(["a", "x", "c"], rules)
    assert apply_rules(once, rules) == once


def test_map_issue_applies_rules_before_cap() -> None:
    """Tag bị chặn không được chiếm chỗ trong MAX_TAGS: label đứng sau vẫn còn."""
    labels = [f"l{i:02d}" for i in range(25)]
    issue: dict[str, Any] = {"key": "ABC-1", "fields": {"summary": "s", "labels": labels}}
    base = {"base_url": "https://x.atlassian.net", "field_names": {}}
    plain = map_issue(issue, **base)
    assert "l00" in plain.tags and len(plain.tags) == 20
    ruled = map_issue(issue, tag_rules={"l00": None, "l01": "renamed"}, **base)
    assert "l00" not in ruled.tags and "l01" not in ruled.tags and "renamed" in ruled.tags
    assert len(ruled.tags) == 20
    # Cắt SAU khi áp rule nên một label đứng sau (đáng lẽ bị cắt) được giữ lại.
    assert len(set(ruled.tags) - set(plain.tags)) >= 1


# ── Helper ──────────────────────────────────────────────────────────


def _item(ext: str, tags: list[str]) -> dict[str, Any]:
    return {"external_id": ext, "title": f"Việc {ext}", "tags": tags}


async def _upsert(client: httpx.AsyncClient, items: list[dict[str, Any]]) -> dict[str, Any]:
    resp = await client.post(UPSERT, json={"source": "jira", "items": items})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _tags_of(ext: str) -> list[str]:
    async with SessionFactory() as s:
        task = (await s.execute(select(Task).where(Task.external_id == ext))).scalar_one()
        return list(task.tags)


async def _rules() -> dict[str, str | None]:
    async with SessionFactory() as s:
        rows = (await s.execute(select(TagRule.source_tag, TagRule.target_tag))).all()
    rules = dict(rows)
    # Bất biến phẳng: không target nào là source của rule khác.
    assert not {t for t in rules.values() if t is not None} & set(rules)
    return rules


async def _audit_actions() -> list[str]:
    async with SessionFactory() as s:
        stmt = select(AuditLog.action).order_by(AuditLog.created_at)
        return list((await s.execute(stmt)).scalars())


# ── Ghi rule + áp khi sync ──────────────────────────────────────────


@pytest.mark.db
async def test_rename_writes_alias_rule_and_sync_applies_it(client: httpx.AsyncClient) -> None:
    await _upsert(client, [_item("J-1", ["a"])])
    resp = await client.patch(f"{TAGS}/a", json={"new_name": "b"})
    assert resp.status_code == 200
    rule = resp.json()["rule"]
    assert (rule["source_tag"], rule["target_tag"], rule["kind"]) == ("a", "b", "alias")
    assert await _tags_of("J-1") == ["b"]

    # Task đã có: tag nguồn `a` được đổi thành `b`, không quay lại.
    res = await _upsert(client, [_item("J-1", ["a"])])
    assert res["unchanged"] == 1
    assert await _tags_of("J-1") == ["b"]
    # Task mới.
    await _upsert(client, [_item("J-2", ["a", "x"])])
    assert await _tags_of("J-2") == ["b", "x"]
    assert "tag_rule_set" in await _audit_actions()


@pytest.mark.db
async def test_delete_writes_block_rule_and_sync_is_noop(client: httpx.AsyncClient) -> None:
    await _upsert(client, [_item("J-1", ["x", "keep"])])
    resp = await client.delete(f"{TAGS}/x")
    assert resp.status_code == 200
    assert resp.json()["rule"]["kind"] == "block"
    assert resp.json()["rule"]["target_tag"] is None

    first = await _upsert(client, [_item("J-1", ["x", "keep"])])
    second = await _upsert(client, [_item("J-1", ["x"])])
    assert first["unchanged"] == 1 and second["unchanged"] == 1
    assert await _tags_of("J-1") == ["keep"]
    await _upsert(client, [_item("J-2", ["x"])])
    assert await _tags_of("J-2") == []


@pytest.mark.db
async def test_chain_and_revive_keep_rules_flat(client: httpx.AsyncClient) -> None:
    await _upsert(client, [_item("J-1", ["a"])])
    await client.patch(f"{TAGS}/a", json={"new_name": "b"})
    await client.patch(f"{TAGS}/b", json={"new_name": "c"})
    assert await _rules() == {"a": "c", "b": "c"}

    # a -> b rồi b -> a: rule a -> b bị hồi sinh xoá, còn b -> a.
    await _upsert(client, [_item("K-1", ["p"])])
    await client.patch(f"{TAGS}/p", json={"new_name": "q"})
    await client.patch(f"{TAGS}/q", json={"new_name": "p"})
    rules = await _rules()
    assert rules["q"] == "p" and "p" not in rules

    # a -> b rồi xoá b: cả hai bị chặn.
    await _upsert(client, [_item("L-1", ["m"])])
    await client.patch(f"{TAGS}/m", json={"new_name": "n"})
    await client.delete(f"{TAGS}/n")
    rules = await _rules()
    assert rules["m"] is None and rules["n"] is None

    # xoá z rồi đổi y -> z: rule chặn z bị hồi sinh xoá.
    await _upsert(client, [_item("M-1", ["z", "y"])])
    await client.delete(f"{TAGS}/z")
    await _upsert(client, [_item("M-2", ["y"])])
    await client.patch(f"{TAGS}/y", json={"new_name": "z"})
    rules = await _rules()
    assert "z" not in rules and rules["y"] == "z"


@pytest.mark.db
async def test_no_rule_for_personal_or_note_only_tags(client: httpx.AsyncClient) -> None:
    await client.post("/api/v1/tasks", json={"title": "t", "tags": ["pa"], "scope": "personal"})
    await client.post("/api/v1/notes", json={"title": "n", "content": "c", "tags": ["na"]})
    r1 = await client.patch(f"{TAGS}/pa", json={"new_name": "pb"})
    r2 = await client.patch(f"{TAGS}/na", json={"new_name": "nb"})
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["rule"] is None and r2.json()["rule"] is None
    assert await _rules() == {}

    member = await create_persona("member-rule@test.local", UserRole.MEMBER)
    await client.post("/api/v1/tasks", json={"title": "w", "tags": ["wa"], "scope": "work"})
    resp = await client.patch(f"{TAGS}/wa", json={"new_name": "wb"}, headers=member.headers)
    assert resp.status_code == 404
    assert await _rules() == {}


@pytest.mark.db
async def test_manual_tags_not_blocked_and_union_kept(client: httpx.AsyncClient) -> None:
    await _upsert(client, [_item("J-1", ["x"])])
    await client.delete(f"{TAGS}/x")
    resp = await client.post(
        "/api/v1/tasks", json={"title": "t", "tags": ["x"], "scope": "work"}
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]
    # PATCH tay vẫn gõ được tag bị chặn.
    patched = await client.patch(f"/api/v1/tasks/{task_id}", json={"tags": ["x"]})
    assert patched.status_code == 200 and patched.json()["tags"] == ["x"]

    # Sync sau đó vẫn giữ `x` do User gõ (union với tag hiện có, rule chỉ áp lên tag nguồn).
    async with SessionFactory() as s:
        await s.execute(
            Task.__table__.update().where(Task.external_id == "J-1").values(tags=["x", "k"])
        )
        await s.commit()
    await _upsert(client, [_item("J-1", ["x", "other"])])
    assert await _tags_of("J-1") == ["x", "k", "other"]


@pytest.mark.db
async def test_personal_duplicate_key_still_skipped(
    client: httpx.AsyncClient, default_user: Persona
) -> None:
    await _upsert(client, [_item("P-1", ["a"])])
    async with SessionFactory() as s:
        await s.execute(
            Task.__table__.update()
            .where(Task.external_id == "P-1")
            .values(scope="personal", owner_id=default_user.id, tags=["mine"])
        )
        await s.commit()
    await client.post("/api/v1/tasks", json={"title": "w", "tags": ["a"], "scope": "work"})
    await client.patch(f"{TAGS}/a", json={"new_name": "b"})
    res = await _upsert(client, [_item("P-1", ["a"])])
    assert res["skipped_personal"] == 1
    assert await _tags_of("P-1") == ["mine"]


# ── API ─────────────────────────────────────────────────────────────


@pytest.mark.db
async def test_list_and_delete_rules(client: httpx.AsyncClient) -> None:
    await _upsert(client, [_item("J-1", ["a", "b", "c"])])
    await client.patch(f"{TAGS}/a", json={"new_name": "a2"})
    await client.patch(f"{TAGS}/b", json={"new_name": "b2"})
    await client.delete(f"{TAGS}/c")

    member = await create_persona("member-list@test.local", UserRole.MEMBER)
    page = await client.get(RULES, params={"limit": 2, "offset": 0}, headers=member.headers)
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3 and body["limit"] == 2 and len(body["items"]) == 2
    assert [i["source_tag"] for i in body["items"]] == ["a", "b"]
    assert "email" not in str(body)
    rest = await client.get(RULES, params={"limit": 2, "offset": 2})
    assert [i["source_tag"] for i in rest.json()["items"]] == ["c"]
    assert rest.json()["items"][0]["kind"] == "block"

    rule_id = body["items"][0]["id"]
    assert (await client.delete(f"{RULES}/{rule_id}", headers=member.headers)).status_code == 403
    assert (await client.delete(f"{RULES}/not-a-uuid")).status_code == 422
    assert (
        await client.delete(f"{RULES}/00000000-0000-0000-0000-000000000000")
    ).status_code == 404
    assert (await client.delete(f"{RULES}/{rule_id}")).status_code == 204
    assert (await client.delete(f"{RULES}/{rule_id}")).status_code == 404

    # Gỡ rule: tag `a` từ nguồn quay lại ở lần sync sau.
    await _upsert(client, [_item("J-9", ["a"])])
    assert await _tags_of("J-9") == ["a"]
    actions = await _audit_actions()
    assert "tag_rule_set" in actions and "tag_rule_deleted" in actions
