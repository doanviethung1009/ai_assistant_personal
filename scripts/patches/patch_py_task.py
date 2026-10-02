import sys

file_path = "apps/core/app/models/task.py"
with open(file_path, "r") as f:
    content = f.read()

target = "description: Mapped[str | None] = mapped_column(Text, default=None)"
new_text = "description: Mapped[str | None] = mapped_column(Text, default=None)\n    assignee: Mapped[str | None] = mapped_column(String(200), default=None, index=True)"
content = content.replace(target, new_text)

with open(file_path, "w") as f:
    f.write(content)
print("Patched models/task.py")
