import "server-only";

/**
 * Xuất và nhập dữ liệu dạng JSON và CSV.
 *
 * Xuất hoạt động ở cả ba chế độ DATA_SOURCE; nhập CSV và nhập JSON kiểu cũ chỉ ở file/memory.
 * Chuyển dữ liệu từ file lên Postgres KHÔNG đi qua đây: dùng endpoint
 * POST /api/v1/import/datafile (xem lib/api.ts importDataFile và
 * docs/DATA_MIGRATION_TO_POSTGRES.md). Ở chế độ api, importJson ném lỗi
 * chỉ về hướng đó vì đường POST từng bản ghi cũ làm hỏng dữ liệu.
 *
 * Ràng buộc quan trọng khi nhập từ instance khác: `project_id` trong file là
 * UUID của nơi xuất, không có ý nghĩa ở nơi nhập. Vì vậy project luôn được
 * đối chiếu theo `key`, không theo id.
 */

import * as apiClient from "../api";
import { DATA_SOURCE } from "./types";
import type { Project } from "../types";
import * as csvCodec from "./csv";
import * as engine from "./engine";
import { ensureLoaded, migrate } from "./json-file";
import {
  SCHEMA_VERSION,
  type DataFile,
  type StoredNote,
  type StoredTask,
} from "./types";

export type ImportMode = "merge" | "replace";

export interface ImportSummary {
  created_projects: number;
  created_tasks: number;
  created_notes: number;
  skipped: { line: number; reason: string }[];
  warnings: string[];
}

const IS_LOCAL = DATA_SOURCE !== "api";

async function localReady(): Promise<void> {
  if (DATA_SOURCE === "file") await ensureLoaded();
}

// ── Xuất ───────────────────────────────────────────────────────────────

/** Gom toàn bộ dữ liệu hiện tại về dạng DataFile. */
export async function collect(): Promise<DataFile> {
  if (IS_LOCAL) {
    await localReady();
    return engine.snapshot();
  }

  // Chế độ api: lấy qua HTTP. Nhật ký task không xuất ở chế độ này vì phải
  // gọi thêm một request cho mỗi task.
  const projects = await apiClient.listProjects(true);
  const tasks: StoredTask[] = [];
  const pageSize = 200;
  let offset = 0;

  for (; ;) {
    const page = await apiClient.listTasks({
      includeClosed: true,
      limit: pageSize,
      offset,
    });
    for (const task of page.items) {
      // Bỏ field tính toán, chúng phụ thuộc thời điểm đọc
      const {
        is_overdue: _overdue,
        days_until_purge: _purge,
        ...rest
      } = task;
      tasks.push({ ...rest, events: [] });
    }
    offset += pageSize;
    if (offset >= page.total || page.items.length === 0) break;
  }

  const notes: StoredNote[] = [];
  offset = 0;
  for (; ;) {
    const page = await apiClient.listNotes({ limit: pageSize, offset });
    for (const note of page.items) {
      const { days_until_purge: _purge, ...rest } = note;
      notes.push(rest);
    }
    offset += pageSize;
    if (offset >= page.total || page.items.length === 0) break;
  }

  return {
    schema_version: SCHEMA_VERSION,
    exported_at: new Date().toISOString(),
    projects,
    tasks,
    notes,
    meta: {
      minutes_logged_today: 0,
      minutes_logged_date: new Date().toISOString().slice(0, 10),
    },
  };
}

// Ghi chú: ở chế độ api, múi giờ nằm trong app_settings của backend và đi theo đường
// import/datafile riêng, nên bản xuất ở chế độ api không mang meta.display_timezone.

export async function buildJson(): Promise<string> {
  return JSON.stringify(await collect(), null, 2);
}

export async function buildTasksCsv(): Promise<string> {
  const data = await collect();
  return csvCodec.tasksToCsv(data.tasks, data.projects);
}

export async function buildProjectsCsv(): Promise<string> {
  const data = await collect();
  return csvCodec.projectsToCsv(data.projects);
}

export async function buildNotesCsv(): Promise<string> {
  const data = await collect();
  return csvCodec.notesToCsv(data.notes, data.projects);
}

// ── Nhập ───────────────────────────────────────────────────────────────

function emptySummary(): ImportSummary {
  return {
    created_projects: 0,
    created_tasks: 0,
    created_notes: 0,
    skipped: [],
    warnings: [],
  };
}

const API_IMPORT_REDIRECT =
  "Ở chế độ Core API, dùng mục 'Chuyển dữ liệu JSON vào Postgres' (có bước Kiểm tra trước khi nhập).";

function assertReplaceAllowed(mode: ImportMode): void {
  if (mode === "replace" && !IS_LOCAL) {
    throw new Error(
      "Chế độ replace bị chặn khi DATA_SOURCE=api, vì nó sẽ phải xoá dữ liệu " +
      "trong Postgres. Dùng merge, hoặc xử lý trực tiếp trên database.",
    );
  }
}

/**
 * Ghi một tập dữ liệu vào store hiện tại.
 *
 * merge   → thêm mới, bỏ qua project trùng key và task trùng id
 * replace → thay toàn bộ, chỉ cho phép ở chế độ cục bộ
 */
async function apply(
  projects: Project[],
  tasks: StoredTask[],
  notes: StoredNote[],
  mode: ImportMode,
): Promise<ImportSummary> {
  assertReplaceAllowed(mode);
  const summary = emptySummary();

  if (IS_LOCAL) {
    await localReady();

    if (mode === "replace") {
      const remapped = relinkByKey(projects, tasks, summary);
      const remappedNotes = relinkNotesByKey(projects, notes, summary);
      engine.replaceAll({
        projects,
        tasks: remapped,
        notes: remappedNotes,
      });
      summary.created_projects = projects.length;
      summary.created_tasks = remapped.length;
      summary.created_notes = remappedNotes.length;
      return summary;
    }

    const existingKeys = new Set(
      engine.allProjects().map((p) => p.key.toUpperCase()),
    );
    for (const project of projects) {
      if (existingKeys.has(project.key.toUpperCase())) {
        summary.warnings.push(`Bỏ qua project '${project.key}', đã tồn tại`);
        continue;
      }
      engine.createProject({
        key: project.key,
        name: project.name,
        color: project.color,
      });
      summary.created_projects += 1;
    }

    const keyById = new Map(projects.map((p) => [p.id, p.key.toUpperCase()]));
    const currentByKey = new Map(
      engine.allProjects().map((p) => [p.key.toUpperCase(), p.id]),
    );

    let skippedTrash = 0;
    for (const task of tasks) {
      // Không hồi sinh task đang ở trong thùng rác. Nhập kiểu merge mà tự
      // dựng lại thứ người dùng đã xoá là hành vi gây ngạc nhiên.
      if (task.deleted_at) {
        skippedTrash += 1;
        continue;
      }

      const key = task.project?.key?.toUpperCase() ?? keyById.get(task.project_id ?? "");
      engine.createTask({
        title: task.title,
        description: task.description,
        status: task.status,
        priority: task.priority,
        project_id: key ? (currentByKey.get(key) ?? null) : null,
        due_at: task.due_at,
        due_all_day: task.due_all_day,
        scheduled_for: task.scheduled_for,
        estimate_minutes: task.estimate_minutes,
        tags: task.tags,
      });
      summary.created_tasks += 1;
    }

    if (skippedTrash > 0) {
      summary.warnings.push(
        `Bỏ qua ${skippedTrash} task đang ở trong thùng rác của file nguồn`,
      );
    }

    // Note trùng bị bỏ qua, khác với task.
    //
    // Nhập lại đúng một file backup là việc hay làm với sổ tay, và nhân đôi
    // toàn bộ câu lệnh thì danh sách thành vô dụng. Dấu hiệu nhận trùng là
    // cùng tiêu đề và cùng nội dung; sửa một trong hai thì coi là note khác.
    const existingNoteKeys = new Set(
      engine.allNotes().map((n) => `${n.title}\u0000${n.content}`),
    );
    let skippedNoteTrash = 0;
    let duplicateNotes = 0;

    for (const note of notes) {
      if (note.deleted_at) {
        skippedNoteTrash += 1;
        continue;
      }

      const fingerprint = `${note.title}\u0000${note.content}`;
      if (existingNoteKeys.has(fingerprint)) {
        duplicateNotes += 1;
        continue;
      }
      existingNoteKeys.add(fingerprint);

      const key =
        note.project?.key?.toUpperCase() ?? keyById.get(note.project_id ?? "");
      engine.createNote({
        title: note.title,
        content: note.content,
        kind: note.kind,
        description: note.description,
        context: note.context,
        project_id: key ? (currentByKey.get(key) ?? null) : null,
        tags: note.tags,
        is_pinned: note.is_pinned,
        is_dangerous: note.is_dangerous,
      });
      summary.created_notes += 1;
    }

    if (skippedNoteTrash > 0) {
      summary.warnings.push(
        `Bỏ qua ${skippedNoteTrash} note đang ở trong thùng rác của file nguồn`,
      );
    }
    if (duplicateNotes > 0) {
      summary.warnings.push(
        `Bỏ qua ${duplicateNotes} note đã có sẵn (trùng tiêu đề và nội dung)`,
      );
    }

    return summary;
  }

  // Chế độ api: đẩy từng bản ghi lên core API
  const existing = await apiClient.listProjects(true);
  const currentByKey = new Map(existing.map((p) => [p.key.toUpperCase(), p.id]));

  for (const project of projects) {
    const key = project.key.toUpperCase();
    if (currentByKey.has(key)) {
      summary.warnings.push(`Bỏ qua project '${project.key}', đã tồn tại`);
      continue;
    }
    const created = await apiClient.createProject({
      key: project.key,
      name: project.name,
      color: project.color,
    });
    currentByKey.set(key, created.id);
    summary.created_projects += 1;
  }

  const keyById = new Map(projects.map((p) => [p.id, p.key.toUpperCase()]));

  let skippedTrashRemote = 0;
  for (const [index, task] of tasks.entries()) {
    if (task.deleted_at) {
      skippedTrashRemote += 1;
      continue;
    }

    const key = task.project?.key?.toUpperCase() ?? keyById.get(task.project_id ?? "");
    try {
      await apiClient.createTask({
        title: task.title,
        description: task.description,
        status: task.status,
        priority: task.priority,
        project_id: key ? (currentByKey.get(key) ?? null) : null,
        due_at: task.due_at,
        scheduled_for: task.scheduled_for,
        estimate_minutes: task.estimate_minutes,
        tags: task.tags,
      });
      summary.created_tasks += 1;
    } catch (error) {
      summary.skipped.push({
        line: index + 2,
        reason: error instanceof Error ? error.message : String(error),
      });
    }
  }

  if (skippedTrashRemote > 0) {
    summary.warnings.push(
      `Bỏ qua ${skippedTrashRemote} task đang ở trong thùng rác của file nguồn`,
    );
  }

  // Note: cùng luật bỏ trùng như đường cục bộ. Chỉ lấy một trang đủ lớn để
  // dựng bảng đối chiếu; nếu sổ tay vượt 500 mục thì có thể lọt trùng, và đó
  // là đánh đổi có ý thức để không phải phân trang toàn bộ trước mỗi lần nhập.
  let existingNoteKeysRemote = new Set<string>();
  try {
    const current = await apiClient.listNotes({ limit: 200 });
    existingNoteKeysRemote = new Set(
      current.items.map((n) => `${n.title}\u0000${n.content}`),
    );
    if (current.total > current.items.length) {
      summary.warnings.push(
        `Chỉ đối chiếu trùng với ${current.items.length}/${current.total} note hiện có`,
      );
    }
  } catch {
    summary.warnings.push("Không đọc được sổ tay hiện có, bỏ qua bước lọc trùng");
  }

  let skippedNoteTrashRemote = 0;
  let duplicateNotesRemote = 0;

  for (const [index, note] of notes.entries()) {
    if (note.deleted_at) {
      skippedNoteTrashRemote += 1;
      continue;
    }

    const fingerprint = `${note.title}\u0000${note.content}`;
    if (existingNoteKeysRemote.has(fingerprint)) {
      duplicateNotesRemote += 1;
      continue;
    }
    existingNoteKeysRemote.add(fingerprint);

    const key =
      note.project?.key?.toUpperCase() ?? keyById.get(note.project_id ?? "");
    try {
      await apiClient.createNote({
        title: note.title,
        content: note.content,
        kind: note.kind,
        description: note.description,
        context: note.context,
        project_id: key ? (currentByKey.get(key) ?? null) : null,
        tags: note.tags,
        is_pinned: note.is_pinned,
        is_dangerous: note.is_dangerous,
      });
      summary.created_notes += 1;
    } catch (error) {
      summary.skipped.push({
        line: index + 2,
        reason: error instanceof Error ? error.message : String(error),
      });
    }
  }

  if (skippedNoteTrashRemote > 0) {
    summary.warnings.push(
      `Bỏ qua ${skippedNoteTrashRemote} note đang ở trong thùng rác của file nguồn`,
    );
  }
  if (duplicateNotesRemote > 0) {
    summary.warnings.push(
      `Bỏ qua ${duplicateNotesRemote} note đã có sẵn (trùng tiêu đề và nội dung)`,
    );
  }

  return summary;
}

/** Gắn lại quan hệ project theo key, dùng cho chế độ replace cục bộ. */
function relinkByKey(
  projects: Project[],
  tasks: StoredTask[],
  summary: ImportSummary,
): StoredTask[] {
  const byKey = new Map(projects.map((p) => [p.key.toUpperCase(), p]));

  return tasks.map((task) => {
    const key = task.project?.key?.toUpperCase();
    const project = key ? byKey.get(key) : undefined;

    if (key && !project) {
      summary.warnings.push(
        `Task '${task.title}' trỏ tới project '${key}' không có trong file, đã bỏ liên kết`,
      );
    }

    return {
      ...task,
      project_id: project?.id ?? null,
      project: project
        ? {
          id: project.id,
          key: project.key,
          name: project.name,
          color: project.color,
        }
        : null,
    };
  });
}

/** Gắn lại quan hệ project cho note theo key, dùng cho chế độ replace cục bộ. */
function relinkNotesByKey(
  projects: Project[],
  notes: StoredNote[],
  summary: ImportSummary,
): StoredNote[] {
  const byKey = new Map(projects.map((p) => [p.key.toUpperCase(), p]));

  return notes.map((note) => {
    const key = note.project?.key?.toUpperCase();
    const project = key ? byKey.get(key) : undefined;

    if (key && !project) {
      summary.warnings.push(
        `Note '${note.title}' trỏ tới project '${key}' không có trong file, đã bỏ liên kết`,
      );
    }

    return {
      ...note,
      project_id: project?.id ?? null,
      project: project
        ? {
          id: project.id,
          key: project.key,
          name: project.name,
          color: project.color,
        }
        : null,
    };
  });
}

function parseDataFile(text: string): DataFile {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("Không phải JSON hợp lệ");
  }

  if (typeof parsed !== "object" || parsed === null) {
    throw new Error("JSON phải là một object");
  }

  const candidate = parsed as Partial<DataFile>;
  if (!Array.isArray(candidate.tasks) || !Array.isArray(candidate.projects)) {
    throw new Error(
      "Thiếu mảng 'tasks' hoặc 'projects'. Dùng file xuất ra từ chính app này.",
    );
  }
  if ((candidate.schema_version ?? 1) > SCHEMA_VERSION) {
    throw new Error(
      `File dùng schema_version ${candidate.schema_version}, app chỉ đọc tới ${SCHEMA_VERSION}`,
    );
  }

  // Chạy qua migrate để file cũ được backfill field mới, giống lúc nạp
  // từ đĩa. Thiếu bước này thì nhập file v1 sẽ ra task không có deleted_at.
  return migrate({
    schema_version: candidate.schema_version ?? 1,
    exported_at: candidate.exported_at ?? new Date().toISOString(),
    projects: candidate.projects,
    tasks: candidate.tasks,
    // File v2 không có `notes`. migrate() sẽ backfill, nhưng đặt sẵn ở đây để
    // object đúng kiểu DataFile ngay từ lúc dựng.
    notes: candidate.notes ?? [],
    meta: candidate.meta ?? {
      minutes_logged_today: 0,
      minutes_logged_date: new Date().toISOString().slice(0, 10),
    },
  });
}

export async function importJson(
  text: string,
  mode: ImportMode,
): Promise<ImportSummary> {
  // Ở chế độ api, nhập JSON phải đi qua endpoint có dry-run, báo cáo ghi đè và audit.
  if (!IS_LOCAL) throw new Error(API_IMPORT_REDIRECT);
  const data = parseDataFile(text);
  const summary = await apply(data.projects, data.tasks, data.notes, mode);
  // Múi giờ là cài đặt (cùng nhóm current_users), chỉ thay khi nhập kiểu replace và file có
  // mang theo. Tên rác thì cảnh báo, không làm hỏng cả lần nhập.
  if (mode === "replace" && data.meta?.display_timezone) {
    try {
      engine.setDisplayTimezone(data.meta.display_timezone);
    } catch {
      summary.warnings.push("Bỏ qua display_timezone không hợp lệ trong file");
    }
  }
  return summary;
}

export async function importProjectsCsv(
  text: string,
  mode: ImportMode,
): Promise<ImportSummary> {
  const parsed = csvCodec.csvToProjects(text);
  const summary = await apply(parsed.items, [], [], mode);
  summary.skipped.push(...parsed.skipped);
  return summary;
}

export async function importTasksCsv(
  text: string,
  mode: ImportMode,
): Promise<ImportSummary> {
  // Task CSV chỉ mang project_key, nên cần danh sách project hiện có để
  // đối chiếu. Không tự tạo project mới từ file task.
  const projects = IS_LOCAL
    ? (await localReady(), engine.allProjects())
    : await apiClient.listProjects(true);

  const parsed = csvCodec.csvToTasks(text, projects);
  const summary = await apply(
    mode === "replace" ? projects : [],
    parsed.items,
    // Replace từ CSV task không được xoá sổ tay. Truyền sổ tay hiện có để
    // replaceAll ghi lại đúng những gì đang có.
    mode === "replace" ? engineNotesOrEmpty() : [],
    mode,
  );
  summary.skipped.push(...parsed.skipped);

  if (mode === "replace") {
    summary.created_projects = 0;
    summary.created_notes = 0;
    summary.warnings.push(
      "Chế độ replace chỉ thay task, project và sổ tay được giữ nguyên",
    );
  }

  return summary;
}

/** Sổ tay hiện tại ở chế độ cục bộ, mảng rỗng ở chế độ api. */
function engineNotesOrEmpty(): StoredNote[] {
  return IS_LOCAL ? engine.allNotes() : [];
}

export async function importNotesCsv(
  text: string,
  mode: ImportMode,
): Promise<ImportSummary> {
  // Note CSV chỉ mang project_key, nên cần danh sách project hiện có để đối
  // chiếu. Không tự tạo project mới từ file note.
  const projects = IS_LOCAL
    ? (await localReady(), engine.allProjects())
    : await apiClient.listProjects(true);

  const parsed = csvCodec.csvToNotes(text, projects);
  const summary = await apply(
    mode === "replace" ? projects : [],
    // Replace từ CSV note không được xoá task.
    mode === "replace" ? engineTasksOrEmpty() : [],
    parsed.items,
    mode,
  );
  summary.skipped.push(...parsed.skipped);

  if (mode === "replace") {
    summary.created_projects = 0;
    summary.created_tasks = 0;
    summary.warnings.push(
      "Chế độ replace chỉ thay sổ tay, project và task được giữ nguyên",
    );
  }

  return summary;
}

/** Task hiện tại ở chế độ cục bộ, mảng rỗng ở chế độ api. */
function engineTasksOrEmpty(): StoredTask[] {
  return IS_LOCAL ? engine.allTasks() : [];
}
