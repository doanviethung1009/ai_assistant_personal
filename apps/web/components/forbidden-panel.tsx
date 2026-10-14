/** Hiện khi core trả 403 `forbidden`: người dùng đã đăng nhập nhưng thiếu quyền cho trang này. */
export function ForbiddenPanel({ message }: { message?: string }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 p-4"
    >
      <p className="text-sm font-medium text-[var(--color-warn)]">Không đủ quyền</p>
      <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
        {message ?? "Bạn không có quyền xem nội dung này. Liên hệ quản trị viên nếu cần truy cập."}
      </p>
    </div>
  );
}
