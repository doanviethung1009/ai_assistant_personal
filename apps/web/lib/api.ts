import "server-only";

import * as engine from "./store/engine";
import { ensureLoaded } from "./store/json-file";
import { DATA_SOURCE, trashRetentionDays } from "./store/types";
import type {
  Agenda,
  Note,
  NoteKind,
  NoteSortField,
  NoteTrashResponse,
  Paged,
  Project,
  PurgeResponse,
  Stats,
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

// ── Đọc ────────────────────────────────────────────────────────────────

export function getAgenda(referenceDate?: string): Promise<Agenda> {
  if (IS_LOCAL) return local(() => engine.getAgenda());
  const query = referenceDate ? `?reference_date=${referenceDate}` : "";
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
  return coreFetch<TaskDetail>(`/api/v1/tasks/${id}`);
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
  scheduled_for?: string | null;
  estimate_minutes?: number | null;
  tags?: string[];
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
  return coreFetch<TaskDetail>(`/api/v1/tasks/${id}`, {
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
  return coreFetch<void>(`/api/v1/tasks/${id}${query}`, { method: "DELETE" });
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
  return coreFetch<TaskDetail>(`/api/v1/tasks/${id}/restore`, {
    method: "POST",
  });
}

/** Xoá vĩnh viễn một task đang ở trong thùng rác. */
export function purgeTask(id: string): Promise<void> {
  if (IS_LOCAL) return local(() => engine.purgeTask(id));
  return coreFetch<void>(`/api/v1/tasks/${id}?permanent=true`, {
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
  return coreFetch<TaskDetail>(`/api/v1/tasks/${id}/time`, {
    method: "POST",
    body: JSON.stringify({ minutes, note: note ?? null }),
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
}

export function listNotes(options: ListNotesOptions = {}): Promise<Paged<Note>> {
  if (IS_LOCAL) return local(() => engine.listNotes(options));

  const params = new URLSearchParams();
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
  return coreFetch<Note>(`/api/v1/notes/${id}`);
}

export function getNoteStats(): Promise<Record<string, number>> {
  if (IS_LOCAL) return local(() => engine.countNotesByKind());
  return coreFetch<Record<string, number>>("/api/v1/notes/stats");
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
  return coreFetch<Note>(`/api/v1/notes/${id}`, {
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
  return coreFetch<void>(`/api/v1/notes/${id}${query}`, { method: "DELETE" });
}

/** Ghi nhận một lần dùng, để sắp xếp theo mức độ hay dùng. */
export function markNoteUsed(id: string): Promise<Note> {
  if (IS_LOCAL) return local(() => engine.markNoteUsed(id));
  return coreFetch<Note>(`/api/v1/notes/${id}/use`, { method: "POST" });
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
  return coreFetch<Note>(`/api/v1/notes/${id}/restore`, { method: "POST" });
}

/** Xoá vĩnh viễn một note đang ở trong thùng rác. */
export function purgeNote(id: string): Promise<void> {
  if (IS_LOCAL) return local(() => engine.purgeNote(id));
  return coreFetch<void>(`/api/v1/notes/${id}?permanent=true`, {
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
