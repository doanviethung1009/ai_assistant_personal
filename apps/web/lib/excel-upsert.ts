import "server-only";

import { CoreApiError, UpsertBatchError, upsertTasksBatch, verifyImportSecret } from "./api";
import type { TaskStatus, TaskUpsertItem, UpsertSummary } from "./types";

/**
 * Cầu nối Excel/URL -> `POST /tasks/upsert-batch` cho chế độ api (B4a).
 *
 * Web vẫn là bên tải và đọc file (giữ allowlist URL và trần 20 MB của B2); ở đây chỉ
 * ánh xạ dòng sang TaskUpsert rồi đẩy lên core thay cho engine. Cố ý KHÔNG đặt trong file
 * "use server": file đó chỉ được export hàm async, và các hàm ở đây không được phơi ra
 * thành endpoint công khai.
 */

/** Nguồn CỐ ĐỊNH ở server, khớp chế độ file (engine ghi `source: 'jira'` cho Excel/URL). */
export const EXCEL_SOURCE = "jira" as const;

const MAX_ERRORS_SHOWN = 20;
const MAX_REASON_LEN = 200;

/** Mật khẩu đi vào header HTTP: chỉ ASCII in được, 1-256 ký tự. Trả null nếu không hợp lệ. */
export function parseImportSecret(raw: unknown): string | null {
  return typeof raw === "string" && /^[\x20-\x7e]{1,256}$/.test(raw) ? raw : null;
}

export const SECRET_REQUIRED_MESSAGE =
  "Chưa nhập mật khẩu nhập dữ liệu (hoặc chứa ký tự không hợp lệ).";

const FORBIDDEN_MESSAGE =
  "Mật khẩu nhập sai, hoặc core chưa cấu hình IMPORT_COMMIT_SECRET (đặt biến này trong .env của core rồi khởi động lại api).";

const UNAVAILABLE_MESSAGE =
  "Core chưa sẵn sàng cho thao tác này (503). Kiểm tra cấu hình biến môi trường của service api (ví dụ IMPORT_COMMIT_SECRET) rồi thử lại.";

const VALIDATION_MESSAGE =
  "Core từ chối dữ liệu (422). Kiểm tra định dạng các cột trong file (ngày, độ dài tiêu đề, Issue Key...).";

const MAX_CORE_MESSAGE_LEN = 500;

/**
 * Đổi lỗi của core thành thông báo an toàn cho client. 403/503/422 dùng câu tự viết (msg
 * validator của 422 có thể chứa giá trị lấy từ file Excel); lỗi khác cắt còn ~500 ký tự.
 */
function coreErrorText(error: CoreApiError): string {
  if (error.status === 403) return FORBIDDEN_MESSAGE;
  if (error.status === 503) return UNAVAILABLE_MESSAGE;
  if (error.status === 422) return VALIDATION_MESSAGE;
  return error.message.slice(0, MAX_CORE_MESSAGE_LEN);
}

/**
 * Cổng vào của mọi thao tác ghi hàng loạt: kiểm dạng mật khẩu rồi hỏi core xem có đúng
 * không, TRƯỚC khi fetch URL hay parse file. Nhờ vậy request sai mật khẩu không bắt server
 * tải URL ngoài hay giải nén XLSX (tốn CPU/RAM). Mật khẩu không bao giờ nằm trong lỗi trả về.
 */
export async function authorizeImport(
  raw: unknown,
): Promise<{ ok: true; secret: string } | { ok: false; error: string }> {
  const secret = parseImportSecret(raw);
  if (secret === null) return { ok: false, error: SECRET_REQUIRED_MESSAGE };
  try {
    await verifyImportSecret(secret);
    return { ok: true, secret };
  } catch (error) {
    if (error instanceof CoreApiError) return { ok: false, error: coreErrorText(error) };
    console.error("kiểm mật khẩu nhập thất bại", error instanceof Error ? error.name : "unknown");
    return { ok: false, error: "Không gọi được core API. Kiểm tra service api." };
  }
}

function parseDate(val: unknown): string | null {
  if (val === null || val === undefined || val === "" || val === "No Due Date" || val === "Not Closed") {
    return null;
  }
  if (typeof val === "number") {
    // Số serial của Excel (1900 date system).
    const d = new Date(Math.round((val - 25569) * 86400 * 1000));
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
  }
  if (typeof val === "string") {
    const d = new Date(val.replace(/([+-]\d{2})(\d{2})$/, "$1:$2"));
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
  }
  return null;
}

const STATUS_MAP: Record<string, TaskStatus> = {
  "To Do": "todo",
  "In Progress": "in_progress",
  Done: "done",
  Closed: "done",
};

function cell(row: Record<string, unknown>, ...names: string[]): string | null {
  for (const n of names) {
    const v = row[n];
    if (v !== undefined && v !== null && String(v).trim() !== "") return String(v).trim();
  }
  return null;
}

/**
 * Ánh xạ dòng Excel sang TaskUpsert, cùng quy tắc với engine ở chế độ file (tag từ
 * Company/Projects/Labels, project theo Company, trạng thái theo bảng map).
 *
 * Dòng thiếu Summary bị bỏ như chế độ file. Dòng thiếu Issue Key KHÔNG gửi được (core khớp
 * theo external_id; chế độ file khớp theo tiêu đề) nên được đếm vào `skippedNoKey`.
 * `rowNumbers[i]` là số dòng Excel (dòng 1 = tiêu đề) của `items[i]`, để lỗi từ core chỉ
 * đúng dòng người dùng thấy trong file.
 *
 * KHÔNG gửi `priority`: core chỉ ghi các trường có gửi và mặc định MEDIUM khi tạo mới, còn
 * chế độ file không đụng priority khi cập nhật. Gửi "medium" sẽ ghi đè mức ưu tiên người
 * dùng đã đổi tay trên task đã có sau mỗi lần nhập.
 *
 * Ô trống: sheet_to_json bỏ khoá của ô rỗng, nên "file CÓ cột" được suy ra từ hợp mọi khoá
 * của mọi dòng. Cột có mặt mà ô rỗng/"No Due Date" thì gửi `null` tường minh (due_at,
 * assignee, project_key) để xoá giá trị cũ, khớp chế độ file (nó gán null ở nhánh cập nhật).
 */
export function rowsToUpsertItems(rows: unknown[]): {
  items: TaskUpsertItem[];
  rowNumbers: number[];
  skippedNoKey: number;
} {
  const columns = new Set<string>();
  for (const raw of rows) {
    if (typeof raw === "object" && raw !== null && !Array.isArray(raw)) {
      for (const k of Object.keys(raw)) columns.add(k);
    }
  }
  const items: TaskUpsertItem[] = [];
  const rowNumbers: number[] = [];
  let skippedNoKey = 0;
  for (const [rawIndex, raw] of rows.entries()) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) continue;
    const row = raw as Record<string, unknown>;
    const title = cell(row, "Summary", "Title");
    if (!title) continue;
    const key = cell(row, "Issue Key", "Key");
    if (!key) {
      skippedNoKey++;
      continue;
    }

    const company = cell(row, "Company");
    const projects = cell(row, "Projects");
    const labels = cell(row, "Labels");
    const tags = ["jira"];
    if (company) tags.push(company.toLowerCase().replace(/[^a-z0-9]/g, ""));
    if (projects) tags.push(...projects.split(",").map((s) => s.trim().toLowerCase().replace(/[^a-z0-9]/g, "")));
    if (labels) tags.push(...labels.split(",").map((s) => s.trim().toLowerCase()));

    const statusCell = cell(row, "Status");
    const status: TaskStatus = (statusCell && STATUS_MAP[statusCell]) || "todo";
    const description = cell(row, "Description");

    const item: TaskUpsertItem = {
      external_id: key.slice(0, 255),
      title: title.slice(0, 500),
      status,
      tags: Array.from(new Set(tags.filter((t) => t.length > 0))),
      // NỢ KỸ THUẬT: host Jira bị hardcode theo công ty của người dùng, y hệt chế độ file
      // (engine). File Excel không chứa URL nên chưa có nguồn khác; khi có kết nối Jira ở
      // core (B4b) nên lấy base_url từ đó thay vì hardcode.
      external_url: `https://onemount.atlassian.net/browse/${encodeURIComponent(key)}`,
    };
    if (description) item.description = description.slice(0, 32_000);
    const assignee = cell(row, "Assignee");
    if (assignee) item.assignee = assignee;
    else if (columns.has("Assignee")) item.assignee = null;
    const created = parseDate(row["Created Date"]);
    if (created) item.created_at = created;
    const due = parseDate(row["Due Date"]);
    if (due) item.due_at = due;
    else if (columns.has("Due Date")) item.due_at = null;
    if (status === "done") {
      const closed = parseDate(row["Closed Date"]);
      if (closed) item.completed_at = closed;
    }
    const projectKey = company ? company.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 20) : "";
    if (projectKey) {
      item.project_key = projectKey;
      item.project_name = company ? company.slice(0, 200) : undefined;
    } else if (columns.has("Company")) {
      item.project_key = null;
    }
    items.push(item);
    rowNumbers.push(rawIndex + 2);
  }
  return { items, rowNumbers, skippedNoKey };
}

export interface CoreUpsertOutcome {
  ok: boolean;
  error?: string;
  summary?: UpsertSummary;
}

/**
 * Đẩy các dòng đã đọc lên core. `secret` PHẢI đã qua `authorizeImport`. Mật khẩu và nội
 * dung lỗi thô của core không bao giờ được lặp lại cho client (xem coreErrorText).
 *
 * `errors`/`warnings` trả về có `index` = SỐ DÒNG EXCEL và bị cắt còn 20 mục; tổng thật
 * nằm ở `errors_total`/`warnings_total`.
 */
export async function pushRowsToCore(rows: unknown[], secret: string): Promise<CoreUpsertOutcome> {
  const { items, rowNumbers, skippedNoKey } = rowsToUpsertItems(rows);
  if (items.length === 0) {
    return {
      ok: false,
      error:
        skippedNoKey > 0
          ? `Không có dòng nào dùng được: ${skippedNoKey} dòng thiếu cột Issue Key/Key nên không đồng bộ được.`
          : "Không có dòng nào có cột Summary/Title.",
    };
  }
  const toRow = (index: number): number => rowNumbers[index] ?? index + 2;
  try {
    const res = await upsertTasksBatch(EXCEL_SOURCE, items, secret);
    const errors = res.errors ?? [];
    const warnings = res.warnings ?? [];
    return {
      ok: true,
      summary: {
        ...res,
        errors: errors.slice(0, MAX_ERRORS_SHOWN).map((e) => ({ index: toRow(e.index), reason: e.reason.slice(0, MAX_REASON_LEN) })),
        warnings: warnings.slice(0, MAX_ERRORS_SHOWN).map((w) => ({ index: toRow(w.index), reason: w.reason.slice(0, MAX_REASON_LEN) })),
        errors_total: errors.length,
        warnings_total: warnings.length,
        skipped_no_key: skippedNoKey,
      },
    };
  } catch (error) {
    if (error instanceof UpsertBatchError) {
      return {
        ok: false,
        error:
          `Đã ghi xong ${error.batchesDone}/${error.batchesTotal} lô đầu, lô tiếp theo lỗi: ${coreErrorText(error)} ` +
          "Chạy lại an toàn (không nhân đôi dữ liệu).",
      };
    }
    if (error instanceof CoreApiError) return { ok: false, error: coreErrorText(error) };
    // Chỉ log tên lỗi: tránh ghi header chứa mật khẩu.
    console.error("upsert-batch thất bại", error instanceof Error ? error.name : "unknown");
    return { ok: false, error: "Không gọi được core API. Kiểm tra service api." };
  }
}
