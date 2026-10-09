import "server-only";

import { cache } from "react";

import { isValidTimezone, tzOffsetMinutes } from "./format";
import * as engine from "./store/engine";
import { ensureLoaded } from "./store/json-file";
import { syncUrlError } from "./sync-url-policy";
import { DATA_SOURCE, trashRetentionDays, type WipeOptions } from "./store/types";
import type {
  Agenda,
  DisplayTimezoneRead,
  HealthResponse,
  ImportReport,
  IntegrationConnection,
  IntegrationCreateBody,
  IntegrationSyncResult,
  IntegrationUpdateBody,
  Note,
  NoteKind,
  NoteSortField,
  NoteTrashResponse,
  Paged,
  Project,
  PurgeResponse,
  Stats,
  SystemInfo,
  Task,
  TaskDetail,
  TaskScope,
  TaskStatus,
  TaskUpsertItem,
  TaskUpsertResult,
  TaskView,
  TimezoneList,
  TrashResponse,
} from "./types";

/**
 * Cửa duy nhất để đọc và ghi dữ liệu của web app.
 *
 * Ba chế độ, chọn bằng biến môi trường DATA_SOURCE:
 *   api     → gọi core API, dữ liệu trong Postgres
 *   file    → lưu file JSON trên đĩa, không cần Docker
 *   memory  → dữ liệu mẫu trong RAM, mất khi restart
 *
 * Hàm export ra ngoài giữ nguyên chữ ký ở cả ba chế độ, nên page và Server
 * Action không cần biết dữ liệu đang nằm ở đâu.
 *
 * API key chỉ tồn tại ở process Next.js phía server. Vì mọi lời gọi đều đi
 * qua file này (có "server-only"), key không bao giờ xuống browser.
 */

const BASE_URL = process.env.CORE_API_URL ?? "http://api:8000";
const API_KEY = process.env.CORE_API_KEY ?? "";

export { DATA_SOURCE };

/** true khi dữ liệu nằm ngay trong process này, không qua mạng. */
export const IS_LOCAL = DATA_SOURCE !== "api";

export class CoreApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "CoreApiError";
  }
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Chặn path injection khi nối `id` vào URL core API.
 *
 * Server Action là endpoint HTTP công khai: client gửi được `id` tuỳ ý. Nếu là
 * "../tasks/<uuid>/restore?" thì fetch chuẩn hoá `..` và gọi một route khác
 * KÈM API key của server (confused deputy). Backend dùng UUID cho path param nên
 * chỉ cần từ chối mọi chuỗi không phải UUID ở đây.
 */
function pathId(id: string): string {
  if (!UUID_RE.test(id)) throw new CoreApiError("id không hợp lệ", 400);
  return id;
}

// ── Đường cục bộ: engine + persistence ─────────────────────────────────

// Cờ phải sống qua hot reload, nếu không mỗi lần sửa file là seed lại
const globalFlags = globalThis as typeof globalThis & {
  __builderMemorySeeded?: boolean;
};

async function ready(): Promise<void> {
  if (DATA_SOURCE === "file") {
    await ensureLoaded();
    return;
  }
  if (DATA_SOURCE === "memory" && !globalFlags.__builderMemorySeeded) {
    if (engine.isEmpty()) engine.seed();
    globalFlags.__builderMemorySeeded = true;
  }
}

/** Chạy thao tác cục bộ, đổi lỗi sang CoreApiError cho đồng nhất với đường mạng. */
async function local<T>(run: () => T): Promise<T> {
  await ready();
  try {
    return run();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return Promise.reject(new CoreApiError(message, 400));
  }
}

// ── Đường mạng: core API ───────────────────────────────────────────────

async function coreFetch<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_KEY) {
    throw new CoreApiError(
      "Thiếu biến môi trường CORE_API_KEY. Đặt DATA_SOURCE=file nếu muốn " +
      "chạy không cần backend.",
      500,
    );
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "X-API-Key": API_KEY,
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    // Body không phải JSON (ví dụ 413 từ proxy): với lỗi thì dùng thông báo mặc định.
    if (response.ok) throw new CoreApiError("Core API trả về body không phải JSON", 502);
  }

  if (!response.ok) {
    const rawDetail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : undefined;
    // 422 của FastAPI trả `detail` là mảng lỗi; String(mảng) chỉ ra "[object Object]".
    const detail = Array.isArray(rawDetail)
      ? rawDetail
          .map((d) =>
            d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d),
          )
          .join("; ")
      : rawDetail !== undefined
        ? String(rawDetail)
        : `Core API trả về ${response.status}`;
    throw new CoreApiError(detail, response.status);
  }

  return body as T;
}

/**
 * Trạng thái của core API, cho trang Thông tin hệ thống.
 *
 * Gọi riêng, không qua coreFetch(): /health/ready không yêu cầu X-API-Key
 * (xem app/api/health.py — probe của Prometheus/blackbox phải gọi được mà
 * không cần khoá), và coreFetch() sẽ throw ngay nếu thiếu CORE_API_KEY dù
 * endpoint này không cần nó. Ở chế độ file/memory không có core API thật để
 * hỏi, nên trả về null — trang gọi hàm này tự hiển thị "không áp dụng".
 */
export async function getHealth(): Promise<HealthResponse | null> {
  if (IS_LOCAL) return null;

  const response = await fetch(`${BASE_URL}/health/ready`, { cache: "no-store" });
  const text = await response.text();
  const body: unknown = text ? JSON.parse(text) : null;

  // health.py set status 503 khi degraded nhưng vẫn trả body hợp lệ —
  // không throw ở đây, để trang tự hiển thị "degraded" kèm chi tiết.
  if (!body || typeof body !== "object") {
    throw new CoreApiError(`Core API trả về ${response.status} không có body`, response.status);
  }
  return body as HealthResponse;
}

/**
 * Config vận hành không nhạy cảm, cho trang Thông tin hệ thống.
 *
 * Dùng coreFetch() bình thường vì /api/v1/system/info YÊU CẦU X-API-Key
 * (khác /health/ready) — tự nó đã lọc field nhạy cảm ở phía backend
 * (xem app/schemas/system.py), nên không cần làm gì thêm ở đây.
 */
export function getSystemInfo(): Promise<SystemInfo | null> {
  if (IS_LOCAL) return Promise.resolve(null);
  return coreFetch<SystemInfo>("/api/v1/system/info");
}

// ── Nhập hàng loạt vào Postgres (B1) ─────────────────────────────────────

export interface ImportCallOptions {
  /** true (mặc định phía core): chạy thử rồi rollback. */
  dryRun: boolean;
  /** Bắt buộc khi dryRun=false: tổng số bản ghi sẽ bị ghi đè, lấy từ lần Kiểm tra. */
  expectReplaced?: number;
  /** Bắt buộc khi dryRun=false: `file_sha256` của báo cáo Kiểm tra (chứng minh cùng một file). */
  expectSha256?: string;
  /**
   * Bắt buộc khi dryRun=false: mật khẩu IMPORT_COMMIT_SECRET. Chỉ đi qua header,
   * KHÔNG đưa vào URL, log hay thông báo lỗi.
   */
  secret?: string;
  /**
   * true: cho phép file ghi đè cả task đang `personal` trong Postgres. Phải gửi ở
   * CẢ dry-run lẫn nhập thật, nếu không số ghi đè lệch và expect_replaced từ chối.
   */
  includePersonal?: boolean;
}

/**
 * Gửi nguyên văn nội dung file lên core. Chỉ chạy ở chế độ api.
 *
 * Vì sao body là chuỗi thô: core tính sha256 từ body để audit, và tự validate
 * từng dòng. Web không parse lại, nên không thể vô tình sửa nội dung. BOM đầu
 * file (Excel/Windows hay thêm) làm JSON.parse phía core lỗi nên bỏ ở đây.
 */
async function postImport(
  endpoint: "datafile",
  text: string,
  options: ImportCallOptions,
): Promise<ImportReport> {
  if (IS_LOCAL) {
    return Promise.reject(
      new CoreApiError("Nhập vào Postgres chỉ dùng được ở chế độ DATA_SOURCE=api", 501),
    );
  }
  const params = new URLSearchParams({ dry_run: options.dryRun ? "true" : "false" });
  if (options.includePersonal) params.set("include_personal", "true");
  if (!options.dryRun) {
    if (
      options.expectReplaced === undefined ||
      !Number.isInteger(options.expectReplaced) ||
      options.expectReplaced < 0
    ) {
      return Promise.reject(new CoreApiError("Thiếu số bản ghi dự kiến bị ghi đè (expect_replaced)", 400));
    }
    params.set("expect_replaced", String(options.expectReplaced));
    if (!options.expectSha256 || !/^[0-9a-f]{64}$/i.test(options.expectSha256)) {
      return Promise.reject(new CoreApiError("Thiếu mã băm file của lần Kiểm tra (expect_sha256)", 400));
    }
    if (!options.secret) {
      return Promise.reject(new CoreApiError("Thiếu mật khẩu nhập", 400));
    }
    params.set("expect_sha256", options.expectSha256.toLowerCase());
  }
  const body = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  const headers: Record<string, string> = {};
  if (!options.dryRun && options.secret) headers["X-Import-Secret"] = options.secret;
  return coreFetch<ImportReport>(`/api/v1/import/${endpoint}?${params.toString()}`, {
    method: "POST",
    body,
    headers,
  });
}

/** Nhập file backup JSON (projects/tasks/notes) vào Postgres. */
export function importDataFile(text: string, options: ImportCallOptions): Promise<ImportReport> {
  return postImport("datafile", text, options);
}

// ── Settings ─────────────────────────────────────────────────────────────

export async function getCurrentUsersApi(): Promise<string[]> {
  if (IS_LOCAL) return local(() => engine.getCurrentUsers());
  const body = await coreFetch<{ names: string[] }>("/api/v1/settings/current-users");
  return body.names;
}

/** Gợi ý tên cho ô "tôi là ai": chế độ api chỉ lấy assignee của task công việc còn sống. */
export async function getAssigneesApi(): Promise<string[]> {
  if (IS_LOCAL) return local(() => engine.getAssignees());
  return coreFetch<string[]>("/api/v1/tasks/assignees");
}

export async function setCurrentUsersApi(names: string[]): Promise<void> {
  if (IS_LOCAL) return local(() => { engine.setCurrentUsers(names); return undefined as any; });
  await coreFetch<{ names: string[] }>("/api/v1/settings/current-users", {
    method: "PUT",
    body: JSON.stringify({ names }),
  });
}

// ── Múi giờ hiển thị ─────────────────────────────────────────────────────

// Dự phòng khi API sập hoặc chưa có cài đặt. Đây là nơi DUY NHẤT còn đọc biến build-time
// này; nguồn chính là backend (chế độ api) hoặc meta của file JSON (chế độ file).
// Giá trị env sai (gõ nhầm tên múi giờ) phải rơi về mặc định, không để Intl ném RangeError lúc render.
const FALLBACK_TZ =
  process.env.NEXT_PUBLIC_DISPLAY_TZ && isValidTimezone(process.env.NEXT_PUBLIC_DISPLAY_TZ)
    ? process.env.NEXT_PUBLIC_DISPLAY_TZ
    : "Asia/Ho_Chi_Minh";
engine.setDefaultTimezone(FALLBACK_TZ);

/**
 * Múi giờ hiển thị hiện hành, cho layout và các trang. Bọc `cache()` để một lần render
 * chỉ gọi backend một lần dù nhiều Server Component cùng hỏi.
 *
 * KHÔNG BAO GIỜ ném lỗi: layout bọc cả app, nếu API sập mà layout vỡ thì không còn trang
 * nào mở được (kể cả trang /system để chẩn đoán). Lỗi thì trả múi giờ dự phòng.
 */
export const getDisplayTimezoneApi = cache(async (): Promise<DisplayTimezoneRead> => {
  if (IS_LOCAL) {
    try {
      return await local(() => engine.getDisplayTimezone());
    } catch {
      return { timezone: FALLBACK_TZ, default: FALLBACK_TZ, source: "default" };
    }
  }
  try {
    return await coreFetch<DisplayTimezoneRead>("/api/v1/settings/display-timezone");
  } catch {
    return { timezone: FALLBACK_TZ, default: FALLBACK_TZ, source: "default" };
  }
});

/** Lưu múi giờ. `null` = xoá lựa chọn, về mặc định. Backend 409 nếu đang có lần nhập giữ khoá. */
export async function setDisplayTimezoneApi(tz: string | null): Promise<DisplayTimezoneRead> {
  if (IS_LOCAL) {
    return local(() => {
      engine.setDisplayTimezone(tz);
      return engine.getDisplayTimezone();
    });
  }
  return coreFetch<DisplayTimezoneRead>("/api/v1/settings/display-timezone", {
    method: "PUT",
    body: JSON.stringify({ timezone: tz }),
  });
}

/**
 * Danh mục tên IANA cho ô chọn. Chế độ file lấy từ Intl của Node. Cố ý không phân trang:
 * danh mục tĩnh khoảng 600 tên, không phải dữ liệu người dùng tăng dần.
 */
export async function listTimezonesApi(): Promise<TimezoneList> {
  if (IS_LOCAL) {
    const now = new Date();
    const names = Intl.supportedValuesOf("timeZone");
    // Intl bỏ "UTC" khỏi danh sách trên một số bản Node.
    if (!names.includes("UTC")) names.push("UTC");
    names.sort();
    const items = names.map((name) => ({
      name,
      utc_offset_minutes: tzOffsetMinutes(name, now),
    }));
    return { items, total: items.length };
  }
  return coreFetch<TimezoneList>("/api/v1/settings/timezones");
}

// ── Đọc ────────────────────────────────────────────────────────────────

/**
 * Tên "của tôi" cho view=mine. LUÔN lấy từ cài đặt phía server, không bao giờ
 * từ searchParams hay client, để URL không đổi được "việc của tôi" là gì.
 * Trước B2, chế độ api trả [] nên "Hôm nay" chỉ còn task cá nhân (S6).
 */
async function ownersFor(view: TaskView): Promise<string[]> {
  return view === "mine" ? getCurrentUsersApi() : [];
}

/** Gắn view và owner (lặp lại) vào query của core. owner chỉ hợp lệ với view=mine. */
function appendView(params: URLSearchParams, view: TaskView, owners: readonly string[]): void {
  params.set("view", view);
  if (view === "mine") owners.forEach((name) => params.append("owner", name));
}

export async function getAgenda(
  opts: { view?: TaskView; referenceDate?: string } = {},
): Promise<Agenda> {
  const view = opts.view ?? "mine";
  const owners = await ownersFor(view);
  if (IS_LOCAL) return local(() => engine.getAgenda({ view, owners }));
  const params = new URLSearchParams();
  if (opts.referenceDate) params.set("reference_date", opts.referenceDate);
  appendView(params, view, owners);
  return coreFetch<Agenda>(`/api/v1/tasks/agenda?${params.toString()}`);
}

export async function getStats(opts: { view?: TaskView } = {}): Promise<Stats> {
  const view = opts.view ?? "mine";
  const owners = await ownersFor(view);
  if (IS_LOCAL) return local(() => engine.getStats({ view, owners }));
  const params = new URLSearchParams();
  appendView(params, view, owners);
  return coreFetch<Stats>(`/api/v1/tasks/stats?${params.toString()}`);
}

export interface ListTasksOptions {
  status?: TaskStatus[];
  projectId?: string;
  query?: string;
  includeClosed?: boolean;
  limit?: number;
  offset?: number;
  sortBy?: string;
  sortDesc?: boolean;
  assignee?: string | null;
  /** Mặc định `all` (giữ hành vi cũ); `mine` lấy owner từ cài đặt phía server. */
  view?: TaskView;
}

export async function listTasks(options: ListTasksOptions = {}): Promise<Paged<Task>> {
  const view = options.view ?? "all";
  const owners = await ownersFor(view);
  if (IS_LOCAL) return local(() => engine.listTasks({ ...options, view, owners }));

  const params = new URLSearchParams();
  // Trước epic scope, chế độ api bỏ qua assignee nên /tasks hiện mọi task.
  if (options.assignee) params.set("assignee", options.assignee);
  appendView(params, view, owners);
  options.status?.forEach((value) => params.append("status", value));
  if (options.projectId) params.set("project_id", options.projectId);
  if (options.query) params.set("q", options.query);
  if (options.includeClosed) params.set("include_closed", "true");
  params.set("limit", String(options.limit ?? 100));
  params.set("offset", String(options.offset ?? 0));
  if (options.sortBy) params.set("sort_by", options.sortBy);
  if (options.sortDesc !== undefined) {
    params.set("sort_desc", String(options.sortDesc));
  }
  return coreFetch<Paged<Task>>(`/api/v1/tasks?${params.toString()}`);
}

export function getTask(id: string): Promise<TaskDetail> {
  if (IS_LOCAL) return local(() => engine.getTask(id));
  return coreFetch<TaskDetail>(`/api/v1/tasks/${pathId(id)}`);
}

export function listProjects(includeArchived = false): Promise<Project[]> {
  if (IS_LOCAL) return local(() => engine.listProjects(includeArchived));
  const query = includeArchived ? "?include_archived=true" : "";
  return coreFetch<Project[]>(`/api/v1/projects${query}`);
}

// ── Ghi ────────────────────────────────────────────────────────────────

export interface CreateTaskInput {
  title: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: string;
  project_id?: string | null;
  due_at?: string | null;
  created_at?: string;
  scheduled_for?: string | null;
  estimate_minutes?: number | null;
  tags?: string[];
  source?: string;
  external_id?: string | null;
  external_url?: string | null;
  assignee?: string | null;
  /** Vắng thì core/engine suy từ source (manual -> personal). */
  scope?: TaskScope;
}

export function createTask(input: CreateTaskInput): Promise<TaskDetail> {
  if (IS_LOCAL) return local(() => engine.createTask(input));
  return coreFetch<TaskDetail>("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function patchTask(
  id: string,
  input: Record<string, unknown>,
): Promise<TaskDetail> {
  if (IS_LOCAL) return local(() => engine.patchTask(id, input));
  return coreFetch<TaskDetail>(`/api/v1/tasks/${pathId(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

/**
 * Xoá task. Mặc định là xoá mềm, task vào thùng rác và còn phục hồi được.
 * Truyền permanent=true để xoá thẳng, không hoàn tác.
 */
export function deleteTask(id: string, permanent = false): Promise<void> {
  if (IS_LOCAL) {
    return local(() =>
      permanent ? engine.purgeTaskNow(id) : engine.deleteTask(id),
    );
  }
  const query = permanent ? "?permanent=true" : "";
  return coreFetch<void>(`/api/v1/tasks/${pathId(id)}${query}`, { method: "DELETE" });
}

// ── Thùng rác ──────────────────────────────────────────────────────────

export function listTrash(limit = 100, offset = 0): Promise<TrashResponse> {
  if (IS_LOCAL) {
    return local(() => {
      // Dọn quá hạn ngay lúc mở thùng rác, vì chưa có scheduler
      const purged = engine.purgeExpired();
      const page = engine.listTrash(limit, offset);
      return {
        items: page.items,
        total: page.total,
        limit,
        offset,
        retention_days: trashRetentionDays(),
        purged_now: purged,
      };
    });
  }

  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return coreFetch<TrashResponse>(`/api/v1/tasks/trash?${params.toString()}`);
}

export function restoreTask(id: string): Promise<TaskDetail> {
  if (IS_LOCAL) return local(() => engine.restoreTask(id));
  return coreFetch<TaskDetail>(`/api/v1/tasks/${pathId(id)}/restore`, {
    method: "POST",
  });
}

/** Xoá vĩnh viễn một task đang ở trong thùng rác. */
export function purgeTask(id: string): Promise<void> {
  if (IS_LOCAL) return local(() => engine.purgeTask(id));
  return coreFetch<void>(`/api/v1/tasks/${pathId(id)}?permanent=true`, {
    method: "DELETE",
  });
}

export function purgeExpired(): Promise<PurgeResponse> {
  if (IS_LOCAL) {
    return local(() => ({
      purged: engine.purgeExpired(),
      retention_days: trashRetentionDays(),
    }));
  }
  return coreFetch<PurgeResponse>("/api/v1/tasks/trash/purge", {
    method: "POST",
  });
}

export function emptyTrash(): Promise<PurgeResponse> {
  if (IS_LOCAL) {
    return local(() => ({
      purged: engine.emptyTrash(),
      retention_days: trashRetentionDays(),
    }));
  }
  return coreFetch<PurgeResponse>("/api/v1/tasks/trash/empty", {
    method: "POST",
  });
}

export function logTime(
  id: string,
  minutes: number,
  note?: string | null,
): Promise<TaskDetail> {
  if (IS_LOCAL) return local(() => engine.logTime(id, minutes, note));
  return coreFetch<TaskDetail>(`/api/v1/tasks/${pathId(id)}/time`, {
    method: "POST",
    body: JSON.stringify({ minutes, note: note ?? null }),
  });
}


export function patchProject(
  id: string,
  input: {
    key?: string;
    name?: string;
    description?: string | null;
    color?: string | null;
    is_archived?: boolean;
  },
): Promise<Project> {
  if (IS_LOCAL) return local(() => engine.patchProject(id, input));
  return coreFetch<Project>(`/api/v1/projects/${pathId(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteProject(id: string): Promise<void> {
  if (IS_LOCAL) {
    return local(() => {
      engine.deleteProject(id);
      return undefined as any;
    });
  }
  return coreFetch<void>(`/api/v1/projects/${pathId(id)}`, {
    method: "DELETE",
  });
}

export function createProject(input: {
  key: string;
  name: string;
  color?: string | null;
}): Promise<Project> {
  if (IS_LOCAL) return local(() => engine.createProject(input));
  return coreFetch<Project>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// ═══════════════════════════════════════════════════════════════════════
//  Sổ tay
//
//  `content` của note đi qua đây nguyên văn, không escape và không biến đổi.
//  Nó chỉ là chuỗi dữ liệu. Chỗ duy nhất phải cẩn thận là lúc render ở
//  component: dùng text node, không dangerouslySetInnerHTML.
// ═══════════════════════════════════════════════════════════════════════

export interface ListNotesOptions {
  kind?: NoteKind[];
  projectId?: string;
  tags?: string[];
  query?: string;
  pinnedOnly?: boolean;
  limit?: number;
  offset?: number;
  sortBy?: NoteSortField;
  sortDesc?: boolean;
  assignee?: string | null;
  /** true = chỉ note đã lưu trữ. Mặc định (false) = chỉ note đang dùng. */
  archived?: boolean;
}

export function listNotes(options: ListNotesOptions = {}): Promise<Paged<Note>> {
  if (IS_LOCAL) {
    // File/memory mode chưa có khái niệm lưu trữ. Trả trang rỗng thay vì để
    // engine âm thầm bỏ qua cờ và hiện toàn bộ note ở tab Lưu trữ.
    if (options.archived) {
      return Promise.resolve({
        items: [],
        total: 0,
        limit: options.limit ?? 100,
        offset: options.offset ?? 0,
      });
    }
    return local(() => engine.listNotes(options));
  }

  const params = new URLSearchParams();
  if (options.archived) params.set("archived", "true");
  options.kind?.forEach((value) => params.append("kind", value));
  options.tags?.forEach((value) => params.append("tags", value));
  if (options.projectId) params.set("project_id", options.projectId);
  if (options.query) params.set("q", options.query);
  if (options.pinnedOnly) params.set("pinned_only", "true");
  params.set("limit", String(options.limit ?? 100));
  params.set("offset", String(options.offset ?? 0));
  if (options.sortBy) params.set("sort_by", options.sortBy);
  if (options.sortDesc !== undefined) {
    params.set("sort_desc", String(options.sortDesc));
  }
  return coreFetch<Paged<Note>>(`/api/v1/notes?${params.toString()}`);
}

export function getNote(id: string): Promise<Note> {
  if (IS_LOCAL) return local(() => engine.getNote(id));
  return coreFetch<Note>(`/api/v1/notes/${pathId(id)}`);
}

/** Đếm note theo loại trong đúng view đang xem (đang dùng hoặc lưu trữ). */
export function getNoteStats(
  options: { archived?: boolean } = {},
): Promise<Record<string, number>> {
  if (IS_LOCAL) {
    if (options.archived) return Promise.resolve({});
    return local(() => engine.countNotesByKind());
  }
  const query = options.archived ? "?archived=true" : "";
  return coreFetch<Record<string, number>>(`/api/v1/notes/stats${query}`);
}

/**
 * Lưu trữ note: ẩn khỏi danh sách mặc định nhưng không bị dọn như thùng rác.
 * Chỉ hỗ trợ DATA_SOURCE=api; engine cục bộ chưa có trạng thái này nên
 * từ chối rõ ràng thay vì giả vờ thành công.
 */
export function archiveNote(id: string): Promise<Note> {
  if (IS_LOCAL) return Promise.reject(localArchiveUnsupported());
  return coreFetch<Note>(`/api/v1/notes/${pathId(id)}/archive`, { method: "POST" });
}

/** Đưa note từ Lưu trữ về danh sách đang dùng. Cùng giới hạn như archiveNote. */
export function unarchiveNote(id: string): Promise<Note> {
  if (IS_LOCAL) return Promise.reject(localArchiveUnsupported());
  return coreFetch<Note>(`/api/v1/notes/${pathId(id)}/unarchive`, { method: "POST" });
}

function localArchiveUnsupported(): CoreApiError {
  return new CoreApiError("Lưu trữ note chỉ hỗ trợ khi DATA_SOURCE=api", 501);
}

export interface CreateNoteInput {
  title: string;
  content: string;
  kind?: NoteKind;
  description?: string | null;
  context?: string | null;
  project_id?: string | null;
  tags?: string[];
  is_pinned?: boolean;
  is_dangerous?: boolean;
}

export function createNote(input: CreateNoteInput): Promise<Note> {
  if (IS_LOCAL) return local(() => engine.createNote(input));
  return coreFetch<Note>("/api/v1/notes", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function patchNote(
  id: string,
  input: Record<string, unknown>,
): Promise<Note> {
  if (IS_LOCAL) return local(() => engine.patchNote(id, input));
  return coreFetch<Note>(`/api/v1/notes/${pathId(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

/**
 * Xoá note. Mặc định là xoá mềm, note vào thùng rác và còn phục hồi được.
 * Truyền permanent=true để xoá thẳng, không hoàn tác.
 */
export function deleteNote(id: string, permanent = false): Promise<void> {
  if (IS_LOCAL) {
    return local(() =>
      permanent ? engine.purgeNoteNow(id) : engine.deleteNote(id),
    );
  }
  const query = permanent ? "?permanent=true" : "";
  return coreFetch<void>(`/api/v1/notes/${pathId(id)}${query}`, { method: "DELETE" });
}

/** Ghi nhận một lần dùng, để sắp xếp theo mức độ hay dùng. */
export function markNoteUsed(id: string): Promise<Note> {
  if (IS_LOCAL) return local(() => engine.markNoteUsed(id));
  return coreFetch<Note>(`/api/v1/notes/${pathId(id)}/use`, { method: "POST" });
}

export function listNoteTrash(
  limit = 100,
  offset = 0,
): Promise<NoteTrashResponse> {
  if (IS_LOCAL) {
    return local(() => {
      // Dọn quá hạn ngay lúc mở thùng rác, vì chưa có scheduler
      const purged = engine.purgeExpiredNotes();
      const page = engine.listNoteTrash(limit, offset);
      return {
        items: page.items,
        total: page.total,
        limit,
        offset,
        retention_days: trashRetentionDays(),
        purged_now: purged,
      };
    });
  }

  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return coreFetch<NoteTrashResponse>(
    `/api/v1/notes/trash?${params.toString()}`,
  );
}

export function restoreNote(id: string): Promise<Note> {
  if (IS_LOCAL) return local(() => engine.restoreNote(id));
  return coreFetch<Note>(`/api/v1/notes/${pathId(id)}/restore`, { method: "POST" });
}

/** Xoá vĩnh viễn một note đang ở trong thùng rác. */
export function purgeNote(id: string): Promise<void> {
  if (IS_LOCAL) return local(() => engine.purgeNote(id));
  return coreFetch<void>(`/api/v1/notes/${pathId(id)}?permanent=true`, {
    method: "DELETE",
  });
}

export function purgeExpiredNotes(): Promise<PurgeResponse> {
  if (IS_LOCAL) {
    return local(() => ({
      purged: engine.purgeExpiredNotes(),
      retention_days: trashRetentionDays(),
    }));
  }
  return coreFetch<PurgeResponse>("/api/v1/notes/trash/purge", {
    method: "POST",
  });
}

export function emptyNoteTrash(): Promise<PurgeResponse> {
  if (IS_LOCAL) {
    return local(() => ({
      purged: engine.emptyNoteTrash(),
      retention_days: trashRetentionDays(),
    }));
  }
  return coreFetch<PurgeResponse>("/api/v1/notes/trash/empty", {
    method: "POST",
  });
}

export async function getSyncUrlsApi(): Promise<string[]> {
  if (IS_LOCAL) return local(() => engine.getSyncUrls());
  const body = await coreFetch<{ urls: string[] }>("/api/v1/settings/sync-urls");
  return body.urls;
}

async function putSyncUrls(urls: string[]): Promise<void> {
  await coreFetch<{ urls: string[] }>("/api/v1/settings/sync-urls", {
    method: "PUT",
    body: JSON.stringify({ urls }),
  });
}

/**
 * Lưu URL đồng bộ. URL là thứ server SẼ FETCH nên phải qua allowlist (https + host
 * cho phép) ở CẢ hai tầng: ở đây để báo lỗi rõ và không phụ thuộc vào core, và core
 * kiểm lại khi PUT. Thông báo lỗi không chứa URL (link chia sẻ thường mang token).
 */
export interface SyncUrlChange {
  /** Số link cũ không còn qua allowlist bị bỏ khỏi danh sách trong lần lưu này. */
  dropped: number;
}

/**
 * PUT kiểm lại MỌI phần tử, nên một link cũ không còn hợp lệ (đổi allowlist sau khi lưu)
 * sẽ khóa cả việc thêm lẫn xoá. Lọc chúng ra trước khi PUT và báo số lượng để UI nói
 * rõ với người dùng thay vì lặng lẽ làm mất link.
 */
async function putFilteredSyncUrls(urls: string[]): Promise<SyncUrlChange> {
  const valid = urls.filter((u) => syncUrlError(u) === null);
  await putSyncUrls(valid);
  return { dropped: urls.length - valid.length };
}

export async function addSyncUrlApi(url: string): Promise<SyncUrlChange> {
  const rejected = syncUrlError(url);
  if (rejected !== null) throw new CoreApiError(rejected, 400);
  if (IS_LOCAL) return local(() => { engine.addSyncUrl(url); return { dropped: 0 }; });
  const current = await getSyncUrlsApi();
  if (current.includes(url)) return { dropped: 0 };
  return putFilteredSyncUrls([...current, url]);
}
export async function removeSyncUrlApi(url: string): Promise<SyncUrlChange> {
  if (IS_LOCAL) return local(() => { engine.removeSyncUrl(url); return { dropped: 0 }; });
  const current = await getSyncUrlsApi();
  return putFilteredSyncUrls(current.filter((u) => u !== url));
}

// ── Tags Management ──────────────────────────────────────────────────────

export interface TagStat {
  name: string;
  taskCount: number;
  noteCount: number;
}

export async function getTagsStatsApi(): Promise<TagStat[]> {
  if (IS_LOCAL) return local(() => engine.getTagsStats());
  return []; // TBD core API
}

export async function renameGlobalTagApi(oldName: string, newName: string): Promise<void> {
  if (IS_LOCAL) return local(() => engine.renameGlobalTag(oldName, newName));
}

export async function deleteGlobalTagApi(name: string): Promise<void> {
  if (IS_LOCAL) return local(() => engine.deleteGlobalTag(name));
}

/**
 * Xoá hàng loạt chỉ có ở chế độ file/memory. Ở chế độ api từ chối rõ ràng:
 * trước đây hàm trả undefined nên UI báo "đã xoá" mà không xoá gì.
 */
export async function wipeAllDataApi(options?: WipeOptions): Promise<void> {
  if (IS_LOCAL) return local(() => engine.wipeAllData(options));
  return Promise.reject(new CoreApiError("Xoá hàng loạt chỉ hỗ trợ chế độ file", 501));
}


// ═══════════════════════════════════════════════════════════════════════
//  Tích hợp và upsert hàng loạt (B4a) — chỉ chế độ api
// ═══════════════════════════════════════════════════════════════════════

function requireApiMode(): void {
  if (IS_LOCAL) {
    throw new CoreApiError("Chỉ dùng được ở chế độ DATA_SOURCE=api", 501);
  }
}

/**
 * Danh sách kết nối. Core không bao giờ trả token, chỉ has_secret + secret_last4.
 * Giới hạn 100 (trần của core): số kết nối Jira của một người rất nhỏ nên không phân trang.
 */
export function listIntegrations(): Promise<Paged<IntegrationConnection>> {
  requireApiMode();
  return coreFetch<Paged<IntegrationConnection>>("/api/v1/integrations?limit=100");
}

/** Tạo kết nối. `token` là write-only; không log và không đưa vào thông báo lỗi. */
export function createIntegration(body: IntegrationCreateBody): Promise<IntegrationConnection> {
  requireApiMode();
  return coreFetch<IntegrationConnection>("/api/v1/integrations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Sửa kết nối. Không gửi `token` = giữ token cũ; `clear_token: true` để xoá. */
export function patchIntegration(id: string, body: IntegrationUpdateBody): Promise<IntegrationConnection> {
  requireApiMode();
  return coreFetch<IntegrationConnection>(`/api/v1/integrations/${pathId(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteIntegration(id: string): Promise<void> {
  requireApiMode();
  await coreFetch<void>(`/api/v1/integrations/${pathId(id)}`, { method: "DELETE" });
}

/**
 * Cào Jira theo kết nối đã lưu (B4b). Core tự gọi Jira bằng token đã giải mã; web chỉ
 * kích hoạt. Mật khẩu IMPORT_COMMIT_SECRET đi DUY NHẤT qua header X-Import-Secret.
 *
 * Không đặt timeout ngắn: core có trần 5 phút cho một lượt sync. Ở đây dùng 6 phút để
 * core là bên tự cắt trước và trả 504 có thông báo rõ.
 */
export async function syncIntegration(id: string, secret: string, since?: string): Promise<IntegrationSyncResult> {
  requireApiMode();
  const query = since ? `?since=${encodeURIComponent(since)}` : "";
  return coreFetch<IntegrationSyncResult>(`/api/v1/integrations/${pathId(id)}/sync${query}`, {
    method: "POST",
    headers: { "X-Import-Secret": secret },
    signal: AbortSignal.timeout(6 * 60_000),
  });
}

/**
 * Kiểm mật khẩu nhập (IMPORT_COMMIT_SECRET) mà KHÔNG ghi gì. Gọi trước các việc tốn kém
 * (fetch URL, đọc/parse file) để request sai mật khẩu bị từ chối sớm, không biến server
 * thành công cụ tải URL hay parse file cho người chưa xác thực. Core trả 204 nếu đúng,
 * 403 nếu sai/thiếu/chưa cấu hình (ném CoreApiError status 403).
 */
export async function verifyImportSecret(secret: string): Promise<void> {
  requireApiMode();
  await coreFetch<void>("/api/v1/import/verify-secret", {
    method: "POST",
    headers: { "X-Import-Secret": secret },
  });
}

/** Trần số item mỗi lô của core (TaskUpsertBatch.items). */
const UPSERT_BATCH_SIZE = 1000;
/** Trần kích thước JSON mỗi lô: dưới nhiều so với trần body 20 MB của core. */
const UPSERT_BATCH_MAX_BYTES = 8 * 1024 * 1024;

/** Kết quả upsert kèm số lô đã ghi, để báo cáo khi lô sau thất bại. */
export class UpsertBatchError extends CoreApiError {
  constructor(
    message: string,
    status: number,
    readonly batchesDone: number,
    readonly batchesTotal: number,
  ) {
    super(message, status);
    this.name = "UpsertBatchError";
  }
}

/**
 * Chia item thành lô theo CẢ số item (<= 1000) lẫn kích thước JSON (< 8 MB) để không vượt
 * trần body 20 MB của core. Một item đơn lẻ lớn hơn trần vẫn thành lô riêng (core sẽ trả
 * 413/lỗi cho lô đó).
 */
function splitBatches(items: TaskUpsertItem[]): TaskUpsertItem[][] {
  const batches: TaskUpsertItem[][] = [];
  let current: TaskUpsertItem[] = [];
  let bytes = 0;
  for (const item of items) {
    const size = Buffer.byteLength(JSON.stringify(item), "utf8") + 1;
    if (current.length > 0 && (current.length >= UPSERT_BATCH_SIZE || bytes + size > UPSERT_BATCH_MAX_BYTES)) {
      batches.push(current);
      current = [];
      bytes = 0;
    }
    current.push(item);
    bytes += size;
  }
  if (current.length > 0) batches.push(current);
  return batches;
}

/**
 * Upsert task theo `(source, external_id)`, tự chia lô và cộng dồn kết quả.
 *
 * Mật khẩu IMPORT_COMMIT_SECRET chỉ đi qua header X-Import-Secret. Chỉ số `index` trong
 * errors/warnings được quy đổi về vị trí trong MẢNG GỐC (cộng offset lô). Mỗi lô là một
 * giao dịch riêng: nếu lô sau thất bại thì các lô trước ĐÃ ghi; lỗi ném ra là
 * UpsertBatchError (mang số lô đã xong) và chạy lại an toàn vì upsert idempotent.
 */
export async function upsertTasksBatch(
  source: "jira",
  items: TaskUpsertItem[],
  secret: string,
): Promise<TaskUpsertResult> {
  requireApiMode();
  const total: TaskUpsertResult = {
    added: 0,
    updated: 0,
    unchanged: 0,
    skipped_personal: 0,
    errors: [],
    warnings: [],
  };
  const batches = splitBatches(items);
  let offset = 0;
  for (const [i, chunk] of batches.entries()) {
    let res: TaskUpsertResult;
    try {
      res = await coreFetch<TaskUpsertResult>("/api/v1/tasks/upsert-batch", {
        method: "POST",
        body: JSON.stringify({ source, items: chunk }),
        headers: { "X-Import-Secret": secret },
      });
    } catch (error) {
      if (i > 0 && error instanceof CoreApiError) {
        throw new UpsertBatchError(error.message, error.status, i, batches.length);
      }
      throw error;
    }
    total.added += res.added;
    total.updated += res.updated;
    total.unchanged += res.unchanged;
    total.skipped_personal += res.skipped_personal;
    for (const e of res.errors ?? []) total.errors?.push({ ...e, index: e.index + offset });
    for (const w of res.warnings ?? []) total.warnings?.push({ ...w, index: w.index + offset });
    offset += chunk.length;
  }
  return total;
}
