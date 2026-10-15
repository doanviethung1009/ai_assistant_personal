import { redirect } from "next/navigation";

import { authEnabled, readAuthConfig } from "@/lib/auth-config";
import { loginErrorMessage } from "@/lib/login-message";
import { safeCallbackPath } from "@/lib/redirect-safety";
import { PasswordLoginForm } from "@/components/password-login-form";
import { loginWithGoogleAction } from "./actions";

export const dynamic = "force-dynamic";


/** Trang đăng nhập: KHÔNG gọi core (chỉ form POST sang Auth.js). */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; code?: string; callbackUrl?: string }>;
}) {
  if (!authEnabled()) redirect("/");
  const { error: rawError, code, callbackUrl } = await searchParams;
  const callback = safeCallbackPath(callbackUrl, process.env.AUTH_URL);
  // Mã lạ (mã nội bộ của Auth.js: OAuthCallbackError, Configuration, state cookie hết hạn...) ra câu
  // "thử lại" chung, không lộ chi tiết; chỉ các mã "không được mời" mới nói chưa được cấp quyền.
  const cfg = readAuthConfig();
  const warnings = cfg.ok ? cfg.warnings : [];
  // Cấu hình hỏng thì middleware đã rewrite sang /config-error; ở đây chỉ phòng thủ.
  const googleEnabled = cfg.ok && cfg.googleEnabled;
  const passwordEnabled = cfg.ok && cfg.passwordEnabled;
  const message = loginErrorMessage(rawError, code);

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
