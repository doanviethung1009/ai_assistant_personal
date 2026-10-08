"""Kết nối tích hợp (B4a): token write-only, mã hoá khi lưu, validate base_url.

Không gọi mạng. Mọi dữ liệu đều tổng hợp; token trong test là chuỗi giả.
"""

from __future__ import annotations

import logging
import uuid

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import secrets as secrets_mod
from app.core.config import settings
from app.db.session import SessionFactory
from app.models.integration import IntegrationConnection
from app.schemas.integration import validate_base_url

URL = "/api/v1/integrations"
TOKEN = "ATATT3xFfGF0-fake-token-ZZ9876"  # noqa: S105
BASE = "https://acme.atlassian.net"


def _body(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "name": "Jira công ty",
        "base_url": BASE,
        "account_email": "me@acme.com",
        "token": TOKEN,
        "config": {"jql": "assignee = currentUser()", "project_key": "one nexus"},
    }
    body.update(over)
    return body


async def _raw_row(connection_id: str) -> tuple[bytes | None, str | None]:
    async with SessionFactory() as s:
        row = await s.get(IntegrationConnection, uuid.UUID(connection_id))
        assert row is not None
        return row.secret_ciphertext, row.secret_last4


# ═══════════════════════════════════════════════════════════════════════
#  Validate base_url (thuần)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://acme.atlassian.net", "https://acme.atlassian.net"),
        ("https://Acme.Atlassian.NET/", "https://acme.atlassian.net"),
        ("  https://jira.acme.com:443  ", "https://jira.acme.com"),
    ],
)
def test_base_url_accepts_and_normalizes(raw: str, expected: str) -> None:
    assert validate_base_url(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "http://acme.atlassian.net",
        "ftp://acme.atlassian.net",
        "acme.atlassian.net",
        "https://127.0.0.1",
        "https://127.0.0.1:443",
        "https://10.0.0.5",
        "https://169.254.169.254",
        "https://[::1]",
        "https://[::ffff:127.0.0.1]",
        "https://2130706433",
        "https://0x7f.0.0.1",
        "https://127.1",
        "https://localhost",
        "https://LOCALHOST",
        "https://api.localhost",
        "https://printer.local",
        "https://jira.internal",
        "https://jira",
        "https://acme.atlassian.net.",
        "https://user:pw@acme.atlassian.net",
        "https://user@acme.atlassian.net",
        "https://acme.atlassian.net:8443",
        "https://acme.atlassian.net:",
        "https://acme.atlassian.net/jira",
        "https://acme.atlassian.net/?a=1",
        "https://acme.atlassian.net/#x",
        "https://acme.atlassian.net?x",
        "https://acme.atlassian.net\\@evil.com",
        "https://acme .atlassian.net",
        "https://acme.atlas\nsian.net",
        "https://jíra.acme.com",
        "https://-bad.acme.com",
        "",
        "   ",
    ],
)
def test_base_url_rejects(bad: str) -> None:
    with pytest.raises(ValueError) as exc:
        validate_base_url(bad)
    # Thông báo lỗi không được lặp lại đầu vào.
    if bad.strip():
        assert bad.strip() not in str(exc.value)


CID = uuid.UUID("00000000-0000-4000-8000-000000000001")
OTHER_CID = uuid.UUID("00000000-0000-4000-8000-000000000002")


def test_last4_and_encrypt_roundtrip() -> None:
    ct = secrets_mod.encrypt_token(TOKEN, connection_id=CID, base_url=BASE)
    assert TOKEN.encode() not in ct
    assert secrets_mod.decrypt_token(ct, connection_id=CID, base_url=BASE) == TOKEN
    assert secrets_mod.last4(TOKEN) == "9876"


def test_ciphertext_is_bound_to_connection() -> None:
    ct = secrets_mod.encrypt_token(TOKEN, connection_id=CID, base_url=BASE)
    for kwargs in (
        {"connection_id": OTHER_CID, "base_url": BASE},
        {"connection_id": CID, "base_url": "https://evil.example.com"},
    ):
        with pytest.raises(secrets_mod.SecretsUnavailableError) as exc:
            secrets_mod.decrypt_token(ct, **kwargs)  # type: ignore[arg-type]
        assert TOKEN not in str(exc.value)


def test_key_rotation_old_key_still_decrypts(monkeypatch: pytest.MonkeyPatch) -> None:
    from cryptography.fernet import Fernet

    old_key = settings.integration_secret_key.get_secret_value()
    ct_old = secrets_mod.encrypt_token(TOKEN, connection_id=CID, base_url=BASE)
    new_key = Fernet.generate_key().decode()

    # Chỉ có khoá mới: không giải mã được ciphertext cũ.
    monkeypatch.setattr(settings, "integration_secret_key", SecretStr(new_key))
    with pytest.raises(secrets_mod.SecretsUnavailableError):
        secrets_mod.decrypt_token(ct_old, connection_id=CID, base_url=BASE)

    # Thêm khoá cũ (danh sách phân cách dấu phẩy, chừa khoảng trắng): giải mã được.
    other = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "integration_secret_key_old", SecretStr(f"{other}, {old_key}"))
    assert secrets_mod.decrypt_token(ct_old, connection_id=CID, base_url=BASE) == TOKEN

    # Ghi mới dùng khoá chính; xoay xong thì bỏ khoá cũ vẫn giải mã được.
    rotated = secrets_mod.rotate_ciphertext(ct_old)
    monkeypatch.setattr(settings, "integration_secret_key_old", SecretStr(""))
    assert secrets_mod.decrypt_token(rotated, connection_id=CID, base_url=BASE) == TOKEN
    fresh = secrets_mod.encrypt_token(TOKEN, connection_id=CID, base_url=BASE)
    assert secrets_mod.decrypt_token(fresh, connection_id=CID, base_url=BASE) == TOKEN


def test_malformed_old_key_gives_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "integration_secret_key_old", SecretStr("rác-OLDSECRET"))
    with pytest.raises(secrets_mod.SecretsUnavailableError) as exc:
        secrets_mod.encrypt_token(TOKEN, connection_id=CID, base_url=BASE)
    assert "OLDSECRET" not in str(exc.value)


def test_settings_repr_hides_keys() -> None:
    assert settings.integration_secret_key.get_secret_value() not in repr(settings)
    assert "aW50ZWdyYXRpb24" not in repr(settings)


# ═══════════════════════════════════════════════════════════════════════
#  Endpoint
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.db
async def test_token_never_in_responses_logs_or_plain_in_db(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    created = await client.post(URL, json=_body())
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["has_secret"] is True
    assert data["secret_last4"] == "9876"  # noqa: S105
    assert data["config"]["project_key"] == "ONE_NEXUS"
    assert set(data).isdisjoint({"token", "secret_ciphertext"})

    listed = await client.get(URL)
    patched = await client.patch(f"{URL}/{data['id']}", json={"name": "Đổi tên"})
    # Lỗi validate có kèm token trong body và một lỗi khác (base_url http).
    bad = await client.post(URL, json=_body(name="x", base_url="http://acme.atlassian.net"))
    short = await client.post(URL, json=_body(name="y", token="short"))  # noqa: S106
    for resp in (created, listed, patched, bad, short):
        assert TOKEN not in resp.text
    assert bad.status_code == 422 and short.status_code == 422
    # Mọi phần tử lỗi không có `input` và `ctx`.
    for resp in (bad, short):
        for err in resp.json()["detail"]:
            assert set(err) == {"type", "loc", "msg"}
    assert TOKEN not in caplog.text
    assert settings.integration_secret_key.get_secret_value() not in caplog.text

    ciphertext, last4 = await _raw_row(data["id"])
    assert ciphertext is not None and TOKEN.encode() not in ciphertext
    assert last4 == "9876"
    assert (
        secrets_mod.decrypt_token(
            ciphertext, connection_id=uuid.UUID(data["id"]), base_url=data["base_url"]
        )
        == TOKEN
    )

    # Không có chuỗi token ở bất kỳ cột nào của dòng.
    async with SessionFactory() as s:
        dump = (await s.execute(text("SELECT t::text FROM integration_connections t"))).scalar()
    assert TOKEN not in (dump or "")


@pytest.mark.db
async def test_missing_key_gives_503_without_leaking(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "integration_secret_key", SecretStr(""))
    resp = await client.post(URL, json=_body())
    assert resp.status_code == 503
    assert "INTEGRATION_SECRET_KEY" in resp.json()["detail"]
    assert TOKEN not in resp.text
    # 503 xảy ra trước khi ghi DB: không để lại dòng nào.
    assert (await client.get(URL)).json()["total"] == 0
    # Không có token thì không cần khoá.
    ok = await client.post(URL, json=_body(token=None))
    assert ok.status_code == 201 and ok.json()["has_secret"] is False


@pytest.mark.db
async def test_malformed_key_gives_503(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_key = "not-a-fernet-key-SECRETVALUE"
    monkeypatch.setattr(settings, "integration_secret_key", SecretStr(bad_key))
    resp = await client.post(URL, json=_body())
    assert resp.status_code == 503
    assert bad_key not in resp.text and TOKEN not in resp.text


@pytest.mark.db
async def test_patch_keeps_token_unless_told(client: httpx.AsyncClient) -> None:
    conn = (await client.post(URL, json=_body())).json()
    before, _ = await _raw_row(conn["id"])

    for body in ({"name": "A"}, {"name": "B", "token": ""}, {"name": "C", "token": None}):
        resp = await client.patch(f"{URL}/{conn['id']}", json=body)
        assert resp.status_code == 200, resp.text
        assert resp.json()["has_secret"] is True
        assert (await _raw_row(conn["id"]))[0] == before

    new_token = "NEWTOKEN-abcdef-4321"  # noqa: S105
    resp = await client.patch(f"{URL}/{conn['id']}", json={"token": new_token})
    assert resp.json()["secret_last4"] == "4321"  # noqa: S105
    assert new_token not in resp.text
    after, _ = await _raw_row(conn["id"])
    assert after != before
    assert (
        secrets_mod.decrypt_token(
            after or b"", connection_id=uuid.UUID(conn["id"]), base_url=conn["base_url"]
        )
        == new_token
    )

    both = await client.patch(f"{URL}/{conn['id']}", json={"token": new_token, "clear_token": True})
    assert both.status_code == 422

    cleared = await client.patch(f"{URL}/{conn['id']}", json={"clear_token": True})
    assert cleared.json()["has_secret"] is False and cleared.json()["secret_last4"] is None
    assert await _raw_row(conn["id"]) == (None, None)


@pytest.mark.db
async def test_changing_base_url_requires_new_token(client: httpx.AsyncClient) -> None:
    conn = (await client.post(URL, json=_body())).json()
    other = "https://other.atlassian.net"
    resp = await client.patch(f"{URL}/{conn['id']}", json={"base_url": other})
    assert resp.status_code == 422
    assert (await client.get(URL)).json()["items"][0]["base_url"] == BASE

    ok = await client.patch(f"{URL}/{conn['id']}", json={"base_url": other, "token": TOKEN})
    assert ok.status_code == 200 and ok.json()["base_url"] == other
    # Gửi lại đúng host cũ thì không đòi token.
    same = await client.patch(f"{URL}/{conn['id']}", json={"base_url": other})
    assert same.status_code == 200


@pytest.mark.db
@pytest.mark.parametrize(
    "bad_url",
    [
        "http://acme.atlassian.net",
        "https://127.0.0.1",
        "https://localhost",
        "https://user:pw@acme.atlassian.net",
        "https://10.1.2.3",
        "https://acme.atlassian.net:9999",
        "https://acme.atlassian.net/x?y=1",
    ],
)
async def test_create_and_patch_reject_bad_base_url(
    client: httpx.AsyncClient, bad_url: str
) -> None:
    resp = await client.post(URL, json=_body(base_url=bad_url))
    assert resp.status_code == 422
    assert bad_url not in resp.text and TOKEN not in resp.text
    conn = (await client.post(URL, json=_body())).json()
    assert (
        await client.patch(f"{URL}/{conn['id']}", json={"base_url": bad_url, "token": TOKEN})
    ).status_code == 422


@pytest.mark.db
async def test_validation_errors_and_conflict(client: httpx.AsyncClient) -> None:
    conn = (await client.post(URL, json=_body())).json()
    dup = await client.post(URL, json=_body())
    assert dup.status_code == 409 and TOKEN not in dup.text
    assert (await client.patch(f"{URL}/{conn['id']}", json={"name": None})).status_code == 422
    assert (
        await client.post(URL, json=_body(name="z", config={"api_key": "x"}))
    ).status_code == 422
    assert (await client.post(URL, json=_body(name="z", kind="bogus"))).status_code == 422
    assert (await client.patch(f"{URL}/{uuid.uuid4()}", json={"name": "q"})).status_code == 404


@pytest.mark.db
async def test_delete_and_pagination(client: httpx.AsyncClient) -> None:
    ids = [(await client.post(URL, json=_body(name=f"c{i}"))).json()["id"] for i in range(3)]
    page = (await client.get(URL, params={"limit": 2, "offset": 0})).json()
    assert page["total"] == 3 and len(page["items"]) == 2 and page["limit"] == 2
    assert (await client.delete(f"{URL}/{ids[0]}")).status_code == 204
    assert (await client.delete(f"{URL}/{ids[0]}")).status_code == 404
    assert (await client.get(URL)).json()["total"] == 2


@pytest.mark.db
async def test_requires_api_key() -> None:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anon:
        assert (await anon.get(URL)).status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════
#  Vòng sửa sau review (B4a)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.db
async def test_ciphertext_copied_to_other_connection_fails_to_decrypt(
    client: httpx.AsyncClient,
) -> None:
    a = (await client.post(URL, json=_body(name="A"))).json()
    b = (await client.post(URL, json=_body(name="B", base_url="https://evil.atlassian.net"))).json()
    ct_a, _ = await _raw_row(a["id"])
    assert ct_a is not None
    # Kẻ có quyền ghi DB chép ciphertext của A sang B (khác id và khác host).
    async with SessionFactory() as s:
        row = await s.get(IntegrationConnection, uuid.UUID(b["id"]))
        assert row is not None
        row.secret_ciphertext = ct_a
        await s.commit()
    ct_b, _ = await _raw_row(b["id"])
    with pytest.raises(secrets_mod.SecretsUnavailableError):
        secrets_mod.decrypt_token(
            ct_b or b"", connection_id=uuid.UUID(b["id"]), base_url=b["base_url"]
        )
    # Với đúng kết nối gốc thì vẫn giải mã được.
    assert (
        secrets_mod.decrypt_token(ct_a, connection_id=uuid.UUID(a["id"]), base_url=a["base_url"])
        == TOKEN
    )


@pytest.mark.db
@pytest.mark.parametrize(
    "override",
    [
        {"name": "a\x00b"},
        {"name": "a\nb"},
        {"account_email": "me\x00@acme.com"},
        {"config": {"jql": "project = X\x00"}},
        {"config": {"project_key": "AB\x00"}},
        {"config": {"project_name": "Tên\x07"}},
    ],
)
async def test_control_chars_are_422_not_500(
    client: httpx.AsyncClient, override: dict[str, object]
) -> None:
    resp = await client.post(URL, json=_body(**override))
    assert resp.status_code == 422, resp.text
    assert TOKEN not in resp.text
    conn = (await client.post(URL, json=_body())).json()
    assert (await client.patch(f"{URL}/{conn['id']}", json=override)).status_code == 422


@pytest.mark.db
async def test_multiline_jql_is_allowed(client: httpx.AsyncClient) -> None:
    jql = "project = X\nAND status = Open"
    resp = await client.post(URL, json=_body(config={"jql": jql}))
    assert resp.status_code == 201 and resp.json()["config"]["jql"] == jql


@pytest.mark.db
async def test_secret_last4_is_varchar_and_kind_check_matches_model() -> None:
    import re

    from app.models.enums import IntegrationKind

    async with SessionFactory() as s:
        col = (
            await s.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'integration_connections' AND column_name = 'secret_last4'"
                )
            )
        ).scalar()
        assert col == "character varying"
        defn = (
            await s.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname = 'ck_integration_connections_kind_valid'"
                )
            )
        ).scalar()
    assert defn is not None
    # Postgres viết lại `kind IN (...)` thành `= ANY(...)`: so tập giá trị, không so chuỗi.
    assert set(re.findall(r"'([^']+)'", defn)) == {m.value for m in IntegrationKind}


def _integrity_error(constraint: str | None) -> IntegrityError:
    class _Orig(Exception):
        constraint_name = constraint

    return IntegrityError("INSERT ...", {}, _Orig())


@pytest.mark.db
async def test_integrity_error_is_classified_by_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import integration_service
    from app.services.errors import ConflictError, ValidationError

    async with SessionFactory() as s:

        async def boom(constraint: str | None) -> None:
            async def flush() -> None:
                raise _integrity_error(constraint)

            monkeypatch.setattr(s, "flush", flush)
            await integration_service._flush_or_classify(s, "trùng")

        with pytest.raises(ConflictError):
            await boom("uq_integration_connections_kind_name")
        with pytest.raises(ValidationError):
            await boom("ck_integration_connections_base_url_https")
        # Constraint lạ hay không rõ tên: KHÔNG được báo nhầm là "trùng tên".
        for other in ("pk_integration_connections", "fk_something", None):
            with pytest.raises(IntegrityError):
                await boom(other)


@pytest.mark.db
async def test_real_duplicate_name_reports_constraint_name(client: httpx.AsyncClient) -> None:
    """Driver thật có cung cấp tên constraint (nếu không, 409 sẽ không bao giờ xảy ra)."""
    await client.post(URL, json=_body())
    resp = await client.post(URL, json=_body())
    assert resp.status_code == 409
    assert "tên" in resp.json()["detail"]


@pytest.mark.db
async def test_patch_waits_on_row_lock_then_409(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import integration_service

    conn = (await client.post(URL, json=_body())).json()
    monkeypatch.setattr(integration_service, "_ROW_LOCK_TIMEOUT", "200ms")
    async with SessionFactory() as holder:
        await holder.execute(
            text("SELECT 1 FROM integration_connections WHERE id = :i FOR UPDATE"),
            {"i": conn["id"]},
        )
        patched = await client.patch(f"{URL}/{conn['id']}", json={"name": "Chen ngang"})
        deleted = await client.delete(f"{URL}/{conn['id']}")
        await holder.rollback()
    assert patched.status_code == 409 and deleted.status_code == 409
    assert (await client.patch(f"{URL}/{conn['id']}", json={"name": "Sau"})).status_code == 200


@pytest.mark.db
async def test_audit_log_has_fields_but_no_values(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    conn = (await client.post(URL, json=_body())).json()
    rotate = {"name": "Tên mới", "token": "NEWTOKEN-abc-0000"}
    await client.patch(f"{URL}/{conn['id']}", json=rotate)
    await client.patch(f"{URL}/{conn['id']}", json={"clear_token": True})
    await client.patch(f"{URL}/{conn['id']}", json={"name": "Tên mới"})  # không đổi gì
    await client.delete(f"{URL}/{conn['id']}")

    audits = [r for r in caplog.records if getattr(r, "audit", None) == "integration"]
    summary = [
        (r.audit_action, r.changed_fields, r.has_secret_before, r.has_secret_after)  # type: ignore[attr-defined]
        for r in audits
    ]
    assert summary == [
        ("create", [], False, True),
        ("update", ["name", "token"], True, True),
        ("update", ["token"], True, False),
        ("update", [], False, False),
        ("delete", [], False, False),
    ]
    assert all(r.connection_id == conn["id"] for r in audits)  # type: ignore[attr-defined]
    blob = " ".join(r.getMessage() + repr(r.__dict__) for r in audits)
    for secret in (TOKEN, "NEWTOKEN", "Tên mới", "me@acme.com", "acme.atlassian"):
        assert secret not in blob


@pytest.mark.db
async def test_engine_hides_statement_parameters() -> None:
    from sqlalchemy.exc import DBAPIError

    from app.db.session import engine

    assert engine.sync_engine.hide_parameters is True
    async with SessionFactory() as s:
        with pytest.raises(DBAPIError) as exc:
            await s.execute(
                text("SELECT no_such_column, :n FROM integration_connections"),
                {"n": "SECRET-PARAM-VALUE"},
            )
    # Chỉ tham số do SQLAlchemy in mới bị ẩn. Thông điệp DETAIL do chính Postgres sinh
    # (vd. "Failing row contains (...)" khi vi phạm NOT NULL/CHECK) vẫn có thể chứa giá trị:
    # hide_parameters không che được, nên log lỗi DB vẫn phải coi là nhạy cảm.
    assert "SECRET-PARAM-VALUE" not in str(exc.value)
