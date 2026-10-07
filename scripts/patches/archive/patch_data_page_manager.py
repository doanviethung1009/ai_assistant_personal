import sys
with open("apps/web/app/data/page.tsx", "r") as f:
    c = f.read()

c = c.replace(
    'import { UrlSyncForm } from "@/components/url-sync-form";',
    'import { UrlSyncManager } from "@/components/url-sync-manager";\nimport { getSyncUrlsApi } from "@/lib/api";'
)
c = c.replace(
    "export default async function DataPage() {",
    "export default async function DataPage() {\n  const syncUrls = await getSyncUrlsApi();"
)
c = c.replace(
    "<UrlSyncForm />",
    "<UrlSyncManager initialUrls={syncUrls} />"
)
with open("apps/web/app/data/page.tsx", "w") as f:
    f.write(c)
print("Patched data page to use UrlSyncManager")
