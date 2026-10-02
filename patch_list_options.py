import sys
file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "offset?: number;\n}",
    "offset?: number;\n  assignee?: string | null;\n  forCurrentUser?: boolean;\n}"
)
with open(file_path, "w") as f:
    f.write(c)
