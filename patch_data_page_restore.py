import sys
with open("apps/web/app/data/page.tsx", "r") as f:
    c = f.read()

c = c.replace(
    'import { WipeDataManager } from "@/components/wipe-data-manager";',
    'import { WipeDataManager } from "@/components/wipe-data-manager";\nimport { RestoreJsonManager } from "@/components/restore-json-manager";'
)

c = c.replace(
    '<WipeDataManager />',
    '<RestoreJsonManager />\n        <WipeDataManager />'
)

with open("apps/web/app/data/page.tsx", "w") as f:
    f.write(c)

