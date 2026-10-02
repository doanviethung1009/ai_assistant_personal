import sys

file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'import { local, IS_LOCAL } from "@/lib/api";',
    'import { IS_LOCAL } from "@/lib/api";'
)
c = c.replace(
    'import { engine } from "@/lib/store";',
    'import * as engine from "@/lib/store/engine";'
)
c = c.replace(
    'return local(() => {',
    'return (async () => {'
)
c = c.replace(
    'const prefix = match[1].toUpperCase();',
    'const prefix = match[1]?.toUpperCase() || "";'
)
c = c.replace(
    'finalTitle = match[2].trim();',
    'finalTitle = match[2]?.trim() || finalTitle;'
)

with open(file_path, "w") as f:
    f.write(c)

file_path = "apps/web/components/file-upload-manager.tsx"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'const ws = wb.Sheets[wsname];',
    'if (!wsname) throw new Error("Sheet không hợp lệ");\n        const ws = wb.Sheets[wsname];'
)

with open(file_path, "w") as f:
    f.write(c)
