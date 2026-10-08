"use server";

import * as api from "@/lib/api";
import { revalidatePath } from "next/cache";

import {
  CoreApiError,
  createNote,
  createProject,
  createTask,
  archiveNote,
  unarchiveNote,
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
  importAiLogsJson,
  importNotesCsv,
  importProjectsCsv,
  importTasksCsv,
  type ImportMode,
  type ImportSummary,
} from "@/lib/store/transfer";
import type { ImportReport, NoteKind, TaskPriority, TaskScope, TaskStatus, UpsertSummary } from "@/lib/types";
import { authorizeImport, pushRowsToCore } from "@/lib/excel-upsert";

export interface ActionResult {
  ok: boolean;
  error?: string;
}

function revalidateAll(): void {
  revalidatePath("/");
  revalidatePath("/tasks");
  revalidatePath("/team");
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
  scope?: TaskScope;
}

export async function createTaskAction(input: NewTaskInput): Promise<ActionResult> {
  const title = input.title?.trim();
  if (!title) {
    return { ok: false, error: "Tiêu đề không được để trống" };
  }
  if (title.length > 500) {
    return { ok: false, error: "Tiêu đề tối đa 500 ký tự" };
  }
  if (input.scope !== undefined && input.scope !== "work" && input.scope !== "personal") {
    return { ok: false, error: "scope phải là 'work' hoặc 'personal'" };
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
      // undefined -> core/engine suy từ source (manual -> personal)
      scope: input.scope,
    });
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

/**
 * Đổi task giữa việc công ty và việc riêng.
 *
 * Quyết định quan trọng: `personal` nghĩa là "tách khỏi đồng bộ" (Jira sync,
 * nhập Excel/URL bỏ qua task này), còn `work` đưa task trở lại vòng đồng bộ.
 * Server Action là endpoint công khai nên scope được kiểm lại ở đây; `id` đi
 * qua pathId() trong lib/api.ts.
 */
export async function setScopeAction(
  id: string,
  scope: TaskScope,
): Promise<ActionResult> {
  if (scope !== "work" && scope !== "personal") {
    return { ok: false, error: "scope phải là 'work' hoặc 'personal'" };
  }
  try {
    await patchTask(id, { scope });
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

/** Lưu trữ note: ẩn khỏi tab Đang dùng, không bị dọn như thùng rác. */
export async function archiveNoteAction(id: string): Promise<ActionResult> {
  try {
    await archiveNote(id);
    revalidateAll();
    return { ok: true };
  } catch (error) {
    return toResult(error);
  }
}

export async function unarchiveNoteAction(id: string): Promise<ActionResult> {
  try {
    await unarchiveNote(id);
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
    } else if (kind === "ai-logs-json") {
      summary = await importAiLogsJson(text, mode);
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
import {
  SyncFetchError,
  assertSpreadsheetContentType,
  fetchAllowlisted,
  readCappedBody,
  syncUrlError,
} from "@/lib/sync-url-policy";

/** Số dòng tối đa đọc từ một sheet cào về. */
const MAX_SYNC_ROWS = 50_000;

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

/**
 * Convert Google Sheets URL to a direct XLSX export link.
 * Supports formats:
 *   https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit?gid=SHEET_ID#gid=SHEET_ID
 *   https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit#gid=0
 */
function toDirectDownloadUrl(url: string): string {
  const gsheetMatch = url.match(/docs\.google\.com\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/);
  if (gsheetMatch) {
    const spreadsheetId = gsheetMatch[1];
    // Try to extract gid for specific sheet
    const gidMatch = url.match(/gid=(\d+)/);
    const gid = gidMatch ? gidMatch[1] : '0';
    return `https://docs.google.com/spreadsheets/d/${spreadsheetId}/export?format=xlsx&gid=${gid}`;
  }
  return url;
}

/**
 * Cào một link Excel/CSV đã qua allowlist rồi nhập task.
 *
 * Chế độ api: web vẫn tải và đọc file (giữ allowlist + stream trần 20 MB), ánh xạ dòng sang
 * TaskUpsert rồi đẩy qua `upsert-batch` với `source` cố định `jira` (khớp chế độ file).
 * Cần mật khẩu nhập vì là ghi đè hàng loạt; mật khẩu không bao giờ vào log hay thông báo lỗi.
 * Mọi tham số kiểm kiểu lại ở đây vì Server Action là endpoint công khai.
 */
export async function syncFromUrlAction(
  url: unknown,
  secret?: unknown,
): Promise<ActionResult & { count?: number; skipped_personal?: number; summary?: UpsertSummary }> {
  if (typeof url !== "string") return { ok: false, error: "URL không hợp lệ" };
  // Server Action là endpoint công khai: kiểm URL gốc trước, rồi kiểm lại ở MỖI bước
  // redirect bên trong fetchAllowlisted (SSRF).
  const rejected = syncUrlError(url);
  if (rejected !== null) return { ok: false, error: rejected };

  // Chế độ api: hỏi core xem mật khẩu đúng không TRƯỚC khi fetch URL, để server không bị
  // dùng làm công cụ tải URL ngoài bởi request chưa xác thực.
  let verifiedSecret = "";
  if (!api.IS_LOCAL) {
    const auth = await authorizeImport(secret);
    if (!auth.ok) return { ok: false, error: auth.error };
    verifiedSecret = auth.secret;
  }

  try {
    const downloadUrl = toDirectDownloadUrl(url);

    const res = await fetchAllowlisted(downloadUrl, {
      Accept: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, text/csv, */*',
    });
    // Không đưa statusText vào lỗi: nó đến từ máy chủ ngoài.
    if (!res.ok) {
      void res.body?.cancel().catch(() => undefined);
      throw new SyncFetchError(`Link trả về lỗi HTTP ${res.status}.`);
    }
    assertSpreadsheetContentType(res);

    // Đọc theo stream và dừng ngay khi vượt 20 MB (không arrayBuffer() toàn phần).
    const buffer = await readCappedBody(res);
    // sheetRows chặn sheet khổng lồ làm phình RAM khi parse.
    const workbook = XLSX.read(buffer, { type: 'array', sheetRows: MAX_SYNC_ROWS });
    const sheetName = workbook.SheetNames[0];
    if (!sheetName) throw new Error('File không chứa sheet nào');
    const sheet = workbook.Sheets[sheetName];
    if (!sheet) throw new Error('Không đọc được sheet');
    const rows = XLSX.utils.sheet_to_json(sheet) as any[];
    if (!rows || rows.length === 0) throw new Error('Sheet rỗng, không có dữ liệu');

    if (!api.IS_LOCAL) {
      const out = await pushRowsToCore(rows, verifiedSecret);
      if (!out.ok || !out.summary) return { ok: false, error: out.error ?? "Nhập thất bại" };
      revalidateAll();
      return {
        ok: true,
        count: out.summary.added + out.summary.updated,
        skipped_personal: out.summary.skipped_personal,
        summary: out.summary,
      };
    }

    // Delegate to the unified import logic (handles Company, Projects, Labels, dedup, etc.)
    const { importBulkTasksAction } = await import("@/app/actions-import");
    const result = await importBulkTasksAction(rows);

    revalidateAll();
    return {
      ok: true,
      count: (result.added || 0) + (result.updated || 0),
      skipped_personal: result.skipped_personal,
    };
  } catch (error) {
    // Chỉ thông điệp tự viết mới ra client; lỗi khác (fetch, XLSX) có thể chứa URL/chi tiết ngoài.
    if (error instanceof SyncFetchError) return { ok: false, error: error.message };
    console.error("cào URL thất bại", error instanceof Error ? error.name : "unknown");
    return { ok: false, error: "Không đọc được dữ liệu từ link (không phải file Excel/CSV hợp lệ?)." };
  }
}

import { addSyncUrlApi, removeSyncUrlApi } from "@/lib/api";

/** Lưu URL đồng bộ; trả {ok:false,error} (thay vì ném) để UI hiện lỗi allowlist rõ ràng. */
export type SyncUrlActionResult = ActionResult & { dropped?: number };

export async function addSyncUrlAction(url: string): Promise<SyncUrlActionResult> {
  if (typeof url !== "string") return { ok: false, error: "URL không hợp lệ" };
  try {
    const { dropped } = await addSyncUrlApi(url.trim());
    revalidateAll();
    return { ok: true, dropped };
  } catch (error) {
    return toResult(error);
  }
}

export async function removeSyncUrlAction(url: string): Promise<SyncUrlActionResult> {
  if (typeof url !== "string") return { ok: false, error: "URL không hợp lệ" };
  try {
    const { dropped } = await removeSyncUrlApi(url);
    revalidateAll();
    return { ok: true, dropped };
  } catch (error) {
    return toResult(error);
  }
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

// ═══════════════════════════════════════════════════════════════════════
//  Nhập hàng loạt vào Postgres qua core API (B1)
// ═══════════════════════════════════════════════════════════════════════

export interface CoreImportResult extends ActionResult {
  report?: ImportReport;
  /** Mã HTTP của lỗi từ core, để UI phân biệt 409 (đang có lần nhập khác) và 413. */
  status?: number;
}

/**
 * Kiểm tra (dry_run) hoặc nhập thật một file JSON vào Postgres.
 *
 * ══════════════════════════════════════════════════════════════════════
 *  ĐÂY LÀ THAO TÁC GHI ĐÈ. Bản ghi đã có trong Postgres bị thay bằng nội
 *  dung file. Server Action là endpoint HTTP công khai nên KHÔNG tin UI đã
 *  bắt người dùng Kiểm tra trước: nhập thật vẫn bị từ chối nếu thiếu
 *  `expect_replaced` hợp lệ (core cũng kiểm lại và đối chiếu số thực tế).
 * ══════════════════════════════════════════════════════════════════════
 *
 * Nội dung file là dữ liệu không đáng tin: web không parse, chỉ chuyển nguyên
 * văn cho core validate. API key chỉ nằm ở server (lib/api.ts).
 */
export async function importToCoreAction(formData: FormData): Promise<CoreImportResult> {
  if (api.IS_LOCAL) {
    return { ok: false, error: "Chỉ dùng được khi DATA_SOURCE=api", status: 501 };
  }

  const file = formData.get("file");
  const kind = String(formData.get("kind") ?? "");
  const dryRun = String(formData.get("dry_run") ?? "1") !== "0";
  // Chỉ đúng "1" mới bật; mặc định tắt để task cá nhân trong Postgres được bảo vệ (S8).
  const includePersonal = String(formData.get("include_personal") ?? "") === "1";

  if (!(file instanceof File) || file.size === 0) {
    return { ok: false, error: "Chưa chọn file" };
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return { ok: false, error: "File vượt quá 8 MB", status: 413 };
  }
  if (kind !== "datafile" && kind !== "ai-logs") {
    return { ok: false, error: `Loại file không hợp lệ: ${kind}` };
  }

  let expectReplaced: number | undefined;
  let expectSha256: string | undefined;
  let secret: string | undefined;
  if (!dryRun) {
    const raw = String(formData.get("expect_replaced") ?? "");
    // Chỉ nhận số nguyên không âm ở dạng chữ số thuần, không để "1e3" hay " 5" lọt qua.
    if (!/^\d{1,9}$/.test(raw)) {
      return { ok: false, error: "Thiếu hoặc sai số bản ghi dự kiến bị ghi đè. Hãy bấm Kiểm tra trước." };
    }
    expectReplaced = Number(raw);

    const sha = String(formData.get("expect_sha256") ?? "");
    if (!/^[0-9a-f]{64}$/i.test(sha)) {
      return { ok: false, error: "Thiếu mã băm file của lần Kiểm tra. Hãy bấm Kiểm tra trước." };
    }
    expectSha256 = sha.toLowerCase();

    const rawSecret = formData.get("import_secret");
    // ASCII in được: giá trị đi vào header HTTP, ký tự lạ làm fetch ném lỗi chứa giá trị.
    if (typeof rawSecret !== "string" || !/^[\x20-\x7e]{1,256}$/.test(rawSecret)) {
      return { ok: false, error: "Chưa nhập mật khẩu nhập dữ liệu (hoặc chứa ký tự không hợp lệ)." };
    }
    secret = rawSecret;
  }

  let text: string;
  try {
    text = await file.text();
  } catch {
    return { ok: false, error: "Không đọc được nội dung file" };
  }

  try {
    const options = { dryRun, expectReplaced, expectSha256, secret, includePersonal };
    const report =
      kind === "datafile"
        ? await api.importDataFile(text, options)
        : await api.importAiLogsFile(text, options);
    // Chỉ làm mới cache khi dữ liệu thật sự đổi.
    if (report.committed) revalidateAll();
    return { ok: true, report };
  } catch (error) {
    if (error instanceof CoreApiError) {
      if (error.status === 403) {
        // Thông điệp tự viết, không chuyển tiếp detail của core và không nhắc lại giá trị đã gõ.
        return {
          ok: false,
          status: 403,
          error:
            "Mật khẩu nhập sai, hoặc core chưa cấu hình IMPORT_COMMIT_SECRET (đặt biến này trong .env của core rồi khởi động lại api).",
        };
      }
      return { ok: false, error: error.message, status: error.status };
    }
    // Chỉ log tên lỗi, không log cả object: tránh vô tình ghi header chứa mật khẩu.
    console.error("nhập vào Postgres thất bại", error instanceof Error ? error.name : "unknown");
    return { ok: false, error: "Không gọi được core API. Kiểm tra service api." };
  }
}
