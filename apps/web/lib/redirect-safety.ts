/**
 * Lọc `callbackUrl` để không thành open redirect. Thuần, không phụ thuộc server.
 *
 * Chỉ nhận đường dẫn nội bộ (bắt đầu bằng một dấu `/`) hoặc URL tuyệt đối cùng origin với
 * AUTH_URL. Mọi thứ khác (kể cả dạng mã hoá %2F%2F, `\`, ký tự điều khiển, `javascript:`) → "/".
 */
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

export function safeCallbackPath(input: string | null | undefined, authUrl?: string): string {
  if (typeof input !== "string" || input.length === 0 || input.length > 2048) return "/";
  if (CONTROL_CHARS.test(input)) return "/";

  let base: URL;
  try {
    base = new URL(authUrl || "http://localhost");
  } catch {
    return "/";
  }

  let current = input;
  // Lặp tới khi kết quả không đổi: chuẩn hoá có thể lộ ra dạng mới cần kiểm lại (vd. "/./%2F/evil.com"
  // → "/%2F/evil.com" → "//evil.com" ở vòng sau). Tối đa 3 vòng; vẫn đổi thì từ chối.
  for (let round = 0; round < 3; round++) {
    const next = sanitizeOnce(current, base);
    if (next === current) return next;
    if (next === "/") return "/";
    current = next;
  }
  return "/";
}

/** Một vòng kiểm + chuẩn hoá; trả "/" khi từ chối. Kết quả là path+query cùng origin, bắt đầu bằng một "/". */
function sanitizeOnce(input: string, base: URL): string {
  if (CONTROL_CHARS.test(input)) return "/";
  let candidate = input;
  if (!candidate.startsWith("/")) {
    // Chỉ chấp nhận URL tuyệt đối cùng origin, rồi quy về path+query.
    let abs: URL;
    try {
      abs = new URL(candidate);
    } catch {
      return "/";
    }
    if (abs.origin !== base.origin) return "/";
    candidate = `${abs.pathname}${abs.search}`;
  }

  if (candidate.startsWith("//") || candidate.startsWith("/\\")) return "/";
  // Kiểm cả sau decode: "/%2F%2Fevil" trở thành "//evil" ở trình duyệt/proxy phía sau.
  let decoded: string;
  try {
    decoded = decodeURIComponent(candidate);
  } catch {
    return "/";
  }
  if (CONTROL_CHARS.test(decoded)) return "/";
  if (decoded.startsWith("//") || decoded.startsWith("/\\") || decoded.includes("\\")) return "/";

  let resolved: URL;
  try {
    resolved = new URL(candidate, base);
  } catch {
    return "/";
  }
  if (resolved.origin !== base.origin) return "/";
  const normalized = `${resolved.pathname}${resolved.search}`;
  if (normalized.startsWith("//") || normalized.startsWith("/\\")) return "/";
  return normalized;
}
