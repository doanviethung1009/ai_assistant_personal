import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace('import * as XLSX from "xlsx";\n', '')

# add to top after imports
c = c.replace('import { uuid, nowIso } from "@/lib/store/engine";', 'import { uuid, nowIso } from "@/lib/store/engine";\nimport * as XLSX from "xlsx";')

with open(file_path, "w") as f:
    f.write(c)

