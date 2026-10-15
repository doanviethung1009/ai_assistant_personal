import { isApiMode } from "./data-source";

/**
 * Đọc và kiểm biến môi trường auth LÚC CHẠY (không lúc build: image build không có AUTH_*).
 * Thiếu biến → trả danh sách TÊN biến (không bao giờ giá trị) cho trang lỗi cấu hình.
 * Chỉ dùng ở server (middleware, Server Component, route); không import từ client component.
 */
export type AuthConfig =
  | {
      ok: true;
      authSecret: string;
      authUrl: string;
      /** Rỗng khi `googleEnabled` = false (chỉ dùng đăng nhập mật khẩu). */
      googleId: string;
      googleSecret: string;
      /** Có đủ AUTH_GOOGLE_ID và AUTH_GOOGLE_SECRET thì mới khai provider Google và hiện nút. */
      googleEnabled: boolean;
      /** PASSWORD_LOGIN_ENABLED !== "false": công tắc khi có sự cố brute-force (core có công tắc riêng). */
      passwordEnabled: boolean;
      coreJwtSecret: string;
      allowedHd: string[];
      secureCookies: boolean;
      /** Cảnh báo cấu hình không an toàn nhưng vẫn chạy được (hiện ở trang /login). */
      warnings: string[];
    }
  | { ok: false; missing: string[] };

export const MIN_SECRET_LENGTH = 32;

const LOOPBACK_HOSTS: ReadonlySet<string> = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

export function readAuthConfig(env: Readonly<Record<string, string | undefined>> = process.env): AuthConfig {
  const missing: string[] = [];
  const get = (name: string): string => {
    const value = env[name]?.trim() ?? "";
    if (!value) missing.push(name);
    return value;
  };

  const authSecret = get("AUTH_SECRET");
  const authUrl = get("AUTH_URL");
  // Google là TUỲ CHỌN (có đăng nhập mật khẩu): cả hai biến vắng = tắt Google. Chỉ có một trong hai là
  // cấu hình dở, báo thiếu biến còn lại thay vì lặng lẽ tắt.
  const googleId = env.AUTH_GOOGLE_ID?.trim() ?? "";
  const googleSecret = env.AUTH_GOOGLE_SECRET?.trim() ?? "";
  if (googleId && !googleSecret) missing.push("AUTH_GOOGLE_SECRET");
  if (googleSecret && !googleId) missing.push("AUTH_GOOGLE_ID");
  const googleEnabled = Boolean(googleId && googleSecret);
  const passwordEnabled = env.PASSWORD_LOGIN_ENABLED?.trim().toLowerCase() !== "false";
  if (!googleEnabled && !passwordEnabled) {
    missing.push("AUTH_GOOGLE_ID + AUTH_GOOGLE_SECRET (hoặc bật PASSWORD_LOGIN_ENABLED): không còn cách đăng nhập nào");
  }
  const coreJwtSecret = env.CORE_JWT_SECRET ?? "";
  if (coreJwtSecret.length < MIN_SECRET_LENGTH) missing.push("CORE_JWT_SECRET (tối thiểu 32 ký tự)");
  if (env.AUTH_TRUST_HOST?.trim().toLowerCase() !== "true") missing.push("AUTH_TRUST_HOST (phải là true)");
  if (authUrl) {
    try {
      new URL(authUrl);
    } catch {
      missing.push("AUTH_URL (không phải URL hợp lệ)");
    }
  }
  if (missing.length > 0) return { ok: false, missing };

  const allowedHd = (env.GOOGLE_ALLOWED_HD ?? "")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  // http ngoài localhost: cookie phiên KHÔNG có cờ Secure nên đi qua LAN dạng chữ rõ. Chỉ cảnh báo
  // (không từ chối khởi động) vì tunnel SSH vào localhost và dev nội bộ vẫn hợp lệ; Google chỉ
  // chấp nhận redirect URI http cho localhost nên cấu hình này thường không đăng nhập được.
  const warnings: string[] = [];
  const parsed = new URL(authUrl);
  if (parsed.protocol === "http:" && !LOOPBACK_HOSTS.has(parsed.hostname)) {
    warnings.push(
      "AUTH_URL dùng http ngoài localhost: cookie phiên không có cờ Secure và đi qua mạng dạng chữ rõ. Dùng https (xem docs/STAGING_DOMAIN_HTTPS.md) hoặc SSH tunnel vào localhost.",
    );
  }
  return {
    ok: true,
    authSecret,
    authUrl,
    googleId,
    googleSecret,
    googleEnabled,
    passwordEnabled,
    coreJwtSecret,
    allowedHd,
    secureCookies: authUrl.startsWith("https://"),
    warnings,
  };
}

/** true khi web chạy có đăng nhập (DATA_SOURCE=api). file/memory: không auth (mục 4.10). */
export function authEnabled(): boolean {
  return isApiMode();
}
