import { redirect } from "next/navigation";

import { authEnabled, readAuthConfig } from "@/lib/auth-config";
import { safeCallbackPath } from "@/lib/redirect-safety";
import { PasswordLoginForm } from "@/components/password-login-form";
import { loginWithGoogleAction } from "./actions";

export const dynamic = "force-dynamic";

// Ba mã "chưa được cấp quyền" dùng chung một câu: không cho kẻ lạ dò xem email nào đã được mời.
const NOT_AUTHORIZED = "Tài khoản này chưa được cấp quyền truy cập. Liên hệ quản trị viên.";
const GENERIC_FAILURE = "Đăng nhập không thành công, vui lòng thử lại.";
const ERROR_MESSAGES: Record<string, string> = {
  not_invited: NOT_AUTHORIZED,
  disabled: NOT_AUTHORIZED,
  account_mismatch: NOT_AUTHORIZED,
  denied: NOT_AUTHORIZED,
  email_unverified: "Email Google chưa được xác minh. Hãy xác minh email rồi thử lại.",
  hd_not_allowed: "Tài khoản Google này không thuộc tổ chức được phép đăng nhập.",
  session: "Phiên đăng nhập đã hết hiệu lực. Vui lòng đăng nhập lại.",
  rate_limited: "Thử đăng nhập quá nhiều lần. Chờ một phút rồi thử lại.",
  unavailable: "Chưa kết nối được máy chủ dữ liệu. Thử lại sau ít phút.",
  config: "Cấu hình khoá giữa web và core không khớp. Báo quản trị viên.",
  // Mật khẩu: MỌI thất bại thật (sai, khoá, tắt tài khoản, mật khẩu tạm hết hạn, không có user) dùng một câu.
  invalid_credentials:
    "Sai thông tin đăng nhập hoặc tài khoản tạm bị khoá. Thử lại sau ít phút hoặc liên hệ quản trị viên.",
  password_login_disabled: "Đăng nhập bằng mật khẩu đang tạm tắt. Liên hệ quản trị viên.",
};

/** Mã lỗi hiển thị: Auth.js đưa lỗi Credentials lên URL dạng `error=CredentialsSignin&code=<mã>`. */
function errorKey(error?: string, code?: string): string | undefined {
  return error === "CredentialsSignin" ? (code ?? "invalid_credentials") : error;
}

/** Trang đăng nhập: KHÔNG gọi core (chỉ form POST sang Auth.js). */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; code?: string; callbackUrl?: string }>;
}) {
  if (!authEnabled()) redirect("/");
  const { error: rawError, code, callbackUrl } = await searchParams;
  const error = errorKey(rawError, code);
  const callback = safeCallbackPath(callbackUrl, process.env.AUTH_URL);
  // Mã lạ (mã nội bộ của Auth.js: OAuthCallbackError, Configuration, state cookie hết hạn...) ra câu
  // "thử lại" chung, không lộ chi tiết; chỉ các mã "không được mời" mới nói chưa được cấp quyền.
  const cfg = readAuthConfig();
  const warnings = cfg.ok ? cfg.warnings : [];
  // Cấu hình hỏng thì middleware đã rewrite sang /config-error; ở đây chỉ phòng thủ.
  const googleEnabled = cfg.ok && cfg.googleEnabled;
  const passwordEnabled = cfg.ok && cfg.passwordEnabled;
  const message = error ? (ERROR_MESSAGES[error] ?? GENERIC_FAILURE) : null;

  return (
    <div className="flex min-h-screen w-full items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-8 shadow-lg">
        <h1 className="text-xl font-semibold tracking-tight text-[var(--color-ink)]">Builder AI Assistant</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">Đăng nhập để tiếp tục.</p>

        {warnings.map((w) => (
          <p
            key={w}
            role="status"
            className="mt-5 rounded-md border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-xs text-[var(--color-warn)]"
          >
            {w}
          </p>
        ))}

        {message ? (
          <p
            role="alert"
            className="mt-5 rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]"
          >
            {message}
          </p>
        ) : null}

        {passwordEnabled ? <PasswordLoginForm callbackUrl={callback} /> : null}

        {googleEnabled && passwordEnabled ? (
          <div className="my-5 flex items-center gap-3 text-xs text-[var(--color-ink-muted)]" aria-hidden>
            <span className="h-px flex-1 bg-[var(--color-border)]" />
            hoặc
            <span className="h-px flex-1 bg-[var(--color-border)]" />
          </div>
        ) : null}

        {googleEnabled ? (
          <form action={loginWithGoogleAction} className={passwordEnabled ? "" : "mt-6"}>
            <input type="hidden" name="callbackUrl" value={callback} />
            <button
              type="submit"
              className={`w-full rounded-md px-4 py-2.5 text-sm font-medium transition hover:opacity-90 ${
                passwordEnabled
                  ? "border border-[var(--color-border)] text-[var(--color-ink)] hover:bg-[var(--color-surface-hover)]"
                  : "bg-[var(--color-accent)] text-white"
              }`}
            >
              Đăng nhập với Google
            </button>
          </form>
        ) : null}
      </div>
    </div>
  );
}
