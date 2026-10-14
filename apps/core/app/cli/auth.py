"""CLI quản lý đăng nhập: gán chủ cho dữ liệu cũ, mời user, mint JWT dev.

Chạy trong container `api` (orchestrator nối vào Makefile):

  python -m app.cli.auth bootstrap --owner <email-admin> [--dry-run]
  python -m app.cli.auth invite --email <email> [--role member|lead|admin] [--name <tên>]
  python -m app.cli.auth token --email <email> [--ttl 60]

══════════════════════════════════════════════════════════════════════
 `token` in ra một JWT hợp lệ cho user. Ai chạy được lệnh này (vào được container core) vốn
 đã có toàn quyền trên máy đó, nên không thêm lớp bảo vệ riêng. In token CHỈ ra stdout, không
 log; đừng dán vào chat hay commit.
══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import mint_token
from app.core.config import settings
from app.db.session import SessionFactory, engine
from app.models.enums import AliasSource, AuditAction, SettingKey, UserRole, UserStatus
from app.models.user import User
from app.services import audit_service, settings_service, user_service
from app.services.errors import DomainError

EXIT_OK = 0
EXIT_ERROR = 2


class CliError(Exception):
    """Lỗi người dùng gõ sai/điều kiện chưa đủ: in thông báo, thoát mã 2 (không in traceback)."""


# ═══════════════════════════════════════════════════════════════════════
#  bootstrap
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class BootstrapReport:
    owner_id: uuid.UUID
    tasks: int
    notes: int
    aliases_added: list[str]
    aliases_skipped: list[str]
    timezone_set: str | None


async def _count_null_owner(session: AsyncSession, table: str, extra: str = "") -> int:
    # `table` và `extra` là hằng của file này, không phải đầu vào người dùng.
    sql = f"SELECT count(*) FROM {table} WHERE owner_id IS NULL {extra}"  # noqa: S608
    return int((await session.execute(text(sql))).scalar_one())


async def bootstrap(session: AsyncSession, owner_email: str, *, dry_run: bool) -> BootstrapReport:
    """Gán chủ cho dữ liệu có sẵn trước khi có đăng nhập. Idempotent, MỘT transaction.

    Không đụng `updated_at`: dùng câu UPDATE thuần SQL (không qua ORM/Core có `onupdate`), vì
    đổi `updated_at` sẽ làm lần nhập file sau báo nhầm `file_older_than_db`. Task `work` và
    project để NULL (thuộc team / dùng chung).
    """
    # 1. Upsert ADMIN_EMAILS (như lúc khởi động) rồi tìm chủ.
    await user_service.sync_admin_emails(session, settings.admin_emails)
    owner_email = user_service.normalize_email(owner_email)
    if owner_email not in settings.admin_emails:
        raise CliError("--owner phải là một email trong ADMIN_EMAILS")
    owner = await user_service.get_by_email(session, owner_email)
    if owner is None:  # không thể xảy ra sau sync_admin_emails, giữ cho chắc
        raise CliError("Không tìm thấy user chủ sau khi đồng bộ ADMIN_EMAILS")

    # 2. Gán chủ cho task personal và note chưa có chủ.
    if dry_run:
        tasks = await _count_null_owner(session, "tasks", "AND scope = 'personal'")
        notes = await _count_null_owner(session, "notes")
    else:
        params = {"owner": owner.id}
        tasks = (
            await session.execute(
                text(
                    "UPDATE tasks SET owner_id = :owner "
                    "WHERE owner_id IS NULL AND scope = 'personal'"
                ),
                params,
            )
        ).rowcount
        notes = (
            await session.execute(
                text("UPDATE notes SET owner_id = :owner WHERE owner_id IS NULL"), params
            )
        ).rowcount

    # 3. Sao chép (không xoá) cài đặt cũ: current_users -> alias Jira, display_timezone -> múi giờ.
    names = await settings_service.get_value(session, SettingKey.CURRENT_USERS)
    added: list[str] = []
    skipped: list[str] = []
    if isinstance(names, list):
        clean = [n for n in names if isinstance(n, str)]
        if dry_run:
            added = [n for n in clean if n.strip()]
        else:
            added, skipped = await user_service.add_aliases(
                session, owner.id, AliasSource.JIRA, clean
            )
    tz = await settings_service.get_value(session, SettingKey.DISPLAY_TIMEZONE)
    timezone_set: str | None = None
    if isinstance(tz, str) and owner.timezone is None:
        timezone_set = tz
        if not dry_run:
            await user_service.set_timezone(session, owner.id, tz)

    if not dry_run:
        # 4. Dữ liệu đã có chủ hết: biến hai CHECK NOT VALID thành VALID (thất bại thì rollback
        # cả bootstrap, in tên constraint chứ không in dữ liệu).
        await session.execute(
            text("ALTER TABLE tasks VALIDATE CONSTRAINT ck_tasks_personal_has_owner")
        )
        await session.execute(text("ALTER TABLE notes VALIDATE CONSTRAINT ck_notes_owner_required"))
        # 5. Nhật ký.
        audit_service.record(
            session,
            AuditAction.BOOTSTRAP_BACKFILL,
            actor_user_id=owner.id,
            target_type="user",
            target_id=owner.id,
            details={"tasks": tasks, "notes": notes, "aliases": len(added)},
        )
    return BootstrapReport(
        owner_id=owner.id,
        tasks=tasks,
        notes=notes,
        aliases_added=added,
        aliases_skipped=skipped,
        timezone_set=timezone_set,
    )


async def _cmd_bootstrap(args: argparse.Namespace) -> int:
    async with SessionFactory() as session:
        report = await bootstrap(session, args.owner, dry_run=args.dry_run)
        if args.dry_run:
            await session.rollback()
        else:
            await session.commit()
    prefix = "[DRY-RUN, không ghi gì] " if args.dry_run else ""
    print(f"{prefix}chủ: {report.owner_id}")
    print(f"{prefix}task personal sẽ gán chủ: {report.tasks}")
    print(f"{prefix}note sẽ gán chủ: {report.notes}")
    print(f"{prefix}alias Jira thêm cho chủ: {len(report.aliases_added)}")
    for name in report.aliases_skipped:
        print(f"CẢNH BÁO: alias {name!r} đã thuộc user khác, bỏ qua")
    if report.timezone_set:
        print(f"{prefix}múi giờ của chủ: {report.timezone_set}")
    if not args.dry_run:
        print("Đã VALIDATE hai CHECK ck_tasks_personal_has_owner và ck_notes_owner_required.")
        print(
            "Két (Vault) trên volume web: đổi tên vault.json thành "
            f"vault-{report.owner_id}.json (chạy trong volume dữ liệu của web)."
        )
    return EXIT_OK


# ═══════════════════════════════════════════════════════════════════════
#  invite, token
# ═══════════════════════════════════════════════════════════════════════


async def _cmd_invite(args: argparse.Namespace) -> int:
    async with SessionFactory() as session:
        user = await user_service.invite(
            session, args.email, UserRole(args.role), name=args.name, invited_by=None
        )
        audit_service.record(
            session,
            AuditAction.USER_INVITED,
            target_type="user",
            target_id=user.id,
            details={"role": user.role.value, "via": "cli"},
        )
        await session.commit()
    print(f"Đã mời {user.email} (role {user.role.value}, id {user.id}). Người được mời đăng nhập")
    print("bằng Google với đúng địa chỉ này để kích hoạt.")
    return EXIT_OK


async def _cmd_token(args: argparse.Namespace) -> int:
    async with SessionFactory() as session:
        user: User | None = await user_service.get_by_email(session, args.email)
        if user is None:
            raise CliError("Không có user với email này (mời trước bằng lệnh invite)")
        if user.status is not UserStatus.ACTIVE:
            raise CliError(
                f"User ở trạng thái {user.status.value}: core chỉ nhận token của user active "
                "(đăng nhập bằng Google một lần để kích hoạt)"
            )
        token = mint_token(user.id, user.session_version, ttl=args.ttl)
    # Chỉ token ra stdout để `$(...)` bắt được gọn.
    print(token)
    return EXIT_OK


# ═══════════════════════════════════════════════════════════════════════
#  Điểm vào
# ═══════════════════════════════════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli.auth", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    boot = sub.add_parser("bootstrap", help="gán chủ cho dữ liệu cũ (idempotent)")
    boot.add_argument("--owner", required=True, help="email admin (phải thuộc ADMIN_EMAILS)")
    boot.add_argument("--dry-run", action="store_true", help="chỉ đếm, không ghi")
    boot.set_defaults(func=_cmd_bootstrap)

    inv = sub.add_parser("invite", help="mời một email")
    inv.add_argument("--email", required=True)
    inv.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.MEMBER.value)
    inv.add_argument("--name", default=None)
    inv.set_defaults(func=_cmd_invite)

    tok = sub.add_parser("token", help="in JWT cho user active (dev, smoke test)")
    tok.add_argument("--email", required=True)
    tok.add_argument("--ttl", type=int, default=60, help="giây, tối đa 120")
    tok.set_defaults(func=_cmd_token)
    return parser


async def _run(args: argparse.Namespace) -> int:
    try:
        return await args.func(args)
    except (CliError, DomainError) as exc:
        print(f"Lỗi: {getattr(exc, 'message', None) or exc}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "ttl", 60) > 120:
        print("Lỗi: --ttl tối đa 120 giây (core từ chối token sống lâu hơn)", file=sys.stderr)
        return EXIT_ERROR
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
