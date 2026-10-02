import sys

file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

target = """  if (options.projectId) {
    result = result.filter((t) => t.project_id === options.projectId);
  }"""

new_code = """  if (options.projectId) {
    result = result.filter((t) => t.project_id === options.projectId);
  }
  
  if (options.forCurrentUser) {
    result = result.filter((t) => t.assignee === null || t.assignee === "Đoàn Việt Hưng");
  } else if (options.assignee) {
    result = result.filter((t) => t.assignee === options.assignee);
  }"""

c = c.replace(target, new_code)
with open(file_path, "w") as f:
    f.write(c)

print("Fixed listTasks in engine.ts")
