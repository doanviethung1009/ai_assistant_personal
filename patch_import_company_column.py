import sys

file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

start_idx = c.find("export async function importBulkTasksAction(rows: any[]) {")
end_idx = c.find("export async function importBulkFileAction(formData: FormData) {")

if start_idx != -1 and end_idx != -1:
    new_func = """export async function importBulkTasksAction(rows: any[]) {
  if (!IS_LOCAL) throw new Error("Chỉ hỗ trợ chế độ Local File");

  const db = engine.state();
  let added = 0;
  let updated = 0;

  for (const ticket of rows) {
    const summary = ticket['Summary'] || ticket['Title'];
    if (!summary) continue;

    const key = ticket['Issue Key'] || ticket['Key'];
    const issueKey = key ? String(key) : null;
    
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
          color: "zinc",
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
    
    let task = db.tasks.find((t: any) => 
      (issueKey && t.external_id === issueKey) || 
      (!issueKey && t.title.toLowerCase() === finalTitle.toLowerCase())
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
  return { ok: true, added, updated };
}

import * as XLSX from "xlsx";
"""
    c = c[:start_idx] + new_func + c[end_idx + len("import * as XLSX from \"xlsx\";\n"):]
    with open(file_path, "w") as f:
        f.write(c)

