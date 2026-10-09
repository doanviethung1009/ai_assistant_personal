import "server-only";

import type { Note, Project, Task, TaskEvent } from "../types";

/**
 * Nguồn dữ liệu của web app.
 *
 *   api     → gọi core API, dữ liệu nằm trong Postgres. Đây là chế độ thật.
 *   file    → lưu vào file JSON trên đĩa. Chạy được không cần Docker.
 *   memory  → dữ liệu mẫu trong RAM, mất khi restart. Chỉ để xem UI.
 *
 * Đặt bằng biến môi trường DATA_SOURCE.
 */
export type DataSource = "api" | "file" | "memory";

export function resolveDataSource(): DataSource {
  const raw = process.env.DATA_SOURCE?.trim().toLowerCase();
  if (raw === "api" || raw === "file" || raw === "memory") return raw;

  // Tương thích ngược với cấu hình cũ
  if (process.env.DEMO_MODE === "1") return "memory";

  return "api";
}

export const DATA_SOURCE: DataSource = resolveDataSource();

/**
 * Task kèm nhật ký, dạng lưu trong file.
 *
 * Bỏ các field tính toán (`is_overdue`, `days_until_purge`) vì chúng phụ
 * thuộc thời điểm đọc, lưu xuống đĩa là sai ngay hôm sau.
 */
export interface StoredTask
  extends Omit<Task, "is_overdue" | "days_until_purge"> {
  events: TaskEvent[];
  /**
   * Chỉ chế độ file: `duedate` Jira (YYYY-MM-DD) của lần sync trước, thay cho
   * raw_payload.fields.duedate ở backend. Dùng để biết User đã sửa hạn tay chưa
   * (xem applyJiraDue ở app/jira-actions.ts). undefined = chưa biết, null = Jira không có hạn.
   */
  jira_duedate?: string | null;
}

/**
 * Note dạng lưu trong file. Cùng lý do như StoredTask: bỏ field tính toán
 * theo thời điểm đọc. Note không có nhật ký nên không thêm gì.
 */
export type StoredNote = Omit<Note, "days_until_purge">;

/**
 * Danh mục xoá hàng loạt (Vùng nguy hiểm). Định nghĩa theo `scope`:
 *   tasks          mọi task
 *   tasks_work     scope=work (làm lại dữ liệu Jira, giữ task cá nhân)
 *   tasks_team     scope=work và KHÔNG phải "của tôi"
 *   tasks_personal scope=personal
 *   tasks_assignee scope=work và assignee thuộc danh sách tên (cách nhau dấu phẩy)
 */
export interface WipeOptions {
  tasks?: boolean;
  tasks_work?: boolean;
  tasks_personal?: boolean;
  tasks_team?: boolean;
  tasks_assignee?: string;
  projects?: boolean;
  notes?: boolean;
  sync_urls?: boolean;
}

/** Số ngày giữ task đã xoá. 0 nghĩa là xoá thẳng, không qua thùng rác. */
export function trashRetentionDays(): number {
  const raw = Number.parseInt(process.env.TRASH_RETENTION_DAYS ?? "", 10);
  if (Number.isFinite(raw) && raw >= 0 && raw <= 365) return raw;
  return 30;
}

/**
 * Cấu trúc file JSON.
 *
 * Tên field gần với schema của core API, nhưng KHÔNG đủ để POST từng bản ghi lên
 * /api/v1/tasks: màu `hsl(...)`, key project có dấu cách, `source`/`external_id`/
 * `assignee`/`completed_at` và event sẽ bị từ chối hoặc mất. Nhập vào Postgres đi qua
 * endpoint riêng POST /api/v1/import/datafile (chuẩn hoá, idempotent, có audit);
 * xem docs/DATA_MIGRATION_TO_POSTGRES.md.
 */
export interface DataFile {
  /** Tăng khi cấu trúc file đổi, dùng để migrate về sau. */
  schema_version: number;
  exported_at: string;
  projects: Project[];
  tasks: StoredTask[];
  notes: StoredNote[];
  /** Danh sách URL đồng bộ (từ v6). Trước đó snapshot() bỏ sót nên file cũ không có. */
  sync_urls?: string[];
  meta: {
    minutes_logged_today: number;
    /** Ngày ứng với minutes_logged_today, để reset khi sang ngày mới. */
    minutes_logged_date: string;
    /** Danh sách người dùng (để lọc task của mình) */
    current_users?: string[];
    /** Múi giờ hiển thị người dùng chọn (từ v7). Vắng = dùng mặc định. */
    display_timezone?: string;
  };
}

/**
 * Lịch sử phiên bản cấu trúc file (builder-data.json):
 *   1 → bản đầu
 *   2 → thêm `deleted_at` cho thùng rác
 *   3 → thêm mảng `notes` cho sổ tay
 *   4 → phiên bản dọn dẹp (bỏ ai_logs khỏi file)
 *   5 → thêm scope cho task (work | personal)
 *   6 → lưu `sync_urls` (trước đó snapshot() bỏ sót, nên mất sau mỗi lần khởi động)
 *   7 → thêm `due_all_day` cho task (hạn cả ngày của Jira), `meta.display_timezone`
 */
export const SCHEMA_VERSION = 7;
