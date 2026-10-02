import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'keyParts[0].toUpperCase()',
    'keyParts[0]?.toUpperCase()'
)
c = c.replace(
    'titleMatch[2].trim()',
    'titleMatch[2]?.trim()'
)
c = c.replace(
    'deleted_at: null',
    'is_archived: false'
)

# Fix assignedProject undefined issues by using a non-null assertion or separate type
c = c.replace(
    'let assignedProject = db.projects.find((p: any) => p.key === projectKey);',
    'let assignedProject = db.projects.find((p: any) => p.key === projectKey) as any;'
)

with open(file_path, "w") as f:
    f.write(c)

