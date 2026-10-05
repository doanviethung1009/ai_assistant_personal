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
  Note,
  NoteKind,
  NoteSortField,
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
  type StoredNote,
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
  sync_urls?: string[];
  projects: Project[];
  tasks: StoredTask[];
  notes: StoredNote[];
  ai_logs: any[];
  minutesLoggedToday: number;
  minutesLoggedDate: string;
  currentUsers: string[];
  /** Gọi sau mỗi lần ghi, để lớp persistence lưu xuống đĩa. */
  onChange: (() => void) | null;
  onAiLogsChange: (() => void) | null;
}

const globalState = globalThis as typeof globalThis & {
  __builderStoreState?: StoreState;
};

export function state(): StoreState {
  globalState.__builderStoreState ??= {
    projects: [],
    tasks: [],
    notes: [],
    ai_logs: [],
    minutesLoggedToday: 0,
    minutesLoggedDate: isoDate(),
    currentUsers: ["Đoàn Việt Hưng"], // Giá trị mặc định
    onChange: null,
    onAiLogsChange: null,
  };
  return globalState.__builderStoreState;
}

export function setChangeHandler(handler: (() => void) | null): void {
  state().onChange = handler;
}

export function setAiLogsChangeHandler(handler: (() => void) | null): void {
  state().onAiLogsChange = handler;
}

export function touched(): void {
  state().onChange?.();
}

export function touchedAiLogs(): void {
  state().onAiLogsChange?.();
}

export function getCurrentUsers(): string[] {
  return state().currentUsers || ["Đoàn Việt Hưng"];
}

export function setCurrentUsers(names: string[]): void {
  const store = state();
  store.currentUsers = names.map(n => n.trim()).filter(Boolean);
  touched();
}

export function getAssignees(): string[] {
  const assignees = state().tasks.map(t => t.assignee).filter(Boolean) as string[];
  return Array.from(new Set(assignees)).sort();
}

// ── Snapshot / restore, dùng bởi lớp persistence ────────────────────────

export function snapshot(): DataFile {
  const store = state();
  return {
    schema_version: SCHEMA_VERSION,
    exported_at: nowIso(),
    projects: structuredClone(store.projects),
    tasks: structuredClone(store.tasks),
    notes: structuredClone(store.notes),
    meta: {
      minutes_logged_today: store.minutesLoggedToday,
      minutes_logged_date: store.minutesLoggedDate,
      current_users: store.currentUsers,
    },
  };
}

export function snapshotAiLogs(): { schema_version: number; exported_at: string; ai_logs: any[] } {
  const store = state();
  return {
    schema_version: 1, // Phiên bản độc lập cho ai_logs.json
    exported_at: nowIso(),
    ai_logs: structuredClone(store.ai_logs),
  };
}

export function restore(data: DataFile): void {
  const store = state();
  const projMap = new Map<string, Project>();
  store.projects = (data.projects ?? []).map(p => {
    if (!p.color) {
      p.color = stringToColor(p.key);
    }
    projMap.set(p.id, p);
    return p;
  });
  store.tasks = (data.tasks ?? []).map(t => {
    if (t.project_id && t.project && !t.project.color) {
       const p = projMap.get(t.project_id);
       if (p) {
          t.project.color = p.color;
       }
    }
    return t;
  });
  // `?? []` là lớp bảo vệ thứ hai sau bước migrate v2→v3. File v2 đọc trực
  // tiếp qua restore() mà không qua migrate sẽ không làm sập engine.
  store.notes = data.notes ?? [];
  
  // Tương thích ngược: Nếu file cũ v4 có chứa ai_logs (trước khi tách), ta nạp nó vào RAM tạm.
  if ("ai_logs" in data && Array.isArray((data as any).ai_logs)) {
    store.ai_logs = (data as any).ai_logs;
  }
  
  store.minutesLoggedToday = data.meta?.minutes_logged_today ?? 0;
  store.minutesLoggedDate = data.meta?.minutes_logged_date ?? isoDate();
  
  if (data.meta?.current_users && Array.isArray(data.meta.current_users)) {
    store.currentUsers = data.meta.current_users;
  } else if ((data.meta as any)?.current_user) {
    store.currentUsers = [(data.meta as any).current_user]; // migrate từ bản cũ
  } else {
    store.currentUsers = ["Đoàn Việt Hưng"];
  }

  // Đồng hồ đã sang ngày mới thì số phút của hôm qua không còn ý nghĩa
  if (store.minutesLoggedDate !== isoDate()) {
    store.minutesLoggedToday = 0;
    store.minutesLoggedDate = isoDate();
  }
}

export function restoreAiLogs(data: { ai_logs?: any[] }): void {
  const store = state();
  store.ai_logs = data.ai_logs ?? [];
}

export function isEmpty(): boolean {
  const store = state();
  return (
    store.projects.length === 0 &&
    store.tasks.length === 0 &&
    store.notes.length === 0
  );
}

export function replaceAll(data: {
  projects: Project[];
  tasks: StoredTask[];
  /** Không truyền thì giữ nguyên sổ tay hiện tại. */
  notes?: StoredNote[];
  sync_urls?: string[];
}): void {
  const store = state();
  store.projects = data.projects;
  store.tasks = data.tasks;
  if (data.notes !== undefined) store.notes = data.notes;
  if (data.sync_urls !== undefined) store.sync_urls = data.sync_urls;
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
  const created = (partial as any).created_at ?? nowIso();
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
    assignee: partial.assignee ?? null,
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

function makeNote(partial: Partial<StoredNote> & { title: string; content: string }): StoredNote {
  const created = (partial as any).created_at ?? nowIso();
  return {
    id: partial.id ?? uuid(),
    title: partial.title,
    kind: partial.kind ?? "command",
    content: partial.content,
    description: partial.description ?? null,
    context: partial.context ?? null,
    project_id: partial.project_id ?? null,
    project: partial.project ?? null,
    tags: partial.tags ?? [],
    is_pinned: partial.is_pinned ?? false,
    is_dangerous: partial.is_dangerous ?? false,
    use_count: partial.use_count ?? 0,
    last_used_at: partial.last_used_at ?? null,
    source: partial.source ?? "manual",
    external_id: partial.external_id ?? null,
    created_at: created,
    updated_at: partial.updated_at ?? created,
    deleted_at: partial.deleted_at ?? null,
    assignee: partial.assignee ?? null,
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

  store.notes = [
    makeNote({
      title: "Dựng stack và chạy migration",
      kind: "command",
      content: "make bootstrap",
      description:
        "Sinh .env nếu chưa có, build image, dựng profile core, rồi chạy alembic upgrade head.",
      context: "gốc repo",
      project_id: homelab.id,
      project: summary(homelab),
      tags: ["docker", "setup"],
      is_pinned: true,
      use_count: 4,
      last_used_at: shiftIso(-1),
    }),
    makeNote({
      title: "Xem task quá hạn chưa đóng",
      kind: "sql",
      content: [
        "SELECT title, due_at, priority",
        "FROM tasks",
        "WHERE deleted_at IS NULL",
        "  AND status NOT IN ('done', 'cancelled')",
        "  AND due_at < now()",
        "ORDER BY due_at;",
      ].join("\n"),
      description:
        "Nhớ điều kiện deleted_at IS NULL, nếu không sẽ đếm cả task trong thùng rác.",
      context: "DB builder_ai",
      project_id: ops.id,
      project: summary(ops),
      tags: ["database", "bao-cao"],
      is_pinned: true,
      use_count: 2,
    }),
    makeNote({
      title: "Backup database ra file gzip",
      kind: "command",
      content:
        "docker compose exec -T postgres pg_dump -U builder -d builder_ai | gzip > backups/builder_ai_$(date +%Y%m%d_%H%M%S).sql.gz",
      description:
        "Chạy trước mỗi lần migrate trên prod. Makefile đã gói lại thành make backup.",
      context: "máy prod",
      tags: ["backup", "postgres"],
      use_count: 1,
    }),
    makeNote({
      title: "Xoá sạch volume rồi dựng lại",
      kind: "command",
      content: "docker compose --profile llm --profile monitoring down -v",
      description:
        "Cờ -v xoá luôn named volume, nghĩa là mất toàn bộ dữ liệu Postgres, Redis và Grafana.",
      context: "chỉ dùng ở máy dev",
      tags: ["docker", "reset"],
      is_dangerous: true,
    }),
    makeNote({
      title: "Vì sao không dùng create_all",
      kind: "text",
      content: [
        "Schema chỉ đổi qua Alembic. create_all lúc runtime sẽ:",
        "- tạo bảng không khớp với lịch sử migration",
        "- không sinh partial index và CHECK constraint",
        "- làm hai môi trường lệch schema mà không ai biết",
      ].join("\n"),
      description: "Ghi lại để lần sau không phải tranh luận lại.",
      tags: ["thiet-ke", "database"],
    }),
    makeNote({
      title: "Biến môi trường cho UAT",
      kind: "config",
      content: [
        "COMPOSE_PROJECT_NAME=builder-uat",
        "ENVIRONMENT=staging",
        "WEB_PORT=3100",
        "API_PORT=8100",
        "POSTGRES_PORT=5433",
        "LOG_LEVEL=DEBUG",
      ].join("\n"),
      description:
        "ENVIRONMENT phải là staging, không phải uat: config.py validate bằng Literal.",
      context: "/srv/builder-ai/uat/.env",
      tags: ["deploy", "uat"],
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
  const store = state();
  const users = store.currentUsers || ["Đoàn Việt Hưng"];
  const isMyTask = (t: any) => {
    if (t.assignee) return users.length > 0 && users.includes(t.assignee);
    return t.source !== 'jira'; // Task Jira không có người nhận thì không phải của mình
  };
  const tasks = aliveTasks().filter(isMyTask);

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
  const users = store.currentUsers || ["Đoàn Việt Hưng"];
  const isMyTask = (t: any) => {
    if (t.assignee) return users.length > 0 && users.includes(t.assignee);
    return t.source !== 'jira';
  };
  const tasks = aliveTasks().filter(isMyTask);

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
  assignee?: string | null;
  forCurrentUser?: boolean;
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
  
  if (options.forCurrentUser) {
    const store = state();
    const users = store.currentUsers || ["Đoàn Việt Hưng"];
    const isMyTask = (t: any) => {
      if (t.assignee) return users.length > 0 && users.includes(t.assignee);
      return t.source !== 'jira';
    };
    result = result.filter(isMyTask);
  } else if (options.assignee) {
    result = result.filter((t) => t.assignee === options.assignee);
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
  if ("assignee" in input) task.assignee = (input.assignee as string | null) ?? null;
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

function stringToColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 70%, 65%)`;
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
    color: input.color || stringToColor(key),
    is_archived: false,
    created_at: nowIso(),
    updated_at: nowIso(),
  };
  store.projects.push(project);
  touched();
  return project;
}

// ═══════════════════════════════════════════════════════════════════════
//  Sổ tay
//
//  `content` chỉ được lưu và trả về như chuỗi. Không có chỗ nào trong file
//  này eval, exec, hay nội suy nó vào một câu lệnh.
// ═══════════════════════════════════════════════════════════════════════

function toNote(note: StoredNote): Note {
  return { ...note, days_until_purge: daysUntilPurge(note.deleted_at) };
}

/** Note chưa bị xoá mềm. Phải dùng ở mọi truy vấn nghiệp vụ. */
function isNoteAlive(note: StoredNote): boolean {
  return note.deleted_at === null;
}

function aliveNotes(): StoredNote[] {
  return state().notes.filter(isNoteAlive);
}

function findNote(id: string, includeDeleted = false): StoredNote {
  const note = state().notes.find((n) => n.id === id);
  if (!note || (note.deleted_at !== null && !includeDeleted)) {
    throw new Error(`Không tìm thấy note ${id}`);
  }
  return note;
}

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

export function getSyncUrls(): string[] { return state().sync_urls || []; }
export function addSyncUrl(url: string) { const s = state(); if (!s.sync_urls) s.sync_urls = []; if (!s.sync_urls.includes(url)) s.sync_urls.push(url); touched(); }
export function removeSyncUrl(url: string) { const s = state(); if (s.sync_urls) s.sync_urls = s.sync_urls.filter((u: string) => u !== url); touched(); }
export function listNotes(options: ListNotesOptions = {}): Paged<Note> {
  let result = aliveNotes();

  if (options.kind && options.kind.length > 0) {
    result = result.filter((n) => options.kind!.includes(n.kind));
  }
  if (options.projectId) {
    result = result.filter((n) => n.project_id === options.projectId);
  }
  if (options.tags && options.tags.length > 0) {
    // Khớp mọi tag được yêu cầu, giống toán tử @> bên Postgres
    result = result.filter((n) =>
      options.tags!.every((tag) => n.tags.includes(tag)),
    );
  }
  if (options.pinnedOnly) {
    result = result.filter((n) => n.is_pinned);
  }
  if (options.query) {
    // Tìm cả trong content, vì thường chỉ nhớ một đoạn trong câu lệnh chứ
    // không nhớ tiêu đề. Khớp với hành vi của note_service bên backend.
    const needle = options.query.trim().toLowerCase();
    result = result.filter(
      (n) =>
        n.title.toLowerCase().includes(needle) ||
        n.content.toLowerCase().includes(needle) ||
        (n.description ?? "").toLowerCase().includes(needle) ||
        (n.context ?? "").toLowerCase().includes(needle),
    );
  }

  const sortBy = options.sortBy ?? "updated_at";
  const desc = options.sortDesc ?? true;

  result.sort((a, b) => {
    // Note đã ghim luôn đứng trước, bất kể sắp xếp theo gì
    if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;

    const direction = desc ? -1 : 1;

    if (sortBy === "use_count") {
      if (a.use_count !== b.use_count) {
        return (a.use_count - b.use_count) * direction;
      }
    } else if (sortBy === "title") {
      const compared = a.title.localeCompare(b.title, "vi");
      if (compared !== 0) return compared * direction;
    } else {
      // Các field còn lại đều là ISO timestamp, so sánh chuỗi là đủ.
      // last_used_at có thể null: đẩy xuống cuối như nulls_last bên SQL.
      const left = a[sortBy] ?? "";
      const right = b[sortBy] ?? "";
      if (left !== right) {
        if (left === "") return 1;
        if (right === "") return -1;
        return left.localeCompare(right) * direction;
      }
    }

    return b.created_at.localeCompare(a.created_at);
  });

  const limit = options.limit ?? 100;
  const offset = options.offset ?? 0;

  return {
    items: result.slice(offset, offset + limit).map(toNote),
    total: result.length,
    limit,
    offset,
  };
}

export function getNote(id: string): Note {
  return toNote(findNote(id));
}

export function allNotes(): StoredNote[] {
  return [...state().notes];
}

export function countNotesByKind(): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const note of aliveNotes()) {
    counts[note.kind] = (counts[note.kind] ?? 0) + 1;
  }
  return counts;
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

export function createNote(input: CreateNoteInput): Note {
  const store = state();
  const title = input.title.trim();
  if (!title) throw new Error("title không được rỗng");

  const content = input.content.trim();
  if (!content) throw new Error("content không được rỗng");

  if (input.project_id && !store.projects.some((p) => p.id === input.project_id)) {
    throw new Error(`project_id ${input.project_id} không tồn tại`);
  }

  const note = makeNote({
    title,
    content,
    kind: input.kind ?? "command",
    description: input.description ?? null,
    context: input.context ?? null,
    project_id: input.project_id ?? null,
    project: summary(store.projects.find((p) => p.id === input.project_id)),
    tags: normalizeTags(input.tags),
    is_pinned: input.is_pinned ?? false,
    is_dangerous: input.is_dangerous ?? false,
  });

  store.notes.unshift(note);
  touched();
  return toNote(note);
}

export function patchNote(id: string, input: Record<string, unknown>): Note {
  const note = findNote(id);

  if ("title" in input && typeof input.title === "string") {
    const title = input.title.trim();
    if (!title) throw new Error("title không được rỗng");
    note.title = title;
  }
  if ("content" in input && typeof input.content === "string") {
    // Chỉ trim hai đầu. Thụt lề bên trong là phần nội dung, nhất là với
    // YAML và SQL nhiều dòng.
    const content = input.content.trim();
    if (!content) throw new Error("content không được rỗng");
    note.content = content;
  }
  if ("kind" in input) note.kind = input.kind as NoteKind;
  if ("description" in input) {
    note.description = (input.description as string | null) ?? null;
  }
  if ("context" in input) {
    note.context = (input.context as string | null) ?? null;
  }
  if ("tags" in input) {
    note.tags = normalizeTags(input.tags as string[] | undefined);
  }
  if ("is_pinned" in input) note.is_pinned = Boolean(input.is_pinned);
  if ("is_dangerous" in input) note.is_dangerous = Boolean(input.is_dangerous);
  if ("project_id" in input) {
    const projectId = (input.project_id as string | null) ?? null;
    const known = state().projects;
    if (projectId && !known.some((p) => p.id === projectId)) {
      throw new Error(`project_id ${projectId} không tồn tại`);
    }
    note.project_id = projectId;
    note.project = summary(known.find((p) => p.id === projectId));
  }

  note.updated_at = nowIso();
  touched();
  return toNote(note);
}

/** Ghi nhận một lần dùng. Web gọi khi người dùng bấm copy. */
export function markNoteUsed(id: string): Note {
  const note = findNote(id);
  note.use_count += 1;
  note.last_used_at = nowIso();
  // Cố tình KHÔNG đổi updated_at: copy không phải là sửa nội dung, và nếu
  // đổi thì mọi lần copy sẽ đẩy note lên đầu danh sách sắp xếp mặc định.
  touched();
  return toNote(note);
}

export function deleteNote(id: string): void {
  const note = findNote(id);

  if (trashRetentionDays() === 0) {
    purgeNoteNow(id);
    return;
  }

  note.deleted_at = nowIso();
  touched();
}

export function restoreNote(id: string): Note {
  const note = findNote(id, true);
  if (note.deleted_at === null) {
    throw new Error(`Note ${id} không nằm trong thùng rác`);
  }

  // Giữ đúng ràng buộc unique (source, external_id) như bên backend
  if (note.external_id !== null) {
    const clash = state().notes.find(
      (other) =>
        other.id !== note.id &&
        other.deleted_at === null &&
        other.source === note.source &&
        other.external_id === note.external_id,
    );
    if (clash) {
      throw new Error(
        `Đã có note khác từ nguồn ${note.source} với external_id ` +
        `'${note.external_id}'. Xoá note đó trước khi phục hồi.`,
      );
    }
  }

  note.deleted_at = null;
  touched();
  return toNote(note);
}

/** Xoá vĩnh viễn một note đang ở trong thùng rác. */
export function purgeNote(id: string): void {
  const note = findNote(id, true);
  if (note.deleted_at === null) {
    throw new Error(`Note ${id} chưa ở trong thùng rác`);
  }
  purgeNoteNow(id);
}

/** Xoá vĩnh viễn ngay, bỏ qua thùng rác. */
export function purgeNoteNow(id: string): void {
  const notes = state().notes;
  const index = notes.findIndex((n) => n.id === id);
  if (index === -1) throw new Error(`Không tìm thấy note ${id}`);
  notes.splice(index, 1);
  touched();
}

export function listNoteTrash(limit = 100, offset = 0): {
  items: Note[];
  total: number;
} {
  const deleted = state()
    .notes.filter((n) => n.deleted_at !== null)
    .sort((a, b) => (b.deleted_at ?? "").localeCompare(a.deleted_at ?? ""));

  return {
    items: deleted.slice(offset, offset + limit).map(toNote),
    total: deleted.length,
  };
}

/** Xoá vĩnh viễn note đã quá thời hạn giữ. Trả về số bản ghi đã xoá. */
export function purgeExpiredNotes(): number {
  const retention = trashRetentionDays();
  if (retention === 0) return 0;

  const store = state();
  const cutoff = Date.now() - retention * DAY_MS;
  const before = store.notes.length;

  store.notes = store.notes.filter(
    (note) =>
      note.deleted_at === null || new Date(note.deleted_at).getTime() >= cutoff,
  );

  const removed = before - store.notes.length;
  if (removed > 0) touched();
  return removed;
}

export function emptyNoteTrash(): number {
  const store = state();
  const before = store.notes.length;
  store.notes = store.notes.filter((note) => note.deleted_at === null);
  const removed = before - store.notes.length;
  if (removed > 0) touched();
  return removed;
}

export { makeNote, makeTask, normalizeTags, summary, uuid, nowIso };

export function patchProject(
  id: string,
  input: {
    key?: string;
    name?: string;
    description?: string | null;
    color?: string | null;
    is_archived?: boolean;
  },
): Project {
  const store = state();
  const idx = store.projects.findIndex((p) => p.id === id);
  if (idx === -1) throw new Error("Không tìm thấy project");

  const project = store.projects[idx]!;
  
  if (input.key !== undefined) {
    const newKey = input.key.trim().toUpperCase();
    if (!newKey) throw new Error("key không được rỗng");
    if (newKey !== project.key && store.projects.some((p) => p.key === newKey)) {
      throw new Error(`Project key '${newKey}' đã tồn tại`);
    }
    project.key = newKey;
  }
  
  if (input.name !== undefined) project.name = input.name.trim();
  if (input.description !== undefined) project.description = input.description;
  if (input.color !== undefined) project.color = input.color;
  if (input.is_archived !== undefined) project.is_archived = input.is_archived;

  project.updated_at = nowIso();
  touched();
  return { ...project };
}

export function deleteProject(id: string): void {
  const store = state();
  const idx = store.projects.findIndex((p) => p.id === id);
  if (idx === -1) throw new Error("Không tìm thấy project");

  // Xoá project
  store.projects.splice(idx, 1);
  
  // Gỡ project_id khỏi tasks và notes
  for (const t of store.tasks) {
    if (t.project_id === id) t.project_id = null;
  }
  for (const n of store.notes) {
    if (n.project_id === id) n.project_id = null;
  }
  
  touched();
}


// ── Tags Management ──────────────────────────────────────────────────────

export interface TagStat {
  name: string;
  taskCount: number;
  noteCount: number;
}

export function getTagsStats(): TagStat[] {
  const store = state();
  const tagMap: Record<string, { t: number; n: number }> = {};
  
  for (const task of aliveTasks()) {
    for (const tag of task.tags) {
      if (!tagMap[tag]) tagMap[tag] = { t: 0, n: 0 };
      tagMap[tag].t++;
    }
  }
  
  for (const note of aliveNotes()) {
    for (const tag of note.tags) {
      if (!tagMap[tag]) tagMap[tag] = { t: 0, n: 0 };
      tagMap[tag].n++;
    }
  }
  
  return Object.entries(tagMap).map(([name, counts]) => ({
    name,
    taskCount: counts.t,
    noteCount: counts.n
  })).sort((a, b) => a.name.localeCompare(b.name));
}

export function renameGlobalTag(oldName: string, newName: string): void {
  const oldT = oldName.trim().toLowerCase();
  const newT = newName.trim().toLowerCase();
  if (!oldT || !newT || oldT === newT) return;
  
  let changed = false;
  
  for (const task of state().tasks) {
    if (task.tags.includes(oldT)) {
      task.tags = [...new Set(task.tags.map(t => t === oldT ? newT : t))];
      task.updated_at = nowIso();
      changed = true;
    }
  }
  
  for (const note of state().notes) {
    if (note.tags.includes(oldT)) {
      note.tags = [...new Set(note.tags.map(t => t === oldT ? newT : t))];
      note.updated_at = nowIso();
      changed = true;
    }
  }
  
  if (changed) touched();
}

export function deleteGlobalTag(name: string): void {
  const target = name.trim().toLowerCase();
  if (!target) return;
  
  let changed = false;
  
  for (const task of state().tasks) {
    if (task.tags.includes(target)) {
      task.tags = task.tags.filter(t => t !== target);
      task.updated_at = nowIso();
      changed = true;
    }
  }
  
  for (const note of state().notes) {
    if (note.tags.includes(target)) {
      note.tags = note.tags.filter(t => t !== target);
      note.updated_at = nowIso();
      changed = true;
    }
  }
  
  if (changed) touched();
}

export function wipeAllData(options?: { tasks?: boolean, tasks_personal?: boolean, tasks_team?: boolean, tasks_assignee?: string, projects?: boolean, notes?: boolean, sync_urls?: boolean, chrome_history?: boolean }): void {
  const store = state();

  try {
    const fs = require('fs');
    const path = require('path');
    const backupDir = path.join(process.cwd(), "../../data/backups");
    if (!fs.existsSync(backupDir)) {
      fs.mkdirSync(backupDir, { recursive: true });
    }
    // Dọn dẹp tất cả các file backup cũ trong thư mục trước
    const files = fs.readdirSync(backupDir);
    for (const file of files) {
      if (file.endsWith('.json')) {
        fs.unlinkSync(path.join(backupDir, file));
      }
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    
    // Backup main database
    const backupFile = path.join(backupDir, `builder-data-backup-${timestamp}.json`);
    fs.writeFileSync(backupFile, JSON.stringify(store, null, 2));
    console.log(`[Backup] Data automatically backed up to ${backupFile}`);

    // Backup chrome history if it exists
    const chromePath = path.join(process.cwd(), "../../data/chrome-history.json");
    if (fs.existsSync(chromePath)) {
      const chromeBackup = path.join(backupDir, `chrome-history-backup-${timestamp}.json`);
      fs.copyFileSync(chromePath, chromeBackup);
      console.log(`[Backup] Chrome history backed up to ${chromeBackup}`);
    }
  } catch (e) {
    console.error("[Backup] Failed to create backup before wiping:", e);
  }

  if (!options || options.projects) store.projects = [];
  if (!options || options.tasks) store.tasks = [];
  if (options && options.tasks_personal) {
    const users = store.currentUsers || ["Đoàn Việt Hưng"];
    const isMyTask = (t: any) => {
      if (t.assignee) return users.length > 0 && users.includes(t.assignee);
      return t.source !== 'jira';
    };
    store.tasks = store.tasks.filter(t => !isMyTask(t));
  }
  if (options && options.tasks_assignee) {
    const names = options.tasks_assignee.split(",").map(s => s.trim().toLowerCase()).filter(Boolean);
    store.tasks = store.tasks.filter(t => !names.includes((t.assignee || "").trim().toLowerCase()));
  }
  if (options && options.tasks_team) {
    const users = store.currentUsers || ["Đoàn Việt Hưng"];
    const isTeamTask = (t: any) => {
      if (t.assignee) return users.length === 0 || !users.includes(t.assignee);
      return t.source === 'jira';
    };
    store.tasks = store.tasks.filter(t => !isTeamTask(t));
  }
  if (!options || options.notes) store.notes = [];
  if (!options || options.sync_urls) store.sync_urls = [];
  
  if (!options || options.chrome_history) {
    const fs = require('fs');
    const path = require('path');
    const outPath = path.join(process.cwd(), "../../data/chrome-history.json");
    if (fs.existsSync(outPath)) {
      fs.unlinkSync(outPath);
    }
  }
  
  touched();
}
