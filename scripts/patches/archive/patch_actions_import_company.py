import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

old_logic = """      const issueKey = key ? String(key) : null;
      const keyParts = issueKey ? issueKey.split('-') : [];
      const projectKey = keyParts.length > 1 ? keyParts[0].toUpperCase() : null;

      let finalTitle = String(ticket['Summary'] || "No Title");
      const titleMatch = finalTitle.match(/^\[([^\]]+)\]\s*(.*)$/);
      if (titleMatch) {
        finalTitle = titleMatch[2]?.trim() || finalTitle;
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
        let assignedProject = db.projects.find((p: any) => p.key.toUpperCase() === projectKey.toUpperCase()) as any;
        
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
            is_archived: false
          };
          db.projects.push(assignedProject);
        }

        projectId = assignedProject.id;
        projectObj = { id: assignedProject.id, key: assignedProject.key, name: assignedProject.name, color: assignedProject.color };
        
        const projectTag = assignedProject.key.toLowerCase();
        if (!tags.includes(projectTag)) tags.push(projectTag);
      }"""

new_logic = """      const issueKey = key ? String(key) : null;
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
      
      // Add Company to tags
      if (companyName !== "Others") {
        tags.push(companyName.toLowerCase().replace(/[^a-z0-9]/g, ''));
      }

      // Add Labels
      if (ticket['Labels']) {
        tags.push(...String(ticket['Labels']).split(',').map(s => s.trim().toLowerCase()));
      }
      
      // Add all bracket tags as tags
      bracketMatches.forEach(b => {
        const cleanB = b.toLowerCase().replace(/[^a-z0-9]/g, '');
        if (cleanB && !ignoreAsCompany.includes(b.toUpperCase())) {
          tags.push(cleanB);
        }
      });

      let projectId = null;
      let projectObj = null;

      // Auto-create Project based on Company
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
      }"""

c = c.replace(old_logic, new_logic)

with open(file_path, "w") as f:
    f.write(c)

