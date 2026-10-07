import sys
with open("apps/web/app/data/page.tsx", "r") as f:
    c = f.read()

c = c.replace(
    'import { FileUploadManager } from "@/components/file-upload-manager";',
    'import { FileUploadManager } from "@/components/file-upload-manager";\nimport { ChromeHistoryManager } from "@/components/chrome-history-manager";\nimport { WipeDataManager } from "@/components/wipe-data-manager";'
)

c = c.replace(
    '<FileUploadManager />',
    '<FileUploadManager />\n        <ChromeHistoryManager />\n        <WipeDataManager />'
)

with open("apps/web/app/data/page.tsx", "w") as f:
    f.write(c)
