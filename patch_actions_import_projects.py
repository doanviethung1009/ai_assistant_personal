import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

import re

# We need to replace the logic inside the loop.
# Finding the block to replace.
old_logic = """      const titleRaw = `[${ticket['Projects'] || 'JIRA'}] ${ticket['Summary']}`;
      
      const statusMap: Record<string, string> = {
        'To Do': 'todo',
        'In Progress': 'in_progress',
        'Done': 'done',
        'Closed': 'done',
      };
      const status = statusMap[ticket['Status']] || 'todo';
      
      const tags = ['jira'];
      if (ticket['Labels']) {
        tags.push(...String(ticket['Labels']).split(',').map(s => s.trim().toLowerCase()));
      }

      const match = titleRaw.match(/^\[([^\]]+)\]\s*(.*)$/);
      let projectId = null;
      let projectObj = null;
      let finalTitle = titleRaw;
      
      if (match) {
        const prefix = match[1]?.toUpperCase() || "";
        const projectKeys = ['MAG', 'OM', 'IOTEK', 'GIAI', 'CBP'];
        const matchedKey = projectKeys.find(k => prefix.startsWith(k));
        
        if (matchedKey) {
          const assignedProject = db.projects.find((p: any) => p.key === matchedKey);
          if (assignedProject) {
            projectId = assignedProject.id;
            projectObj = { id: assignedProject.id, key: assignedProject.key, name: assignedProject.name, color: assignedProject.color };
            const projectTag = assignedProject.key.toLowerCase();
            if (!tags.includes(projectTag)) tags.push(projectTag);
            finalTitle = match[2]?.trim() || finalTitle;
          }
        }
      }"""

new_logic = """      const issueKey = String(key);
      const keyParts = issueKey.split('-');
      const projectKey = keyParts.length > 1 ? keyParts[0].toUpperCase() : null;

      let finalTitle = String(ticket['Summary'] || "No Title");
      const titleMatch = finalTitle.match(/^\[([^\]]+)\]\s*(.*)$/);
      if (titleMatch) {
        finalTitle = titleMatch[2].trim();
      }
      
      const statusMap: Record<string, string> = {
        'To Do': 'todo',
        'In Progress': 'in_progress',
        'Done': 'done',
        'Closed': 'done',
      };
      const status = statusMap[ticket['Status']] || 'todo';
      
      const tags = ['jira'];
      if (ticket['Labels']) {
        tags.push(...String(ticket['Labels']).split(',').map(s => s.trim().toLowerCase()));
      }

      let projectId = null;
      let projectObj = null;

      if (projectKey) {
        let assignedProject = db.projects.find((p: any) => p.key === projectKey);
        
        // Auto-create project if it doesn't exist
        if (!assignedProject) {
          const rawProjectName = ticket['Projects'] ? String(ticket['Projects']) : projectKey;
          assignedProject = {
            id: uuid(),
            key: projectKey,
            name: rawProjectName,
            color: "zinc",
            created_at: nowIso(),
            updated_at: nowIso(),
            deleted_at: null
          };
          db.projects.push(assignedProject);
        }

        projectId = assignedProject.id;
        projectObj = { id: assignedProject.id, key: assignedProject.key, name: assignedProject.name, color: assignedProject.color };
        
        const projectTag = assignedProject.key.toLowerCase();
        if (!tags.includes(projectTag)) tags.push(projectTag);
      }"""

c = c.replace(old_logic, new_logic)

with open(file_path, "w") as f:
    f.write(c)

