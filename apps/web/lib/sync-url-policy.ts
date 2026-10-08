import "server-only";

import { REASON_MESSAGES, checkSyncUrl } from "./url-allowlist";

/**
 * Host bổ sung cho allowlist, đọc từ biến môi trường SYNC_URL_EXTRA_HOSTS (phân tách
 * bằng dấu phẩy, cùng cú pháp và cùng biến với core). CHỈ đọc ở server: client không
 * bao giờ quyết định được host nào được phép. Mục sai cú pháp làm checkSyncUrl ném lỗi
 * (fail closed): thiếu host chỉ bất tiện, thừa host mới mở lỗ hổng.
 */
export function extraHostsFromEnv(): string[] {
  return (process.env.SYNC_URL_EXTRA_HOSTS ?? "")
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean);
}

/** Lỗi có thông điệp an toàn để trả cho client (không chứa URL, statusText hay chi tiết mạng). */
export class SyncFetchError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SyncFetchError";
  }
}

const MAX_REDIRECTS = 5;
const FETCH_TIMEOUT_MS = 30_000;
const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);

/**
 * fetch URL do người dùng nhập, chống SSRF qua redirect.
 *
 * Kiểm allowlist cho URL của MỖI bước TRƯỚC khi gọi, và tắt redirect tự động
 * (`manual`): với `follow`, một host hợp lệ trả 302 sang http://169.254.169.254/...
 * thì fetch đi theo mà không ai kiểm lại. Tối đa 5 bước. Mọi lỗi ném ra là
 * SyncFetchError với thông điệp chung, không nhắc URL gốc/URL đích (có thể chứa token).
 */
export async function fetchAllowlisted(startUrl: string, headers: Record<string, string>): Promise<Response> {
  let current = startUrl;
  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    const rejected = syncUrlError(current);
    if (rejected !== null) {
      throw new SyncFetchError(hop === 0 ? rejected : "Link chuyển hướng tới địa chỉ không được phép.");
    }
    let res: Response;
    try {
      res = await fetch(current, {
        redirect: "manual",
        headers,
        signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      });
    } catch {
      throw new SyncFetchError("Không kết nối được tới link.");
    }
    if (!REDIRECT_STATUSES.has(res.status)) return res;

    const location = res.headers.get("location");
    // Giải phóng body của phản hồi redirect.
    void res.body?.cancel().catch(() => undefined);
    if (!location) throw new SyncFetchError("Link chuyển hướng không hợp lệ.");
    try {
      current = new URL(location, current).toString();
    } catch {
      throw new SyncFetchError("Link chuyển hướng không hợp lệ.");
    }
  }
  throw new SyncFetchError("Link chuyển hướng quá nhiều lần.");
}

/** Trả thông điệp lỗi (không chứa URL) nếu URL bị từ chối, null nếu được phép. */
export function syncUrlError(url: unknown): string | null {
  try {
    const reason = checkSyncUrl(url, extraHostsFromEnv());
    return reason === null ? null : REASON_MESSAGES[reason];
  } catch {
    // Cấu hình SYNC_URL_EXTRA_HOSTS hỏng: từ chối tất cả thay vì bỏ qua kiểm tra.
    return "Cấu hình SYNC_URL_EXTRA_HOSTS không hợp lệ, không thể kiểm tra URL.";
  }
}
