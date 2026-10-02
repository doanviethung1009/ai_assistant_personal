import sys
file_path = "apps/web/app/history/page.tsx"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'import { formatFullPlainDate } from "@/lib/format";',
    'import { formatDateTime } from "@/lib/format";'
)

c = c.replace(
    'Đồng bộ lần cuối: {formatFullPlainDate(data.synced_at)}',
    'Đồng bộ lần cuối: {formatDateTime(data.synced_at)}'
)

with open(file_path, "w") as f:
    f.write(c)
