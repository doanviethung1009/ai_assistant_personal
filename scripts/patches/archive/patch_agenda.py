import sys
file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "const tasks = aliveTasks();",
    "const tasks = aliveTasks().filter((t) => t.assignee === null || t.assignee === \"Đoàn Việt Hưng\");"
)
with open(file_path, "w") as f:
    f.write(c)

print("Patched getAgenda to filter for current user")
