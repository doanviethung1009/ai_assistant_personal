// ═══════════════════════════════════════════════════════════════════════
//  Chính sách URL được phép đồng bộ (sync_urls): chỉ https và host trong allowlist.
//
//  BẢN CHÉP CỦA apps/core/app/core/url_allowlist.py. Hai bên phải cho cùng kết
//  quả với mọi URL; sửa bên này thì sửa bên kia.
//
//  VÌ SAO CÓ: web SẼ FETCH URL do người dùng nhập, nên không giới hạn thì đó là
//  SSRF (metadata cloud 169.254.169.254, dịch vụ nội bộ, localhost).
//
//  MODULE THUẦN: không đọc env, không I/O, để test được ngoài Next. Host bổ sung
//  (SYNC_URL_EXTRA_HOSTS) do NGƯỜI GỌI đọc phía server rồi truyền vào.
//
//  Kiểm tra chuỗi URL KHÔNG đủ nếu fetch theo redirect: nơi fetch phải gọi lại
//  hàm này cho URL của MỖI bước redirect (hoặc tắt redirect).
// ═══════════════════════════════════════════════════════════════════════

export const DEFAULT_EXACT_HOSTS: ReadonlySet<string> = new Set([
  "docs.google.com",
  "drive.google.com",
  // Drive chuyển hướng 303 sang host này khi tải file (đã kiểm trên mạng thật).
  "drive.usercontent.google.com",
  "onedrive.live.com",
  "1drv.ms",
]);
// Đuôi miền: chấp nhận tên miền con (>= 1 nhãn phía trước), KHÔNG chấp nhận chính đuôi đó.
export const DEFAULT_SUFFIX_HOSTS: ReadonlySet<string> = new Set([
  "googleusercontent.com",
  "sharepoint.com",
]);

export const MAX_URL_LEN = 2048;
const ALLOWED_PORT = 443;

const LABEL = "[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?";
const HOST_RE = new RegExp(`^${LABEL}(?:\\.${LABEL})*$`);
// netloc hợp lệ DUY NHẤT: host, tuỳ chọn ":443". Không userinfo, ipv6, cổng lạ, cổng rỗng.
const NETLOC_RE = new RegExp(`^(${LABEL}(?:\\.${LABEL})*)(?::${ALLOWED_PORT})?$`, "i");
// eslint-disable-next-line no-control-regex
const FORBIDDEN_CHARS = /[\x00-\x20\x7f\\]/;

export const REASON_TOO_LONG = "too_long";
export const REASON_BAD_CHARS = "bad_chars";
export const REASON_MALFORMED = "malformed";
export const REASON_NOT_HTTPS = "not_https";
export const REASON_BAD_NETLOC = "bad_netloc";
export const REASON_IP_LITERAL = "ip_literal";
export const REASON_HOST_NOT_ALLOWED = "host_not_allowed";

export type RejectReason =
  | typeof REASON_TOO_LONG
  | typeof REASON_BAD_CHARS
  | typeof REASON_MALFORMED
  | typeof REASON_NOT_HTTPS
  | typeof REASON_BAD_NETLOC
  | typeof REASON_IP_LITERAL
  | typeof REASON_HOST_NOT_ALLOWED;

/** Thông điệp cho người dùng. Cố ý KHÔNG nhắc lại URL: link chia sẻ thường chứa token. */
export const REASON_MESSAGES: Record<RejectReason, string> = {
  too_long: "URL quá dài.",
  bad_chars: "URL chứa khoảng trắng hoặc ký tự điều khiển.",
  malformed: "URL không đúng dạng https://host/...",
  not_https: "Chỉ chấp nhận URL https.",
  bad_netloc: "URL có user:pass@, cổng khác 443 hoặc host không hợp lệ.",
  ip_literal: "Không chấp nhận địa chỉ IP.",
  host_not_allowed: "Host không nằm trong danh sách cho phép.",
};

function isIpv4Strict(host: string): boolean {
  const parts = host.split(".");
  if (parts.length !== 4) return false;
  return parts.every((p) => /^(0|[1-9][0-9]{0,2})$/.test(p) && Number(p) <= 255);
}

/**
 * True nếu host là IP ở dạng chuẩn hoặc dạng số nguyên/hex mà resolver cũ vẫn hiểu
 * (`2130706433`, `0x7f000001`, `127.1`). Allowlist đã đủ chặn IP, nhưng kiểm tường
 * minh để báo đúng lý do và phòng khi vận hành thêm nhầm host kiểu số.
 */
function isIpLiteral(host: string): boolean {
  if (isIpv4Strict(host)) return true;
  if (host.includes(":") && /^[0-9a-f:.]+$/i.test(host)) return true; // IPv6
  return host.split(".").every((part) => /^(?:0x[0-9a-f]+|[0-9]+)$/i.test(part));
}

/**
 * Đuôi miền dùng chung / công cộng: `*.github.io` mở cho MỌI người dùng github.io, nên
 * wildcard trên chúng bị từ chối. BEST-EFFORT: không thể liệt kê hết Public Suffix List;
 * người vận hành vẫn phải tự chịu trách nhiệm với từng host thêm vào. Giữ đồng bộ với backend.
 */
export const SHARED_SUFFIXES: ReadonlySet<string> = new Set([
  "github.io",
  "nip.io",
  "sslip.io",
  "xip.io",
  "herokuapp.com",
  "vercel.app",
  "netlify.app",
  "pages.dev",
  "workers.dev",
  "ngrok.io",
  "ngrok-free.app",
  "blogspot.com",
  "azurewebsites.net",
  "cloudfront.net",
  "amazonaws.com",
  "appspot.com",
]);

/** Dạng co.uk / com.au: nhãn đầu 2-3 ký tự, nhãn cuối đúng 2 ký tự. */
function isTwoLabelPublicSuffix(host: string): boolean {
  return /^[a-z]{2,3}\.[a-z]{2}$/.test(host);
}

/**
 * Tách `host` / `*.host` thành (exact, suffix). Sai cú pháp thì ném lỗi (fail closed).
 * Từ chối: host không có dấu chấm, wildcard trên đuôi dùng chung (SHARED_SUFFIXES, co.uk...).
 */
export function parseExtraHosts(raw: Iterable<string>): { exact: Set<string>; suffix: Set<string> } {
  const exact = new Set<string>();
  const suffix = new Set<string>();
  for (const item of raw) {
    const entry = item.trim().toLowerCase();
    if (!entry) continue;
    const wildcard = entry.startsWith("*.");
    const host = wildcard ? entry.slice(2) : entry;
    if (!HOST_RE.test(host) || host.length > 253) {
      throw new Error(`SYNC_URL_EXTRA_HOSTS: '${item.trim().slice(0, 80)}' không phải tên host hợp lệ`);
    }
    if (isIpLiteral(host)) throw new Error("SYNC_URL_EXTRA_HOSTS: không chấp nhận địa chỉ IP");
    if (!host.includes(".")) {
      throw new Error(`SYNC_URL_EXTRA_HOSTS: '${item.trim().slice(0, 80)}' thiếu dấu chấm (cần tên miền đầy đủ)`);
    }
    if (wildcard && (SHARED_SUFFIXES.has(host) || isTwoLabelPublicSuffix(host))) {
      throw new Error(`SYNC_URL_EXTRA_HOSTS: '*.${host}' là đuôi miền dùng chung, quá rộng`);
    }
    (wildcard ? suffix : exact).add(host);
  }
  return { exact, suffix };
}

/** Khớp theo ranh giới nhãn: `endsWith("." + suffix)` (có dấu chấm) là điểm mấu chốt. */
export function hostMatches(host: string, exact: Iterable<string>, suffix: Iterable<string>): boolean {
  if (new Set(exact).has(host)) return true;
  for (const s of suffix) if (host.endsWith("." + s)) return true;
  return false;
}

/** Trả null nếu URL được phép, ngược lại trả MÃ LÝ DO. Không chuẩn hoá URL. */
export function checkSyncUrl(url: unknown, extraHosts: Iterable<string> = []): RejectReason | null {
  if (typeof url !== "string" || url === "") return REASON_MALFORMED;
  if (Array.from(url).length > MAX_URL_LEN) return REASON_TOO_LONG;
  if (FORBIDDEN_CHARS.test(url)) return REASON_BAD_CHARS;

  const schemeMatch = /^([a-z][a-z0-9+.-]*):/i.exec(url);
  if (!schemeMatch || schemeMatch[1]!.toLowerCase() !== "https") return REASON_NOT_HTTPS;
  // Bắt buộc dạng `https://host...`: `https:host`, `https:/x` không có `//`.
  if (url.slice(0, 8).toLowerCase() !== "https://") return REASON_MALFORMED;

  // netloc kết thúc ở / ? # đầu tiên (giống urlsplit)
  const rest = url.slice(8);
  const end = rest.search(/[/?#]/);
  const netloc = end === -1 ? rest : rest.slice(0, end);

  // Ký tự Unicode mà NFKC biến thành dấu phân tách (／ toàn chiều rộng...): urlsplit ném ValueError.
  if (/[^\x00-\x7f]/.test(netloc) && /[/?#@:]/.test(netloc.normalize("NFKC"))) {
    return REASON_MALFORMED;
  }

  const match = NETLOC_RE.exec(netloc);
  if (match === null) {
    if (!netloc.includes("@")) {
      const trimmed = netloc.replace(/^[[\]]+|[[\]]+$/g, "");
      const candidate = trimmed.slice(0, trimmed.lastIndexOf(":") === -1 ? undefined : trimmed.lastIndexOf(":")).replace(/^[[\]]+|[[\]]+$/g, "");
      if (netloc.startsWith("[") || (candidate !== "" && isIpLiteral(candidate))) return REASON_IP_LITERAL;
    }
    return REASON_BAD_NETLOC;
  }
  const host = match[1]!.toLowerCase();
  if (isIpLiteral(host)) return REASON_IP_LITERAL;

  const extra = parseExtraHosts(extraHosts);
  const exact = new Set([...DEFAULT_EXACT_HOSTS, ...extra.exact]);
  const suffix = new Set([...DEFAULT_SUFFIX_HOSTS, ...extra.suffix]);
  return hostMatches(host, exact, suffix) ? null : REASON_HOST_NOT_ALLOWED;
}

export function isAllowedSyncUrl(url: unknown, extraHosts: Iterable<string> = []): boolean {
  return checkSyncUrl(url, extraHosts) === null;
}
