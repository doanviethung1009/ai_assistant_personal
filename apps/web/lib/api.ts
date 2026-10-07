import "server-only";

import * as engine from "./store/engine";
import { ensureLoaded, reloadAiLogsFromDisk } from "./store/json-file";
import { DATA_SOURCE, trashRetentionDays } from "./store/types";
import type {
  Agenda,
  HealthResponse,
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
  TaskStatus,
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
  const body: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
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

// ── Settings ─────────────────────────────────────────────────────────────

export async function getCurrentUsersApi(): Promise<string[]> {
  if (IS_LOCAL) return local(() => engine.getCurrentUsers());
  return [];
}

export async function getAssigneesApi(): Promise<string[]> {
  if (IS_LOCAL) return local(() => engine.getAssignees());
  return []; // Tương lai: gọi API lấy ds assignees từ Postgres nếu chạy thật
}

export async function setCurrentUsersApi(names: string[]): Promise<void> {
  if (IS_LOCAL) return local(() => { engine.setCurrentUsers(names); return undefined as any; });
}

// ── Đọc ────────────────────────────────────────────────────────────────

export function getAgenda(referenceDate?: string): Promise<Agenda> {
  if (IS_LOCAL) return local(() => engine.getAgenda());
  const query = referenceDate ? `?reference_date=${encodeURIComponent(referenceDate)}` : "";
  return coreFetch<Agenda>(`/api/v1/tasks/agenda${query}`);
}

export function getStats(): Promise<Stats> {
  if (IS_LOCAL) return local(() => engine.getStats());
  return coreFetch<Stats>("/api/v1/tasks/stats");
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
  forCurrentUser?: boolean;
}

export function listTasks(options: ListTasksOptions = {}): Promise<Paged<Task>> {
  if (IS_LOCAL) return local(() => engine.listTasks(options));

  const params = new URLSearchParams();
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
  forCurrentUser?: boolean;
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
  forCurrentUser?: boolean;
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
  return []; // Not implemented for core API yet
}
export async function addSyncUrlApi(url: string): Promise<void> {
  if (IS_LOCAL) return local(() => engine.addSyncUrl(url));
}
export async function removeSyncUrlApi(url: string): Promise<void> {
  if (IS_LOCAL) return local(() => engine.removeSyncUrl(url));
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

export async function wipeAllDataApi(options?: { tasks?: boolean, tasks_personal?: boolean, tasks_team?: boolean, tasks_assignee?: string, projects?: boolean, notes?: boolean, sync_urls?: boolean, chrome_history?: boolean }): Promise<void> {
  if (IS_LOCAL) return local(() => engine.wipeAllData(options));
}

// ── AI Logs ───────────────────────────────────────────────────────────────

export async function listAiLogs(): Promise<any[]> {
  if (IS_LOCAL) {
    await ready();
    // Chế độ file: log được ghi từ ngoài process, phải đọc lại từ đĩa
    if (DATA_SOURCE === "file") await reloadAiLogsFromDisk();
    return local(() => engine.snapshotAiLogs().ai_logs ?? []);
  }
  const res = await coreFetch<any>("/api/v1/ai-logs?limit=100");
  return res.items ?? [];
}

export async function createAiLog(input: any): Promise<any> {
  if (IS_LOCAL) {
    // Actually, local ai_logs uses a different flow via JSON file, but for consistency if we wanted to import we just push to the snapshot
    // In our case, we will handle ai-logs directly in transfer.ts via read/write JSON, since it's a separate file.
    // So this might just be a stub for API mode.
  }
  return coreFetch<any>("/api/v1/ai-logs", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

