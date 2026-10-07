import sys
file_path = "apps/web/app/actions-chrome.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'import { scrapeChromeHistory } from "@/lib/chrome-history";',
    'import { scrapeChromeHistory } from "@/lib/chrome-history";\nimport { revalidatePath } from "next/cache";'
)

c = c.replace(
    'return { ok: true, count: res.count, path: res.savedPath };',
    'revalidatePath("/history");\n    revalidatePath("/data");\n    return { ok: true, count: res.count, path: res.savedPath };'
)

with open(file_path, "w") as f:
    f.write(c)

print("Patched actions-chrome.ts")
