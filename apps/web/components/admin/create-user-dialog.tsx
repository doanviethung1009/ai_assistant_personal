"use client";

import { Suspense, use, useId, useState, useTransition } from "react";

import { createLocalUserAction, inviteGoogleUserAction } from "@/app/admin/actions";
import { TempPasswordReveal } from "@/components/admin/temp-password-reveal";
import { normalizeAliases, skippedAliasesMessage, splitAliasText } from "@/lib/alias-input";
import { useActionAuth } from "@/lib/use-action-auth";
import { USER_ROLES, USER_ROLE_LABELS } from "@/lib/types";

type Tab = "local" | "google";

const INPUT =
  "mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]";

/**
 * Nút "Thêm người dùng" + hộp thoại hai tab: tài khoản nội bộ (core sinh mật khẩu tạm) và mời Google.
 * Mật khẩu tạm đi thẳng từ kết quả Server Action vào state của component này rồi sang
 * TempPasswordReveal; không qua URL, Server Component hay lưu trữ nào (xem cảnh báo ở đó).
 * Ô "Tên trên Jira" gửi lặp field `aliases`; alias đang thuộc người khác bị core bỏ qua (user VẪN được
 * tạo) và hiện cảnh báo, riêng tạo local thì cảnh báo nằm CẠNH mật khẩu tạm, không thay nó.
 * Không optimistic: cần kết quả thật của server (trùng username/email, mật khẩu tạm).
 */
export function CreateUserDialog({ assigneesPromise }: { assigneesPromise?: Promise<string[]> }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("local");
  const [role, setRole] = useState("member");
  const [error, setError] = useState<string | null>(null);
  const [reveal, setReveal] = useState<{ username: string; password: string; notice?: string } | null>(null);
  const [aliasText, setAliasText] = useState("");
  const [inviteNotice, setInviteNotice] = useState<string | null>(null);
  const listId = useId();
  const [pending, startTransition] = useTransition();
  const handleAuth = useActionAuth();

  function close() {
    setOpen(false);
    setError(null);
    setReveal(null);
    setInviteNotice(null);
    setAliasText("");
  }

  function submit(formData: FormData) {
    setError(null);
    const parsed = normalizeAliases(splitAliasText(aliasText));
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }
    formData.delete("aliases");
    for (const alias of parsed.aliases) formData.append("aliases", alias);
    startTransition(async () => {
      if (tab === "local") {
        const result = await createLocalUserAction(formData);
        if (!result.ok) {
          if (!handleAuth(result)) setError(result.error);
          return;
        }
        setOpen(false);
        setReveal({
          username: result.username,
          password: result.temporaryPassword,
          ...(result.aliasesSkipped.length ? { notice: skippedAliasesMessage(result.aliasesSkipped) } : {}),
        });
      } else {
        const result = await inviteGoogleUserAction(formData);
        if (!result.ok) {
          if (!handleAuth(result)) setError(result.error);
          return;
        }
        if (result.aliasesSkipped.length) {
          setOpen(false);
          setInviteNotice(skippedAliasesMessage(result.aliasesSkipped, "được mời"));
        } else {
          close();
        }
      }
    });
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90"
      >
        Thêm người dùng
      </button>

      {open ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 px-4" role="presentation">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-user-title"
            className="w-full max-w-md rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-6 shadow-xl"
          >
            <h2 id="create-user-title" className="text-lg font-semibold">
              Thêm người dùng
            </h2>
            <div className="mt-3 flex gap-1 rounded-md bg-black/10 p-1 text-sm" role="tablist">
              {(["local", "google"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  role="tab"
                  aria-selected={tab === t}
                  onClick={() => {
                    setTab(t);
                    setError(null);
                  }}
                  className={`flex-1 rounded px-3 py-1.5 ${tab === t ? "bg-[var(--color-surface)] font-medium" : "text-[var(--color-ink-muted)]"}`}
                >
                  {t === "local" ? "Tài khoản nội bộ" : "Mời qua Google"}
                </button>
              ))}
            </div>

            <form action={submit} className="mt-4 space-y-3" autoComplete="off">
              {error ? (
                <p role="alert" className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">
                  {error}
                </p>
              ) : null}
              {tab === "local" ? (
                <label className="block text-sm">
                  <span className="text-[var(--color-ink-muted)]">Tên đăng nhập</span>
                  <input name="username" required minLength={3} maxLength={64} pattern="[a-zA-Z0-9][a-zA-Z0-9._\-]{2,63}" className={INPUT} autoCapitalize="none" spellCheck={false} />
                </label>
              ) : null}
              <label className="block text-sm">
                <span className="text-[var(--color-ink-muted)]">Email</span>
                <input name="email" type="email" required maxLength={320} className={INPUT} />
              </label>
              <label className="block text-sm">
                <span className="text-[var(--color-ink-muted)]">Tên hiển thị (tuỳ chọn)</span>
                <input name="name" maxLength={200} className={INPUT} />
              </label>
              <label className="block text-sm">
                <span className="text-[var(--color-ink-muted)]">Vai trò</span>
                <select name="role" value={role} onChange={(e) => setRole(e.target.value)} className={INPUT}>
                  {USER_ROLES.map((r) => (
                    <option key={r} value={r}>
                      {USER_ROLE_LABELS[r]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <span className="text-[var(--color-ink-muted)]">Tên trên Jira (tuỳ chọn, cách nhau bằng dấu phẩy, tối đa 20)</span>
                <input
                  list={listId}
                  value={aliasText}
                  onChange={(e) => setAliasText(e.target.value)}
                  // 4100 = 20 alias x 200 ký tự + dấu phẩy; core vẫn kiểm từng mục.
                  maxLength={4100}
                  className={INPUT}
                  autoComplete="off"
                />
                {/* Gợi ý chỉ đọc khi dialog mở, trong Suspense: không chặn shell trang. Giới hạn đã chấp
                    nhận: datalist + dấu phẩy nên chọn một gợi ý sẽ thay CẢ chuỗi đang gõ (không làm chip). */}
                {assigneesPromise ? (
                  <Suspense fallback={null}>
                    <AssigneeOptions id={listId} promise={assigneesPromise} />
                  </Suspense>
                ) : (
                  <datalist id={listId} />
                )}
              </label>
              {tab === "local" && role === "admin" ? (
                <p className="text-xs text-[var(--color-warn)]">
                  Lưu ý: tài khoản nội bộ không có xác thực hai lớp (2FA). Quản trị viên chính nên dùng Google.
                </p>
              ) : null}
              {tab === "local" ? (
                <p className="text-xs text-[var(--color-ink-muted)]">
                  Hệ thống tự sinh mật khẩu tạm và chỉ hiện một lần sau khi tạo.
                </p>
              ) : null}
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={close} className="rounded-md border border-[var(--color-border)] px-4 py-2 text-sm hover:bg-[var(--color-surface-hover)]">
                  Huỷ
                </button>
                <button type="submit" disabled={pending} className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
                  {pending ? "Đang tạo..." : tab === "local" ? "Tạo tài khoản" : "Gửi lời mời"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {reveal ? (
        <TempPasswordReveal
          title="Mật khẩu tạm"
          username={reveal.username}
          password={reveal.password}
          {...(reveal.notice ? { notice: reveal.notice } : {})}
          onClose={close}
        />
      ) : null}

      {inviteNotice ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" role="presentation">
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="invite-notice-title"
            aria-describedby="invite-notice-desc"
            onKeyDown={(e) => {
              if (e.key === "Escape") close();
            }}
            className="w-full max-w-md rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-6 shadow-xl"
          >
            <h2 id="invite-notice-title" className="text-lg font-semibold">Đã thêm lời mời</h2>
            <p id="invite-notice-desc" className="mt-3 rounded-md border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-sm text-[var(--color-warn)]">
              {inviteNotice}
            </p>
            <div className="mt-5 flex justify-end">
              <button type="button" autoFocus onClick={close} className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90">
                Đã hiểu
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

/** Đọc promise gợi ý alias bằng use(); promise đã có .catch ở page nên không ném lỗi. */
function AssigneeOptions({ id, promise }: { id: string; promise: Promise<string[]> }) {
  const assignees = use(promise);
  return (
    <datalist id={id}>
      {assignees.slice(0, 200).map((s) => (
        <option key={s} value={s} />
      ))}
    </datalist>
  );
}
