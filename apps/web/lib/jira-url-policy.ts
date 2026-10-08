// ═══════════════════════════════════════════════════════════════════════
//  Chính sách baseUrl Jira cho syncJiraAction (chế độ file)
//
//  VÌ SAO CÓ: chế độ file fetch baseUrl do người dùng nhập, KÈM header Authorization
//  (email:token). Không giới hạn thì đó là SSRF + rò token sang host lạ.
//  Jira là CLOUD nên chỉ nhận https://<tenant>.atlassian.net (cổng 443, không userinfo).
//
//  MODULE THUẦN (không I/O, không env): test được ngoài Next, và an toàn nếu lỡ
//  import ở client vì không chứa bí mật. Nơi fetch vẫn phải dùng redirect:"manual".
// ═══════════════════════════════════════════════════════════════════════

const SUFFIX = ".atlassian.net";
const LABEL = "[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?";
// Tenant là đúng MỘT nhãn trước .atlassian.net.
const HOST_RE = new RegExp(`^${LABEL}\\.atlassian\\.net$`);
// eslint-disable-next-line no-control-regex
const FORBIDDEN_CHARS = /[\x00-\x20\x7f\\@]/;

export const JIRA_URL_HINT = "Chỉ hỗ trợ Jira Cloud (https://tên.atlassian.net).";

/** Kết quả: baseUrl đã chuẩn hoá `https://host`, hoặc lý do từ chối (không nhắc lại URL). */
export type JiraUrlCheck = { ok: true; baseUrl: string } | { ok: false; error: string };

/**
 * Chuẩn hoá và kiểm baseUrl Jira. Chấp nhận URL có/không path hay "/" cuối nhưng
 * luôn trả về `https://host` (path bị bỏ: API luôn gắn đường dẫn cố định).
 */
export function checkJiraBaseUrl(input: unknown): JiraUrlCheck {
  if (typeof input !== "string") return { ok: false, error: "URL Jira không hợp lệ." };
  const raw = input.trim();
  if (raw.length === 0 || raw.length > 2048) return { ok: false, error: "URL Jira không hợp lệ." };
  if (FORBIDDEN_CHARS.test(raw)) return { ok: false, error: "URL Jira chứa ký tự không được phép." };
  // Cho phép gõ "x.atlassian.net" không scheme (hành vi cũ), nhưng không scheme nào khác ngoài https.
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`;
  if (!/^https:\/\//i.test(withScheme)) return { ok: false, error: "Chỉ chấp nhận https. " + JIRA_URL_HINT };
  let u: URL;
  try {
    u = new URL(withScheme);
  } catch {
    return { ok: false, error: "URL Jira không hợp lệ." };
  }
  if (u.username || u.password) return { ok: false, error: "URL Jira không được chứa user:pass@." };
  if (u.port && u.port !== "443") return { ok: false, error: "URL Jira chỉ dùng cổng 443." };
  // Kiểm cả netloc thô: new URL chuẩn hoá (vd 0x7f.1 thành 127.0.0.1) nên so lại hostname đã chuẩn hoá.
  const host = u.hostname.toLowerCase();
  if (!HOST_RE.test(host) || !host.endsWith(SUFFIX)) {
    return { ok: false, error: "Host không được phép. " + JIRA_URL_HINT };
  }
  return { ok: true, baseUrl: `https://${host}` };
}
