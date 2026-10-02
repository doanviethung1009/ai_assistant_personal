import sys
file_path = "apps/web/app/team/page.tsx"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "let teamTasks = allTasks.filter(t => t.assignee);",
    "let teamTasks = allTasks.filter(t => t.assignee && t.assignee !== \"Đoàn Việt Hưng\");"
)

with open(file_path, "w") as f:
    f.write(c)
print("Excluded Đoàn Việt Hưng from Team page")
