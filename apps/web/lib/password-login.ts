import "server-only";

import { CredentialsSignin } from "next-auth";

import { clientIpFrom } from "./client-ip";
import { CoreApiError } from "./core-errors";

/**
 * Đăng nhập bằng mật khẩu cho provider Credentials của Auth.js (auth.ts). Tách ra file riêng để test
 * được mà không phải khởi tạo NextAuth.
 *
 * ══════════════════════════════════════════════════════════════════════
 *  MẬT KHẨU CHỈ ĐI QUA ĐÂY TRONG BỘ NHỚ, TỪ FORM TỚI body của một lời gọi core.
 *  Không log `credentials`, không đưa mật khẩu hay identifier vào Error.message, không đưa vào URL.
 *  `code` của lỗi bị Auth.js đưa lên URL (/login?error=CredentialsSignin&code=...) nên chỉ được là
 *  một trong bốn mã dưới đây, và mọi lý do thất bại thật (sai mật khẩu, khoá, tắt, hết hạn, không
 *  có user) PHẢI cùng ra `invalid_credentials` để không lộ tài khoản có tồn tại hay không.
 * ══════════════════════════════════════════════════════════════════════
 */

export const PASSWORD_LOGIN_ERROR_CODES = [
  "invalid_credentials",
  "rate_limited",
  "password_login_disabled",
  "unavailable",
] as const;
export type PasswordLoginErrorCode = (typeof PASSWORD_LOGIN_ERROR_CODES)[number];

/** Trần độ dài khớp core: chặn payload khổng lồ đốt CPU argon2 trước khi gọi mạng. */
export const MAX_IDENTIFIER_LENGTH = 320;
export const MAX_PASSWORD_LENGTH = 1024;

/** Lớp con CredentialsSignin để mã nằm trong `error.code` (Auth.js đọc nó khi dựng URL lỗi). */
export class PasswordLoginError extends CredentialsSignin {
  declare code: PasswordLoginErrorCode;
  constructor(code: PasswordLoginErrorCode) {
    super();
    this.code = code;
  }
}

/** Thông tin core trả về, đã gắn lên `user` để callbacks.jwt chép vào cookie. */
export interface PasswordLoginUser {
  id: string;
  uid: string;
  sv: number;
}

type HeaderReader = { get(name: string): string | null } | null | undefined;

/**
 * Credentials.authorize. Kiểm kiểu và độ dài TRƯỚC khi gọi core: đầu vào sai dạng ra
 * `invalid_credentials` ngay, không tốn một lời gọi mạng. `identifier` được trim, mật khẩu thì KHÔNG
 * (khoảng trắng đầu/cuối có thể là một phần mật khẩu).
 */
export async function authorizePassword(
  credentials: Partial<Record<string, unknown>> | undefined,
  headers: HeaderReader,
): Promise<PasswordLoginUser> {
  const rawIdentifier = credentials?.identifier;
  const password = credentials?.password;
  if (typeof rawIdentifier !== "string" || typeof password !== "string") {
    throw new PasswordLoginError("invalid_credentials");
  }
  const identifier = rawIdentifier.trim();
  if (
    identifier.length < 1 ||
    identifier.length > MAX_IDENTIFIER_LENGTH ||
    password.length < 1 ||
    password.length > MAX_PASSWORD_LENGTH
  ) {
    throw new PasswordLoginError("invalid_credentials");
  }

  // Import lười: lib/api import lib/session import auth.ts (vòng), nên chỉ nạp khi cần.
  const { corePasswordLogin } = await import("./api");
  try {
    const result = await corePasswordLogin({
      identifier,
      password,
      // Hop tin cậy tính từ BÊN PHẢI X-Forwarded-For (lib/client-ip.ts), không bao giờ hop đầu.
      client_ip: headers ? clientIpFrom(headers) : null,
    });
    return { id: result.user_id, uid: result.user_id, sv: result.session_version };
  } catch (error) {
    throw new PasswordLoginError(classifyPasswordLoginError(error));
  }
}

/** Đổi lỗi core thành mã hiển thị. 403 không `code` là sai khoá API (cấu hình), không phải sai mật khẩu. */
export function classifyPasswordLoginError(error: unknown): PasswordLoginErrorCode {
  if (!(error instanceof CoreApiError)) return "unavailable";
  if (error.status === 429) return "rate_limited";
  if (error.status === 403) {
    if (error.code === "invalid_credentials") return "invalid_credentials";
    if (error.code === "password_login_disabled") return "password_login_disabled";
    return "unavailable";
  }
  // 422 (độ dài/dạng) và các 4xx khác của body mà web đã lọc: không để lộ chi tiết, coi như sai thông tin.
  if (error.status === 422 || error.status === 400) return "invalid_credentials";
  return "unavailable";
}

/**
 * Bước 4 của signIn (web-authjs-login 4.3): ký JWT với {uid, sv} vừa nhận và gọi GET /me. Lệch
 * CORE_JWT_SECRET giữa web và core dừng ở đây thay vì để người dùng lặp login → expired → login.
 * Dùng chung cho Google và mật khẩu. Trả `true` nếu ổn, hoặc URL lỗi để callback signIn trả về.
 * Tài khoản đang `must_change_password` vẫn là đăng nhập hợp lệ (GET /me được phép): layout lo phần ép đổi.
 */
export async function verifySessionWithCore(uid: string, sv: number): Promise<true | string> {
  const { coreProbeMe } = await import("./api");
  try {
    await coreProbeMe({ uid, sv });
    return true;
  } catch (error) {
    if (error instanceof CoreApiError && error.status === 401 && error.code === "token_invalid") {
      return "/login?error=config";
    }
    return "/login?error=unavailable";
  }
}
