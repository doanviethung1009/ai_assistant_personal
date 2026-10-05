"use server";

import { revalidatePath } from "next/cache";
import { IS_LOCAL } from "@/lib/api";
import * as engine from "@/lib/store/engine";
import { uuid, nowIso } from "@/lib/store/engine";

export async function syncJiraAction(formData: FormData) {
  if (!IS_LOCAL) {
    return { ok: false, error: "Chỉ hỗ trợ chế độ Local File (Jira Sync ở Phase 1 chỉ hỗ trợ local engine)" };
  }
  
  const url = formData.get("url") as string;
  const email = formData.get("email") as string;
  const token = formData.get("token") as string;
  const customJql = formData.get("jql") as string;
  
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
  
  const searchUrl = `${baseUrl}/rest/api/3/search/jql`;
  
  try {
    const authHeader = `Basic ${Buffer.from(`${email.trim()}:${token.trim()}`).toString('base64')}`;
    
    let allIssues: any[] = [];
    let nextPageToken: string | undefined = undefined;
    let hasMore = true;
    let pagesFetched = 0;

    while (hasMore && pagesFetched < 100) { // Nâng giới hạn lên 100 trang * 100 = 10,000 tasks
      const body: any = {
        jql: jql,
        maxResults: 100, // Tối ưu: Lấy 100 kết quả mỗi trang thay vì 50
        fields: ["summary", "status", "created", "updated", "resolutiondate", "duedate", "assignee", "project", "labels", "description"]
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
    let updated = 0;
    
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
      
      const tags = ['jira'];
      if (fields.project?.key) {
        tags.push(fields.project.key.toLowerCase());
      }
      if (Array.isArray(fields.labels)) {
         fields.labels.forEach((l: string) => tags.push(l.toLowerCase()));
      }
      
      const validTags = tags.filter(t => t.length > 0);
      
      let task = db.tasks.find((t: any) => t.external_id === issueKey);
      
      const resolvedAt = fields.resolutiondate 
        ? new Date(fields.resolutiondate).toISOString() 
        : (fields.updated ? new Date(fields.updated).toISOString() : nowIso());
        
      if (task) {
        task.title = title;
        if (!task.description) task.description = description; 
        task.status = status as any;
        task.tags = Array.from(new Set([...task.tags, ...validTags]));
        task.updated_at = nowIso();
        if (status === 'done') {
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
          completed_at: status === 'done' ? resolvedAt : null,
          tags: Array.from(new Set(validTags)),
          source: 'jira',
          external_id: issueKey,
          external_url: `${baseUrl}/browse/${issueKey}`,
          assignee: fields.assignee?.displayName || null,
          created_at: fields.created ? new Date(fields.created).toISOString() : nowIso(),
          updated_at: nowIso(),
          deleted_at: null,
          events: [],
        };
        db.tasks.unshift(task);
        added++;
      }
    }
    
    engine.touched();
    revalidatePath('/', 'layout');
    
    return { ok: true, added, updated };
    
  } catch (error: any) {
    return { ok: false, error: "Lỗi kết nối tới Jira: " + error.message };
  }
}
