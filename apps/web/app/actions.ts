"use server";

import * as api from "@/lib/api";
import { revalidatePath } from "next/cache";

import {
  CoreApiError,
  createNote,
  createProject,
  createTask,
  deleteNote,
  deleteTask,
  emptyNoteTrash,
  emptyTrash,
  logTime,
  markNoteUsed,
  patchNote,
  patchTask,
  purgeExpired,
  purgeExpiredNotes,
  purgeNote,
  purgeTask,
  restoreNote,
  restoreTask,
} from "@/lib/api";
import {
  importJson,
  importNotesCsv,
  importProjectsCsv,
  importTasksCsv,
  type ImportMode,
  type ImportSummary,
} from "@/lib/store/transfer";
import type { NoteKind, TaskPriority, TaskStatus } from "@/lib/types";

export interface ActionResult {
  ok: boolean;
  error?: string;
}

function revalidateAll(): void {
  revalidatePath("/");
  revalidatePath("/tasks");
  revalidatePath("/projects");
  revalidatePath("/notes");
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


export async function updateProjectAction(
  id: string,
  input: {
    key?: string;
    name?: string;
    description?: string | null;
    color?: string | null;
    is_archived?: boolean;
  },
): Promise<ActionResult> {
  try {
    const payload = { ...input };
    if (payload.key) payload.key = payload.key.trim().toUpperCase();
    if (payload.name) payload.name = payload.name.trim();
    
    // api import is at top: import { ..., patchProject, deleteProject } from "@/lib/api" 
    // We need to make sure patchProject and deleteProject are imported!
    await api.patchProject(id, payload);
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

export async function deleteProjectAction(id: string): Promise<ActionResult> {
  try {
    await api.deleteProject(id);
    revalidateAll();
    return { ok: true };
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
//  Sổ tay
//
//  `content` của note là dữ liệu do người dùng nhập. Nó chỉ được validate độ
//  dài rồi lưu, không parse và không thực thi. Không có action nào ở đây chạy
//  nội dung note.
// ═══════════════════════════════════════════════════════════════════════

const MAX_NOTE_CONTENT = 20_000;

export interface NewNoteInput {
  title: string;
  content: string;
  kind?: NoteKind;
  description?: string;
  context?: string;
  projectId?: string;
  tags?: string[];
  isPinned?: boolean;
  isDangerous?: boolean;
}

export async function createNoteAction(
  input: NewNoteInput,
): Promise<ActionResult> {
  const title = input.title?.trim();
  if (!title) {
    return { ok: false, error: "Tiêu đề không được để trống" };
  }
  if (title.length > 300) {
    return { ok: false, error: "Tiêu đề tối đa 300 ký tự" };
  }

  const content = input.content?.trim();
  if (!content) {
    return { ok: false, error: "Nội dung không được để trống" };
  }
  if (content.length > MAX_NOTE_CONTENT) {
    return {
      ok: false,
      error: `Nội dung tối đa ${MAX_NOTE_CONTENT.toLocaleString("vi-VN")} ký tự`,
    };
  }

  try {
    await createNote({
      title,
      content,
      kind: input.kind ?? "command",
      description: input.description?.trim() || null,
      context: input.context?.trim() || null,
      project_id: input.projectId || null,
      tags: input.tags ?? [],
      is_pinned: input.isPinned ?? false,
      is_dangerous: input.isDangerous ?? false,
    });
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

export async function updateNoteAction(
  id: string,
  patch: Record<string, unknown>,
): Promise<ActionResult> {
  if (typeof patch.title === "string" && !patch.title.trim()) {
    return { ok: false, error: "Tiêu đề không được để trống" };
  }
  if (typeof patch.content === "string") {
    if (!patch.content.trim()) {
      return { ok: false, error: "Nội dung không được để trống" };
    }
    if (patch.content.length > MAX_NOTE_CONTENT) {
      return {
        ok: false,
        error: `Nội dung tối đa ${MAX_NOTE_CONTENT.toLocaleString("vi-VN")} ký tự`,
      };
    }
  }

  try {
    await patchNote(id, patch);
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

export async function toggleNotePinAction(
  id: string,
  isPinned: boolean,
): Promise<ActionResult> {
  try {
    await patchNote(id, { is_pinned: isPinned });
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

/**
 * Ghi nhận người dùng vừa copy note.
 *
 * Cố tình KHÔNG revalidate: copy là hành động rất thường xuyên, và render lại
 * cả trang chỉ để tăng một con số đếm sẽ làm danh sách nhảy dưới tay người
 * dùng. Số liệu sẽ đúng ở lần tải trang sau.
 */
export async function markNoteUsedAction(id: string): Promise<ActionResult> {
  try {
    await markNoteUsed(id);
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

/** Xoá mềm: note vào thùng rác, còn phục hồi được trong thời hạn giữ. */
export async function deleteNoteAction(id: string): Promise<ActionResult> {
  try {
    await deleteNote(id);
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

export async function restoreNoteAction(id: string): Promise<ActionResult> {
  try {
    await restoreNote(id);
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

/** Xoá vĩnh viễn một note trong thùng rác. Không hoàn tác được. */
export async function purgeNoteAction(id: string): Promise<ActionResult> {
  try {
    await purgeNote(id);
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

export async function purgeExpiredNotesAction(): Promise<PurgeActionResult> {
  try {
    const result = await purgeExpiredNotes();
    revalidateAll();
    return { ok: true, purged: result.purged };
  } catch (error) {
    return toResult(error);
  }
}

/** Xoá vĩnh viễn toàn bộ thùng rác sổ tay, không chờ hết hạn. */
export async function emptyNoteTrashAction(): Promise<PurgeActionResult> {
  try {
    const result = await emptyNoteTrash();
    revalidateAll();
    return { ok: true, purged: result.purged };
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
    } else if (kind === "notes-csv") {
      summary = await importNotesCsv(text, mode);
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

import * as XLSX from 'xlsx';

function parseJiraDate(val: any): string | null {
  if (!val || val === "No Due Date" || val === "Not Closed") return null;
  if (typeof val === "number") {
    const d = new Date(Math.round((val - 25569) * 86400 * 1000));
    return isNaN(d.getTime()) ? null : d.toISOString();
  }
  if (typeof val === "string") {
    // 2026-10-01T18:22:05.573+0700 -> 2026-10-01T18:22:05.573+07:00 (Next.js can parse this or we insert colon)
    const cleaned = val.replace(/([+-]\d{2})(\d{2})$/, "$1:$2");
    const d = new Date(cleaned);
    return isNaN(d.getTime()) ? null : d.toISOString();
  }
  return null;
}

export async function syncFromUrlAction(url: string): Promise<ActionResult & { count?: number }> {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Lỗi HTTP: ${res.status}`);
    const buffer = await res.arrayBuffer();
    const workbook = XLSX.read(buffer, { type: 'array' });
    const sheetName = workbook.SheetNames[0];
    if (!sheetName) throw new Error('No sheet');
    const sheet = workbook.Sheets[sheetName];
    if (!sheet) throw new Error('No sheet');
    const data = XLSX.utils.sheet_to_json(sheet) as any[];

    let added = 0;
    const projects = await api.listProjects();
    const projectMap = Object.fromEntries(projects.map((p: any) => [p.key.toUpperCase(), p]));
    
    // We fetch all tasks to deduplicate by external_id
    const { items: allTasks } = await api.listTasks();
    const existingKeys = new Set(allTasks.filter(t => t.external_id).map(t => t.external_id));

    for (const ticket of data) {
      if (typeof ticket !== 'object' || !ticket['Issue Key']) continue;
      const key = String(ticket['Issue Key']);
      if (existingKeys.has(key)) continue;
      
      const titleRaw = `[${ticket['Projects'] || 'JIRA'}] ${ticket['Summary'] || 'No summary'}`;
      
      const statusMap: Record<string, any> = {
        'To Do': 'todo',
        'In Progress': 'in_progress',
        'Done': 'done',
        'Closed': 'done',
      };
      const status = statusMap[String(ticket['Status'])] || 'todo';
      
      const tags = ['jira'];
      if (ticket['Labels']) {
        tags.push(...String(ticket['Labels']).split(',').map(s => s.trim().toLowerCase()));
      }
      
      let projectId = null;
      let finalTitle = titleRaw;
      
      const match = titleRaw.match(/^\[([^\]]+)\]\s*(.*)$/);
      if (match && match[1] && match[2]) {
        const prefix = match[1].toUpperCase();
        let assignedProject = null;
        if (prefix.startsWith('MAG')) assignedProject = projectMap['MAG'];
        else if (prefix.startsWith('OM')) assignedProject = projectMap['OM'];
        else if (prefix.startsWith('IOTEK')) assignedProject = projectMap['IOTEK'];
        else if (prefix.startsWith('GIAI')) assignedProject = projectMap['GIAI'];
        
        if (assignedProject) {
          projectId = assignedProject.id;
          const projectTag = assignedProject.key.toLowerCase();
          if (!tags.includes(projectTag)) tags.push(projectTag);
          finalTitle = match[2].trim();
        }
      }
      
      await api.createTask({
        title: finalTitle,
        description: ticket['Description'] ? String(ticket['Description']) : undefined,
        status,
        priority: 'medium',
        project_id: projectId,
        tags,
        
        source: 'jira',
        external_id: key,
        external_url: `https://onemount.atlassian.net/browse/${key}`,
        assignee: ticket['Assignee'] ? String(ticket['Assignee']) : null,
        due_at: parseJiraDate(ticket['Due Date']),
        created_at: parseJiraDate(ticket['Created Date']) || undefined
      });
      added++;
    }

    revalidateAll();
    return { ok: true, count: added };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "Sync failed" };
  }
}

import { addSyncUrlApi, removeSyncUrlApi } from "@/lib/api";

export async function addSyncUrlAction(url: string) {
  await addSyncUrlApi(url);
  revalidateAll();
}

export async function removeSyncUrlAction(url: string) {
  await removeSyncUrlApi(url);
  revalidateAll();
}

import { renameGlobalTagApi, deleteGlobalTagApi } from "@/lib/api";

export async function renameTagAction(oldName: string, newName: string) {
  await renameGlobalTagApi(oldName, newName);
  revalidateAll();
}

export async function deleteTagAction(name: string) {
  await deleteGlobalTagApi(name);
  revalidateAll();
}
