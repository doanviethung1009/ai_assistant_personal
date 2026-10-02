import sys

file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

# patch makeTask
c = c.replace(
    "is_overdue: false,\n    days_until_purge: null,",
    "is_overdue: false,\n    days_until_purge: null,\n    assignee: (input as any).assignee ?? null,"
)

# patch patchTask
c = c.replace(
    "if (\"priority\" in input) task.priority = input.priority as TaskPriority;",
    "if (\"priority\" in input) task.priority = input.priority as TaskPriority;\n  if (\"assignee\" in input) task.assignee = (input.assignee as string | null) ?? null;"
)

with open(file_path, "w") as f:
    f.write(c)
print("Patched engine.ts for assignee")
