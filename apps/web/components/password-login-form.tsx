"use client";

import { useActionState } from "react";

import { passwordSignInAction, type PasswordSignInState } from "@/app/login/actions";

const ERROR_TEXT: Record<string, string> = {
  invalid_credentials:
    "Sai thông tin đăng nhập hoặc tài khoản tạm bị khoá. Thử lại sau ít phút hoặc liên hệ quản trị viên.",
  rate_limited: "Thử đăng nhập quá nhiều lần. Chờ một phút rồi thử lại.",
  password_login_disabled: "Đăng nhập bằng mật khẩu đang tạm tắt. Liên hệ quản trị viên.",
  unavailable: "Chưa kết nối được máy chủ dữ liệu. Thử lại sau ít phút.",
};

/**
 * Form đăng nhập tài khoản nội bộ. `useActionState` giữ `pending` (khoá nút, không gửi lại) và giữ ô
 * identifier khi lỗi; mật khẩu thì KHÔNG được giữ lại (state không chứa nó, React reset form sau action).
 * Thành công: action ném redirect của Next nên trình duyệt tự chuyển trang.
 */
export function PasswordLoginForm({ callbackUrl }: { callbackUrl: string }) {
  const [state, formAction, pending] = useActionState<PasswordSignInState, FormData>(passwordSignInAction, {});

  return (
    <form action={formAction} className="mt-6 space-y-3">
      <input type="hidden" name="callbackUrl" value={callbackUrl} />
      {state.error ? (
        <p
          role="alert"
          className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]"
        >
          {ERROR_TEXT[state.error] ?? ERROR_TEXT.invalid_credentials}
        </p>
      ) : null}
      <label className="block text-sm">
        <span className="text-[var(--color-ink-muted)]">Tên đăng nhập hoặc email</span>
        <input
          name="identifier"
          type="text"
          required
          maxLength={320}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          defaultValue={state.identifier ?? ""}
          className="mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
        />
      </label>
      <label className="block text-sm">
        <span className="text-[var(--color-ink-muted)]">Mật khẩu</span>
        <input
          name="password"
          type="password"
          required
          maxLength={1024}
          autoComplete="current-password"
          className="mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
        />
      </label>
      <button
        type="submit"
        disabled={pending}
        className="w-full rounded-md bg-[var(--color-accent)] px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-60"
      >
        {pending ? "Đang đăng nhập..." : "Đăng nhập"}
      </button>
    </form>
  );
}
