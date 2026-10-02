import sys

# 1. Update engine.ts
file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "if (options.assignee && t.assignee !== options.assignee) return false;",
    """if (options.forCurrentUser) {
      if (t.assignee !== null && t.assignee !== "Đoàn Việt Hưng") return false;
    } else if (options.assignee && t.assignee !== options.assignee) {
      return false;
    }"""
)
with open(file_path, "w") as f:
    f.write(c)

# 2. Update api.ts ListTasksOptions
file_path = "apps/web/lib/api.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "assignee?: string | null;",
    "assignee?: string | null;\n  forCurrentUser?: boolean;"
)
c = c.replace(
    "if (options.assignee) params.append(\"assignee\", options.assignee);",
    "if (options.assignee) params.append(\"assignee\", options.assignee);\n  if (options.forCurrentUser) params.append(\"forCurrentUser\", \"1\");"
)
with open(file_path, "w") as f:
    f.write(c)

# 3. Update /tasks/page.tsx
file_path = "apps/web/app/tasks/page.tsx"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "query: params.q,",
    "query: params.q,\n        forCurrentUser: true,"
)
with open(file_path, "w") as f:
    f.write(c)

# 4. Update /page.tsx (Home/Dashboard)
file_path = "apps/web/app/page.tsx"
with open(file_path, "r") as f:
    c = f.read()

# For Dashboard, we should probably also only show my tasks
c = c.replace(
    "listTasks({ scheduledOn: todayInDisplayTz() }),",
    "listTasks({ scheduledOn: todayInDisplayTz(), forCurrentUser: true }),"
)
c = c.replace(
    "listTasks({ dueBefore: new Date().toISOString(), includeClosed: false }),",
    "listTasks({ dueBefore: new Date().toISOString(), includeClosed: false, forCurrentUser: true }),"
)
with open(file_path, "w") as f:
    f.write(c)

print("Patched lists to filter for current user")
