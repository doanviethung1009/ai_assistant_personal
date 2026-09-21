import "server-only";

/**
 * Xuất và nhập dữ liệu dạng JSON và CSV.
 *
 * Hoạt động ở cả ba chế độ DATA_SOURCE. Đây là cầu nối để sau này chuyển
 * dữ liệu từ file lên Postgres: cùng một file JSON, chỉ cần đổi
 * DATA_SOURCE=api rồi nhập lại.
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
import { SCHEMA_VERSION, type DataFile, type StoredTask } from "./types";

export type ImportMode = "merge" | "replace";

export interface ImportSummary {
  created_projects: number;
  created_tasks: number;
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

  return {
    schema_version: SCHEMA_VERSION,
    exported_at: new Date().toISOString(),
    projects,
    tasks,
    meta: {
      minutes_logged_today: 0,
      minutes_logged_date: new Date().toISOString().slice(0, 10),
    },
  };
}

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

// ── Nhập ───────────────────────────────────────────────────────────────

function emptySummary(): ImportSummary {
  return { created_projects: 0, created_tasks: 0, skipped: [], warnings: [] };
}

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
  mode: ImportMode,
): Promise<ImportSummary> {
  assertReplaceAllowed(mode);
  const summary = emptySummary();

  if (IS_LOCAL) {
    await localReady();

    if (mode === "replace") {
      const remapped = relinkByKey(projects, tasks, summary);
      engine.replaceAll({ projects, tasks: remapped });
      summary.created_projects = projects.length;
      summary.created_tasks = remapped.length;
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
  const data = parseDataFile(text);
  return apply(data.projects, data.tasks, mode);
}

export async function importProjectsCsv(
  text: string,
  mode: ImportMode,
): Promise<ImportSummary> {
  const parsed = csvCodec.csvToProjects(text);
  const summary = await apply(parsed.items, [], mode);
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
  const summary = await apply(mode === "replace" ? projects : [], parsed.items, mode);
  summary.skipped.push(...parsed.skipped);

  if (mode === "replace") {
    summary.created_projects = 0;
    summary.warnings.push("Chế độ replace chỉ thay task, project được giữ nguyên");
  }

  return summary;
}
