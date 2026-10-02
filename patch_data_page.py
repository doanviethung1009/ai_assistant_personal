import sys

with open("apps/web/app/data/page.tsx", "r") as f:
    content = f.read()

# Add import
import_stmt = 'import { UrlSyncForm } from "@/components/url-sync-form";'
content = content.replace(
    'import { DataImport } from "@/components/data-import";',
    f'import {{ DataImport }} from "@/components/data-import";\n{import_stmt}'
)

# Add component
target = '<DataImport allowReplace={IS_LOCAL} />'
new_code = target + '\n\n      <UrlSyncForm />'
content = content.replace(target, new_code)

with open("apps/web/app/data/page.tsx", "w") as f:
    f.write(content)
print("Patched data page successfully")
