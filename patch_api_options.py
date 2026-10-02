import sys
file_path = "apps/web/lib/api.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "sortDesc?: boolean;\n}",
    "sortDesc?: boolean;\n  assignee?: string | null;\n  forCurrentUser?: boolean;\n}"
)
with open(file_path, "w") as f:
    f.write(c)

print("Patched api options")
