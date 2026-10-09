import "server-only";

/**
 * Xuất và nhập CSV theo RFC 4180.
 *
 * CSV là kênh trao đổi, không phải nơi lưu chính. Nó không biểu diễn được
 * mảng và object lồng nhau, nên hai thứ sau bị làm phẳng hoặc bỏ:
 *   - tags     → nối bằng dấu chấm phẩy
 *   - events   → không xuất, và nhập vào sẽ không có nhật ký cũ
 *
 * Cột project dùng `project_key` thay vì `project_id` để bạn sửa được bằng
 * Excel mà không cần tra UUID.
 */

import type {
  NoteKind,
  NoteSource,
  Project,
  TaskPriority,
  TaskSource,
  TaskStatus,
} from "../types";
import { parseScope, scopeOf } from "../task-scope";
import { makeNote, makeTask, normalizeTags, nowIso, summary, uuid } from "./engine";
import type { StoredNote, StoredTask } from "./types";

const BOM = "\uFEFF";

// ── Sinh CSV ───────────────────────────────────────────────────────────

function escapeField(value: string): string {
  // Chỉ bọc ngoặc kép khi cần: có dấu phẩy, ngoặc kép, hoặc xuống dòng
  if (/[",\r\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function buildCsv(columns: readonly string[], rows: string[][]): string {
  const lines = [columns.map(escapeField).join(",")];
  for (const row of rows) {
    lines.push(row.map(escapeField).join(","));
  }
  // BOM để Excel đọc đúng tiếng Việt, CRLF theo đúng RFC 4180
  return BOM + lines.join("\r\n") + "\r\n";
}

// ── Đọc CSV ────────────────────────────────────────────────────────────

/** Parser xử lý được field có ngoặc kép, dấu phẩy và xuống dòng bên trong. */
export function parseCsv(input: string): string[][] {
  const text = input.startsWith(BOM) ? input.slice(1) : input;
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  let index = 0;

  while (index < text.length) {
    const char = text[index]!;

    if (inQuotes) {
      if (char === '"') {
        if (text[index + 1] === '"') {
          field += '"';
          index += 2;
          continue;
        }
        inQuotes = false;
        index += 1;
        continue;
      }
      field += char;
      index += 1;
      continue;
    }

    if (char === '"') {
      inQuotes = true;
      index += 1;
      continue;
    }
    if (char === ",") {
      row.push(field);
      field = "";
      index += 1;
      continue;
    }
    if (char === "\r") {
      // Bỏ qua, xử lý ở \n để CRLF và LF cho kết quả giống nhau
      index += 1;
      continue;
    }
    if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      index += 1;
      continue;
    }

    field += char;
    index += 1;
  }

  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  // Bỏ dòng trống hoàn toàn
  return rows.filter((cells) => cells.some((cell) => cell.trim() !== ""));
}

function toRecords(rows: string[][]): Record<string, string>[] {
  const [header, ...body] = rows;
  if (!header) return [];
  const columns = header.map((name) => name.trim());

  return body.map((cells) => {
    const record: Record<string, string> = {};
    columns.forEach((column, position) => {
      record[column] = (cells[position] ?? "").trim();
    });
    return record;
  });
}

// ── Task ───────────────────────────────────────────────────────────────

export const TASK_COLUMNS = [
  "id",
  "title",
  "description",
  "status",
  "priority",
  "project_key",
  "due_at",
  // true khi hạn là cả ngày (Jira duedate). Vắng khi nhập: suy từ source=jira + 00:00 UTC.
  "due_all_day",
  "scheduled_for",
  "estimate_minutes",
  "spent_minutes",
  "completed_at",
  "tags",
  "source",
  // work | personal. Vắng hoặc rỗng khi nhập nghĩa là suy từ source.
  "scope",
  "external_id",
  "external_url",
  "created_at",
  "updated_at",
  // Khác rỗng nghĩa là task đang ở trong thùng rác. Giữ cột này để backup
  // và phục hồi không làm mất trạng thái đã xoá.
  "deleted_at",
] as const;

export function tasksToCsv(tasks: StoredTask[], projects: Project[]): string {
  const keyById = new Map(projects.map((p) => [p.id, p.key]));

  const rows = tasks.map((task) => [
    task.id,
    task.title,
    task.description ?? "",
    task.status,
    task.priority,
    task.project_id ? (keyById.get(task.project_id) ?? "") : "",
    task.due_at ?? "",
    task.due_all_day ? "true" : "false",
    task.scheduled_for ?? "",
    task.estimate_minutes?.toString() ?? "",
    task.spent_minutes.toString(),
    task.completed_at ?? "",
    task.tags.join(";"),
    task.source,
    scopeOf(task),
    task.external_id ?? "",
    task.external_url ?? "",
    task.created_at,
    task.updated_at,
    task.deleted_at ?? "",
  ]);

  return buildCsv(TASK_COLUMNS, rows);
}

const VALID_STATUS: readonly TaskStatus[] = [
  "backlog",
  "todo",
  "in_progress",
  "blocked",
  "done",
  "cancelled",
];
const VALID_PRIORITY: readonly TaskPriority[] = ["low", "medium", "high", "urgent"];
const VALID_SOURCE: readonly TaskSource[] = [
  "manual",
  "jira",
  "calendar",
  "email",
  "obsidian",
  "github",
  "gitlab",
  "agent",
];

export interface CsvImportResult<T> {
  items: T[];
  /** Dòng bị bỏ qua kèm lý do, số dòng tính theo file gồm cả header. */
  skipped: { line: number; reason: string }[];
}

function optionalInt(raw: string): number | null {
  if (!raw) return null;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function csvToTasks(
  csv: string,
  projects: Project[],
): CsvImportResult<StoredTask> {
  const records = toRecords(parseCsv(csv));
  const byKey = new Map(projects.map((p) => [p.key.toUpperCase(), p]));

  const items: StoredTask[] = [];
  const skipped: { line: number; reason: string }[] = [];

  records.forEach((record, position) => {
    const line = position + 2; // +1 cho header, +1 vì đếm từ 1
    const title = (record.title ?? "").trim();

    if (!title) {
      skipped.push({ line, reason: "thiếu title" });
      return;
    }

    const status = record.status as TaskStatus;
    if (status && !VALID_STATUS.includes(status)) {
      skipped.push({ line, reason: `status không hợp lệ: ${record.status}` });
      return;
    }

    const priority = record.priority as TaskPriority;
    if (priority && !VALID_PRIORITY.includes(priority)) {
      skipped.push({ line, reason: `priority không hợp lệ: ${record.priority}` });
      return;
    }

    const source = record.source as TaskSource;
    if (source && !VALID_SOURCE.includes(source)) {
      skipped.push({ line, reason: `source không hợp lệ: ${record.source}` });
      return;
    }

    // Cột vắng hoặc rỗng -> suy từ source; giá trị lạ bỏ dòng, giống source.
    const rawScope = (record.scope ?? "").trim();
    const parsedScope = parseScope(rawScope);
    if (rawScope && parsedScope === null) {
      skipped.push({ line, reason: `scope không hợp lệ: ${record.scope}` });
      return;
    }

    const projectKey = (record.project_key ?? "").toUpperCase();
    const project = projectKey ? byKey.get(projectKey) : undefined;
    if (projectKey && !project) {
      skipped.push({ line, reason: `không có project key '${projectKey}'` });
      return;
    }

    const resolvedStatus = status || "todo";
    const spent = Number.parseInt(record.spent_minutes ?? "", 10);

    items.push(
      makeTask({
        id: record.id || uuid(),
        title,
        description: record.description || null,
        status: resolvedStatus,
        priority: priority || "medium",
        project_id: project?.id ?? null,
        project: summary(project),
        due_at: record.due_at || null,
        // Cột vắng (CSV cũ) thì suy như migrate v6→v7; có cột thì tin giá trị trong file.
        due_all_day:
          record.due_all_day !== undefined && record.due_all_day !== ""
            ? record.due_all_day.toLowerCase() === "true"
            : (source || "manual") === "jira" && /T00:00:00(\.0+)?Z$/.test(record.due_at ?? ""),
        scheduled_for: record.scheduled_for || null,
        estimate_minutes: optionalInt(record.estimate_minutes ?? ""),
        spent_minutes: Number.isFinite(spent) && spent > 0 ? spent : 0,
        completed_at:
          record.completed_at ||
          (resolvedStatus === "done" ? nowIso() : null),
        tags: normalizeTags((record.tags ?? "").split(";")),
        source: source || "manual",
        ...(parsedScope ? { scope: parsedScope } : {}),
        external_id: record.external_id || null,
        external_url: record.external_url || null,
        created_at: record.created_at || nowIso(),
        updated_at: record.updated_at || nowIso(),
        deleted_at: record.deleted_at || null,
      }),
    );
  });

  return { items, skipped };
}

// ── Project ────────────────────────────────────────────────────────────

export const PROJECT_COLUMNS = [
  "id",
  "key",
  "name",
  "description",
  "color",
  "is_archived",
  "created_at",
  "updated_at",
] as const;

export function projectsToCsv(projects: Project[]): string {
  const rows = projects.map((project) => [
    project.id,
    project.key,
    project.name,
    project.description ?? "",
    project.color ?? "",
    project.is_archived ? "true" : "false",
    project.created_at,
    project.updated_at,
  ]);

  return buildCsv(PROJECT_COLUMNS, rows);
}

export function csvToProjects(csv: string): CsvImportResult<Project> {
  const records = toRecords(parseCsv(csv));
  const items: Project[] = [];
  const skipped: { line: number; reason: string }[] = [];
  const seenKeys = new Set<string>();

  records.forEach((record, position) => {
    const line = position + 2;
    const key = (record.key ?? "").trim().toUpperCase();
    const name = (record.name ?? "").trim();

    if (!key || !name) {
      skipped.push({ line, reason: "thiếu key hoặc name" });
      return;
    }
    if (seenKeys.has(key)) {
      skipped.push({ line, reason: `key '${key}' trùng trong file` });
      return;
    }
    seenKeys.add(key);

    items.push({
      id: record.id || uuid(),
      key,
      name,
      description: record.description || null,
      color: record.color || null,
      is_archived: record.is_archived === "true",
      created_at: record.created_at || nowIso(),
      updated_at: record.updated_at || nowIso(),
    });
  });

  return { items, skipped };
}

// ── Note ───────────────────────────────────────────────────────────────

export const NOTE_COLUMNS = [
  "id",
  "title",
  "kind",
  // Nội dung thường có nhiều dòng. Parser RFC 4180 ở trên xử lý được xuống
  // dòng bên trong dấu ngoặc kép, nên không cần làm phẳng.
  "content",
  "description",
  "context",
  "project_key",
  "tags",
  "is_pinned",
  "is_dangerous",
  "use_count",
  "last_used_at",
  "source",
  "external_id",
  "created_at",
  "updated_at",
  "deleted_at",
] as const;

export function notesToCsv(notes: StoredNote[], projects: Project[]): string {
  const keyById = new Map(projects.map((p) => [p.id, p.key]));

  const rows = notes.map((note) => [
    note.id,
    note.title,
    note.kind,
    note.content,
    note.description ?? "",
    note.context ?? "",
    note.project_id ? (keyById.get(note.project_id) ?? "") : "",
    note.tags.join(";"),
    note.is_pinned ? "true" : "false",
    note.is_dangerous ? "true" : "false",
    note.use_count.toString(),
    note.last_used_at ?? "",
    note.source,
    note.external_id ?? "",
    note.created_at,
    note.updated_at,
    note.deleted_at ?? "",
  ]);

  return buildCsv(NOTE_COLUMNS, rows);
}

const VALID_NOTE_KIND: readonly NoteKind[] = [
  "command",
  "sql",
  "text",
  "config",
  "code",
  "system_info",
  "system_flow",
  "knowledge",
];
const VALID_NOTE_SOURCE: readonly NoteSource[] = [
  "manual",
  "obsidian",
  "github",
  "agent",
];

export function csvToNotes(
  csv: string,
  projects: Project[],
): CsvImportResult<StoredNote> {
  const records = toRecords(parseCsv(csv));
  const byKey = new Map(projects.map((p) => [p.key.toUpperCase(), p]));

  const items: StoredNote[] = [];
  const skipped: { line: number; reason: string }[] = [];

  records.forEach((record, position) => {
    const line = position + 2; // +1 cho header, +1 vì đếm từ 1
    const title = (record.title ?? "").trim();
    // content KHÔNG trim sâu: thụt lề bên trong là phần nội dung, nhất là
    // với YAML và SQL nhiều dòng. Chỉ kiểm tra có ký tự thật hay không.
    const content = record.content ?? "";

    if (!title) {
      skipped.push({ line, reason: "thiếu title" });
      return;
    }
    if (!content.trim()) {
      skipped.push({ line, reason: "thiếu content" });
      return;
    }

    const kind = record.kind as NoteKind;
    if (kind && !VALID_NOTE_KIND.includes(kind)) {
      skipped.push({ line, reason: `kind không hợp lệ: ${record.kind}` });
      return;
    }

    const source = record.source as NoteSource;
    if (source && !VALID_NOTE_SOURCE.includes(source)) {
      skipped.push({ line, reason: `source không hợp lệ: ${record.source}` });
      return;
    }

    const projectKey = (record.project_key ?? "").toUpperCase();
    const project = projectKey ? byKey.get(projectKey) : undefined;
    if (projectKey && !project) {
      skipped.push({ line, reason: `không có project key '${projectKey}'` });
      return;
    }

    const used = Number.parseInt(record.use_count ?? "", 10);

    items.push(
      makeNote({
        id: record.id || uuid(),
        title,
        kind: kind || "command",
        content,
        description: record.description || null,
        context: record.context || null,
        project_id: project?.id ?? null,
        project: summary(project),
        tags: normalizeTags((record.tags ?? "").split(";")),
        is_pinned: record.is_pinned === "true",
        is_dangerous: record.is_dangerous === "true",
        use_count: Number.isFinite(used) && used > 0 ? used : 0,
        last_used_at: record.last_used_at || null,
        source: source || "manual",
        external_id: record.external_id || null,
        created_at: record.created_at || nowIso(),
        updated_at: record.updated_at || nowIso(),
        deleted_at: record.deleted_at || null,
      }),
    );
  });

  return { items, skipped };
}
