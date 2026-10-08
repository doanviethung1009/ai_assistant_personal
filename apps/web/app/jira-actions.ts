"use server";

import { revalidatePath } from "next/cache";
import {
  CoreApiError,
  IS_LOCAL,
  createIntegration,
  deleteIntegration,
  patchIntegration,
} from "@/lib/api";
import type { IntegrationConnection, IntegrationCreateBody, IntegrationUpdateBody } from "@/lib/types";
import * as engine from "@/lib/store/engine";
import { uuid, nowIso } from "@/lib/store/engine";
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

export async function syncJiraAction(formData: FormData) {
  if (!IS_LOCAL) {
    return { ok: false, error: "Đồng bộ Jira ở chế độ api cần pha B4b (endpoint sync phía core chưa có). Hiện chỉ chạy được ở chế độ Local File." };
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
  
  // Xử lý URL
  let baseUrl = url.trim().replace(/\/$/, "");
  if (!baseUrl.startsWith("http")) {
    baseUrl = "https://" + baseUrl;
  }
  
  // Tạo JQL
  let jql = "";
  if (customJql && customJql.trim() !== "") {
    jql = customJql.trim();
    // Tự động nhận diện nếu user chỉ gõ mã dự án (ví dụ "DBA" hoặc "DBA, PROJ")
    if (!jql.includes("=") && !jql.toLowerCase().includes(" in ") && !jql.toLowerCase().includes(" is ") && !jql.includes("~")) {
      const spaces = jql.split(",").map(s => `"${s.trim()}"`).join(",");
      jql = `project in (${spaces}) ORDER BY updated DESC`;
    }
  } else {
    // Lấy task assign cho mình theo cài đặt Tên người dùng cá nhân (danh sách)
    const storeUsers = engine.state().currentUsers || [];
    if (storeUsers.length > 0) {
      const usersStr = storeUsers.map(u => `"${u}"`).join(", ");
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
  
  try {
    const authHeader = `Basic ${Buffer.from(`${email.trim()}:${token.trim()}`).toString('base64')}`;
    
    let allIssues: any[] = [];
    const fieldNames: Record<string, string> = {};
    let nextPageToken: string | undefined = undefined;
    let hasMore = true;
    let pagesFetched = 0;

    while (hasMore && pagesFetched < 100) { // Nâng giới hạn lên 100 trang * 100 = 10,000 tasks
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
        body: JSON.stringify(body)
      });
      
      if (!res.ok) {
        const errorText = await res.text();
        console.error("Jira API Error:", res.status, errorText);
        if (res.status === 401 || res.status === 403) {
          return { ok: false, error: `Xác thực thất bại (Sai Email/Token hoặc thiếu quyền). Jira: ${errorText}` };
        }
        return { ok: false, error: `Jira trả về lỗi: ${res.status} ${res.statusText}. Chi tiết: ${errorText}` };
      }
      
      const data = await res.json();
      if (data.names) Object.assign(fieldNames, data.names);
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

    for (const issue of allIssues) {
      const issueKey = issue.key;
      const fields = issue.fields || {};
      
      const title = fields.summary || "No Title";
      
      // Parse description for v2 (string) vs v3 (Atlassian Document Format)
      let description = null;
      if (typeof fields.description === 'string') {
        description = fields.description;
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
          due_at: fields.duedate ? new Date(fields.duedate).toISOString() : null,
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
    
    return { ok: true, added, updated, skipped_personal: skippedPersonal };

  } catch (error: any) {
    return { ok: false, error: "Lỗi kết nối tới Jira: " + error.message };
  }
}

// ═══════════════════════════════════════════════════════════════════════
//  Kết nối Jira lưu ở core (chế độ api, B4a)
// ═══════════════════════════════════════════════════════════════════════
//
// TOKEN LÀ WRITE-ONLY. Nó đi một chiều: form -> Server Action -> core (mã hoá ở core). Không
// hàm nào dưới đây trả token về client, không log, và thông báo lỗi được lọc để không lặp
// lại token dù core có lỡ echo. Sync thật (`/integrations/{id}/sync`) thuộc B4b, chưa có.

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
