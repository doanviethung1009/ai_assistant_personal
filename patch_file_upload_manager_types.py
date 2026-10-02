import sys

file_path = "apps/web/components/file-upload-manager.tsx"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'if (res.ok) {',
    'if (res.ok && "added" in res) {'
)
c = c.replace(
    'message: `Lỗi: ${res.error}`',
    'message: `Lỗi: ${"error" in res ? res.error : "Unknown error"}`'
)

with open(file_path, "w") as f:
    f.write(c)
