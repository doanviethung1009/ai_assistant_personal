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
        // identity: không nhận nội dung nén, giảm rủi ro nén bom (readCappedBody vẫn đếm byte sau giải nén).
        headers: { ...headers, "Accept-Encoding": "identity" },
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

/** Trần kích thước file cào về, tránh một link độc làm tràn RAM của web. */
export const MAX_SYNC_BYTES = 20 * 1024 * 1024;

const ALLOWED_CONTENT_TYPES = new Set([
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
  "text/csv",
  "application/csv",
  "application/octet-stream",
]);

/** Từ chối kiểu nội dung lạ (HTML đăng nhập, JSON...). Thiếu header thì cho qua, XLSX.read sẽ tự bắt. */
export function assertSpreadsheetContentType(res: Response): void {
  const raw = res.headers.get("content-type");
  if (!raw) return;
  const type = raw.split(";")[0]!.trim().toLowerCase();
  if (!ALLOWED_CONTENT_TYPES.has(type)) {
    throw new SyncFetchError("Link không trả về file Excel/CSV.");
  }
}

/**
 * Đọc body theo STREAM, cộng dồn byte và dừng ngay khi vượt trần.
 *
 * Không dùng arrayBuffer(): nó nạp toàn bộ vào RAM trước khi ta kịp kiểm, và
 * Content-Length có thể vắng (chunked) hoặc nói dối. Đếm trên byte đã GIẢI NÉN nên
 * cũng chặn được nén bom dù đã yêu cầu Accept-Encoding: identity.
 */
export async function readCappedBody(res: Response, maxBytes: number = MAX_SYNC_BYTES): Promise<Uint8Array> {
  const declared = Number(res.headers.get("content-length") ?? 0);
  if (declared > maxBytes) {
    void res.body?.cancel().catch(() => undefined);
    throw new SyncFetchError("File quá lớn (tối đa 20 MB).");
  }
  if (!res.body) return new Uint8Array(0);
  const reader = res.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel().catch(() => undefined);
        throw new SyncFetchError("File quá lớn (tối đa 20 MB).");
      }
      chunks.push(value);
    }
  } catch (error) {
    if (error instanceof SyncFetchError) throw error;
    throw new SyncFetchError("Đọc dữ liệu từ link bị gián đoạn.");
  }
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.byteLength;
  }
  return out;
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
