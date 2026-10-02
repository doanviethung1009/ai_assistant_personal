import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'finalTitle = titleMatch[2]?.trim();',
    'finalTitle = titleMatch[2]?.trim() || finalTitle;'
)

# For Task object:
c = c.replace(
    'updated_at: nowIso(),\n          is_archived: false,\n          events: [],',
    'updated_at: nowIso(),\n          deleted_at: null,\n          events: [],'
)

with open(file_path, "w") as f:
    f.write(c)

