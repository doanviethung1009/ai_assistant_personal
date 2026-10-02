import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

old_code = """    for (const ticket of rows) {
      const key = ticket['Issue Key'] || ticket['Key'];
      if (!key) continue;

      const issueKey = String(key);"""

new_code = """    for (const ticket of rows) {
      const summary = ticket['Summary'] || ticket['Title'];
      if (!summary) continue;

      const key = ticket['Issue Key'] || ticket['Key'];
      const issueKey = key ? String(key) : null;"""

c = c.replace(old_code, new_code)

old_code2 = """      const keyParts = issueKey.split('-');
      const projectKey = keyParts.length > 1 ? keyParts[0].toUpperCase() : null;"""

new_code2 = """      const keyParts = issueKey ? issueKey.split('-') : [];
      const projectKey = keyParts.length > 1 ? keyParts[0].toUpperCase() : null;"""

c = c.replace(old_code2, new_code2)

old_code3 = """      let task = db.tasks.find((t: any) => t.external_id === key);"""

new_code3 = """      let task = db.tasks.find((t: any) => 
        (issueKey && t.external_id === issueKey) || 
        (!issueKey && t.title.toLowerCase() === finalTitle.toLowerCase())
      );"""

c = c.replace(old_code3, new_code3)

# For creation, use issueKey or null
old_code4 = """          external_id: key,
          external_url: `https://onemount.atlassian.net/browse/${key}`,"""

new_code4 = """          external_id: issueKey,
          external_url: issueKey ? `https://onemount.atlassian.net/browse/${issueKey}` : null,"""

c = c.replace(old_code4, new_code4)


with open(file_path, "w") as f:
    f.write(c)

