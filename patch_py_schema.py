import sys

file_path = "apps/core/app/schemas/task.py"
with open(file_path, "r") as f:
    content = f.read()

target = "description: str | None = None"
new_text = "description: str | None = None\n    assignee: str | None = None"
content = content.replace(target, new_text)

with open(file_path, "w") as f:
    f.write(content)
print("Patched schemas/task.py")
