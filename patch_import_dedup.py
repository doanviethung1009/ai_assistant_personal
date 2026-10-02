import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'let assignedProject = db.projects.find((p: any) => p.key === projectKey);',
    'let assignedProject = db.projects.find((p: any) => p.key.toUpperCase() === projectKey.toUpperCase());'
)

with open(file_path, "w") as f:
    f.write(c)

print("Patched project deduplication in actions-import.ts")
