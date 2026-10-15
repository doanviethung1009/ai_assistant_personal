"use client";

import Link from "next/link";
import { useOptimistic, useState, useTransition } from "react";

import {
  deleteUserAction,
  resetPasswordAction,
  revokeSessionsAction,
  setAliasesAction,
  unlockUserAction,
  updateUserAction,
  type AdminResult,
} from "@/app/admin/actions";
import { AliasEditor } from "@/components/admin/alias-editor";
import { TempPasswordReveal } from "@/components/admin/temp-password-reveal";
import { formatDateTime } from "@/lib/format";
import { useDisplayTz } from "@/lib/timezone-context";
import { useActionAuth } from "@/lib/use-action-auth";
import {
  USER_ROLES,
  USER_ROLE_LABELS,
  USER_STATUS_LABELS,
  type UserAdmin,
  type UserRole,
} from "@/lib/types";

type Patch = Partial<Pick<UserAdmin, "role" | "status" | "locked_until" | "failed_login_count" | "aliases">>;

/**
 * Bảng người dùng. Đổi role, khoá/mở, mở khoá tạm, alias dùng useOptimistic + useTransition: UI đổi
 * ngay, action lỗi thì tự rollback (state optimistic chỉ sống trong transition) và hiện lỗi. Tạo user,
 * đặt lại mật khẩu, xoá KHÔNG optimistic (cần kết quả thật). Nút khoá trong lúc pending để không gửi
 * chồng. UI chặn sớm dòng của chính mình và tài khoản `is_env_admin`, nhưng core mới là bên quyết định.
 * `nowMs` tính ở server để so `locked_until` cùng một mốc, tránh lệch hydration.
 */
export function UserTable({
  users,
  meId,
  assignees,
  nowMs,
}: {
  users: UserAdmin[];
  meId: string;
  assignees: string[];
  nowMs: number;
}) {
  const tz = useDisplayTz();
  const handleAuth = useActionAuth();
  const [pending, startTransition] = useTransition();
  const [rows, applyPatch] = useOptimistic(users, (state, change: { id: string; patch: Patch }) =>
    state.map((u) => (u.id === change.id ? { ...u, ...change.patch } : u)),
  );
  const [error, setError] = useState<string | null>(null);
  const [editingAliases, setEditingAliases] = useState<string | null>(null);
  const [reveal, setReveal] = useState<{ username: string; password: string } | null>(null);

  /** Chạy một action: lỗi phiên → chuyển trang; lỗi khác → hiện thông báo (và optimistic tự rollback). */
  function run(
    id: string,
    patch: Patch | null,
    call: () => Promise<AdminResult>,
  ) {
    setError(null);
    startTransition(async () => {
      if (patch) applyPatch({ id, patch });
      const result = await call();
      if (!result.ok) {
        if (!handleAuth(result)) setError(result.error);
      }
    });
  }

  function changeRole(user: UserAdmin, role: UserRole) {
    if (role === user.role) return;
    run(user.id, { role }, () => updateUserAction(user.id, { role }));
  }

  function toggleStatus(user: UserAdmin) {
    const next = user.status === "disabled" ? "active" : "disabled";
    if (next === "disabled" && !window.confirm(`Khoá tài khoản ${user.email}? Mọi phiên của họ sẽ bị đăng xuất.`)) return;
    run(user.id, { status: next }, () => updateUserAction(user.id, { status: next }));
  }

  function resetPassword(user: UserAdmin) {
    if (!window.confirm(`Đặt lại mật khẩu của ${user.username ?? user.email}? Mọi phiên của họ sẽ bị đăng xuất.`)) return;
    setError(null);
    startTransition(async () => {
      const result = await resetPasswordAction(user.id);
      if (!result.ok) {
        if (!handleAuth(result)) setError(result.error);
        return;
      }
      setReveal({ username: user.username ?? user.email, password: result.temporaryPassword });
    });
  }

  function remove(user: UserAdmin) {
    if (!window.confirm(`Xoá vĩnh viễn ${user.email}? Không hoàn tác được.`)) return;
    run(user.id, null, () => deleteUserAction(user.id));
  }

  return (
    <div className="space-y-3">
      {error ? (
        <p role="alert" className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">
          {error}
        </p>
      ) : null}

      {rows.length === 0 ? (
        <p className="rounded-md border border-[var(--color-border)] px-4 py-6 text-center text-sm text-[var(--color-ink-muted)]">
          Không có người dùng nào khớp bộ lọc.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full text-left text-sm">
            <thead className="bg-[var(--color-surface-raised)] text-xs uppercase tracking-wide text-[var(--color-ink-muted)]">
              <tr>
                <th className="px-3 py-2">Người dùng</th>
                <th className="px-3 py-2">Vai trò</th>
                <th className="px-3 py-2">Trạng thái</th>
                <th className="px-3 py-2">Đăng nhập gần nhất</th>
                <th className="px-3 py-2">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {rows.map((user) => {
                const isSelf = user.id === meId;
                const protectedRow = isSelf || user.is_env_admin;
                const locked = user.locked_until !== null && Date.parse(user.locked_until) > nowMs;
                const btn =
                  "rounded px-2 py-1 text-xs transition hover:bg-[var(--color-surface-hover)] disabled:cursor-not-allowed disabled:opacity-40";
                return (
                  <tr key={user.id} className="align-top">
                    <td className="px-3 py-2">
                      <p className="font-medium">{(user.name || user.email).slice(0, 80)}</p>
                      <p className="text-xs text-[var(--color-ink-muted)]">
                        {user.email.slice(0, 120)}
                        {user.username ? ` · ${user.username.slice(0, 64)}` : ""}
                      </p>
                      <p className="mt-1 flex flex-wrap gap-1 text-[10px]">
                        <span className="rounded-full bg-black/15 px-2 py-0.5">{user.auth_provider === "local" ? "Nội bộ" : "Google"}</span>
                        {isSelf ? <span className="rounded-full bg-[var(--color-accent)]/15 px-2 py-0.5">Bạn</span> : null}
                        {user.is_env_admin ? <span className="rounded-full bg-black/15 px-2 py-0.5">ADMIN_EMAILS</span> : null}
                        {user.aliases.map((a) => (
                          <span key={`${a.source}:${a.alias}`} className="rounded-full bg-orange-500/10 px-2 py-0.5 text-orange-600 dark:text-orange-400">
                            {a.alias.slice(0, 60)}
                          </span>
                        ))}
                      </p>
                      {editingAliases === user.id ? (
                        <div className="mt-2 max-w-sm">
                          <AliasEditor
                            initial={user.aliases.map((a) => a.alias)}
                            suggestions={assignees}
                            disabled={pending}
                            onCancel={() => setEditingAliases(null)}
                            onSave={(list) => {
                              setEditingAliases(null);
                              run(
                                user.id,
                                { aliases: list.map((alias) => ({ source: "jira" as const, alias })) },
                                () => setAliasesAction(user.id, list),
                              );
                            }}
                          />
                        </div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <select
                        aria-label={`Vai trò của ${user.email}`}
                        value={user.role}
                        disabled={pending || protectedRow}
                        onChange={(e) => changeRole(user, e.target.value as UserRole)}
                        title={protectedRow ? "Không đổi được vai trò của chính mình hoặc tài khoản trong ADMIN_EMAILS" : undefined}
                        className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm disabled:opacity-60"
                      >
                        {USER_ROLES.map((r) => (
                          <option key={r} value={r}>
                            {USER_ROLE_LABELS[r]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <p>{USER_STATUS_LABELS[user.status]}</p>
                      {locked ? <p className="text-xs text-[var(--color-warn)]">Đang khoá tạm</p> : null}
                      {user.must_change_password ? <p className="text-xs text-[var(--color-ink-muted)]">Phải đổi mật khẩu</p> : null}
                    </td>
                    <td className="px-3 py-2 text-xs text-[var(--color-ink-muted)]">
                      {user.last_login_at ? formatDateTime(user.last_login_at, tz) : "Chưa bao giờ"}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        <button type="button" className={btn} disabled={pending || protectedRow} onClick={() => toggleStatus(user)}>
                          {user.status === "disabled" ? "Mở khoá" : "Khoá"}
                        </button>
                        {locked ? (
                          <button
                            type="button"
                            className={btn}
                            disabled={pending}
                            onClick={() =>
                              run(user.id, { locked_until: null, failed_login_count: 0 }, () => unlockUserAction(user.id))
                            }
                          >
                            Mở khoá tạm
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className={btn}
                          disabled={pending}
                          onClick={() => {
                            if (window.confirm(`Thu hồi mọi phiên đăng nhập của ${user.email}?`)) {
                              run(user.id, null, () => revokeSessionsAction(user.id));
                            }
                          }}
                        >
                          Thu hồi phiên
                        </button>
                        {user.auth_provider === "local" && !isSelf ? (
                          <button type="button" className={btn} disabled={pending} onClick={() => resetPassword(user)}>
                            Đặt lại mật khẩu
                          </button>
                        ) : null}
                        <button type="button" className={btn} disabled={pending} onClick={() => setEditingAliases(user.id)}>
                          Alias
                        </button>
                        <Link href={`/admin/audit?target=${user.id}`} className={btn}>
                          Nhật ký
                        </Link>
                        <button type="button" className={`${btn} text-[var(--color-danger)]`} disabled={pending || protectedRow} onClick={() => remove(user)}>
                          Xoá
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {reveal ? (
        <TempPasswordReveal
          title="Mật khẩu tạm mới"
          username={reveal.username}
          password={reveal.password}
          onClose={() => setReveal(null)}
        />
      ) : null}
    </div>
  );
}
