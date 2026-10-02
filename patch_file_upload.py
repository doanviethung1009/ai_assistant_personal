import sys

file_path = "apps/web/components/file-upload-manager.tsx"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'if (!wsname) throw new Error("Sheet không hợp lệ");\n        const ws = wb.Sheets[wsname];',
    'if (!wsname) throw new Error("Sheet không hợp lệ");\n        const ws = wb.Sheets[wsname];\n        if (!ws) throw new Error("Không lấy được Sheet");'
)

with open(file_path, "w") as f:
    f.write(c)

file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'return (async () => {',
    '// no wrapper'
)
c = c.replace(
    '    return { ok: true, added, updated };\n  });',
    '    return { ok: true, added, updated };'
)

with open(file_path, "w") as f:
    f.write(c)
