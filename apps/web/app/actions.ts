"use server";

import { revalidatePath } from "next/cache";

import {
  CoreApiError,
  createProject,
  createTask,
  deleteTask,
  emptyTrash,
  logTime,
  patchTask,
  purgeExpired,
  purgeTask,
  restoreTask,
} from "@/lib/api";
import {
  importJson,
  importProjectsCsv,
  importTasksCsv,
  type ImportMode,
  type ImportSummary,
} from "@/lib/store/transfer";
import type { TaskPriority, TaskStatus } from "@/lib/types";

export interface ActionResult {
  ok: boolean;
  error?: string;
}

function revalidateAll(): void {
  revalidatePath("/");
  revalidatePath("/tasks");
  revalidatePath("/projects");
  revalidatePath("/trash");
  revalidatePath("/data");
}

function toResult(error: unknown): ActionResult {
  if (error instanceof CoreApiError) {
    return { ok: false, error: error.message };
  }
  // Không trả stack trace về browser
  console.error("action thất bại", error);
  return { ok: false, error: "Không gọi được core API. Kiểm tra service api." };
}

export interface NewTaskInput {
  title: string;
  description?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  projectId?: string;
  /** ISO 8601 kèm offset, do client quy đổi từ datetime-local */
  dueAt?: string;
  /** YYYY-MM-DD */
  scheduledFor?: string;
  estimateMinutes?: number;
  tags?: string[];
}

export async function createTaskAction(input: NewTaskInput): Promise<ActionResult> {
  const title = input.title?.trim();
  if (!title) {
    return { ok: false, error: "Tiêu đề không được để trống" };
  }
  if (title.length > 500) {
    return { ok: false, error: "Tiêu đề tối đa 500 ký tự" };
  }

  try {
    await createTask({
      title,
      description: input.description?.trim() || null,
      status: input.status ?? "todo",
      priority: input.priority ?? "medium",
      project_id: input.projectId || null,
      due_at: input.dueAt || null,
      scheduled_for: input.scheduledFor || null,
      estimate_minutes: input.estimateMinutes ?? null,
      tags: input.tags ?? [],
    });
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

export async function setStatusAction(
  id: string,
  status: TaskStatus,
): Promise<ActionResult> {
  try {
    await patchTask(id, { status });
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

export async function setScheduleAction(
  id: string,
  scheduledFor: string | null,
): Promise<ActionResult> {
  try {
    await patchTask(id, { scheduled_for: scheduledFor });
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

export async function logTimeAction(
  id: string,
  minutes: number,
): Promise<ActionResult> {
  if (!Number.isInteger(minutes) || minutes <= 0) {
    return { ok: false, error: "Số phút phải là số nguyên dương" };
  }
  try {
    await logTime(id, minutes);
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

/** Xoá mềm: task vào thùng rác, còn phục hồi được trong thời hạn giữ. */
export async function deleteTaskAction(id: string): Promise<ActionResult> {
  try {
    await deleteTask(id);
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

// ── Thùng rác ──────────────────────────────────────────────────────────

export async function restoreTaskAction(id: string): Promise<ActionResult> {
  try {
    await restoreTask(id);
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

/** Xoá vĩnh viễn một task trong thùng rác. Không hoàn tác được. */
export async function purgeTaskAction(id: string): Promise<ActionResult> {
  try {
    await purgeTask(id);
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

export interface PurgeActionResult extends ActionResult {
  purged?: number;
}

/** Dọn những task đã quá thời hạn giữ. */
export async function purgeExpiredAction(): Promise<PurgeActionResult> {
  try {
    const result = await purgeExpired();
    revalidateAll();
    return { ok: true, purged: result.purged };
  } catch (error) {
    return toResult(error);
  }
}

/** Xoá vĩnh viễn toàn bộ thùng rác, không chờ hết hạn. */
export async function emptyTrashAction(): Promise<PurgeActionResult> {
  try {
    const result = await emptyTrash();
    revalidateAll();
    return { ok: true, purged: result.purged };
  } catch (error) {
    return toResult(error);
  }
}

export async function createProjectAction(
  key: string,
  name: string,
  color?: string,
): Promise<ActionResult> {
  const normalizedKey = key?.trim().toUpperCase();
  if (!normalizedKey || !name?.trim()) {
    return { ok: false, error: "Cần cả mã và tên project" };
  }
  try {
    await createProject({
      key: normalizedKey,
      name: name.trim(),
      color: color || null,
    });
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

// ═══════════════════════════════════════════════════════════════════════
//  Nhập dữ liệu từ file JSON hoặc CSV
// ═══════════════════════════════════════════════════════════════════════

const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

export interface ImportActionResult extends ActionResult {
  summary?: ImportSummary;
}

/**
 * Nhận file do người dùng chọn và nạp vào store hiện tại.
 *
 * Nội dung file là dữ liệu không đáng tin: chỉ đọc, validate, rồi ghi qua
 * đúng các hàm nghiệp vụ, không bao giờ eval hay ghi thẳng xuống đĩa.
 */
export async function importDataAction(
  formData: FormData,
): Promise<ImportActionResult> {
  const file = formData.get("file");
  const kind = String(formData.get("kind") ?? "");
  const mode = String(formData.get("mode") ?? "merge") as ImportMode;

  if (!(file instanceof File) || file.size === 0) {
    return { ok: false, error: "Chưa chọn file" };
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return { ok: false, error: "File vượt quá 8 MB" };
  }
  if (mode !== "merge" && mode !== "replace") {
    return { ok: false, error: `Chế độ không hợp lệ: ${mode}` };
  }

  let text: string;
  try {
    text = await file.text();
  } catch {
    return { ok: false, error: "Không đọc được nội dung file" };
  }

  try {
    let summary: ImportSummary;

    if (kind === "json") {
      summary = await importJson(text, mode);
    } else if (kind === "tasks-csv") {
      summary = await importTasksCsv(text, mode);
    } else if (kind === "projects-csv") {
      summary = await importProjectsCsv(text, mode);
    } else {
      return { ok: false, error: `Loại dữ liệu không hợp lệ: ${kind}` };
    }

    revalidateAll();
    return { ok: true, summary };
  } catch (error) {
    console.error("nhập dữ liệu thất bại", error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : "Nhập dữ liệu thất bại",
    };
  }
}
