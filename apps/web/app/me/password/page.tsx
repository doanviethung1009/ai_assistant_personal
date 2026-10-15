import { ApiErrorPanel } from "@/components/api-error";
import { ChangePasswordForm } from "@/components/change-password-form";
import { IS_LOCAL, getMe } from "@/lib/api";
import type { MeRead } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Đổi mật khẩu tự nguyện, chỉ tài khoản nội bộ. Tài khoản Google không có mật khẩu ở đây. Trang không
 * nhận hay render mật khẩu nào; việc đổi nằm trong Server Action app/me/actions.ts.
 */
export default async function ChangePasswordPage() {
  const notice = (text: string) => (
    <div className="max-w-md">
      <h1 className="text-2xl font-bold tracking-tight">Đổi mật khẩu</h1>
      <p className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-2 text-sm text-[var(--color-ink-muted)]">
        {text}
      </p>
    </div>
  );
  if (IS_LOCAL) return notice("Chế độ file/memory không có đăng nhập nên không có mật khẩu.");

  let me: MeRead;
  try {
    me = await getMe();
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }
  if (me.auth_provider !== "local") return notice("Tài khoản này đăng nhập bằng Google. Đổi mật khẩu ở tài khoản Google của bạn.");

  return (
    <div className="max-w-md">
      <h1 className="text-2xl font-bold tracking-tight">Đổi mật khẩu</h1>
      <div className="mt-5">
        <ChangePasswordForm />
      </div>
    </div>
  );
}
