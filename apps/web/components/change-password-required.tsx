import { logoutAction } from "@/app/login/actions";
import { ChangePasswordForm } from "@/components/change-password-form";

/**
 * Thay THẾ nội dung mọi trang khi core báo must_change_password (layout quyết định, không cần biết
 * pathname). Lớp chặn thật là core: mọi route khác trả 403 password_change_required, nên dù UI này bị
 * bỏ qua cũng không đọc/ghi được gì. Có nút Đăng xuất để người nhận mật khẩu tạm không bị kẹt.
 */
export function ChangePasswordRequired() {
  return (
    <div className="mx-auto max-w-md">
      <h1 className="text-2xl font-bold tracking-tight">Đổi mật khẩu</h1>
      <div className="mt-5">
        <ChangePasswordForm forced />
      </div>
      <form action={logoutAction} className="mt-6">
        <button type="submit" className="text-xs text-[var(--color-ink-muted)] underline hover:text-[var(--color-ink)]">
          Đăng xuất
        </button>
      </form>
    </div>
  );
}
