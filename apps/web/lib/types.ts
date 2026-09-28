// Phản chiếu schema Pydantic của core API. Khi đổi backend, sửa cả file này.
// Về sau nên sinh tự động từ /openapi.json thay vì viết tay.

export type TaskStatus =
  | "backlog"
  | "todo"
  | "in_progress"
  | "blocked"
  | "done"
  | "cancelled";

export type TaskPriority = "low" | "medium" | "high" | "urgent";

export type TaskSource =
  | "manual"
  | "jira"
  | "calendar"
  | "email"
  | "obsidian"
  | "github"
  | "gitlab"
  | "agent";

export type TaskEventType =
  | "created"
  | "updated"
  | "status_changed"
  | "scheduled"
  | "time_logged"
  | "completed"
  | "reopened"
  | "note_added"
  | "synced"
  | "deleted"
  | "restored";

export interface ProjectSummary {
  id: string;
  key: string;
  name: string;
  color: string | null;
}

export interface Project extends ProjectSummary {
  description: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  project_id: string | null;
  project: ProjectSummary | null;
  due_at: string | null;
  scheduled_for: string | null;
  estimate_minutes: number | null;
  spent_minutes: number;
  completed_at: string | null;
  tags: string[];
  source: TaskSource;
  external_id: string | null;
  external_url: string | null;
  created_at: string;
  updated_at: string;
  /** Khác null nghĩa là đang ở trong thùng rác. */
  deleted_at: string | null;
  is_overdue: boolean;
  /** Số ngày còn lại trước khi xoá vĩnh viễn. Null nếu chưa xoá. */
  days_until_purge: number | null;
}

export interface TaskEvent {
  id: string;
  event_type: TaskEventType;
  actor: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface TaskDetail extends Task {
  events: TaskEvent[];
}

// ── Sổ tay ─────────────────────────────────────────────────────────────

export type NoteKind = "command" | "sql" | "text" | "config" | "code";

export type NoteSource = "manual" | "obsidian" | "github" | "agent";

/**
 * Một mục trong sổ tay: câu lệnh, câu SQL, đoạn cấu hình, ghi chú tự do.
 *
 * `content` là DỮ LIỆU. Web chỉ hiển thị và copy vào clipboard, không bao giờ
 * thực thi. Khi render phải dùng text node (JSX `{content}`), tuyệt đối không
 * dangerouslySetInnerHTML — nội dung do người dùng dán vào, có thể chứa HTML.
 */
export interface Note {
  id: string;
  title: string;
  kind: NoteKind;
  content: string;
  description: string | null;
  /** Nơi áp dụng: host, database, môi trường. */
  context: string | null;
  project_id: string | null;
  project: ProjectSummary | null;
  tags: string[];
  is_pinned: boolean;
  /** Người dùng tự đánh dấu. UI cảnh báo trước khi copy. */
  is_dangerous: boolean;
  use_count: number;
  last_used_at: string | null;
  source: NoteSource;
  external_id: string | null;
  created_at: string;
  updated_at: string;
  /** Khác null nghĩa là đang ở trong thùng rác. */
  deleted_at: string | null;
  /** Số ngày còn lại trước khi xoá vĩnh viễn. Null nếu chưa xoá. */
  days_until_purge: number | null;
}

export interface NoteTrashResponse {
  items: Note[];
  total: number;
  limit: number;
  offset: number;
  retention_days: number;
  purged_now: number;
}

export const NOTE_KIND_LABELS: Record<NoteKind, string> = {
  command: "Câu lệnh",
  sql: "SQL",
  text: "Ghi chú",
  config: "Cấu hình",
  code: "Đoạn code",
};

export const NOTE_KINDS: NoteKind[] = [
  "command",
  "sql",
  "text",
  "config",
  "code",
];

/**
 * Loại có thể chạy được ở đâu đó, nên UI nhắc đọc lại trước khi dán.
 * Khớp với NoteKind.is_executable ở backend.
 */
export const EXECUTABLE_NOTE_KINDS: NoteKind[] = ["command", "sql"];

export type NoteSortField =
  | "updated_at"
  | "created_at"
  | "title"
  | "use_count"
  | "last_used_at";

export interface Agenda {
  reference_date: string;
  overdue: Task[];
  scheduled_today: Task[];
  in_progress: Task[];
  due_soon: Task[];
  completed_today: Task[];
  totals: Record<string, number>;
}

export interface Stats {
  reference_date: string;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  completed_last_7_days: Record<string, number>;
  open_total: number;
  overdue_total: number;
  minutes_logged_today: number;
  trash_total: number;
}

export interface TrashResponse {
  items: Task[];
  total: number;
  limit: number;
  offset: number;
  retention_days: number;
  purged_now: number;
}

export interface PurgeResponse {
  purged: number;
  retention_days: number;
}

export interface Paged<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export const STATUS_LABELS: Record<TaskStatus, string> = {
  backlog: "Chờ xử lý",
  todo: "Cần làm",
  in_progress: "Đang làm",
  blocked: "Bị chặn",
  done: "Xong",
  cancelled: "Đã huỷ",
};

export const PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  urgent: "Gấp",
};

export const OPEN_STATUSES: TaskStatus[] = [
  "backlog",
  "todo",
  "in_progress",
  "blocked",
];
