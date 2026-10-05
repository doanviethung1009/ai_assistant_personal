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
}

/**
 * Note dạng lưu trong file. Cùng lý do như StoredTask: bỏ field tính toán
 * theo thời điểm đọc. Note không có nhật ký nên không thêm gì.
 */
export type StoredNote = Omit<Note, "days_until_purge">;

/** Số ngày giữ task đã xoá. 0 nghĩa là xoá thẳng, không qua thùng rác. */
export function trashRetentionDays(): number {
  const raw = Number.parseInt(process.env.TRASH_RETENTION_DAYS ?? "", 10);
  if (Number.isFinite(raw) && raw >= 0 && raw <= 365) return raw;
  return 30;
}

/**
 * Cấu trúc file JSON.
 *
 * Tên field trùng khớp schema của core API. Đây là ràng buộc có chủ đích:
 * nhờ vậy nhập dữ liệu vào Postgres chỉ là POST từng bản ghi lên
 * /api/v1/tasks, không cần viết lớp chuyển đổi.
 */
export interface DataFile {
  /** Tăng khi cấu trúc file đổi, dùng để migrate về sau. */
  schema_version: number;
  exported_at: string;
  projects: Project[];
  tasks: StoredTask[];
  notes: StoredNote[];
  // ai_logs đã được tách ra file riêng để tránh làm chậm hệ thống.
  meta: {
    minutes_logged_today: number;
    /** Ngày ứng với minutes_logged_today, để reset khi sang ngày mới. */
    minutes_logged_date: string;
    /** Danh sách người dùng (để lọc task của mình) */
    current_users?: string[];
  };
}

export interface AiLogsFile {
  schema_version: number;
  exported_at: string;
  ai_logs: any[]; // Tạm thời dùng any, sẽ cập nhật type sau khi gen-types
}

/**
 * Lịch sử phiên bản cấu trúc file (builder-data.json):
 *   1 → bản đầu
 *   2 → thêm `deleted_at` cho thùng rác
 *   3 → thêm mảng `notes` cho sổ tay
 *   4 → phiên bản dọn dẹp (tách ai_logs ra file riêng)
 */
export const SCHEMA_VERSION = 4;
