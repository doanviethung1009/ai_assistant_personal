import sys
with open("apps/web/app/data/page.tsx", "r") as f:
    c = f.read()

c = c.replace(
    'import { UrlSyncManager } from "@/components/url-sync-manager";',
    'import { UrlSyncManager } from "@/components/url-sync-manager";\nimport { FileUploadManager } from "@/components/file-upload-manager";'
)
c = c.replace(
    '<UrlSyncManager initialUrls={syncUrls} />',
    '<UrlSyncManager initialUrls={syncUrls} />\n        <FileUploadManager />'
)
with open("apps/web/app/data/page.tsx", "w") as f:
    f.write(c)

print("Added file upload to DataPage")
