"use server";

import { revalidatePath } from "next/cache";
import {
  CoreApiError,
  IS_LOCAL,
  createIntegration,
  deleteIntegration,
  patchIntegration,
  syncIntegration,
} from "@/lib/api";
import { checkJiraBaseUrl } from "@/lib/jira-url-policy";
import { isValidIssueKey, jqlQuote } from "@/lib/jira-issue-key";
import type {
  IntegrationConnection,
  IntegrationCreateBody,
  IntegrationSyncResult,
  IntegrationUpdateBody,
} from "@/lib/types";
import * as engine from "@/lib/store/engine";
import { uuid, nowIso } from "@/lib/store/engine";
import type { StoredTask } from "@/lib/store/types";
import { scopeOf } from "@/lib/task-scope";

// Tên custom field Jira được coi là thông tin phân nhóm dự án
const CUSTOM_TAG_FIELD = /company|group|customer|client|team|squad|tribe|department|công ty|nhóm|khách|dự án/i;

function slug(s: unknown): string {
  return String(s ?? "").trim().toLowerCase().replace(/\s+/g, "-");
}

function customValueToStrings(val: unknown): string[] {
  if (typeof val === "string") return [val];
  if (Array.isArray(val)) return val.flatMap(customValueToStrings);
  if (val && typeof val === "object") {
    const o = val as any;
    const v = o.value ?? o.name ?? o.displayName;
    return typeof v === "string" ? [v] : [];
  }
  return [];
}

/** Jira `duedate` hợp lệ (YYYY-MM-DD) hoặc null. Jira Cloud không gửi giờ cho trường này. */
function jiraDuedateRaw(raw: unknown): string | null {
  return typeof raw === "string" && /^\d{4}-\d{2}-\d{2}$/.test(raw) && !Number.isNaN(Date.parse(raw))
    ? raw
    : null;
}

/** `duedate` -> 00:00:00 UTC của ngày lịch (cách lưu hạn cả ngày, không phụ thuộc múi giờ). */
function jiraDueIso(raw: unknown): string | null {
  const day = jiraDuedateRaw(raw);
  return day ? `${day}T00:00:00.000Z` : null;
}

/**
 * Cập nhật hạn từ Jira có điều kiện, khớp backend (task_sync_service, phương án C).
 *
 * Chỉ ghi đè khi User CHƯA sửa hạn tay: hạn hiện tại bằng đúng hạn Jira của lần sync trước
 * (`jira_duedate`), hoặc task chưa có hạn. Task tạo bởi bản cũ chưa có baseline: coi hạn hiện
 * có là do sync sinh ra (chưa sửa tay) nếu nó cả ngày hoặc đúng 00:00 UTC, nếu không thì giữ
 * nguyên. Mọi trường hợp đều ghi baseline mới để lần sau so được (tránh kẹt hạn cũ mãi).
 */
function applyJiraDue(task: StoredTask, rawDuedate: unknown): void {
  const prev = task.jira_duedate;
  const hasBaseline = typeof prev === "string";
  const untouched =
    task.due_at === null ||
    (hasBaseline
      ? task.due_all_day && task.due_at === jiraDueIso(prev)
      : task.due_all_day || /T00:00:00(\.000)?Z$/.test(task.due_at));
  if (untouched) {
    task.due_at = jiraDueIso(rawDuedate);
    task.due_all_day = task.due_at !== null;
  }
  task.jira_duedate = jiraDuedateRaw(rawDuedate);
}

/** Trần thời gian và kích thước mỗi trang trả về từ Jira (chế độ file). */
const JIRA_FETCH_TIMEOUT_MS = 30_000;
const JIRA_MAX_PAGE_BYTES = 25 * 1024 * 1024;
/** Trần TỔNG cho cả lượt (cộng dồn qua các trang) và hạn chót cả lượt: 100 trang x 25 MB sẽ tràn RAM. */
const JIRA_MAX_TOTAL_BYTES = 100 * 1024 * 1024;
const JIRA_TOTAL_DEADLINE_MS = 5 * 60_000;
const MAX_TITLE = 500;
const MAX_DESCRIPTION = 32_000;

/** Cờ chống chạy song song trong process: mỗi baseUrl một lượt tại một thời điểm. Nằm trên globalThis như store. */
const syncGlobals = globalThis as typeof globalThis & { __jiraFileSyncRunning?: Set<string> };
function runningSet(): Set<string> {
  return (syncGlobals.__jiraFileSyncRunning ??= new Set<string>());
}

class JiraTooLargeError extends Error {}

/** Thông báo TỰ VIẾT theo mã trạng thái: không bao giờ chuyển tiếp body/statusText của Jira. */
function jiraStatusMessage(status: number): string {
  if (status === 401 || status === 403) return "Xác thực thất bại (sai Email/Token hoặc thiếu quyền).";
  if (status === 400) return "Jira từ chối truy vấn (kiểm tra lại JQL).";
  if (status === 404) return "Jira không tìm thấy tài nguyên (kiểm tra lại URL).";
  if (status === 429) return "Jira giới hạn tần suất truy cập, thử lại sau.";
  if (status >= 500) return "Jira đang lỗi, thử lại sau.";
  return `Jira trả về lỗi (mã ${status}).`;
}

/** Đọc JSON từ response theo stream và dừng khi vượt trần, để Jira (hay kẻ giả mạo) không làm tràn RAM. */
async function readJsonCapped(res: Response, budget: { used: number }): Promise<any> {
  const declared = Number(res.headers.get("content-length") ?? 0);
  if (declared > JIRA_MAX_PAGE_BYTES || !res.body) throw new Error("size");
  const reader = res.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    budget.used += value.byteLength;
    if (total > JIRA_MAX_PAGE_BYTES || budget.used > JIRA_MAX_TOTAL_BYTES) {
      await reader.cancel().catch(() => undefined);
      throw new JiraTooLargeError("size");
    }
    chunks.push(value);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

/**
 * Cào Jira trực tiếp từ web, CHỈ chế độ file (chế độ api dùng syncIntegrationAction).
 *
 * THAY ĐỔI HÀNH VI (vá SSRF): trước đây nhận mọi baseUrl và gửi Authorization tới đó, kèm trả
 * nguyên body lỗi. Nay chỉ nhận Jira Cloud https://*.atlassian.net, không theo redirect
 * (Authorization không bao giờ bị gửi sang host khác), và không trả/log body của Jira.
 */
export async function syncJiraAction(formData: FormData) {
  if (!IS_LOCAL) {
    return { ok: false, error: "Chế độ api dùng nút \"Cào ngay\" ở kết nối Jira đã lưu (trang Dữ liệu)." };
  }
  
  const url = formData.get("url") as string;
  const email = formData.get("email") as string;
  const token = formData.get("token") as string;
  const customJql = formData.get("jql") as string;
  // Dự án (entity Project) sẽ được gắn vào mọi task kéo về; tự tạo nếu chưa có mã này
  const projectKey = String(formData.get("projectKey") || "").trim().toUpperCase();
  const projectName = String(formData.get("projectName") || "").trim();
  
  if (!url || !email || !token) {
    return { ok: false, error: "Thiếu URL, Email hoặc Token" };
  }
  
  // Chặn SSRF: chỉ Jira Cloud, chuẩn hoá về https://host
  const urlCheck = checkJiraBaseUrl(url);
  if (!urlCheck.ok) return { ok: false, error: urlCheck.error };
  const baseUrl = urlCheck.baseUrl;
  
  // Tạo JQL
  let jql = "";
  if (customJql && customJql.trim() !== "") {
    jql = customJql.trim();
    // Tự động nhận diện nếu user chỉ gõ mã dự án (ví dụ "DBA" hoặc "DBA, PROJ")
    if (!jql.includes("=") && !jql.toLowerCase().includes(" in ") && !jql.toLowerCase().includes(" is ") && !jql.includes("~")) {
      const spaces = jql.split(",").map(s => jqlQuote(s.trim())).join(",");
      jql = `project in (${spaces}) ORDER BY updated DESC`;
    }
  } else {
    // Lấy task assign cho mình theo cài đặt Tên người dùng cá nhân (danh sách)
    const storeUsers = engine.state().currentUsers || [];
    if (storeUsers.length > 0) {
      const usersStr = storeUsers.map(u => jqlQuote(String(u))).join(", ");
      jql = `assignee in (${usersStr}) ORDER BY updated DESC`;
    } else {
      jql = `assignee = currentUser() ORDER BY updated DESC`;
    }
  }
  
  // Chế độ cập nhật nhanh: chỉ lấy issue thay đổi từ lần đồng bộ trước (JQL tương đối, không lệch múi giờ)
  const since = formData.get("since") as string | null;
  if (since) {
    const sinceMs = new Date(since).getTime();
    if (!Number.isNaN(sinceMs)) {
      const minutes = Math.max(1, Math.ceil((Date.now() - sinceMs) / 60000) + 5);
      const base = jql.replace(/\s+order\s+by[\s\S]*$/i, "").trim();
      jql = `(${base}) AND updated >= -${minutes}m ORDER BY updated DESC`;
    }
  }

  const searchUrl = `${baseUrl}/rest/api/3/search/jql`;
  
  // Một lượt tại một thời điểm cho mỗi baseUrl (trong process này).
  const running = runningSet();
  if (running.has(baseUrl)) {
    return { ok: false, error: "Đang có một lượt đồng bộ khác chạy cho Jira này. Đợi nó xong rồi thử lại." };
  }
  running.add(baseUrl);
  const deadline = Date.now() + JIRA_TOTAL_DEADLINE_MS;
  const budget = { used: 0 };

  try {
    const authHeader = `Basic ${Buffer.from(`${email.trim()}:${token.trim()}`).toString('base64')}`;
    
    let allIssues: any[] = [];
    // Không prototype: khoá "__proto__" từ Jira không thể làm bẩn prototype.
    const fieldNames: Record<string, string> = Object.create(null);
    let nextPageToken: string | undefined = undefined;
    let hasMore = true;
    let pagesFetched = 0;

    while (hasMore && pagesFetched < 100) {
      if (Date.now() > deadline) {
        return { ok: false, error: "Đồng bộ quá thời gian (5 phút). Thu hẹp JQL hoặc dùng ô Từ ngày." };
      } // Nâng giới hạn lên 100 trang * 100 = 10,000 tasks
      const body: any = {
        jql: jql,
        maxResults: 100, // Tối ưu: Lấy 100 kết quả mỗi trang thay vì 50
        // *all + expand names: lấy cả custom field (Company/Group/Team...) và tên hiển thị của chúng để tự nhận diện
        fields: ["*all"],
        expand: "names"
      };
      
      if (nextPageToken) {
        body.nextPageToken = nextPageToken;
      }

      const res = await fetch(searchUrl, {
        method: "POST",
        headers: {
          "Authorization": authHeader,
          "Accept": "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body),
        // manual: mọi 3xx là lỗi, không để fetch đi theo và gửi Authorization sang host khác
        redirect: "manual",
        signal: AbortSignal.any([AbortSignal.timeout(JIRA_FETCH_TIMEOUT_MS), AbortSignal.timeout(Math.max(1, deadline - Date.now()))]),
      });

      if (res.status >= 300 && res.status < 400) {
        void res.body?.cancel().catch(() => undefined);
        return { ok: false, error: "Jira trả về chuyển hướng, không được phép theo (kiểm tra lại URL Jira)." };
      }
      if (!res.ok) {
        void res.body?.cancel().catch(() => undefined);
        console.error("Jira API Error: status", res.status);
        return { ok: false, error: jiraStatusMessage(res.status) };
      }

      const data = await readJsonCapped(res, budget);
      if (data.names && typeof data.names === "object") {
        for (const [k, v] of Object.entries(data.names)) {
          if (k.startsWith("customfield_") && typeof v === "string") fieldNames[k] = v;
        }
      }
      const issues = data.issues || [];
      allIssues = allIssues.concat(issues);
      
      if (data.nextPageToken && !data.isLast) {
        nextPageToken = data.nextPageToken;
      } else {
        hasMore = false;
      }
      
      pagesFetched++;
    }
    
    const db = engine.state();
    let added = 0;

    // Tìm hoặc tạo dự án theo mã để gắn vào task
    let projectRef: { id: string; key: string; name: string; color: string | null } | null = null;
    if (projectKey) {
      let proj = db.projects.find((p: any) => p.key === projectKey);
      if (!proj) {
        proj = engine.createProject({ key: projectKey, name: projectName || projectKey });
      }
      projectRef = { id: proj.id, key: proj.key, name: proj.name, color: proj.color };
    }
    let updated = 0;
    let skippedPersonal = 0;
    let invalidKeys = 0;

    for (const issue of allIssues) {
      // Key sai định dạng (Jira giả mạo/lỗi) thì bỏ qua, không đưa vào store/URL.
      if (!issue || typeof issue !== "object" || !isValidIssueKey(issue.key)) {
        invalidKeys++;
        continue;
      }
      const issueKey: string = issue.key;
      const fields = issue.fields && typeof issue.fields === "object" ? issue.fields : {};

      const title = (typeof fields.summary === "string" && fields.summary ? fields.summary : "No Title").slice(0, MAX_TITLE);
      
      // Parse description for v2 (string) vs v3 (Atlassian Document Format)
      let description = null;
      if (typeof fields.description === 'string') {
        description = fields.description.slice(0, MAX_DESCRIPTION);
      } else if (fields.description && typeof fields.description === 'object') {
        description = "[Nội dung Jira dạng khối (Atlassian Document Format)]";
      }
      
      const statusName = fields.status?.name?.toLowerCase() || "";
      let status = 'todo';
      if (statusName.includes("progress") || statusName.includes("doing") || statusName.includes("review")) {
        status = "in_progress";
      }
      if (statusName.includes("done") || statusName.includes("close") || statusName.includes("resolved")) {
        status = "done";
      }
      if (statusName.includes("cancel") || statusName.includes("reject") || statusName.includes("won't do") || statusName.includes("obsolete")) {
        status = "cancelled";
      }
      
      const tags = ['jira'];
      if (fields.project?.key) {
        tags.push(fields.project.key.toLowerCase());
      }
      if (Array.isArray(fields.labels)) {
         fields.labels.forEach((l: string) => tags.push(slug(l)));
      }
      // Component, Fix version, loại issue, Epic/parent
      (fields.components || []).forEach((c: any) => tags.push(slug(c?.name)));
      (fields.fixVersions || []).forEach((v: any) => tags.push(slug(v?.name)));
      if (fields.issuetype?.name) tags.push(slug(fields.issuetype.name));
      if (fields.parent?.key) tags.push(slug(fields.parent.key));
      let extractedProjectKey = "";
      // Custom field có tên kiểu Company/Group/Customer/Team...
      for (const [fid, val] of Object.entries(fields)) {
        if (!fid.startsWith("customfield_") || val == null) continue;
        if (!CUSTOM_TAG_FIELD.test(fieldNames[fid] || "")) continue;
        const vals = customValueToStrings(val);
        for (const t of vals) {
          if (!extractedProjectKey) extractedProjectKey = t.trim();
          tags.push(slug(t));
        }
      }
      
      const validTags = tags.filter(t => t.length > 0);
      
      // Khớp theo (source, external_id) như unique của backend, không chỉ external_id.
      let task = db.tasks.find((t) => t.source === "jira" && t.external_id === issueKey);

      // Task đã chuyển sang `personal` nghĩa là User tách nó khỏi đồng bộ: KHÔNG
      // ghi đè, cũng không tạo bản trùng (khoá (jira, KEY) vẫn bị task đó chiếm).
      if (task && scopeOf(task) === "personal") {
        skippedPersonal++;
        continue;
      }

      const resolvedAt = fields.resolutiondate 
        ? new Date(fields.resolutiondate).toISOString() 
        : (fields.updated ? new Date(fields.updated).toISOString() : nowIso());
        
      if (task) {
        task.title = title;
        if (!task.description) task.description = description; 
        task.status = status as any;
        task.tags = Array.from(new Set([...task.tags, ...validTags]));
        task.updated_at = nowIso();
        applyJiraDue(task, fields.duedate);
        let issueProjectRef = projectRef;
        const jKey = (extractedProjectKey || fields.project?.key || issueKey.split('-')[0]).toUpperCase();
        if (jKey) {
          let proj = db.projects.find((p: any) => p.key === jKey);
          if (!proj) {
            proj = engine.createProject({ key: jKey, name: extractedProjectKey || fields.project?.name || jKey });
          }
          issueProjectRef = { id: proj.id, key: proj.key, name: proj.name, color: proj.color };
        }

        if (issueProjectRef) {
          task.project_id = issueProjectRef.id;
          task.project = issueProjectRef;
        }
        if (status === 'done' || status === 'cancelled') {
           // Luôn lấy ngày hoàn thành chính xác từ Jira đè lên ngày hiện tại
           task.completed_at = resolvedAt;
        } else {
           task.completed_at = null;
        }
        updated++;
      } else {
        task = {
          id: uuid(),
          title: title,
          description: description,
          status: status as any,
          priority: 'medium',
          project_id: null,
          project: null,
          due_at: jiraDueIso(fields.duedate),
          // Jira duedate là ngày thuần: hạn cả ngày, quá hạn tính theo ngày (xem engine.ts).
          due_all_day: jiraDueIso(fields.duedate) !== null,
          jira_duedate: jiraDuedateRaw(fields.duedate),
          scheduled_for: null,
          estimate_minutes: null,
          spent_minutes: 0,
          completed_at: (status === 'done' || status === 'cancelled') ? resolvedAt : null,
          tags: Array.from(new Set(validTags)),
          source: 'jira',
          external_id: issueKey,
          external_url: `${baseUrl}/browse/${issueKey}`,
          assignee: fields.assignee?.displayName || null,
          scope: 'work',
          created_at: fields.created ? new Date(fields.created).toISOString() : nowIso(),
          updated_at: nowIso(),
          deleted_at: null,
          events: [],
        };
        
        let issueProjectRef = projectRef;
        const jKey = (extractedProjectKey || fields.project?.key || issueKey.split('-')[0]).toUpperCase();
        if (jKey) {
          let proj = db.projects.find((p: any) => p.key === jKey);
          if (!proj) {
            proj = engine.createProject({ key: jKey, name: extractedProjectKey || fields.project?.name || jKey });
          }
          issueProjectRef = { id: proj.id, key: proj.key, name: proj.name, color: proj.color };
        }
        
        if (issueProjectRef) {
          task.project_id = issueProjectRef.id;
          task.project = issueProjectRef;
        }
        
        db.tasks.unshift(task);
        added++;
      }
    }
    
    engine.touched();
    revalidatePath('/', 'layout');
    
    return { ok: true, added, updated, skipped_personal: skippedPersonal, skipped_invalid_key: invalidKeys };

  } catch (error: unknown) {
    // Thông báo tự viết: error.message của fetch có thể chứa URL/chi tiết mạng.
    console.error("Jira sync lỗi:", error instanceof Error ? error.name : "unknown");
    if (error instanceof JiraTooLargeError) {
      return { ok: false, error: "Dữ liệu Jira quá lớn (vượt trần). Thu hẹp JQL hoặc dùng ô Từ ngày." };
    }
    return { ok: false, error: "Không kết nối được tới Jira hoặc phản hồi không hợp lệ/quá lớn." };
  } finally {
    running.delete(baseUrl);
  }
}

// ═══════════════════════════════════════════════════════════════════════
//  Kết nối Jira lưu ở core (chế độ api, B4a)
// ═══════════════════════════════════════════════════════════════════════
//
// TOKEN LÀ WRITE-ONLY. Nó đi một chiều: form -> Server Action -> core (mã hoá ở core). Không
// hàm nào dưới đây trả token về client, không log, và thông báo lỗi được lọc để không lặp
// lại token dù core có lỡ echo.

export interface ConnectionResult {
  ok: boolean;
  error?: string;
  /** Mã HTTP của core, để UI nhận ra 503 (thiếu INTEGRATION_SECRET_KEY) và 409 (trùng tên). */
  status?: number;
  connection?: IntegrationConnection;
}

const MAX_LOCAL_ITEMS = 50;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function str(v: unknown, max: number): string | undefined {
  return typeof v === "string" && v.length <= max ? v : undefined;
}

/** Đổi lỗi core thành thông báo an toàn: 403/409/503 tự viết, lỗi khác cắt ~500 ký tự và gỡ token. */
function connectionError(error: unknown, token?: string): ConnectionResult {
  if (error instanceof CoreApiError) {
    if (error.status === 403) {
      return { ok: false, status: 403, error: "Core từ chối yêu cầu (sai khoá truy cập của web tới core). Kiểm tra CORE_API_KEY." };
    }
    if (error.status === 409) {
      return { ok: false, status: 409, error: "Đã có kết nối Jira trùng tên. Hãy đặt tên khác." };
    }
    if (error.status === 503) {
      return {
        ok: false,
        status: 503,
        error:
          "Core chưa bật lưu token (503): thiếu INTEGRATION_SECRET_KEY. Đặt biến này trong .env của core (sinh khoá bằng scripts/gen-env.sh) rồi khởi động lại service api.",
      };
    }
    let msg = error.message.slice(0, 500);
    if (token && token.length >= 4) msg = msg.split(token).join("***");
    return { ok: false, status: error.status, error: msg };
  }
  console.error("kết nối Jira thất bại", error instanceof Error ? error.name : "unknown");
  return { ok: false, error: "Không gọi được core API. Kiểm tra service api." };
}

interface ParsedFields {
  name?: string;
  base_url?: string;
  account_email?: string;
  token?: string;
  config: { jql: string | null; project_key: string | null; project_name: string | null };
}

/**
 * Kiểm kiểu và độ dài các trường biểu mẫu. Server Action là endpoint công khai nên không
 * tin chữ ký TypeScript. Lỗi trả về KHÔNG chứa giá trị người dùng nhập.
 */
function parseFields(input: unknown): ParsedFields | string {
  if (typeof input !== "object" || input === null || Array.isArray(input)) return "Dữ liệu không hợp lệ";
  const r = input as Record<string, unknown>;
  const name = str(r.name, 100)?.trim();
  const baseUrl = str(r.base_url, 2048)?.trim();
  const email = str(r.account_email, 200)?.trim();
  if (!name) return "Tên kết nối bắt buộc (tối đa 100 ký tự)";
  if (!baseUrl) return "URL Jira bắt buộc";
  if (!email) return "Email bắt buộc";
  let token: string | undefined;
  if (r.token !== undefined && r.token !== null && r.token !== "") {
    if (typeof r.token !== "string" || r.token.length < 8 || r.token.length > 512) {
      return "Token phải dài 8-512 ký tự";
    }
    token = r.token;
  }
  const opt = (v: unknown, max: number) => {
    if (v === undefined || v === null || v === "") return null;
    return typeof v === "string" && v.length <= max ? v.trim() || null : undefined;
  };
  const jql = opt(r.jql, 2000);
  const projectKey = opt(r.project_key, 100);
  const projectName = opt(r.project_name, 200);
  if (jql === undefined || projectKey === undefined || projectName === undefined) {
    return "JQL hoặc dự án quá dài";
  }
  return {
    name,
    base_url: baseUrl,
    account_email: email,
    token,
    config: { jql, project_key: projectKey ? projectKey.toUpperCase() : null, project_name: projectName },
  };
}

/**
 * Tạo hoặc sửa một kết nối Jira. Có `id` hợp lệ = sửa, không có = tạo mới.
 *
 * Sửa mà không gửi `token` thì core giữ token cũ. Đổi `base_url` khi kết nối đang có token
 * thì core BẮT BUỘC có token mới (hoặc xoá token), nếu không trả 422: chặn việc gửi token
 * cũ sang host lạ.
 */
export async function saveIntegrationAction(input: unknown): Promise<ConnectionResult> {
  if (IS_LOCAL) return { ok: false, error: "Chỉ dùng được khi DATA_SOURCE=api" };
  const parsed = parseFields(input);
  if (typeof parsed === "string") return { ok: false, error: parsed };
  const rawId = (input as Record<string, unknown>).id;
  try {
    let connection: IntegrationConnection;
    if (rawId === undefined || rawId === null || rawId === "") {
      const body: IntegrationCreateBody = {
        kind: "jira",
        name: parsed.name as string,
        base_url: parsed.base_url as string,
        account_email: parsed.account_email as string,
        config: parsed.config,
      };
      if (parsed.token) body.token = parsed.token;
      connection = await createIntegration(body);
    } else {
      if (typeof rawId !== "string" || !UUID_RE.test(rawId)) return { ok: false, error: "id không hợp lệ" };
      const body: IntegrationUpdateBody = {
        name: parsed.name,
        base_url: parsed.base_url,
        account_email: parsed.account_email,
        config: parsed.config,
        clear_token: false,
      };
      if (parsed.token) body.token = parsed.token;
      connection = await patchIntegration(rawId, body);
    }
    revalidatePath("/data");
    return { ok: true, connection };
  } catch (error) {
    return connectionError(error, parsed.token);
  }
}

/** Xoá token đang lưu của một kết nối (kết nối vẫn còn, phải nhập token mới mới dùng được). */
export async function clearIntegrationTokenAction(id: unknown): Promise<ConnectionResult> {
  if (IS_LOCAL) return { ok: false, error: "Chỉ dùng được khi DATA_SOURCE=api" };
  if (typeof id !== "string" || !UUID_RE.test(id)) return { ok: false, error: "id không hợp lệ" };
  try {
    const connection = await patchIntegration(id, { clear_token: true });
    revalidatePath("/data");
    return { ok: true, connection };
  } catch (error) {
    return connectionError(error);
  }
}

/** Xoá kết nối cùng token đã mã hoá. KHÔNG hoàn tác. */
export async function deleteIntegrationAction(id: unknown): Promise<ConnectionResult> {
  if (IS_LOCAL) return { ok: false, error: "Chỉ dùng được khi DATA_SOURCE=api" };
  if (typeof id !== "string" || !UUID_RE.test(id)) return { ok: false, error: "id không hợp lệ" };
  try {
    await deleteIntegration(id);
    revalidatePath("/data");
    return { ok: true };
  } catch (error) {
    return connectionError(error);
  }
}

export interface MigrateItemResult {
  localId: string;
  name: string;
  ok: boolean;
  error?: string;
}

/**
 * Chuyển các cấu hình Jira cũ trong localStorage lên server (D-B4c), MỘT LẦN.
 *
 * Mỗi mục độc lập: mục lỗi (trùng tên, token ngắn, URL không https...) không chặn mục khác.
 * Client chỉ xoá khỏi localStorage những `localId` có `ok: true`; mục lỗi giữ lại để sửa
 * tay. Token đi qua đây rồi vào core, không bao giờ trả ngược lại.
 */
export async function migrateLocalIntegrationsAction(
  items: unknown,
): Promise<{ ok: boolean; error?: string; results: MigrateItemResult[] }> {
  if (IS_LOCAL) return { ok: false, error: "Chỉ dùng được khi DATA_SOURCE=api", results: [] };
  if (!Array.isArray(items) || items.length === 0 || items.length > MAX_LOCAL_ITEMS) {
    return { ok: false, error: `Cần 1-${MAX_LOCAL_ITEMS} cấu hình`, results: [] };
  }
  const results: MigrateItemResult[] = [];
  for (const raw of items) {
    const rec = typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};
    const localId = str(rec.id, 100) ?? "";
    const nameForUi = str(rec.name, 100) ?? "(không tên)";
    // Cấu hình cũ cho phép gõ "host.atlassian.net" không scheme (code sync cũ tự thêm https).
    let url = str(rec.url, 2048)?.trim().replace(/\/+$/, "");
    if (url && !/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) url = `https://${url}`;
    const parsed = parseFields({
      name: rec.name,
      base_url: url,
      account_email: rec.email,
      token: rec.token,
      jql: rec.jql,
      project_key: rec.projectKey === "NEW" ? "" : rec.projectKey,
      project_name: rec.projectName,
    });
    if (!localId || typeof parsed === "string") {
      results.push({ localId, name: nameForUi, ok: false, error: typeof parsed === "string" ? parsed : "Thiếu id" });
      continue;
    }
    if (!parsed.token) {
      results.push({ localId, name: nameForUi, ok: false, error: "Thiếu token" });
      continue;
    }
    try {
      await createIntegration({
        kind: "jira",
        name: parsed.name as string,
        base_url: parsed.base_url as string,
        account_email: parsed.account_email as string,
        token: parsed.token,
        config: parsed.config,
      });
      results.push({ localId, name: nameForUi, ok: true });
    } catch (error) {
      const failed = connectionError(error, parsed.token);
      results.push({
        localId,
        name: nameForUi,
        ok: false,
        error:
          failed.status === 409
            ? "trùng tên với một kết nối đã có trên server; bấm Bỏ khỏi trình duyệt rồi tạo lại bằng form với tên khác"
            : failed.error,
      });
      // Thiếu khoá phía core: các mục sau cũng sẽ hỏng y hệt, dừng sớm.
      if (failed.status === 503) break;
    }
  }
  revalidatePath("/data");
  return { ok: results.length > 0 && results.every((r) => r.ok), results };
}

// ── Sync theo kết nối đã lưu (B4b) ──────────────────────────────

export type SyncActionResult =
  | { ok: true; result: IntegrationSyncResult }
  | { ok: false; error: string; status?: number };

const SECRET_RE = /^[\x20-\x7e]{1,256}$/;
const SINCE_RE = /^\d{4}-\d{2}-\d{2}(?:[T ][0-9:.]+(?:Z|[+-]\d{2}:?\d{2})?)?$/;

/** Thông báo TỰ VIẾT cho lỗi sync: không echo detail của core (có thể chứa input hay chi tiết Jira). */
function syncError(error: unknown): SyncActionResult {
  if (error instanceof CoreApiError) {
    const status = error.status;
    const msgs: Record<number, string> = {
      403: "Sai mật khẩu nhập/đồng bộ (hoặc core chưa cấu hình IMPORT_COMMIT_SECRET).",
      409: "Không đồng bộ được: đang có lượt đồng bộ khác chạy cho kết nối này, hoặc kết nối chưa có token. Đợi lượt kia xong hoặc nhập token.",
      422: "Core từ chối tham số: ngày bắt đầu, JQL hoặc host Jira không hợp lệ (chỉ hỗ trợ Jira Cloud).",
      502: "Core không gọi được Jira hoặc Jira trả lỗi. Kiểm tra URL, email, token và quyền.",
      503: "Core không giải mã được token đã lưu. Hãy nhập lại token cho kết nối này.",
      504: "Đồng bộ quá thời gian. Thu hẹp JQL hoặc dùng ô Từ ngày rồi thử lại.",
    };
    return { ok: false, status, error: msgs[status] ?? "Đồng bộ thất bại. Xem log của core." };
  }
  console.error("sync tích hợp thất bại", error instanceof Error ? error.name : "unknown");
  return { ok: false, error: "Không gọi được core API hoặc quá thời gian chờ. Kiểm tra service api rồi thử lại." };
}

/**
 * Cào Jira cho một kết nối đã lưu, qua core (chế độ api). Core giữ token, web không bao giờ thấy nó.
 *
 * `secret` là IMPORT_COMMIT_SECRET: chỉ đi vào header, không log, không echo. `since` tuỳ chọn
 * (YYYY-MM-DD hoặc ISO) để thu hẹp khi JQL quá rộng (chạm trần 100 trang). Có thể kéo dài hàng
 * phút nên UI phải khoá nút khi đang chạy.
 */
export async function syncIntegrationAction(id: unknown, secret: unknown, since?: unknown): Promise<SyncActionResult> {
  if (IS_LOCAL) return { ok: false, error: "Chỉ dùng được khi DATA_SOURCE=api" };
  if (typeof id !== "string" || !UUID_RE.test(id)) return { ok: false, error: "id không hợp lệ" };
  if (typeof secret !== "string" || !SECRET_RE.test(secret)) {
    return { ok: false, error: "Cần nhập mật khẩu (1-256 ký tự ASCII hiển thị được)." };
  }
  let sinceValue: string | undefined;
  if (since !== undefined && since !== null && since !== "") {
    if (typeof since !== "string" || since.length > 40 || !SINCE_RE.test(since) || Number.isNaN(Date.parse(since))) {
      return { ok: false, error: "Ngày bắt đầu không hợp lệ (dùng YYYY-MM-DD)." };
    }
    sinceValue = since;
  }
  try {
    const result = await syncIntegration(id, secret, sinceValue);
    revalidatePath("/data");
    revalidatePath("/", "layout");
    return { ok: true, result };
  } catch (error) {
    return syncError(error);
  }
}
