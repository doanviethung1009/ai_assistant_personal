import sys

with open("apps/web/app/actions.ts", "r") as f:
    content = f.read()

# Fix SheetNames[0]
content = content.replace(
    "const sheet = workbook.Sheets[workbook.SheetNames[0]];",
    "const sheetName = workbook.SheetNames[0];\n    if (!sheetName) throw new Error('No sheet');\n    const sheet = workbook.Sheets[sheetName];"
)

# Fix listProjects
content = content.replace(
    "const { items: projects } = await api.listProjects();",
    "const projects = await api.listProjects();"
)
content = content.replace(
    "const projectMap = Object.fromEntries(projects.map(p => [p.key.toUpperCase(), p]));",
    "const projectMap = Object.fromEntries(projects.map((p: any) => [p.key.toUpperCase(), p]));"
)

# Fix match[1] and match[2]
old_match = """      if (match) {
        const prefix = match[1].toUpperCase();"""
new_match = """      if (match && match[1] && match[2]) {
        const prefix = match[1].toUpperCase();"""
content = content.replace(old_match, new_match)

# Fix source: 'jira' - it's external_id and external_url, source is usually set inside backend or just omit it if it doesn't exist
content = content.replace(
    "source: 'jira',",
    ""
)

with open("apps/web/app/actions.ts", "w") as f:
    f.write(content)
print("Fixed actions.ts")
