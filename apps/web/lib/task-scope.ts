// ═══════════════════════════════════════════════════════════════════════
//  Phân loại task: việc công ty (work) hay việc riêng (personal).
//
//  MODULE THUẦN: không đánh dấu chỉ-chạy-server, không import runtime. Lý do: engine
//  (server), TaskItem/QuickAddForm (client) và script kiểm chứng chạy bằng
//  `node --experimental-strip-types` đều dùng chung MỘT định nghĩa
//  "việc của tôi". Chỉ được `import type` ở đây.
//
//  Bản sao của backend: apps/core/app/models/enums.py (WORK_SOURCES,
//  default_scope_for) và task_service._view_clause. Hai bên phải khớp.
// ═══════════════════════════════════════════════════════════════════════

export type TaskScope = "work" | "personal";
export type TaskView = "all" | "mine" | "personal" | "work";

/** Nguồn tích hợp mà task mặc định là việc công ty. Khớp backend WORK_SOURCES. */
export const WORK_SOURCES: readonly string[] = ["jira", "github", "gitlab"];

export const TASK_VIEWS: readonly TaskView[] = ["mine", "personal", "work", "all"];

/** Giá trị lạ (từ URL, form) về `fallback` thay vì lan vào truy vấn. */
export function parseView(raw: string | null | undefined, fallback: TaskView = "mine"): TaskView {
  return TASK_VIEWS.find((v) => v === raw) ?? fallback;
}

export function parseScope(raw: unknown): TaskScope | null {
  return raw === "work" || raw === "personal" ? raw : null;
}

/** Quy tắc suy scope từ source. Dùng khi tạo task và khi migrate file cũ. */
export function defaultScopeFor(source: string): TaskScope {
  return WORK_SOURCES.includes(source) ? "work" : "personal";
}

interface ScopeFields {
  scope?: string | null;
  source: string;
}

/**
 * Scope hiệu lực của task. Task cũ thiếu `scope` (chưa qua migrate) vẫn được
 * suy đúng: lớp bảo vệ thứ hai sau bước migrate v4 -> v5.
 */
export function scopeOf(t: ScopeFields): TaskScope {
  return t.scope === "work" || t.scope === "personal" ? t.scope : defaultScopeFor(t.source);
}

interface ViewFields extends ScopeFields {
  assignee?: string | null;
  external_id?: string | null;
}

/**
 * "Việc của tôi" và các view khác, tương đương `view=` của backend.
 *
 * `mine` = personal HOẶC (work VÀ (giao cho một trong `owners`, hoặc không có
 * assignee và không đến từ tích hợp)). So khớp tên CHÍNH XÁC, phân biệt hoa
 * thường: tên hiển thị Jira phải khớp đúng chuỗi trong cài đặt người dùng.
 *
 * Chuỗi rỗng ('') ở assignee/external_id được coi như không có ở cả hai phía:
 * backend chuẩn hoá '' thành NULL khi ghi, và `!t.assignee` / `!t.external_id`
 * ở đây cho cùng kết quả. Engine file cũng chuẩn hoá '' thành null khi tạo/sửa assignee.
 */
export function matchesView(
  t: ViewFields,
  view: TaskView,
  owners: readonly string[],
): boolean {
  if (view === "all") return true;
  const scope = scopeOf(t);
  if (view === "personal") return scope === "personal";
  if (view === "work") return scope === "work";
  if (scope === "personal") return true;
  if (t.assignee) return owners.includes(t.assignee);
  return !t.external_id;
}

/**
 * Task đang bị tích hợp quản lý: work, nguồn khác manual, có external_id.
 * Sync sau sẽ ghi đè các trường trong SYNC_MANAGED_FIELDS.
 */
export function isSyncManaged(t: ScopeFields & { external_id?: string | null }): boolean {
  return scopeOf(t) === "work" && t.source !== "manual" && !!t.external_id;
}

/** Trường mà Jira sync / nhập Excel hiện ghi đè (dùng cho cảnh báo UI). */
export const SYNC_MANAGED_FIELDS = [
  "title",
  "description",
  "status",
  "assignee",
  "due_at",
  "project_id",
  "completed_at",
  "tags",
] as const;
