// Alias sang schema sinh tự động từ /openapi.json (components["schemas"]).
// KHÔNG viết tay field của entity ở đây nữa — sửa backend thì chạy lại
// `npm run gen:types` (hoặc `make gen-types` ở gốc repo), lib/generated/openapi.d.ts
// tự khớp lại. File này chỉ còn: alias tên ngắn, type phụ trợ cho local
// store (file/memory), và hằng số/label chỉ UI cần (không nằm trong OpenAPI
// vì đó là quyết định hiển thị, không phải hợp đồng dữ liệu).
import type { components } from "./generated/openapi";

type Schemas = components["schemas"];

export type TaskStatus = Schemas["TaskStatus"];
export type TaskPriority = Schemas["TaskPriority"];
export type TaskSource = Schemas["TaskSource"];
export type TaskEventType = Schemas["TaskEventType"];
export type TaskScope = Schemas["TaskScope"];
export type TaskView = Schemas["TaskView"];

export const SCOPE_LABELS: Record<TaskScope, string> = {
  work: "Công việc",
  personal: "Cá nhân",
};

export const VIEW_LABELS: Record<TaskView, string> = {
  mine: "Của tôi",
  personal: "Cá nhân",
  work: "Công việc",
  all: "Tất cả",
};

/**
 * `color` ở Pydantic cũng `default=None` nên optional trong schema sinh.
 * Component (ProjectBadge) khai prop `color: string | null`, không nhận
 * `undefined` — ép required tương tự WithRequiredDeletedAt ở dưới.
 */
type WithRequiredColor<T extends { color?: string | null }> = Omit<
  T,
  "color"
> & { color: string | null };

export type ProjectSummary = WithRequiredColor<Schemas["ProjectSummary"]>;
export type Project = WithRequiredColor<Schemas["ProjectRead"]>;

/**
 * `deleted_at` ở Pydantic khai `Field(default=None, ...)`, nên
 * openapi-typescript sinh field này dạng optional (`deleted_at?`), suy ra
 * type `string | null | undefined`. Nhưng FastAPI luôn serialize đủ field
 * trong response thật — giá trị có thể là null, không bao giờ bị thiếu hẳn.
 * Ép lại required ở đây để tránh phải xử lý `undefined` lan ra khắp UI.
 */
type WithRequiredDeletedAt<
  T extends { deleted_at?: string | null; project?: unknown },
> = Omit<T, "deleted_at" | "project"> & {
  deleted_at: string | null;
  project?: ProjectSummary | null;
};

export type Task = WithRequiredDeletedAt<Schemas["TaskRead"]>;
export type TaskEvent = Schemas["TaskEventRead"];
/** TaskDetail = Task + events. `events` cũng optional vì default_factory=list. */
export type TaskDetail = WithRequiredDeletedAt<Schemas["TaskDetail"]> & {
  events: TaskEvent[];
};

export type NoteKind = Schemas["NoteKind"];
export type NoteSource = Schemas["NoteSource"];
export type Note = WithRequiredDeletedAt<Schemas["NoteRead"]>;

export interface NoteTrashResponse {
  items: Note[];
  total: number;
  limit: number;
  offset: number;
  retention_days: number;
  purged_now: number;
}

/**
 * Agenda/TrashResponse/NoteTrashResponse trong schema gốc tham chiếu tới
 * TaskRead/NoteRead CHƯA ép required (xem WithRequiredDeletedAt ở trên), vì
 * openapi-typescript không biết các response này luôn trả đủ field. Định
 * nghĩa lại thủ công, dùng alias Task/Note đã ép required, để component
 * nhận mảng Task[]/Note[] đúng kiểu mà không phải tự ép lại ở từng nơi gọi.
 *
 * openapi-typescript cũng đánh dấu overdue/scheduled_today/... là optional
 * vì Pydantic khai bằng default_factory=list — nhưng response thật của GET
 * /tasks/agenda luôn trả đủ mảng (rỗng nhất là []). Khai required ở đây.
 */
export interface Agenda {
  reference_date: string;
  overdue: Task[];
  scheduled_today: Task[];
  in_progress: Task[];
  due_soon: Task[];
  completed_today: Task[];
  totals: Record<string, number>;
}

export type Stats = Schemas["TaskStatsResponse"];

export interface TrashResponse {
  items: Task[];
  total: number;
  limit: number;
  offset: number;
  retention_days: number;
  purged_now: number;
}

export type PurgeResponse = Schemas["PurgeResponse"];

export type ComponentHealth = Schemas["ComponentHealth"];
export type HealthResponse = Schemas["HealthResponse"];
export type SystemInfo = Schemas["SystemInfo"];

/**
 * Page[T] của core API là generic thật (`Page_TaskRead_`, `Page_NoteRead_`),
 * openapi-typescript sinh ra một interface riêng cho mỗi lần dùng, không
 * phải type generic của TypeScript. Khai lại generic ở đây để code gọi
 * API không phải biết tên cụ thể từng cái.
 */
export interface Paged<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export const NOTE_KIND_LABELS: Record<NoteKind, string> = {
  command: "Câu lệnh",
  sql: "SQL",
  text: "Ghi chú",
  config: "Cấu hình",
  code: "Đoạn code",
  system_info: "Hệ thống",
  system_flow: "Luồng hệ thống",
  knowledge: "Kiến thức",
};

export const NOTE_KINDS: NoteKind[] = [
  "command",
  "sql",
  "text",
  "config",
  "code",
  "system_info",
  "system_flow",
  "knowledge",
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

// ── Nhập hàng loạt vào Postgres (B1) ───────────────────────────────────
export type ImportReport = Schemas["ImportReport"];
export type Replacement = Schemas["Replacement"];
export type FieldChange = Schemas["FieldChange"];
export type EntityCounts = Schemas["EntityCounts"];
export type ImportIssue = Schemas["ImportIssue"];
export type KeyChange = Schemas["KeyChange"];

// ── Tích hợp (B4a) ───────────────────────────────────────────────────────
// Alias thuần từ schema sinh. IntegrationRead không có token: chỉ has_secret + secret_last4.
export type IntegrationConnection = Schemas["IntegrationRead"];
export type IntegrationCreateBody = Schemas["IntegrationCreate"];
export type IntegrationUpdateBody = Schemas["IntegrationUpdate"];
/**
 * OpenAPI ghi `status`/`priority` là bắt buộc vì có default, nhưng core chỉ ghi các trường
 * client THỰC SỰ gửi (model_fields_set). Làm optional để mapper được phép bỏ `priority`.
 */
export type TaskUpsertItem = Omit<Schemas["TaskUpsert"], "status" | "priority"> & {
  status?: Schemas["TaskUpsert"]["status"];
  priority?: Schemas["TaskUpsert"]["priority"];
};
export type TaskUpsertResult = Schemas["TaskUpsertResult"];

/**
 * Kết quả upsert hiển thị cho người dùng. Phía web bổ sung: `skipped_no_key` (dòng Excel
 * thiếu Issue Key, không gửi được), `errors_total`/`warnings_total` (tổng thật trước khi
 * cắt còn 20 mục) và biến `index` của errors/warnings thành SỐ DÒNG EXCEL (dòng 1 = tiêu đề).
 */
export interface UpsertSummary extends TaskUpsertResult {
  skipped_no_key?: number;
  errors_total?: number;
  warnings_total?: number;
}
