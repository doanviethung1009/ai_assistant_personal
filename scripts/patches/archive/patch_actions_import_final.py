import sys
import re

file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

# Define the new function body
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
    const keyParts = issueKey ? issueKey.split('-') : [];
    const jiraProjectCode = keyParts.length > 1 ? keyParts[0].toUpperCase() : null; // e.g., DBA

    let rawSummary = String(ticket['Summary'] || "No Title");
    
    // Extract all bracket tags
    const bracketMatches = [...rawSummary.matchAll(/\\[(.*?)\\]/g)].map(m => m[1].trim());
    
    // Clean title from brackets at the beginning
    let finalTitle = rawSummary.replace(/^(\\[.*?\\]\\s*)+/, '').trim();
    if (!finalTitle) finalTitle = rawSummary;

    // Determine Company (Project)
    const ignoreAsCompany = ['PROD', 'NON-PROD', 'NONPROD', 'UAT', 'STAGING', 'DEV', 'TEST', 'LIVE', 'HOTFIX', 'BUG', 'REVERT', 'QA', 'QC'];
    let companyName = "Others";
    
    const validBrackets = bracketMatches.filter(b => !ignoreAsCompany.includes(b.toUpperCase()));
    if (validBrackets.length > 0) {
      companyName = validBrackets[0];
    }

    const statusMap: Record<string, string> = {
      'To Do': 'todo',
      'In Progress': 'in_progress',
      'Done': 'done',
      'Closed': 'done',
    };
    const status = statusMap[ticket['Status']] || 'todo';
    
    const tags = ['jira'];
    if (jiraProjectCode) tags.push(jiraProjectCode.toLowerCase());
    
    if (companyName !== "Others") {
      tags.push(companyName.toLowerCase().replace(/[^a-z0-9]/g, ''));
    }

    if (ticket['Labels']) {
      tags.push(...String(ticket['Labels']).split(',').map(s => s.trim().toLowerCase()));
    }
    
    bracketMatches.forEach(b => {
      const cleanB = b.toLowerCase().replace(/[^a-z0-9]/g, '');
      if (cleanB && !ignoreAsCompany.includes(b.toUpperCase())) {
        tags.push(cleanB);
      }
    });

    let projectId = null;
    let projectObj = null;

    const projectKey = companyName.toUpperCase().replace(/[^A-Z0-9]/g, '').substring(0, 10);
    
    if (projectKey) {
      let assignedProject = db.projects.find((p: any) => p.key.toUpperCase() === projectKey) as any;
      
      if (!assignedProject) {
        assignedProject = {
          id: uuid(),
          key: projectKey,
          name: companyName,
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
    
    if (task) {
      task.title = finalTitle;
      task.description = ticket['Description'] || null;
      task.status = status as any;
      task.project_id = projectId;
      task.project = projectObj as any;
      task.due_at = dueAt;
      task.completed_at = completedAt;
      task.tags = Array.from(new Set([...task.tags.map((t: string) => t.toLowerCase()), ...tags.map((t: string) => t.toLowerCase())]));
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
        tags: Array.from(new Set(tags.map((t: string) => t.toLowerCase()))),
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
}"""

# Use regex to replace the function
pattern = re.compile(r'export async function importBulkTasksAction\(rows: any\[\]\) \{.*?return \{ ok: true, added, updated \};\n\}', re.DOTALL)
c = pattern.sub(new_func, c)

with open(file_path, "w") as f:
    f.write(c)

