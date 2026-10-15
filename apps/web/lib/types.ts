// Alias sang schema sinh tự động từ /openapi.json (components["schemas"]).
// KHÔNG viết tay field của entity ở đây nữa — sửa backend thì chạy lại
// `npm run gen:types` (hoặc `make gen-types` ở gốc repo), lib/generated/openapi.d.ts
// tự khớp lại. File này chỉ còn: alias tên ngắn, type phụ trợ cho local
// store (file/memory), và hằng số/label chỉ UI cần (không nằm trong OpenAPI
// vì đó là quyết định hiển thị, không phải hợp đồng dữ liệu).
import type { components } from "./generated/openapi";
import type { Permission } from "./permissions";

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
/**
 * `can_edit`/`can_delete`: core tính theo người xem nên schema sinh khai BẮT BUỘC, nhưng dữ liệu của
 * chế độ file/memory (lib/store/**) không có người xem nên không có hai field này. Ép lại thành
 * optional ở kiểu Task/Project dùng chung: UI chỉ ẨN/KHOÁ khi giá trị là `false` (vắng = được phép).
 * Core vẫn là bên chặn thật.
 */
type WithAccess = { can_edit?: boolean; can_delete?: boolean };
type OptionalAccess<T> = Omit<T, "can_edit" | "can_delete"> & WithAccess;
export type Project = OptionalAccess<WithRequiredColor<Schemas["ProjectRead"]>>;

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

/**
 * `reporter` (tên hiển thị người tạo issue ở Jira) khai bù ở đây cho tới khi `openapi.d.ts` được sinh
 * lại từ backend. Omit + khai lại nên vẫn đúng sau khi sinh (không xung đột kiểu), và bỏ được khi tiện.
 */
export type Task = OptionalAccess<Omit<WithRequiredDeletedAt<Schemas["TaskRead"]>, "reporter">> & {
  reporter: string | null;
};
export type TaskEvent = Schemas["TaskEventRead"];
/** TaskDetail = Task + events. `events` cũng optional vì default_factory=list. */
export type TaskDetail = OptionalAccess<WithRequiredDeletedAt<Schemas["TaskDetail"]>> & {
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
export type ProjectProgress = Schemas["ProjectProgress"];

/** Dashboard tham dự dự án của nhóm (GET /tasks/participation). */
export type Participation = Schemas["ParticipationResponse"];
export type ProjectParticipation = Schemas["ProjectParticipation"];
export type ParticipationMember = Schemas["ParticipationMember"];

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
/** Kết quả POST /integrations/{id}/sync (B4b). errors/warnings có external_id, không chứa body Jira. */
export type IntegrationSyncResult = Schemas["SyncResult"];
/**
 * OpenAPI ghi `status`/`priority` là bắt buộc vì có default, nhưng core chỉ ghi các trường
 * client THỰC SỰ gửi (model_fields_set). Làm optional để mapper được phép bỏ `priority`.
 */
export type TaskUpsertItem = Omit<Schemas["TaskUpsert"], "status" | "priority" | "reporter"> & {
  /** Vắng khoá = giữ giá trị đang có ở core; null tường minh = xoá. */
  reporter?: string | null;
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

// ── Đăng nhập (spec web-authjs-login) ───────────────────────────────────
// Alias thuần từ schema sinh (openapi.d.ts đã có /me, /auth/login, /admin). Không viết tay field.

/** Quyền của core: nguồn khai ở lib/permissions.ts. */
export type PermissionName = Permission;

export type MeRead = Omit<Schemas["MeRead"], "permissions"> & { permissions: PermissionName[] };
export type UserRole = Schemas["UserRole"];
export type UserStatus = Schemas["UserStatus"];
export type AuthProvider = Schemas["AuthProvider"];

/** Claim Google đã được web xác minh, gửi cho POST /auth/login (core đặt extra="forbid"). */
export type LoginClaims = Omit<Schemas["LoginRequest"], "client_ip">;
export type LoginResult = Schemas["LoginResult"];

// ── Tài khoản nội bộ và quản trị người dùng (spec admin-users-local-login) ─────
// Mật khẩu chỉ nằm trong các body GỬI ĐI; không schema ĐỌC nào có password/hash.
export type PasswordChangeBody = Schemas["PasswordChange"];
export type PasswordChanged = Schemas["PasswordChanged"];
export type UserAdmin = Schemas["UserAdminRead"];
export type UserAdminUpdate = Schemas["UserAdminUpdate"];
export type GoogleUserInviteBody = Schemas["GoogleUserInvite"];
export type LocalUserCreateBody = Schemas["LocalUserCreate"];
export type LocalUserCreated = Schemas["LocalUserCreated"];
export type TemporaryPassword = Schemas["TemporaryPassword"];
export type AliasItem = Schemas["AliasItem"];
export type AuditAction = Schemas["AuditAction"];
export type AuditEntry = Schemas["AuditRead"];
/** Mọi giá trị AuditAction (cho ô lọc /admin/audit). Thêm action ở core thì thêm ở đây; tsc bắt giá trị sai. */
export const AUDIT_ACTIONS: readonly AuditAction[] = [
  "login_success",
  "login_denied",
  "login_locked",
  "user_invited",
  "user_created",
  "user_updated",
  "user_role_changed",
  "user_status_changed",
  "user_aliases_changed",
  "user_unlocked",
  "user_deleted",
  "sessions_revoked",
  "password_reset",
  "password_changed",
  "password_change_failed",
  "import_committed",
  "integration_created",
  "integration_updated",
  "integration_deleted",
  "integration_synced",
  "bootstrap_backfill",
];

export const USER_ROLES: readonly UserRole[] = ["admin", "lead", "member"];
export const USER_ROLE_LABELS: Record<UserRole, string> = {
  admin: "Quản trị viên",
  lead: "Trưởng nhóm",
  member: "Thành viên",
};
export const USER_STATUS_LABELS: Record<UserStatus, string> = {
  invited: "Đã mời",
  active: "Hoạt động",
  disabled: "Đã khoá",
};
