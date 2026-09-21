import "server-only";

/**
 * ═══════════════════════════════════════════════════════════════════════
 *  Engine dữ liệu trong bộ nhớ, dùng cho chế độ `file` và `memory`.
 *
 *  Đây KHÔNG phải bản thứ hai của logic nghiệp vụ. Nguồn sự thật vẫn là
 *  apps/core. Engine này chỉ giữ đủ hành vi để UI dùng được khi chưa có
 *  backend, và cố tình đơn giản hơn: không validate như Pydantic, không
 *  ghi đủ loại event.
 *
 *  Khi chuyển sang DATA_SOURCE=api, toàn bộ file này không được nạp.
 * ═══════════════════════════════════════════════════════════════════════
 */

import { DISPLAY_TZ } from "../format";
import type {
  Agenda,
  Paged,
  Project,
  ProjectSummary,
  Stats,
  Task,
  TaskDetail,
  TaskEvent,
  TaskPriority,
  TaskStatus,
} from "../types";
import {
  SCHEMA_VERSION,
  trashRetentionDays,
  type DataFile,
  type StoredTask,
} from "./types";

const CLOSED: TaskStatus[] = ["done", "cancelled"];
const DAY_MS = 86_400_000;

function uuid(): string {
  return crypto.randomUUID();
}

function nowIso(): string {
  return new Date().toISOString();
}

function isoDate(offsetDays = 0): string {
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: DISPLAY_TZ,
  }).format(new Date(Date.now() + offsetDays * DAY_MS));
}

function shiftIso(days: number): string {
  return new Date(Date.now() + days * DAY_MS).toISOString();
}

function normalizeTags(tags: readonly string[] | undefined): string[] {
  if (!tags) return [];
  const seen = new Set<string>();
  for (const raw of tags) {
    const tag = raw.trim().toLowerCase().replace(/\s+/g, "-").slice(0, 64);
    if (tag) seen.add(tag);
  }
  return [...seen].slice(0, 20);
}

// ── State ──────────────────────────────────────────────────────────────

/**
 * State phải nằm trên globalThis, KHÔNG được để ở biến mức module.
 *
 * Lý do: Next.js bundle Server Component và Route Handler thành hai module
 * graph riêng, nên cùng file engine.ts có thể tồn tại hai instance với hai
 * bộ biến module khác nhau. Trang thì thấy dữ liệu, còn /api/export lại thấy
 * rỗng. globalThis là thứ duy nhất chắc chắn dùng chung, và nó cũng giúp
 * state sống qua hot reload của dev server.
 */
interface StoreState {
  projects: Project[];
  tasks: StoredTask[];
  minutesLoggedToday: number;
  minutesLoggedDate: string;
  /** Gọi sau mỗi lần ghi, để lớp persistence lưu xuống đĩa. */
  onChange: (() => void) | null;
}

const globalState = globalThis as typeof globalThis & {
  __builderStoreState?: StoreState;
};

function state(): StoreState {
  globalState.__builderStoreState ??= {
    projects: [],
    tasks: [],
    minutesLoggedToday: 0,
    minutesLoggedDate: isoDate(),
    onChange: null,
  };
  return globalState.__builderStoreState;
}

export function setChangeHandler(handler: (() => void) | null): void {
  state().onChange = handler;
}

function touched(): void {
  state().onChange?.();
}

// ── Snapshot / restore, dùng bởi lớp persistence ────────────────────────

export function snapshot(): DataFile {
  const store = state();
  return {
    schema_version: SCHEMA_VERSION,
    exported_at: nowIso(),
    projects: structuredClone(store.projects),
    tasks: structuredClone(store.tasks),
    meta: {
      minutes_logged_today: store.minutesLoggedToday,
      minutes_logged_date: store.minutesLoggedDate,
    },
  };
}

export function restore(data: DataFile): void {
  const store = state();
  store.projects = data.projects ?? [];
  store.tasks = data.tasks ?? [];
  store.minutesLoggedToday = data.meta?.minutes_logged_today ?? 0;
  store.minutesLoggedDate = data.meta?.minutes_logged_date ?? isoDate();

  // Đồng hồ đã sang ngày mới thì số phút của hôm qua không còn ý nghĩa
  if (store.minutesLoggedDate !== isoDate()) {
    store.minutesLoggedToday = 0;
    store.minutesLoggedDate = isoDate();
  }
}

export function isEmpty(): boolean {
  const store = state();
  return store.projects.length === 0 && store.tasks.length === 0;
}

export function replaceAll(data: {
  projects: Project[];
  tasks: StoredTask[];
}): void {
  const store = state();
  store.projects = data.projects;
  store.tasks = data.tasks;
  touched();
}

// ── Dữ liệu mẫu ────────────────────────────────────────────────────────

function summary(project: Project | undefined): ProjectSummary | null {
  if (!project) return null;
  return {
    id: project.id,
    key: project.key,
    name: project.name,
    color: project.color,
  };
}

function makeTask(partial: Partial<StoredTask> & { title: string }): StoredTask {
  const created = partial.created_at ?? nowIso();
  return {
    id: partial.id ?? uuid(),
    title: partial.title,
    description: partial.description ?? null,
    status: partial.status ?? "todo",
    priority: partial.priority ?? "medium",
    project_id: partial.project_id ?? null,
    project: partial.project ?? null,
    due_at: partial.due_at ?? null,
    scheduled_for: partial.scheduled_for ?? null,
    estimate_minutes: partial.estimate_minutes ?? null,
    spent_minutes: partial.spent_minutes ?? 0,
    completed_at: partial.completed_at ?? null,
    tags: partial.tags ?? [],
    source: partial.source ?? "manual",
    external_id: partial.external_id ?? null,
    external_url: partial.external_url ?? null,
    created_at: created,
    updated_at: partial.updated_at ?? created,
    deleted_at: partial.deleted_at ?? null,
    events:
      partial.events ??
      [
        {
          id: uuid(),
          event_type: "created",
          actor: "user",
          payload: { title: partial.title },
          created_at: created,
        },
      ],
  };
}

export function seed(): void {
  const homelab: Project = {
    id: uuid(),
    key: "HOMELAB",
    name: "Home lab migration",
    description: "Chuyển stack từ on-premise sang home lab",
    color: "#4f8cff",
    is_archived: false,
    created_at: nowIso(),
    updated_at: nowIso(),
  };
  const ops: Project = {
    id: uuid(),
    key: "OPS",
    name: "Vận hành hằng ngày",
    description: null,
    color: "#3fbf7f",
    is_archived: false,
    created_at: nowIso(),
    updated_at: nowIso(),
  };
  const store = state();
  store.projects = [homelab, ops];

  store.tasks = [
    makeTask({
      title: "Cài Docker Engine trên máy Ubuntu",
      description: "Dùng Docker Engine chứ không cần Docker Desktop.",
      status: "in_progress",
      priority: "urgent",
      project_id: homelab.id,
      project: summary(homelab),
      scheduled_for: isoDate(),
      estimate_minutes: 45,
      spent_minutes: 20,
      tags: ["setup", "docker"],
    }),
    makeTask({
      title: "Sinh initial migration bằng Alembic",
      description: "migrations/versions còn trống, phải autogenerate từ model.",
      status: "todo",
      priority: "high",
      project_id: homelab.id,
      project: summary(homelab),
      due_at: shiftIso(-1),
      estimate_minutes: 30,
      tags: ["database"],
    }),
    makeTask({
      title: "Chạy make smoke cho tới khi pass sạch",
      status: "todo",
      priority: "high",
      project_id: homelab.id,
      project: summary(homelab),
      scheduled_for: isoDate(),
      estimate_minutes: 60,
      tags: ["kiem-tra"],
    }),
    makeTask({
      title: "Chốt Jira Cloud hay Data Center",
      description: "Auth và endpoint khác nhau hoàn toàn, chặn Phase 2.",
      status: "blocked",
      priority: "high",
      project_id: ops.id,
      project: summary(ops),
      due_at: shiftIso(3),
      tags: ["phase-2"],
    }),
    makeTask({
      title: "Dựng Prometheus và Grafana, xác nhận scrape được api",
      status: "todo",
      priority: "medium",
      project_id: homelab.id,
      project: summary(homelab),
      due_at: shiftIso(5),
      estimate_minutes: 90,
      tags: ["monitoring"],
    }),
    makeTask({
      title: "Đọc lại thiết kế workflow engine",
      status: "backlog",
      priority: "low",
      project_id: ops.id,
      project: summary(ops),
      tags: ["thiet-ke"],
    }),
    makeTask({
      title: "Viết Makefile gói lệnh vận hành",
      status: "done",
      priority: "high",
      project_id: homelab.id,
      project: summary(homelab),
      scheduled_for: isoDate(-1),
      completed_at: shiftIso(-1),
      created_at: shiftIso(-2),
      estimate_minutes: 60,
      spent_minutes: 75,
      tags: ["dx"],
    }),
  ];

  store.minutesLoggedToday = 20;
  store.minutesLoggedDate = isoDate();
  touched();
}

// ── Đọc ────────────────────────────────────────────────────────────────

function daysUntilPurge(deletedAt: string | null): number | null {
  if (!deletedAt) return null;
  const expiresAt =
    new Date(deletedAt).getTime() + trashRetentionDays() * DAY_MS;
  const remaining = expiresAt - Date.now();
  if (remaining <= 0) return 0;
  // Làm tròn lên để không hiện "0 ngày" cho thứ chưa thực sự hết hạn
  return Math.max(1, Math.ceil(remaining / DAY_MS));
}

function toTask(task: StoredTask): Task {
  const isClosed = CLOSED.includes(task.status);
  const { events: _drop, ...rest } = task;
  return {
    ...rest,
    is_overdue:
      !isClosed && task.due_at !== null && new Date(task.due_at) < new Date(),
    days_until_purge: daysUntilPurge(task.deleted_at),
  };
}

/** Task chưa bị xoá mềm. Phải dùng ở mọi truy vấn nghiệp vụ. */
function isAlive(task: StoredTask): boolean {
  return task.deleted_at === null;
}

function aliveTasks(): StoredTask[] {
  return state().tasks.filter(isAlive);
}

function toDetail(task: StoredTask): TaskDetail {
  return { ...toTask(task), events: task.events };
}

function isOpen(task: StoredTask): boolean {
  return !CLOSED.includes(task.status);
}

function find(id: string, includeDeleted = false): StoredTask {
  const task = state().tasks.find((t) => t.id === id);
  if (!task || (task.deleted_at !== null && !includeDeleted)) {
    throw new Error(`Không tìm thấy task ${id}`);
  }
  return task;
}

export function getAgenda(): Agenda {
  const today = isoDate();
  const now = Date.now();
  const tasks = aliveTasks();

  const inProgress = tasks.filter((t) => t.status === "in_progress");
  const skip = new Set(inProgress.map((t) => t.id));

  const overdue = tasks.filter(
    (t) =>
      isOpen(t) &&
      !skip.has(t.id) &&
      t.due_at !== null &&
      new Date(t.due_at).getTime() < now,
  );

  const scheduledToday = tasks.filter(
    (t) => isOpen(t) && !skip.has(t.id) && t.scheduled_for === today,
  );

  const dueSoon = tasks.filter(
    (t) =>
      isOpen(t) &&
      t.scheduled_for === null &&
      t.due_at !== null &&
      new Date(t.due_at).getTime() >= now &&
      new Date(t.due_at).getTime() < now + 7 * DAY_MS,
  );

  const completedToday = tasks.filter(
    (t) =>
      t.status === "done" &&
      t.completed_at !== null &&
      localDay(t.completed_at) === today,
  );

  return {
    reference_date: today,
    overdue: overdue.map(toTask),
    scheduled_today: scheduledToday.map(toTask),
    in_progress: inProgress.map(toTask),
    due_soon: dueSoon.map(toTask),
    completed_today: completedToday.map(toTask),
    totals: {
      overdue: overdue.length,
      scheduled_today: scheduledToday.length,
      in_progress: inProgress.length,
      due_soon: dueSoon.length,
      completed_today: completedToday.length,
    },
  };
}

/** Quy đổi timestamp UTC sang ngày địa phương, dạng YYYY-MM-DD. */
function localDay(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: DISPLAY_TZ,
  }).format(new Date(iso));
}

export function getStats(): Stats {
  const today = isoDate();
  const now = Date.now();
  const windowStart = Date.now() - 6 * DAY_MS;
  const store = state();
  const tasks = aliveTasks();

  const byStatus: Record<string, number> = {};
  for (const task of tasks) {
    byStatus[task.status] = (byStatus[task.status] ?? 0) + 1;
  }

  const byPriority: Record<string, number> = {};
  for (const task of tasks.filter(isOpen)) {
    byPriority[task.priority] = (byPriority[task.priority] ?? 0) + 1;
  }

  const completedLast7: Record<string, number> = {};
  for (const task of tasks) {
    if (task.status !== "done" || !task.completed_at) continue;
    if (new Date(task.completed_at).getTime() < windowStart) continue;
    const day = localDay(task.completed_at);
    completedLast7[day] = (completedLast7[day] ?? 0) + 1;
  }

  if (store.minutesLoggedDate !== today) {
    store.minutesLoggedToday = 0;
    store.minutesLoggedDate = today;
  }

  return {
    reference_date: today,
    by_status: byStatus,
    by_priority: byPriority,
    completed_last_7_days: completedLast7,
    open_total: tasks.filter(isOpen).length,
    overdue_total: tasks.filter(
      (t) => isOpen(t) && t.due_at !== null && new Date(t.due_at).getTime() < now,
    ).length,
    minutes_logged_today: store.minutesLoggedToday,
    trash_total: store.tasks.filter((t) => t.deleted_at !== null).length,
  };
}

export interface ListOptions {
  status?: TaskStatus[];
  projectId?: string;
  query?: string;
  includeClosed?: boolean;
  limit?: number;
  offset?: number;
}

export function listTasks(options: ListOptions = {}): Paged<Task> {
  let result = aliveTasks();

  if (options.status && options.status.length > 0) {
    result = result.filter((t) => options.status!.includes(t.status));
  } else if (!options.includeClosed) {
    result = result.filter(isOpen);
  }

  if (options.projectId) {
    result = result.filter((t) => t.project_id === options.projectId);
  }

  if (options.query) {
    const needle = options.query.trim().toLowerCase();
    result = result.filter(
      (t) =>
        t.title.toLowerCase().includes(needle) ||
        (t.description ?? "").toLowerCase().includes(needle),
    );
  }

  result.sort((a, b) => b.created_at.localeCompare(a.created_at));

  const limit = options.limit ?? 100;
  const offset = options.offset ?? 0;

  return {
    items: result.slice(offset, offset + limit).map(toTask),
    total: result.length,
    limit,
    offset,
  };
}

export function getTask(id: string): TaskDetail {
  return toDetail(find(id));
}

export function listProjects(includeArchived = false): Project[] {
  const all = state().projects;
  return includeArchived ? [...all] : all.filter((p) => !p.is_archived);
}

export function allTasks(): StoredTask[] {
  return [...state().tasks];
}

export function allProjects(): Project[] {
  return [...state().projects];
}

// ── Ghi ────────────────────────────────────────────────────────────────

function addEvent(
  task: StoredTask,
  eventType: TaskEvent["event_type"],
  payload: Record<string, unknown> | null,
): void {
  task.events.unshift({
    id: uuid(),
    event_type: eventType,
    actor: "user",
    payload,
    created_at: nowIso(),
  });
  task.updated_at = nowIso();
}

export interface CreateInput {
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

export function createTask(input: CreateInput): TaskDetail {
  const store = state();
  const title = input.title.trim();
  if (!title) throw new Error("title không được rỗng");

  if (input.project_id && !store.projects.some((p) => p.id === input.project_id)) {
    throw new Error(`project_id ${input.project_id} không tồn tại`);
  }

  const status = input.status ?? "todo";
  const task = makeTask({
    title,
    description: input.description ?? null,
    status,
    priority: (input.priority as TaskPriority | undefined) ?? "medium",
    project_id: input.project_id ?? null,
    project: summary(store.projects.find((p) => p.id === input.project_id)),
    due_at: input.due_at ?? null,
    scheduled_for: input.scheduled_for ?? null,
    estimate_minutes: input.estimate_minutes ?? null,
    tags: normalizeTags(input.tags),
    completed_at: status === "done" ? nowIso() : null,
  });

  store.tasks.unshift(task);
  touched();
  return toDetail(task);
}

export function patchTask(id: string, input: Record<string, unknown>): TaskDetail {
  const task = find(id);
  const oldStatus = task.status;

  if ("title" in input && typeof input.title === "string") {
    const title = input.title.trim();
    if (!title) throw new Error("title không được rỗng");
    task.title = title;
  }
  if ("description" in input) {
    task.description = (input.description as string | null) ?? null;
  }
  if ("priority" in input) task.priority = input.priority as TaskPriority;
  if ("due_at" in input) task.due_at = (input.due_at as string | null) ?? null;
  if ("scheduled_for" in input) {
    task.scheduled_for = (input.scheduled_for as string | null) ?? null;
  }
  if ("estimate_minutes" in input) {
    task.estimate_minutes = (input.estimate_minutes as number | null) ?? null;
  }
  if ("tags" in input) {
    task.tags = normalizeTags(input.tags as string[] | undefined);
  }
  if ("project_id" in input) {
    const projectId = (input.project_id as string | null) ?? null;
    const known = state().projects;
    if (projectId && !known.some((p) => p.id === projectId)) {
      throw new Error(`project_id ${projectId} không tồn tại`);
    }
    task.project_id = projectId;
    task.project = summary(known.find((p) => p.id === projectId));
  }

  if ("status" in input) {
    const newStatus = input.status as TaskStatus;
    task.status = newStatus;

    if (newStatus !== oldStatus) {
      if (newStatus === "done") {
        task.completed_at = nowIso();
        addEvent(task, "completed", { from: oldStatus });
      } else if (CLOSED.includes(oldStatus)) {
        task.completed_at = null;
        addEvent(task, "reopened", { from: oldStatus, to: newStatus });
      } else {
        addEvent(task, "status_changed", { from: oldStatus, to: newStatus });
      }
    }
  } else {
    addEvent(task, "updated", { changes: input });
  }

  touched();
  return toDetail(task);
}

/**
 * Xoá mềm: đưa vào thùng rác, giữ lại theo TRASH_RETENTION_DAYS.
 * Retention bằng 0 thì xoá thẳng.
 */
export function deleteTask(id: string): void {
  const task = find(id);

  if (trashRetentionDays() === 0) {
    purgeTaskNow(id);
    return;
  }

  task.deleted_at = nowIso();
  addEvent(task, "deleted", { retention_days: trashRetentionDays() });
  touched();
}

export function restoreTask(id: string): TaskDetail {
  const task = find(id, true);
  if (task.deleted_at === null) {
    throw new Error(`Task ${id} không nằm trong thùng rác`);
  }

  // Giữ đúng ràng buộc unique (source, external_id) như bên backend
  if (task.external_id !== null) {
    const clash = state().tasks.find(
      (other) =>
        other.id !== task.id &&
        other.deleted_at === null &&
        other.source === task.source &&
        other.external_id === task.external_id,
    );
    if (clash) {
      throw new Error(
        `Đã có task khác từ nguồn ${task.source} với external_id ` +
        `'${task.external_id}'. Xoá task đó trước khi phục hồi.`,
      );
    }
  }

  const deletedAt = task.deleted_at;
  task.deleted_at = null;
  addEvent(task, "restored", { deleted_at: deletedAt });
  touched();
  return toDetail(task);
}

/** Xoá vĩnh viễn một task đang ở trong thùng rác. */
export function purgeTask(id: string): void {
  const task = find(id, true);
  if (task.deleted_at === null) {
    throw new Error(`Task ${id} chưa ở trong thùng rác`);
  }
  purgeTaskNow(id);
}

/** Xoá vĩnh viễn ngay, bỏ qua thùng rác. */
export function purgeTaskNow(id: string): void {
  const tasks = state().tasks;
  const index = tasks.findIndex((t) => t.id === id);
  if (index === -1) throw new Error(`Không tìm thấy task ${id}`);
  tasks.splice(index, 1);
  touched();
}

export function listTrash(limit = 100, offset = 0): {
  items: Task[];
  total: number;
} {
  const deleted = state()
    .tasks.filter((t) => t.deleted_at !== null)
    .sort((a, b) => (b.deleted_at ?? "").localeCompare(a.deleted_at ?? ""));

  return {
    items: deleted.slice(offset, offset + limit).map(toTask),
    total: deleted.length,
  };
}

/** Xoá vĩnh viễn task đã quá thời hạn giữ. Trả về số bản ghi đã xoá. */
export function purgeExpired(): number {
  const retention = trashRetentionDays();
  if (retention === 0) return 0;

  const store = state();
  const cutoff = Date.now() - retention * DAY_MS;
  const before = store.tasks.length;

  store.tasks = store.tasks.filter(
    (task) =>
      task.deleted_at === null || new Date(task.deleted_at).getTime() >= cutoff,
  );

  const removed = before - store.tasks.length;
  if (removed > 0) touched();
  return removed;
}

export function emptyTrash(): number {
  const store = state();
  const before = store.tasks.length;
  store.tasks = store.tasks.filter((task) => task.deleted_at === null);
  const removed = before - store.tasks.length;
  if (removed > 0) touched();
  return removed;
}

export function logTime(
  id: string,
  minutes: number,
  note?: string | null,
): TaskDetail {
  const task = find(id);
  const store = state();
  const today = isoDate();
  if (store.minutesLoggedDate !== today) {
    store.minutesLoggedToday = 0;
    store.minutesLoggedDate = today;
  }

  task.spent_minutes += minutes;
  store.minutesLoggedToday += minutes;
  addEvent(task, "time_logged", {
    minutes,
    note: note ?? null,
    total: task.spent_minutes,
  });
  touched();
  return toDetail(task);
}

export function createProject(input: {
  key: string;
  name: string;
  color?: string | null;
}): Project {
  const store = state();
  const key = input.key.trim().toUpperCase();
  if (!key) throw new Error("key không được rỗng");
  if (store.projects.some((p) => p.key === key)) {
    throw new Error(`Project key '${key}' đã tồn tại`);
  }

  const project: Project = {
    id: uuid(),
    key,
    name: input.name.trim(),
    description: null,
    color: input.color ?? null,
    is_archived: false,
    created_at: nowIso(),
    updated_at: nowIso(),
  };
  store.projects.push(project);
  touched();
  return project;
}

export { makeTask, normalizeTags, summary, uuid, nowIso };
