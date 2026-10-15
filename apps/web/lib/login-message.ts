// Ba mã "chưa được cấp quyền" dùng chung một câu: không cho kẻ lạ dò xem email nào đã được mời.
const NOT_AUTHORIZED = "Tài khoản này chưa được cấp quyền truy cập. Liên hệ quản trị viên.";
export const GENERIC_FAILURE = "Đăng nhập không thành công, vui lòng thử lại.";
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


/**
 * Câu báo lỗi cho trang /login từ `?error=&code=`. Cả hai khoá nằm trên URL nên là input không tin cậy:
 * tra bằng Object.hasOwn để `?error=constructor`/`toString` không lấy nhầm thuộc tính của Object.prototype.
 * Mã lạ (mã nội bộ Auth.js: OAuthCallbackError, Configuration...) ra câu chung, không lộ chi tiết.
 */
export function loginErrorMessage(rawError?: string, code?: string): string | null {
  let key = rawError;
  if (rawError === "CredentialsSignin") {
    key = code !== undefined && Object.hasOwn(ERROR_MESSAGES, code) ? code : "invalid_credentials";
  }
  if (!key) return null;
  return (Object.hasOwn(ERROR_MESSAGES, key) ? ERROR_MESSAGES[key] : undefined) ?? GENERIC_FAILURE;
}
