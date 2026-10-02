import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'task.tags = Array.from(new Set([...task.tags, ...tags]));',
    'task.tags = Array.from(new Set([...task.tags.map((t: string) => t.toLowerCase()), ...tags.map((t: string) => t.toLowerCase())]));'
)

c = c.replace(
    'tags: Array.from(new Set(tags)),',
    'tags: Array.from(new Set(tags.map((t: string) => t.toLowerCase()))),'
)

with open(file_path, "w") as f:
    f.write(c)

