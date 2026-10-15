"""CLI quản lý đăng nhập: gán chủ cho dữ liệu cũ, mời user, tài khoản nội bộ, mint JWT dev.

Chạy trong container `api` (orchestrator nối vào Makefile):

  python -m app.cli.auth bootstrap --owner <email-admin> [--dry-run]
  python -m app.cli.auth invite --email <email> [--role member|lead|admin] [--name <tên>]
                               [--alias <tên>]... [--aliases "a,b"]
  python -m app.cli.auth token --email <email> [--ttl 60]
  python -m app.cli.auth create-local --username <u> --email <email> [--role ...] [--name <tên>]
                               [--alias <tên>]... [--aliases "a,b"]
  python -m app.cli.auth reset-password (--email <email> | --username <u>)
  python -m app.cli.auth unlock (--email <email> | --username <u>)
  python -m app.cli.auth revoke --email <email>
  python -m app.cli.auth disable --email <email>
  python -m app.cli.auth enable --email <email>
  python -m app.cli.auth alias --email <email> (--alias <tên> | --set "a,b" | --remove "a,b")
                               [--source jira]

══════════════════════════════════════════════════════════════════════
 `token` in ra một JWT hợp lệ cho user. Ai chạy được lệnh này (vào được container core) vốn
 đã có toàn quyền trên máy đó, nên không thêm lớp bảo vệ riêng. In token CHỈ ra stdout, không
 log; đừng dán vào chat hay commit.

 `create-local` và `reset-password` in MẬT KHẨU TẠM ra stdout đúng một lần (dòng cuối). Chỉ
 hash được lưu; đừng dán vào chat, đừng để trong lịch sử shell hay log CI.
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
from app.models.enums import (
    AliasSource,
    AuditAction,
    AuthProvider,
    SettingKey,
    UserRole,
    UserStatus,
)
from app.models.user import User
from app.schemas.admin import clean_initial_aliases
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

    # 3. Sao chép (không xoá) cài đặt cũ: current_users -> alias Jira.
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


def _collect_aliases(args: argparse.Namespace) -> list[str]:
    """Gộp `--alias` (lặp được) và `--aliases "a,b"`, kiểm như API (422 thì ở đây là mã 2).
    Kiểm TRƯỚC khi mở transaction để alias dị dạng không để lại user nửa vời."""
    raw = list(args.alias or [])
    if args.aliases:
        raw.extend(args.aliases.split(","))
    try:
        return clean_initial_aliases([n for n in raw if n.strip()])
    except ValueError as exc:
        raise CliError(str(exc)) from exc


def _print_alias_result(added: list[str], skipped: list[str]) -> None:
    for name in added:
        print(f"Đã thêm alias {name!r}")
    for name in skipped:
        print(f"CẢNH BÁO: alias {name!r} đã thuộc user khác, bỏ qua")


async def _cmd_invite(args: argparse.Namespace) -> int:
    aliases = _collect_aliases(args)
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
        added, skipped = await user_service.assign_initial_aliases(
            session, user, aliases, via="cli"
        )
        await session.commit()
    print(f"Đã mời {user.email} (role {user.role.value}, id {user.id}). Người được mời đăng nhập")
    print("bằng Google với đúng địa chỉ này để kích hoạt.")
    _print_alias_result(added, skipped)
    return EXIT_OK


async def _cmd_token(args: argparse.Namespace) -> int:
    async with SessionFactory() as session:
        user: User | None = await user_service.get_by_email(session, args.email)
        if user is None:
            raise CliError("Không có user với email này (mời trước bằng lệnh invite)")
        if user.status is not UserStatus.ACTIVE:
            hint = (
                "mở khoá bằng lệnh enable"
                if user.auth_provider is AuthProvider.LOCAL
                else "đăng nhập bằng Google một lần để kích hoạt"
            )
            raise CliError(
                f"User ở trạng thái {user.status.value}: core chỉ nhận token của user active "
                f"({hint})"
            )
        token = mint_token(user.id, user.session_version, ttl=args.ttl)
    # Chỉ token ra stdout để `$(...)` bắt được gọn.
    print(token)
    return EXIT_OK


# ═══════════════════════════════════════════════════════════════════════
#  revoke, disable, enable, alias
# ═══════════════════════════════════════════════════════════════════════


async def _require_user(session: AsyncSession, email: str) -> User:
    """Khoá dòng user (tránh hai lệnh tăng `session_version` đè nhau) hoặc báo lỗi mã 2."""
    user = await user_service.get_by_email(session, email, lock=True)
    if user is None:
        raise CliError("Không có user với email này")
    return user


async def _warn_if_no_admin(session: AsyncSession) -> None:
    """CLI không bị chặn bởi `last_admin` (người có shell là chủ máy) nhưng phải báo."""
    if await user_service.count_active_admins(session) == 0:
        print(
            "CẢNH BÁO: không còn admin hoạt động nào. Dùng `create-local --role admin` hoặc "
            "ADMIN_EMAILS để lấy lại quyền quản trị.",
            file=sys.stderr,
        )


async def _cmd_revoke(args: argparse.Namespace) -> int:
    async with SessionFactory() as session:
        user = await _require_user(session, args.email)
        await user_service.revoke_sessions(session, user.id, via="cli")
        await session.commit()
    print(f"Đã thu hồi mọi phiên của {user.email}.")
    return EXIT_OK


async def _cmd_disable(args: argparse.Namespace) -> int:
    async with SessionFactory() as session:
        user = await _require_user(session, args.email)
        # Tăng cả sv (trong update_user): token đã cấp bị từ chối ngay cả khi sau này enable lại.
        user = await user_service.update_user(
            session, user.id, {"status": UserStatus.DISABLED.value}, via="cli", enforce=False
        )
        await _warn_if_no_admin(session)
        await session.commit()
    print(f"Đã khoá {user.email} và thu hồi mọi phiên.")
    return EXIT_OK


async def _cmd_enable(args: argparse.Namespace) -> int:
    async with SessionFactory() as session:
        user = await _require_user(session, args.email)
        # Tài khoản nội bộ -> active. Google chưa từng đăng nhập (không có google_sub) thì
        # update_user lưu "invited" để còn kích hoạt.
        user = await user_service.update_user(
            session, user.id, {"status": UserStatus.ACTIVE.value}, via="cli", enforce=False
        )
        await session.commit()
    print(f"Đã mở khoá {user.email}, trạng thái {user.status.value}.")
    return EXIT_OK


async def _cmd_alias(args: argparse.Namespace) -> int:
    async with SessionFactory() as session:
        user = await _require_user(session, args.email)
        source = AliasSource(args.source)
        removed: list[str] = []
        skipped: list[str] = []
        # `_require_user` đã khoá dòng user: thêm/gỡ song song với nhau được tuần tự hoá.
        # Không tăng session_version: alias được đọc từ DB mỗi request, không nằm trong JWT.
        if args.set_aliases is not None:
            added, removed, skipped = await user_service.set_aliases(
                session, user.id, source, args.set_aliases.split(",")
            )
        elif args.remove is not None:
            removed = await user_service.remove_aliases(
                session, user.id, source, args.remove.split(",")
            )
            added = []
        else:
            added, skipped = await user_service.add_aliases(session, user.id, source, [args.alias])
        if added or removed:
            audit_service.record(
                session,
                AuditAction.USER_ALIASES_CHANGED,
                target_type="user",
                target_id=user.id,
                details={
                    "source": args.source,
                    "added": len(added),
                    "removed": len(removed),
                    "via": "cli",
                },
            )
        await session.commit()
    for name in added:
        print(f"Đã thêm alias {name!r} cho {user.email}")
    for name in removed:
        print(f"Đã gỡ alias {name!r} khỏi {user.email}")
    for name in skipped:
        print(f"Bỏ qua alias {name!r}: đã tồn tại (của user này hoặc user khác)")
    if args.set_aliases is not None or args.remove is not None:
        print(f"Tổng: thêm {len(added)}, gỡ {len(removed)}")
    return EXIT_OK


# ═══════════════════════════════════════════════════════════════════════
#  Tài khoản nội bộ: create-local, reset-password, unlock
# ═══════════════════════════════════════════════════════════════════════


async def _require_local_user(session: AsyncSession, args: argparse.Namespace) -> User:
    """Tìm user theo `--email` hoặc `--username`, khoá dòng."""
    if args.username:
        user = await user_service.get_by_username(session, args.username, lock=True)
    else:
        user = await user_service.get_by_email(session, args.email, lock=True)
    if user is None:
        raise CliError("Không có user khớp")
    return user


async def _cmd_create_local(args: argparse.Namespace) -> int:
    aliases = _collect_aliases(args)
    async with SessionFactory() as session:
        user, temporary = await user_service.create_local_user(
            session,
            username=args.username,
            email=args.email,
            name=args.name,
            role=UserRole(args.role),
            via="cli",
        )
        added, skipped = await user_service.assign_initial_aliases(
            session, user, aliases, via="cli"
        )
        await session.commit()
    print(f"Đã tạo tài khoản nội bộ {user.username} (role {user.role.value}, id {user.id}).")
    # Alias in TRƯỚC mật khẩu: mật khẩu phải là dòng cuối (script lấy `tail -n 1`).
    _print_alias_result(added, skipped)
    print("Mật khẩu tạm (CHỈ HIỆN MỘT LẦN, hết hạn sau 72 giờ, phải đổi ở lần đăng nhập đầu):")
    print(temporary)
    return EXIT_OK


async def _cmd_reset_password(args: argparse.Namespace) -> int:
    async with SessionFactory() as session:
        user = await _require_local_user(session, args)
        user, temporary = await user_service.reset_password(session, user.id, via="cli")
        await session.commit()
    print(f"Đã đặt lại mật khẩu của {user.username} và thu hồi mọi phiên.")
    print("Mật khẩu tạm (CHỈ HIỆN MỘT LẦN, hết hạn sau 72 giờ, phải đổi ở lần đăng nhập đầu):")
    print(temporary)
    return EXIT_OK


async def _cmd_unlock(args: argparse.Namespace) -> int:
    async with SessionFactory() as session:
        user = await _require_local_user(session, args)
        user = await user_service.unlock(session, user.id, via="cli")
        await session.commit()
    print(f"Đã mở khoá đăng nhập tạm cho {user.email}.")
    return EXIT_OK


# ═══════════════════════════════════════════════════════════════════════
#  Điểm vào
# ═══════════════════════════════════════════════════════════════════════


def _add_alias_args(cmd: argparse.ArgumentParser) -> None:
    cmd.add_argument(
        "--alias", action="append", default=[], help="gán alias Jira ngay (lặp lại được)"
    )
    cmd.add_argument("--aliases", default=None, help='gán nhiều alias Jira: "a,b"')


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
    _add_alias_args(inv)
    inv.set_defaults(func=_cmd_invite)

    loc = sub.add_parser("create-local", help="tạo tài khoản nội bộ, in mật khẩu tạm một lần")
    loc.add_argument("--username", required=True)
    loc.add_argument("--email", required=True)
    loc.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.MEMBER.value)
    loc.add_argument("--name", default=None)
    _add_alias_args(loc)
    loc.set_defaults(func=_cmd_create_local)

    for name, func, helptext in (
        ("reset-password", _cmd_reset_password, "đặt lại mật khẩu tài khoản nội bộ"),
        ("unlock", _cmd_unlock, "mở khoá đăng nhập tạm (sau 5 lần sai)"),
    ):
        cmd = sub.add_parser(name, help=helptext)
        who = cmd.add_mutually_exclusive_group(required=True)
        who.add_argument("--email")
        who.add_argument("--username")
        cmd.set_defaults(func=func)

    tok = sub.add_parser("token", help="in JWT cho user active (dev, smoke test)")
    tok.add_argument("--email", required=True)
    tok.add_argument("--ttl", type=int, default=60, help="giây, tối đa 120")
    tok.set_defaults(func=_cmd_token)

    for name, func, helptext in (
        ("revoke", _cmd_revoke, "đăng xuất mọi thiết bị (tăng session_version)"),
        ("disable", _cmd_disable, "khoá user và thu hồi phiên"),
        ("enable", _cmd_enable, "mở khoá user (nội bộ: active; Google: active nếu có google_sub)"),
    ):
        cmd = sub.add_parser(name, help=helptext)
        cmd.add_argument("--email", required=True)
        cmd.set_defaults(func=func)

    ali = sub.add_parser("alias", help="thêm/đặt/gỡ alias (tên trong nguồn ngoài) cho user")
    ali.add_argument("--email", required=True)
    mode = ali.add_mutually_exclusive_group(required=True)
    mode.add_argument("--alias", help="thêm một tên (giữ các tên khác)")
    mode.add_argument(
        "--set",
        dest="set_aliases",
        help='thay TOÀN BỘ alias bằng danh sách "a,b" (thêm cái thiếu, gỡ cái thừa)',
    )
    mode.add_argument("--remove", help='gỡ một hay vài tên, phân cách dấu phẩy: "a,b"')
    ali.add_argument("--source", choices=[a.value for a in AliasSource], default="jira")
    ali.set_defaults(func=_cmd_alias)
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
