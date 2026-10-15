/**
 * Lỗi từ core và cách web phân loại (bảng 3.4 của spec web-authjs-login).
 * File thuần (không "server-only") để test được và để middleware/route dùng chung.
 */
export class CoreApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    /** Mã máy đọc được trong body `{detail, code}` của core (token_invalid, forbidden...). */
    readonly code?: string,
  ) {
    super(message);
    this.name = "CoreApiError";
  }
}

export type CoreErrorKind =
  | "unauthenticated" // web tự phát hiện không có phiên, chưa gọi core
  | "session_expired" // core báo token_invalid/user_inactive: phiên bị thu hồi/khoá
  | "forbidden" // thiếu quyền (403 code=forbidden)
  | "password_change_required" // 403 code=password_change_required: phải đổi mật khẩu trước (không đăng xuất)
  | "config" // thiếu/sai X-API-Key: lỗi cấu hình, KHÔNG đăng xuất
  | "other";

/**
 * Chỉ token_invalid/user_inactive mới dẫn tới đăng xuất. 401/403 không có `code` là sai cấu hình
 * web→core, và lỗi mạng/5xx là core sập: không suy ra "hết phiên" để khỏi khoá người dùng oan.
 */
export function classifyCoreError(error: unknown): CoreErrorKind {
  if (!(error instanceof CoreApiError)) return "other";
  if (error.status === 401) {
    if (error.code === "no_session") return "unauthenticated";
    if (error.code === "token_invalid" || error.code === "user_inactive") return "session_expired";
    return "config";
  }
  if (error.status === 403) {
    if (error.code === "password_change_required") return "password_change_required";
    return error.code === "forbidden" ? "forbidden" : "config";
  }
  return "other";
}
