"use server";

import { revalidatePath } from "next/cache";
import { IS_LOCAL } from "@/lib/api";
import * as engine from "@/lib/store/engine";
import { uuid, nowIso, MAX_SYNC_URLS } from "@/lib/store/engine";

/** Trần số dòng đọc từ sheet, cùng giá trị với đường cào URL trong actions.ts. */
const MAX_SYNC_ROWS = 50_000;
import { migrate } from "@/lib/store/json-file";
import type { DataFile } from "@/lib/store/types";
import { syncUrlError } from "@/lib/sync-url-policy";
import { scopeOf } from "@/lib/task-scope";
import { authorizeImport, pushRowsToCore } from "@/lib/excel-upsert";
import type { UpsertSummary } from "@/lib/types";
import * as XLSX from "xlsx";

const PALETTE = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#6366f1', '#84cc16', '#06b6d4', '#d946ef'];
function getRandomColor() {
  return PALETTE[Math.floor(Math.random() * PALETTE.length)];
}


function parseJiraDate(val: any): string | null {
  if (!val || val === "No Due Date" || val === "Not Closed") return null;
  if (typeof val === "number") {
    const d = new Date(Math.round((val - 25569) * 86400 * 1000));
    return isNaN(d.getTime()) ? null : d.toISOString();
  }
  if (typeof val === "string") {
    const cleaned = val.replace(/([+-]\d{2})(\d{2})$/, "$1:$2");
    const d = new Date(cleaned);
    return isNaN(d.getTime()) ? null : d.toISOString();
  }
  return null;
}

export async function importBulkTasksAction(rows: any[]) {
  if (!IS_LOCAL) throw new Error("Chỉ hỗ trợ chế độ Local File");

  const db = engine.state();
  let added = 0;
  let updated = 0;
  let skippedPersonal = 0;

  for (const ticket of rows) {
    const summary = ticket['Summary'] || ticket['Title'];
    if (!summary) continue;

    const key = ticket['Issue Key'] || ticket['Key'];
    const issueKey = key ? String(key) : null;

    // Issue Key trùng một task đã chuyển sang `personal`: User đã tách nó khỏi
    // đồng bộ nên KHÔNG ghi đè, cũng không tạo bản trùng. Kiểm trước khi tạo
    // project để dòng bị bỏ qua không để lại tác dụng phụ.
    if (
      issueKey &&
      db.tasks.some(
        (t) => t.source === "jira" && t.external_id === issueKey && scopeOf(t) === "personal",
      )
    ) {
      skippedPersonal++;
      continue;
    }

    let rawSummary = String(ticket['Summary'] || "No Title");
    let finalTitle = rawSummary;

    // Lấy thông tin cột
    const rawCompany = ticket['Company'] ? String(ticket['Company']).trim() : null;
    const rawProjects = ticket['Projects'] ? String(ticket['Projects']).trim() : null;
    const rawLabels = ticket['Labels'] ? String(ticket['Labels']).trim() : null;

    const statusMap: Record<string, string> = {
      'To Do': 'todo',
      'In Progress': 'in_progress',
      'Done': 'done',
      'Closed': 'done',
    };
    const status = statusMap[ticket['Status']] || 'todo';
    
    const tags = ['jira'];
    
    // Thêm tag từ Company
    if (rawCompany) {
      tags.push(rawCompany.toLowerCase().replace(/[^a-z0-9]/g, ''));
    }
    
    // Thêm tag từ Projects
    if (rawProjects) {
      tags.push(...rawProjects.split(',').map(s => s.trim().toLowerCase().replace(/[^a-z0-9]/g, '')));
    }

    // Thêm tag từ Labels
    if (rawLabels) {
      tags.push(...rawLabels.split(',').map(s => s.trim().toLowerCase()));
    }

    let projectId = null;
    let projectObj = null;

    // DỰ ÁN được tạo TỪ CỘT COMPANY
    if (rawCompany) {
      const projectKey = rawCompany.toUpperCase().replace(/[^A-Z0-9]/g, '').substring(0, 20);
      
      let assignedProject = db.projects.find((p: any) => p.key.toUpperCase() === projectKey) as any;
      
      if (!assignedProject) {
        assignedProject = {
          id: uuid(),
          key: projectKey,
          name: rawCompany,
          color: getRandomColor(),
          created_at: nowIso(),
          updated_at: nowIso(),
          is_archived: false
        };
        db.projects.push(assignedProject);
      }

      projectId = assignedProject.id;
      projectObj = { id: assignedProject.id, key: assignedProject.key, name: assignedProject.name, color: assignedProject.color };
    }
    
    const assignee = ticket['Assignee'] ? String(ticket['Assignee']) : null;
    const createdAt = parseJiraDate(ticket['Created Date']) || nowIso();
    const dueAt = parseJiraDate(ticket['Due Date']);
    const completedAt = status === 'done' ? (parseJiraDate(ticket['Closed Date']) || nowIso()) : null;
    
    // Chỉ khớp trong task Jira thuộc scope `work` (cả theo Issue Key lẫn theo tiêu đề),
    // để dòng Excel không đè lên task tay trùng tên hay task cá nhân.
    let task = db.tasks.find(
      (t) =>
        t.source === "jira" &&
        scopeOf(t) === "work" &&
        (issueKey
          ? t.external_id === issueKey
          : t.title.toLowerCase() === finalTitle.toLowerCase()),
    );
    
    // Lọc bỏ các tag rỗng
    const validTags = tags.filter(t => t.length > 0);
    
    if (task) {
      task.title = finalTitle;
      task.description = ticket['Description'] || null;
      task.status = status as any;
      task.project_id = projectId;
      task.project = projectObj as any;
      task.due_at = dueAt;
      task.completed_at = completedAt;
      task.tags = Array.from(new Set([...task.tags.map((t: string) => t.toLowerCase()), ...validTags]));
      task.assignee = assignee;
      task.created_at = createdAt;
      task.updated_at = nowIso();
      updated++;
    } else {
      task = {
        id: uuid(),
        title: finalTitle,
        description: ticket['Description'] || null,
        status: status as any,
        priority: 'medium',
        project_id: projectId,
        project: projectObj as any,
        due_at: dueAt,
        scheduled_for: null,
        estimate_minutes: null,
        spent_minutes: 0,
        completed_at: completedAt,
        tags: Array.from(new Set(validTags)),
        source: 'jira',
        external_id: issueKey,
        external_url: issueKey ? `https://onemount.atlassian.net/browse/${issueKey}` : null,
        assignee,
        scope: 'work',
        created_at: createdAt,
        updated_at: nowIso(),
        deleted_at: null,
        events: [],
      };
      db.tasks.unshift(task as any);
      added++;
    }
  }
  
  engine.touched();
  revalidatePath('/', 'layout');
  return { ok: true, added, updated, skipped_personal: skippedPersonal };
}

/** Kết quả nhập Excel: chế độ file trả đếm đơn giản, chế độ api trả `summary` đầy đủ từ core. */
export type BulkFileResult =
  | { ok: true; added: number; updated: number; skipped_personal: number; summary?: UpsertSummary }
  | { ok: false; error: string };

/**
 * Đọc file Excel/CSV người dùng tải lên rồi nhập task.
 *
 * Chế độ file: engine như cũ. Chế độ api: web vẫn đọc file, ánh xạ dòng sang TaskUpsert và
 * đẩy qua `upsert-batch` của core với `source` CỐ ĐỊNH `jira` (khớp chế độ file, KHÔNG nhận
 * từ client). Cần mật khẩu `import_secret` vì đây là thao tác ghi đè hàng loạt.
 */
export async function importBulkFileAction(formData: FormData): Promise<BulkFileResult> {
  try {
    const file = formData.get("file");
    if (!(file instanceof File) || file.size === 0) return { ok: false, error: "Không tìm thấy file" };
    // Cùng trần 20 MB với đường URL (B2) và body tối đa của upsert-batch.
    if (file.size > 20 * 1024 * 1024) return { ok: false, error: "File vượt quá 20 MB" };

    // Chế độ api: xác thực mật khẩu với core NGAY, trước khi đọc file hay XLSX.read (tốn
    // CPU/RAM), để request sai mật khẩu bị từ chối sớm.
    let secret = "";
    if (!IS_LOCAL) {
      const auth = await authorizeImport(formData.get("import_secret"));
      if (!auth.ok) return { ok: false, error: auth.error };
      secret = auth.secret;
    }

    const buffer = await file.arrayBuffer();
    // sheetRows chặn sheet khổng lồ làm phình RAM khi parse, như đường URL (MAX_SYNC_ROWS).
    const wb = XLSX.read(buffer, { type: "array", sheetRows: MAX_SYNC_ROWS });
    const wsname = wb.SheetNames[0];
    if (!wsname) return { ok: false, error: "File Excel không hợp lệ" };
    
    const ws = wb.Sheets[wsname];
    if (!ws) return { ok: false, error: "Không lấy được dữ liệu Sheet" };
    
    const rows = XLSX.utils.sheet_to_json(ws);
    if (!rows || rows.length === 0) return { ok: false, error: "Sheet rỗng" };

    if (!IS_LOCAL) {
      const out = await pushRowsToCore(rows, secret);
      if (!out.ok || !out.summary) return { ok: false, error: out.error ?? "Nhập thất bại" };
      revalidatePath("/", "layout");
      return {
        ok: true,
        added: out.summary.added,
        updated: out.summary.updated,
        skipped_personal: out.summary.skipped_personal,
        summary: out.summary,
      };
    }

    const res = await importBulkTasksAction(rows);
    return { ok: true, added: res.added, updated: res.updated, skipped_personal: res.skipped_personal };
  } catch (error) {
    // Lỗi parse XLSX có thể chứa chi tiết nội dung file; chỉ báo chung.
    console.error("nhập Excel thất bại", error instanceof Error ? error.name : "unknown");
    return { ok: false, error: "Không đọc được file (không phải Excel/CSV hợp lệ?)." };
  }
}

/** Giữ phần tử là object thường có đủ các khoá kiểu chuỗi không rỗng; còn lại bỏ. */
function cleanList(value: unknown, requiredStrings: string[]): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => {
    if (typeof item !== "object" || item === null || Array.isArray(item)) return false;
    const rec = item as Record<string, unknown>;
    return requiredStrings.every((k) => typeof rec[k] === "string" && rec[k] !== "");
  });
}

export async function restoreFromJsonAction(jsonData: any) {
  if (!IS_LOCAL) return { ok: false, error: "Chỉ hỗ trợ chế độ Local File" };

  try {
    if (!jsonData || typeof jsonData !== "object") {
      return { ok: false, error: "Dữ liệu JSON không hợp lệ" };
    }

    // Chạy migrate trước khi gộp: file cũ (v1-v4) thiếu `scope` (và trước đây có
    // thể thiếu cả `deleted_at`), nếu đưa nguyên vào RAM thì task biến mất khỏi
    // mọi view. File không ghi schema_version coi như v1 để migrate chạy đủ bước.
    //
    // VALIDATE TOÀN BỘ TRƯỚC KHI GHI: file là dữ liệu không đáng tin. Phần tử không
    // phải object hoặc thiếu id/title bị loại ở đây; mọi bước có thể ném lỗi (lọc,
    // migrate) đều chạy xong trước khi chạm vào db, nên không để lại trạng thái dở dang.
    const version = Number.isInteger(jsonData.schema_version) ? jsonData.schema_version : 1;
    const data = migrate({
      ...jsonData,
      schema_version: version,
      projects: cleanList(jsonData.projects, ["id", "key", "name"]),
      tasks: cleanList(jsonData.tasks, ["id", "title"]).map((t) => ({
        ...t,
        tags: Array.isArray(t.tags) ? t.tags : [],
        events: Array.isArray(t.events) ? t.events : [],
      })),
      notes: cleanList(jsonData.notes, ["id", "title", "content"]).map((n) => ({
        ...n,
        tags: Array.isArray(n.tags) ? n.tags : [],
      })),
    } as DataFile);

    const db = engine.state();
    let restoredTasks = 0;
    let skippedPersonal = 0;
    let restoredProjects = 0;
    let restoredNotes = 0;
    let droppedUrls = 0;

    if (Array.isArray(jsonData.projects)) {
      for (const p of data.projects) {
        const idx = db.projects.findIndex((x) => x.id === p.id);
        if (idx !== -1) db.projects[idx] = p;
        else db.projects.push(p);
      }
      restoredProjects = data.projects.length;
    }

    if (Array.isArray(jsonData.tasks)) {
      for (const t of data.tasks) {
        // Khớp theo id, hoặc (source, external_id) như unique của backend.
        const idx = db.tasks.findIndex(
          (x) =>
            x.id === t.id ||
            (!!t.external_id && x.source === t.source && x.external_id === t.external_id),
        );
        const existing = idx !== -1 ? db.tasks[idx] : undefined;
        // Task cá nhân đang có trong RAM được bảo vệ: file khôi phục không ghi đè
        // (S8). Chế độ file không có tuỳ chọn bật ghi đè; muốn thì đổi sang `work` trước.
        if (existing && scopeOf(existing) === "personal") {
          skippedPersonal++;
          continue;
        }
        if (idx !== -1) db.tasks[idx] = t;
        else db.tasks.push(t);
        restoredTasks++;
      }
    }

    if (Array.isArray(jsonData.notes)) {
      for (const n of data.notes) {
        const idx = db.notes.findIndex((x) => x.id === n.id);
        if (idx !== -1) db.notes[idx] = n;
        else db.notes.push(n);
      }
      restoredNotes = data.notes.length;
    }

    if (Array.isArray(jsonData.sync_urls)) {
      // Chỉ giữ chuỗi qua allowlist: URL này sau đó sẽ được server fetch (SSRF).
      const accepted = Array.from(
        new Set(
          jsonData.sync_urls.filter(
            (u: unknown): u is string => typeof u === "string" && syncUrlError(u) === null,
          ),
        ),
      ) as string[];
      // Giới hạn 50 như backend; phần bị lọc/cắt được báo lại, không im lặng.
      db.sync_urls = accepted.slice(0, MAX_SYNC_URLS);
      droppedUrls = jsonData.sync_urls.length - db.sync_urls.length;
    }

    engine.touched();
    revalidatePath('/', 'layout');

    const skippedNote =
      (skippedPersonal > 0 ? `, giữ nguyên ${skippedPersonal} task cá nhân đang có` : "") +
      (droppedUrls > 0 ? `, bỏ ${droppedUrls} link đồng bộ không hợp lệ/trùng/vượt ${MAX_SYNC_URLS}` : "");
    return {
      ok: true,
      message: `Đã khôi phục thành công! (${restoredTasks} tasks, ${restoredProjects} projects, ${restoredNotes} notes${skippedNote})`
    };
  } catch (error: any) {
    return { ok: false, error: error.message || String(error) };
  }
}

export async function processJsonUploadAction(formData: FormData) {
  if (!IS_LOCAL) return { ok: false, error: "Chỉ hỗ trợ chế độ Local File" };

  try {
    const file = formData.get("file") as File;
    if (!file) return { ok: false, error: "Không tìm thấy file" };

    const text = await file.text();
    const data = JSON.parse(text);

    return await restoreFromJsonAction(data);
  } catch (error: any) {
    return { ok: false, error: "Lỗi đọc file JSON: " + (error.message || String(error)) };
  }
}
