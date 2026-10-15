"use client";

import { useActionState, useEffect, useState } from "react";

import { changeMyPasswordAction, type ChangePasswordState } from "@/app/me/actions";

const MIN_LENGTH = 12;

/**
 * Form đổi mật khẩu (tự nguyện ở /me/password, và bắt buộc khi layout thay nội dung trang vì
 * must_change_password). Chính sách thật nằm ở core; ở đây chỉ gợi ý độ dài và kiểm khớp xác nhận để
 * đỡ một vòng gọi mạng. Không lưu mật khẩu vào state ngoài giá trị ô nhập đang gõ, không log.
 */
export function ChangePasswordForm({ forced = false }: { forced?: boolean }) {
  const [state, formAction, pending] = useActionState<ChangePasswordState, FormData>(changeMyPasswordAction, {});
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const length = Array.from(next).length;
  const mismatch = confirm.length > 0 && next !== confirm;

  // Hết/thu hồi phiên, hoặc đổi xong mà chưa đăng nhập lại được: về /auth/expired (xoá cookie rồi về /login).
  // Điều hướng cứng vì /auth/expired là route handler.
  useEffect(() => {
    if (
      state.code === "session_expired" ||
      state.code === "unauthenticated" ||
      (state.ok && state.code === "relogin_required")
    ) {
      window.location.assign("/auth/expired");
    }
  }, [state]);

  return (
    <form action={formAction} className="space-y-4" autoComplete="off">
      {forced ? (
        <p role="status" className="rounded-md border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-sm text-[var(--color-warn)]">
          Bạn cần đổi mật khẩu trước khi tiếp tục. Mật khẩu tạm do quản trị viên cấp chỉ dùng được một lần.
        </p>
      ) : null}
      {state.error ? (
        <div role="alert" className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">
          <p>{state.error}</p>
          {state.reasons && state.reasons.length > 0 ? (
            <ul className="mt-1 list-disc pl-5 text-xs">
              {state.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <label className="block text-sm">
        <span className="text-[var(--color-ink-muted)]">Mật khẩu hiện tại</span>
        <input
          name="current_password"
          type="password"
          required
          maxLength={1024}
          autoComplete="current-password"
          className="mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
        />
      </label>
      <label className="block text-sm">
        <span className="text-[var(--color-ink-muted)]">Mật khẩu mới</span>
        <input
          name="new_password"
          type="password"
          required
          maxLength={1024}
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          className="mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
        />
        <span className={`mt-1 block text-xs ${length >= MIN_LENGTH ? "text-[var(--color-ink-muted)]" : "text-[var(--color-warn)]"}`}>
          {length} ký tự (tối thiểu {MIN_LENGTH}). Cụm từ dài dễ nhớ tốt hơn ký tự đặc biệt.
        </span>
      </label>
      <label className="block text-sm">
        <span className="text-[var(--color-ink-muted)]">Nhập lại mật khẩu mới</span>
        <input
          name="confirm_password"
          type="password"
          required
          maxLength={1024}
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
        />
        {mismatch ? <span className="mt-1 block text-xs text-[var(--color-danger)]">Hai ô mật khẩu mới chưa khớp.</span> : null}
      </label>

      <button
        type="submit"
        disabled={pending || length < MIN_LENGTH || next !== confirm}
        className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-60"
      >
        {pending ? "Đang đổi..." : "Đổi mật khẩu"}
      </button>
      <p className="text-xs text-[var(--color-ink-muted)]">
        Đổi xong, các thiết bị khác đang đăng nhập bằng tài khoản này sẽ bị đăng xuất.
      </p>
    </form>
  );
}
