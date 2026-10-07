import sys
file_path = "apps/web/lib/api.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "pinnedOnly?: boolean;\n}",
    "pinnedOnly?: boolean;\n  assignee?: string | null;\n}"
)
c = c.replace(
    "if (options.status) params.append(\"status\", options.status);",
    "if (options.status) params.append(\"status\", options.status);\n  if (options.assignee) params.append(\"assignee\", options.assignee);"
)

with open(file_path, "w") as f:
    f.write(c)

file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "if (options.status && t.status !== options.status) return false;",
    "if (options.status && t.status !== options.status) return false;\n    if (options.assignee && t.assignee !== options.assignee) return false;"
)
with open(file_path, "w") as f:
    f.write(c)
print("Patched api.ts and engine.ts for listTasks filter")
