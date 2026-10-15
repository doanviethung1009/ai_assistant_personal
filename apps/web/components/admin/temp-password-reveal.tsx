"use client";

import { CopyButton } from "@/components/copy-button";

/**
 * Hộp thoại hiện mật khẩu tạm MỘT lần. Giá trị chỉ sống trong state của component cha (client) và
 * biến mất khi bấm "Tôi đã lưu", đóng hộp thoại hoặc rời trang.
 *
 * ══════════════════════════════════════════════════════════════════════
 *  KHÔNG đưa mật khẩu này vào URL, searchParams, localStorage, toast, console hay Server Component
 *  (vào RSC payload / route cache). Không có cách xem lại: mất thì admin đặt lại mật khẩu.
 * ══════════════════════════════════════════════════════════════════════
 */
export function TempPasswordReveal({
  title,
  username,
  password,
  onClose,
}: {
  title: string;
  username: string;
  password: string;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="temp-pw-title"
        className="w-full max-w-md rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-6 shadow-xl"
      >
        <h2 id="temp-pw-title" className="text-lg font-semibold">
          {title}
        </h2>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Tài khoản: <span className="font-medium text-[var(--color-ink)]">{username}</span>
        </p>
        <div className="mt-4 flex items-center gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2">
          <code className="min-w-0 flex-1 select-all break-all font-mono text-base tracking-wide">{password}</code>
          <CopyButton value={password} label="Copy" />
        </div>
        <p
          role="alert"
          className="mt-4 rounded-md border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-xs text-[var(--color-warn)]"
        >
          Chỉ hiện một lần. Gửi cho người dùng qua kênh an toàn. Họ phải đổi mật khẩu ngay lần đăng nhập đầu và
          mật khẩu tạm hết hạn sau 72 giờ.
        </p>
        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90"
          >
            Tôi đã lưu
          </button>
        </div>
      </div>
    </div>
  );
}
