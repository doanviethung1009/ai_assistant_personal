"use server";

import { isRedirectError } from "next/dist/client/components/redirect-error";

import { signIn } from "@/auth";
import { changeMyPasswordApi, getMe } from "@/lib/api";
import { requireSession, toActionAuthError } from "@/lib/auth-guard";
import { CoreApiError } from "@/lib/core-errors";
import { MAX_PASSWORD_LENGTH } from "@/lib/password-login";

/** Kết quả đổi mật khẩu. KHÔNG BAO GIỜ chứa mật khẩu (cũ hay mới). */
export interface ChangePasswordState {
  ok?: boolean;
  code?: string;
  error?: string;
  /** Lý do mật khẩu yếu do core liệt kê (không echo mật khẩu). */
  reasons?: string[];
}

/** Core trả "Mật khẩu mới không đạt: r1; r2": bỏ tiêu đề (đã có ở `error`), chỉ giữ danh sách lý do. */
function weakReasons(message: string): string[] {
  const i = message.indexOf(": ");
  const body = i >= 0 ? message.slice(i + 2) : message;
  return body.split("; ").filter(Boolean).slice(0, 8);
}

/**
 * Tự đổi mật khẩu (kể cả lần đầu khi bị ép đổi). Thành công thì core tăng session_version nên MỌI
 * phiên cũ chết, kể cả cookie của chính trình duyệt này; vì vậy đăng nhập lại ngay bằng mật khẩu mới
 * để phiên hiện tại mang `sv` mới, còn các thiết bị khác bị đăng xuất (Q9). signIn thành công thì ném
 * redirect (đừng nuốt). Mật khẩu không trim, ≤ 1024 ký tự; chính sách (độ dài, danh sách phổ biến...)
 * do core quyết định, web không lặp lại.
 */
export async function changeMyPasswordAction(
  _prev: ChangePasswordState,
  formData: FormData,
): Promise<ChangePasswordState> {
  const auth = await requireSession();
  if (!auth.ok) return auth;
  if (auth.user.local) return { ok: false, error: "Chế độ file/memory không có tài khoản." };

  const current = formData.get("current_password");
  const next = formData.get("new_password");
  const confirm = formData.get("confirm_password");
  if (typeof current !== "string" || typeof next !== "string" || typeof confirm !== "string") {
    return { ok: false, error: "Dữ liệu không hợp lệ." };
  }
  if (!current || current.length > MAX_PASSWORD_LENGTH || !next || next.length > MAX_PASSWORD_LENGTH) {
    return { ok: false, error: "Mật khẩu phải từ 1 đến 1024 ký tự." };
  }
  if (next !== confirm) return { ok: false, code: "mismatch", error: "Mật khẩu mới và ô xác nhận không khớp." };

  let username: string;
  try {
    const me = await getMe();
    if (me.auth_provider !== "local" || !me.username) {
      return { ok: false, code: "not_local_account", error: "Tài khoản Google đổi mật khẩu ở Google." };
    }
    username = me.username;
    await changeMyPasswordApi({ current_password: current, new_password: next });
  } catch (error) {
    const authError = toActionAuthError(error);
    if (authError) return authError;
    if (error instanceof CoreApiError) {
      if (error.code === "current_password_invalid") {
        return { ok: false, code: error.code, error: "Mật khẩu hiện tại không đúng." };
      }
      if (error.code === "weak_password") {
        // detail của core liệt kê LÝ DO (không có mật khẩu), phân cách bằng "; " sau khi api.ts gộp.
        return { ok: false, code: error.code, error: "Mật khẩu mới chưa đạt yêu cầu.", reasons: weakReasons(error.message) };
      }
      if (error.code === "not_local_account") {
        return { ok: false, code: error.code, error: "Tài khoản Google đổi mật khẩu ở Google." };
      }
      if (error.status === 429) return { ok: false, code: "rate_limited", error: "Thử quá nhiều lần. Chờ vài phút rồi thử lại." };
    }
    return { ok: false, error: "Không đổi được mật khẩu. Thử lại sau." };
  }

  try {
    await signIn("credentials", { identifier: username, password: next, redirectTo: "/" });
  } catch (error) {
    if (isRedirectError(error)) throw error;
    // Mật khẩu ĐÃ đổi nhưng chưa đăng nhập lại được: client đưa người dùng về trang đăng nhập.
    return { ok: true, code: "relogin_required" };
  }
  return { ok: true, code: "relogin_required" };
}
