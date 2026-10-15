"use server";

import { AuthError, CredentialsSignin } from "next-auth";
import { isRedirectError } from "next/dist/client/components/redirect-error";
import { redirect } from "next/navigation";

import { signIn, signOut } from "@/auth";
import { authEnabled, readAuthConfig } from "@/lib/auth-config";
import {
  MAX_IDENTIFIER_LENGTH,
  MAX_PASSWORD_LENGTH,
  PASSWORD_LOGIN_ERROR_CODES,
  type PasswordLoginErrorCode,
} from "@/lib/password-login";
import { safeCallbackPath } from "@/lib/redirect-safety";

/**
 * Bắt đầu đăng nhập Google. Miễn trừ duy nhất khỏi guard "requireSession" của Server Action
 * (chưa có phiên là đúng). callbackUrl đến từ form nên LUÔN lọc lại ở đây, không tin client.
 */
export async function loginWithGoogleAction(formData: FormData): Promise<void> {
  if (!authEnabled()) redirect("/");
  const cfg = readAuthConfig();
  if (!cfg.ok) redirect("/config-error");
  const raw = formData.get("callbackUrl");
  const redirectTo = safeCallbackPath(typeof raw === "string" ? raw : null, cfg.authUrl);
  await signIn("google", { redirectTo });
}

/** Trạng thái form mật khẩu (useActionState). KHÔNG BAO GIỜ chứa mật khẩu: chỉ mã lỗi và ô identifier để điền lại. */
export interface PasswordSignInState {
  error?: PasswordLoginErrorCode;
  identifier?: string;
}

/**
 * Đăng nhập bằng mật khẩu (Credentials). Miễn trừ guard "requireSession" như action Google: chưa có
 * phiên là đúng. Thành công: signIn ném lỗi redirect của Next, PHẢI ném lại (nuốt nó là đăng nhập
 * xong mà không chuyển trang). Thất bại: AuthError → trả mã cố định cho form, không bao giờ lý do thật.
 * Chống brute-force nằm ở core (Redis theo IP/identifier/toàn cục + khoá tài khoản), không phải ở đây.
 */
export async function passwordSignInAction(
  _prev: PasswordSignInState,
  formData: FormData,
): Promise<PasswordSignInState> {
  if (!authEnabled()) redirect("/");
  const cfg = readAuthConfig();
  if (!cfg.ok) redirect("/config-error");
  if (!cfg.passwordEnabled) return { error: "password_login_disabled" };

  const rawId = formData.get("identifier");
  const password = formData.get("password");
  const identifier = typeof rawId === "string" ? rawId.trim().slice(0, MAX_IDENTIFIER_LENGTH) : "";
  if (
    typeof rawId !== "string" ||
    typeof password !== "string" ||
    !identifier ||
    password.length < 1 ||
    password.length > MAX_PASSWORD_LENGTH
  ) {
    return { error: "invalid_credentials", identifier };
  }
  const rawCb = formData.get("callbackUrl");
  const redirectTo = safeCallbackPath(typeof rawCb === "string" ? rawCb : null, cfg.authUrl);

  try {
    await signIn("credentials", { identifier, password, redirectTo });
  } catch (error) {
    if (isRedirectError(error)) throw error;
    if (error instanceof CredentialsSignin) {
      const code = (PASSWORD_LOGIN_ERROR_CODES as readonly string[]).includes(error.code)
        ? (error.code as PasswordLoginErrorCode)
        : "invalid_credentials";
      return { error: code, identifier };
    }
    // AuthError khác (CallbackRouteError do lỗi bất ngờ...): chỉ tên lỗi, không message/cause (có thể chứa dữ liệu form).
    if (error instanceof AuthError) return { error: "unavailable", identifier };
    throw error;
  }
  return { identifier };
}

/** Đăng xuất: chỉ xoá cookie phiên của trình duyệt này (Q9: không tăng session_version ở core). */
export async function logoutAction(): Promise<void> {
  if (!authEnabled()) redirect("/");
  await signOut({ redirectTo: "/login" });
}
